import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, GameApi } from '../src/api/index.ts';
import { GameController } from '../src/game/controller.ts';
import { createMockApi, fixtureUser, fixturePassword } from './mock-api.mjs';

const target = '000000000000000000000001';
const npcRoute = `/games/${target}/npc-steps`;
const credentials = { username: fixtureUser, password: fixturePassword };
const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', ...headers },
});
const failure = (status, code = 'persistence_unavailable', headers) => json({ detail: { code } }, status, headers);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check) {
  const deadline = Date.now() + 2500;
  while (!check()) {
    assert.ok(Date.now() < deadline, 'Offline recovery fixture did not settle');
    await sleep(2);
  }
}

async function setup(t, { turn = 1, game = true, timeoutMs = 250 } = {}) {
  const mock = createMockApi({ seed: true });
  Object.assign(mock.games.get(target), { current_turn: turn, revision: 4 });
  const delegate = mock.createFetch();
  const interceptors = [];
  const gates = [];
  const requests = []; // Only public paths and gameplay identities; no account secrets.
  const api = new GameApi({ timeoutMs, fetch: async (path, init) => {
    const url = new URL(path, 'http://offline.invalid');
    const route = url.pathname.replace(/^\/api/, '');
    requests.push({ method: init.method, path: route,
      ...(route.startsWith('/games') && init.body ? { body: JSON.parse(init.body),
        key: new Headers(init.headers).get('Idempotency-Key') } : {}) });
    const index = interceptors.findIndex((item) => item.method === init.method && item.route === route);
    const intercept = index < 0 ? null : interceptors.splice(index, 1)[0];
    const response = await delegate(path, init);
    return intercept ? intercept.after(response, init) : response;
  } });
  const controller = new GameController(api);
  t.after(() => { controller.dispose(); gates.forEach((gate) => gate.release()); });
  const state = () => controller.getSnapshot();
  const npcPosts = () => requests.filter((item) => item.method === 'POST' && item.path === npcRoute);
  const afterNext = (method, route, after) => interceptors.push({ method, route, after });
  function hold(method, route) {
    let release;
    const released = new Promise((resolve) => { release = resolve; });
    const gate = { started: false, release };
    gates.push(gate);
    afterNext(method, route, async (response) => { gate.started = true; await released; return response; });
    return gate;
  }
  async function uncertainNpc() {
    afterNext('POST', npcRoute, () => { throw new Error('Offline reply lost after commit'); });
    await controller.stepNpc();
    assert.equal(state().pending?.kind, 'npc');
    assert.equal(mock.games.get(target).revision, 5);
    return state().pending;
  }
  await controller.initialize(game ? target : null);
  await controller.authenticate(credentials, false);
  requests.length = 0;
  mock.calls.length = 0;
  return { mock, api, controller, state, requests, npcPosts, afterNext, hold, uncertainNpc };
}

for (const condition of [401, 503, 'network', 'timeout', 'malformed', 403, 429]) {
  test(`CSRF preparation ${condition} retains the exact pending NPC operation and mutation lock`, async (t) => {
    const f = await setup(t);
    f.controller.configureNpcBudget(2);
    const saved = await f.uncertainNpc();
    const snapshot = JSON.stringify(saved);
    f.afterNext('GET', '/auth/csrf', (_response, init) => {
      if (condition === 'network') throw new Error('Offline CSRF interruption');
      if (condition === 'timeout') return new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => reject(new DOMException('Offline abort', 'AbortError')), { once: true });
      });
      if (condition === 'malformed') return json({ unexpected: true });
      return failure(condition, condition === 401 ? 'authentication_required' : 'persistence_unavailable',
        condition === 429 ? { 'Retry-After': '60' } : {});
    });
    await f.controller.retryPending();
    assert.equal(f.state().pending, saved);
    assert.equal(JSON.stringify(saved), snapshot);
    assert.equal(saved.account.id, 'account-1');
    assert.ok(Object.isFrozen(saved) && Object.isFrozen(saved.account) && Object.isFrozen(saved.operation.command));
    assert.equal(f.state().npcAttempts, 1);
    assert.equal(f.npcPosts().length, 1);
    assert.equal(f.state().fastForward, false);
    assert.ok(f.state().error);
    if (condition === 401) assert.equal(f.state().session, null);
    const count = f.requests.length;
    await f.controller.stepNpc();
    await f.controller.act({ type: 'skip' });
    await f.controller.fastForward();
    await f.controller.create({ game_name: 'Must remain locked', starting_country_id: 'south-africa' });
    await f.controller.openGame('000000000000000000000002');
    await f.controller.refresh();
    await f.controller.dashboard();
    await f.controller.logout();
    await f.controller.authenticate(credentials, true);
    await f.controller.poll();
    assert.equal(f.requests.length, count);
    assert.equal(f.state().pending, saved);
  });
}

test('same-account reauthentication verifies ownership but never replays; explicit retry preserves identity and one commit', async (t) => {
  const f = await setup(t);
  const saved = await f.uncertainNpc();
  f.afterNext('GET', '/auth/csrf', () => failure(401, 'authentication_required'));
  await f.controller.retryPending();
  const count = f.requests.length;
  await f.controller.authenticate(credentials, false);
  assert.deepEqual(f.requests.slice(count).map((item) => item.path), ['/auth/login', '/auth/csrf', '/me/games']);
  assert.equal(f.state().session.user.id, saved.account.id);
  assert.equal(f.state().owner, true);
  assert.equal(f.state().pending, saved);
  assert.equal(f.npcPosts().length, 1);
  assert.equal(f.state().fastForward, false);
  await f.controller.retryPending();
  assert.equal(f.state().pending, null);
  assert.deepEqual(f.npcPosts().map((item) => item.body), [{ expected_revision: 4 }, { expected_revision: 4 }]);
  assert.equal(f.state().npcAttempts, 2);
  assert.equal(f.state().game.revision, 5);
  assert.equal(f.mock.histories.get(target).length, 1);
  assert.equal(f.state().events.length, 1);
  assert.equal(f.state().events[0].action_id, 'npc-4');
  assert.ok(f.state().events[0].npc_decision.explanation);
  assert.equal(f.state().lastResult.npc_decision.explanation, f.state().events[0].npc_decision.explanation);
});

test('a different authenticated account is rejected and cannot submit the saved operation', async (t) => {
  const f = await setup(t);
  const different = { username: 'different_fixture_account', password: fixturePassword };
  await f.api.register(different);
  const saved = await f.uncertainNpc();
  f.afterNext('GET', '/auth/csrf', () => failure(401, 'authentication_required'));
  await f.controller.retryPending();
  await f.controller.authenticate(different, false);
  assert.equal(f.state().pending, saved);
  assert.equal(f.state().session, null);
  assert.equal(f.api.currentSession, null);
  assert.equal(f.state().owner, false);
  assert.match(f.state().error, /original account/);
  await f.controller.retryPending();
  assert.equal(f.state().pending, saved);
  assert.equal(f.npcPosts().length, 1);
  await f.controller.authenticate(credentials, false);
  assert.equal(f.state().session.user.id, 'account-1');
  assert.equal(f.npcPosts().length, 1);
});

test('account IDs are checked even when a recovery login returns the same username', async (t) => {
  const f = await setup(t);
  const saved = await f.uncertainNpc();
  f.afterNext('POST', '/auth/login', async (response) => {
    const value = await response.json();
    value.user.id = 'a-different-account-with-the-same-name';
    return json(value);
  });
  await f.controller.authenticate(credentials, false);
  assert.equal(f.state().session, null);
  assert.equal(f.state().pending, saved);
  assert.match(f.state().error, /original account/);
  assert.equal(f.npcPosts().length, 1);
});

test('bad credentials and login CSRF failure retain the saved operation without automatic replay', async (t) => {
  const f = await setup(t);
  const saved = await f.uncertainNpc();
  await f.controller.authenticate({ ...credentials, password: 'Wrong offline fixture value' }, false);
  assert.equal(f.state().pending, saved);
  assert.equal(f.state().session, null);
  f.afterNext('GET', '/auth/csrf', () => failure(503));
  await f.controller.authenticate(credentials, false);
  assert.equal(f.state().pending, saved);
  assert.equal(f.state().session, null);
  assert.equal(f.npcPosts().length, 1);
  await f.controller.authenticate(credentials, false);
  assert.equal(f.state().owner, true);
  assert.equal(f.state().pending, saved);
  assert.equal(f.npcPosts().length, 1);
});

for (const denied of [false, true]) {
  test(`saved retry verifies ownership before POST when lookup ${denied ? 'denies access' : 'fails'}`, async (t) => {
    const f = await setup(t);
    const saved = await f.uncertainNpc();
    f.afterNext('GET', '/me/games', () => denied ? json({ games: [], next_cursor: null }) : failure(503));
    await f.controller.retryPending();
    assert.equal(f.state().pending, saved);
    assert.equal(f.npcPosts().length, 1);
    assert.equal(f.state().npcAttempts, 1);
    if (denied) assert.equal(f.state().owner, false);
    await f.controller.retryPending();
    assert.equal(f.state().pending, null);
    assert.equal(f.npcPosts().length, 2);
  });
}

test('reauthentication ownership failure preserves pending and does not submit a mutation', async (t) => {
  const f = await setup(t);
  const saved = await f.uncertainNpc();
  f.afterNext('GET', '/me/games', () => failure(503));
  await f.controller.authenticate(credentials, false);
  assert.equal(f.state().pending, saved);
  assert.equal(f.state().owner, false);
  assert.equal(f.npcPosts().length, 1);
});

test('a later rejected retry cannot discard an earlier uncertain operation', async (t) => {
  const f = await setup(t);
  const saved = await f.uncertainNpc();
  f.afterNext('POST', npcRoute, () => failure(409, 'revision_conflict'));
  await f.controller.retryPending();
  assert.equal(f.state().pending, saved);
  assert.equal(f.state().game.revision, 5);
  assert.equal(f.state().npcAttempts, 2);
  const count = f.requests.length;
  await f.controller.stepNpc();
  assert.equal(f.requests.length, count);
  await f.controller.retryPending();
  assert.equal(f.state().pending, null);
  assert.equal(f.mock.histories.get(target).length, 1);
});

test('a replayed old NPC receipt preserves historical evidence without rewinding newer state', async (t) => {
  const f = await setup(t);
  await f.uncertainNpc();
  f.mock.games.get(target).revision = 9;
  await f.api.getGame(target);
  await f.controller.retryPending();
  assert.equal(f.state().game.revision, 9);
  assert.equal(f.state().lastResult.state.revision, 5);
  assert.equal(f.state().eventCursor, 5);
  assert.deepEqual(f.state().events.map((entry) => entry.revision), [5]);
  assert.equal(f.mock.histories.get(target).length, 1);
  assert.deepEqual(f.npcPosts().map((item) => item.body), [{ expected_revision: 4 }, { expected_revision: 4 }]);
});

for (const kind of ['human', 'create']) {
  test(`${kind} recovery also retains the original account, payload and action ID or idempotency key`, async (t) => {
    const f = await setup(t, { turn: 0, game: kind !== 'create' });
    const route = kind === 'create' ? '/games' : `/games/${target}/actions`;
    const before = f.mock.games.size;
    f.afterNext('POST', route, () => { throw new Error('Offline committed reply lost'); });
    if (kind === 'create') await f.controller.create({ game_name: 'Saved creation fixture', starting_country_id: 'south-africa' });
    else await f.controller.act({ type: 'start_attack', source_id: 'south-africa', target_id: 'vatican-city' });
    const saved = f.state().pending;
    assert.equal(saved.kind, kind);
    f.afterNext('GET', '/auth/csrf', () => failure(401, 'authentication_required'));
    await f.controller.retryPending();
    assert.equal(f.state().pending, saved);
    await f.controller.authenticate(credentials, false);
    assert.equal(f.state().pending, saved);
    assert.equal(f.requests.filter((item) => item.path === route).length, 1);
    await f.controller.retryPending();
    const posts = f.requests.filter((item) => item.path === route);
    assert.equal(posts.length, 2);
    assert.deepEqual(posts[0], posts[1]);
    assert.equal(f.state().pending, null);
    assert.equal(f.state().npcAttempts, 0);
    assert.equal(f.mock.games.size, before + (kind === 'create' ? 1 : 0));
  });
}

test('zero budget dispatches no NPC requests; configuring a limit never resets the count', async (t) => {
  const f = await setup(t);
  assert.equal(f.state().npcAttemptBudget, null);
  f.controller.configureNpcBudget(0);
  await f.controller.stepNpc();
  await f.controller.fastForward();
  assert.equal(f.requests.length, 0);
  assert.equal(f.state().pending, null);
  assert.equal(f.state().fastForward, false);
  f.controller.configureNpcBudget(1);
  await f.controller.stepNpc();
  assert.equal(f.state().npcAttempts, 1);
  f.controller.configureNpcBudget(1);
  await f.controller.stepNpc();
  assert.equal(f.npcPosts().length, 1);
  assert.equal(f.state().npcAttempts, 1);
  f.controller.configureNpcBudget(2);
  assert.equal(f.npcPosts().length, 1); // Raising the local limit never submits a move.
  await f.controller.stepNpc();
  assert.equal(f.npcPosts().length, 2);
});

test('individual stepping and fast-forward share one budget and stop automatically at exhaustion', async (t) => {
  const f = await setup(t);
  f.controller.configureNpcBudget(2);
  await f.controller.stepNpc();
  await f.controller.fastForward();
  assert.equal(f.state().fastForward, false);
  assert.match(f.state().notice, /limit reached/);
  assert.equal(f.state().npcAttempts, 2);
  assert.equal(f.state().game.current_turn, 3);
  await sleep(700);
  await f.controller.stepNpc();
  assert.equal(f.npcPosts().length, 2);
  assert.equal(f.state().pending, null);
});

test('an exhausted budget blocks saved retries before preparation and keeps the uncertain operation locked', async (t) => {
  const f = await setup(t);
  f.controller.configureNpcBudget(1);
  const saved = await f.uncertainNpc();
  const count = f.requests.length;
  await f.controller.retryPending();
  assert.equal(f.requests.length, count);
  assert.equal(f.state().pending, saved);
  assert.equal(f.state().npcAttempts, 1);
  f.controller.configureNpcBudget(2);
  await f.controller.retryPending();
  assert.equal(f.state().pending, null);
  assert.equal(f.state().npcAttempts, 2);
  assert.equal(f.mock.histories.get(target).length, 1);
});

test('failed NPC POSTs consume attempts; malformed or negative budget settings cannot reset the limit', async (t) => {
  const f = await setup(t);
  f.controller.configureNpcBudget(2);
  for (const value of [-1, 1.5, NaN, Infinity]) f.controller.configureNpcBudget(value);
  assert.equal(f.state().npcAttemptBudget, 2);
  f.afterNext('POST', npcRoute, () => failure(503));
  await f.controller.stepNpc();
  assert.equal(f.state().npcAttempts, 1);
  assert.ok(f.state().pending);
  await f.controller.retryPending();
  assert.equal(f.state().npcAttempts, 2);
  assert.equal(f.mock.histories.get(target).length, 1);
});

test('the API NPC attempt guard runs after CSRF validation and rejects before HTTP submission', async (t) => {
  const f = await setup(t);
  await f.api.logout();
  let guards = 0;
  const operation = f.api.prepareNpcStep(target, 4);
  await assert.rejects(f.api.npcStep(operation, () => { guards++; }), { code: 'csrf_not_initialized' });
  assert.equal(guards, 0);
  await f.api.login(credentials);
  const count = f.requests.length;
  await assert.rejects(f.api.npcStep(operation, () => {
    guards++; throw new ApiError('client', { code: 'npc_budget_exhausted' });
  }), { code: 'npc_budget_exhausted' });
  assert.equal(guards, 1);
  assert.equal(f.requests.length, count);
});

test('Pause during an in-flight NPC action accepts its result and never schedules another action', async (t) => {
  const f = await setup(t);
  const gate = f.hold('POST', npcRoute);
  const running = f.controller.fastForward();
  await until(() => gate.started);
  assert.equal(f.state().busy, true);
  await f.controller.fastForward(); // Re-entry cannot create another loop.
  await f.controller.poll();
  f.controller.configureNpcBudget(0); // Configuration is locked during active execution.
  assert.equal(f.state().npcAttemptBudget, null);
  f.controller.pause();
  assert.equal(f.state().fastForward, false);
  assert.equal(f.state().pending.kind, 'npc');
  gate.release();
  await running;
  await sleep(700);
  assert.equal(f.npcPosts().length, 1);
  assert.equal(f.state().npcAttempts, 1);
  assert.equal(f.state().game.revision, 5);
  assert.equal(f.state().pending, null);
  assert.ok(f.state().events[0].npc_decision.explanation);
});

test('Pause before the first NPC submission cancels the fast-forward run', async (t) => {
  const f = await setup(t);
  const unsubscribe = f.controller.subscribe(() => {
    if (f.state().fastForward) { unsubscribe(); f.controller.pause(); }
  });
  await f.controller.fastForward();
  assert.equal(f.npcPosts().length, 0);
  assert.equal(f.state().npcAttempts, 0);
});

test('normal fast-forward is sequential, stops at the human turn and preserves all explanations/history', async (t) => {
  const f = await setup(t, { turn: 8 });
  let active = 0, peak = 0;
  const delay = async (response) => { active++; peak = Math.max(peak, active); await sleep(15); active--; return response; };
  f.afterNext('POST', npcRoute, delay);
  f.afterNext('POST', npcRoute, delay);
  await f.controller.fastForward();
  await until(() => !f.state().fastForward);
  assert.equal(peak, 1);
  assert.equal(f.npcPosts().length, 2);
  assert.equal(f.state().game.current_turn, 0);
  assert.equal(f.state().game.phase, 'allocating');
  assert.deepEqual(f.state().events.map((event) => event.revision), [5, 6]);
  assert.ok(f.state().events.every((event) => event.npc_decision.explanation));
  await f.controller.initialize(target);
  assert.deepEqual(f.state().events.map((event) => event.revision), [5, 6]);
  assert.equal(f.npcPosts().length, 2);
});

test('fast-forward stops when an authoritative NPC response completes the game', async (t) => {
  const f = await setup(t);
  f.afterNext('POST', npcRoute, async (response) => {
    const value = await response.json();
    Object.assign(value.state, { status: 'completed', phase: 'finished', winner: 'npc-1' });
    return json(value);
  });
  await f.controller.fastForward();
  assert.equal(f.state().fastForward, false);
  assert.equal(f.state().game.status, 'completed');
  await f.controller.fastForward();
  assert.equal(f.npcPosts().length, 1);
});

test('fast-forward stops after an uncertain response and explicit recovery never resumes it', async (t) => {
  const f = await setup(t);
  f.afterNext('POST', npcRoute, () => { throw new Error('Offline NPC reply lost'); });
  await f.controller.fastForward();
  assert.equal(f.state().fastForward, false);
  assert.equal(f.state().pending.kind, 'npc');
  await sleep(700);
  assert.equal(f.npcPosts().length, 1);
  await f.controller.retryPending();
  assert.equal(f.state().pending, null);
  assert.equal(f.state().fastForward, false);
  assert.equal(f.mock.histories.get(target).length, 1);
});

test('disposing during retry preparation prevents a later NPC POST', async (t) => {
  const f = await setup(t);
  const saved = await f.uncertainNpc();
  const gate = f.hold('GET', '/auth/csrf');
  const retry = f.controller.retryPending();
  await until(() => gate.started);
  f.controller.dispose();
  gate.release();
  await retry;
  assert.equal(f.npcPosts().length, 1);
  assert.equal(f.state().pending, saved);
});
