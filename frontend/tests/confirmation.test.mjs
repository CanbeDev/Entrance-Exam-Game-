import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ApiError, GameApi } from '../src/api/index.ts';
import { HttpClient } from '../src/api/http.ts';
import { GameController } from '../src/game/controller.ts';
import { createMockApi, fixtureUser, fixturePassword } from './mock-api.mjs';

const id = '000000000000000000000001';
const npc = `/games/${id}/npc-steps`;
const events = `/games/${id}/events`;
const credentials = { username: fixtureUser, password: fixturePassword };
const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', ...headers },
});
const failure = (status, headers) => json({ detail: { code: 'persistence_unavailable' } }, status, headers);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(check) {
  const deadline = Date.now() + 2500;
  while (!check()) { assert.ok(Date.now() < deadline, 'Isolated confirmation fixture did not settle'); await sleep(2); }
}

async function setup(t, { revision = 7, turn = 1, history = [] } = {}) {
  const mock = createMockApi({ seed: true });
  Object.assign(mock.games.get(id), { revision, current_turn: turn, turn_sequence: 1 });
  mock.histories.set(id, history);
  const delegate = mock.createFetch();
  const intercepts = [], gates = [], requests = [], errors = [];
  const api = new GameApi({ timeoutMs: 160, fetch: async (path, init) => {
    const url = new URL(path, 'http://offline.invalid');
    const route = url.pathname.replace(/^\/api/, '');
    requests.push({ method: init.method, path: route, query: url.search, credentials: init.credentials,
      csrfPresent: new Headers(init.headers).has('X-CSRF-Token'), signal: init.signal,
      ...(route === npc ? { body: JSON.parse(init.body) } : {}) });
    const index = intercepts.findIndex((item) => item.method === init.method && item.route === route);
    const intercept = index < 0 ? null : intercepts.splice(index, 1)[0];
    const serve = async () => {
      // Anonymous confirmation never receives even the synthetic session cookie.
      const response = init.credentials === 'omit' ? await mock.handle(path, init) : await delegate(path, init);
      if (init.method === 'POST' && route === npc && response.ok) {
        const entry = mock.histories.get(id).at(-1), decision = entry.npc_decision;
        // Canonical server identity from NpcController.prepare. The shared smoke
        // mock intentionally uses simpler IDs; only these fixtures normalize it.
        entry.action_id = `npc-${decision.strategy_version}-${decision.evaluation.turn_sequence}-${decision.evaluation.revision}`;
      }
      return response;
    };
    return intercept ? intercept.before ? intercept.handler(serve, init) : intercept.handler(await serve(), init) : serve();
  } });
  const originalNpc = api.npcStep.bind(api);
  api.npcStep = async (...args) => { try { return await originalNpc(...args); } catch (error) { errors.push(error); throw error; } };
  const controller = new GameController(api);
  const state = () => controller.getSnapshot();
  const afterNext = (method, route, handler) => intercepts.push({ method, route, handler });
  function hold(method, route, before = false) {
    let release;
    const released = new Promise((resolve) => { release = resolve; });
    const gate = { release, started: false };
    gates.push(gate);
    intercepts.push({ method, route, before, handler: async (value) => {
      gate.started = true; await released; return before ? value() : value;
    } });
    return gate;
  }
  const disconnect = () => afterNext('POST', npc, () => { throw new TypeError('NEVER_SURFACE_RAW_TRANSPORT_DETAILS'); });
  t.after(() => { controller.dispose(); gates.forEach((gate) => gate.release()); });
  await controller.initialize(id);
  await controller.authenticate(credentials, false);
  requests.length = 0;
  return { mock, api, controller, state, requests, errors, afterNext, hold, disconnect,
    posts: () => requests.filter((request) => request.method === 'POST' && request.path === npc) };
}

test('an NPC response within deadline follows the normal success path without targeted confirmation', async (t) => {
  const f = await setup(t);
  await f.controller.stepNpc();
  assert.equal(f.state().game.revision, 8);
  assert.equal(f.state().pending, null);
  assert.equal(f.state().npcAttempts, 1);
  assert.equal(f.posts().length, 1);
  assert.ok(f.state().lastResult.npc_decision.explanation);
  assert.ok(f.requests.every((request) => request.credentials === 'include'));
  assert.ok(f.requests.every((request) => !request.query.includes('limit=1&') && !request.query.endsWith('limit=1')));
});

test('a committed POST timeout is confirmed anonymously, without another POST or automatic fast-forward continuation', async (t) => {
  const f = await setup(t);
  f.controller.configureNpcBudget(1);
  f.afterNext('POST', npc, (_response, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(new DOMException('Offline deadline', 'AbortError')), { once: true });
  }));
  await f.controller.fastForward();
  assert.equal(f.errors[0].kind, 'timeout');
  assert.equal(f.errors[0].uncertain, true);
  assert.equal(f.errors[0].diagnostics.phase, 'response');
  assert.ok(f.errors[0].diagnostics.elapsedMs >= 100);
  assert.ok(f.posts()[0].signal.aborted);
  assert.equal(f.state().game.revision, 8);
  assert.equal(f.state().pending, null);
  assert.equal(f.state().fastForward, false);
  assert.equal(f.state().error, null);
  assert.match(f.state().notice, /move 8.*confirmed committed.*Original response: timeout/);
  const checks = f.requests.filter((request) => request.credentials === 'omit');
  assert.deepEqual(checks.map((request) => [request.method, request.path]), [['GET', events], ['GET', `/games/${id}`]]);
  assert.ok(checks.every((request) => !request.csrfPresent));
  assert.equal(checks[0].query, '?after_revision=7&limit=1');
  assert.equal(f.posts().length, 1);
  assert.equal(f.state().npcAttempts, 1);
  assert.equal(f.state().npcAttemptBudget, 1);
  await f.controller.stepNpc();
  assert.equal(f.posts().length, 1);
  assert.equal(f.mock.histories.get(id).length, 1);
});

test('a 200 body transport failure is network uncertainty with safe phase/status diagnostics', async (t) => {
  const f = await setup(t);
  f.afterNext('POST', npc, (response) => {
    response.json = async () => { throw new TypeError('NEVER_SURFACE_RAW_TRANSPORT_DETAILS'); };
    return response;
  });
  await f.controller.stepNpc();
  const error = f.errors[0];
  assert.equal(error.kind, 'network');
  assert.equal(error.status, undefined);
  assert.equal(error.diagnostics.responseStatus, 200);
  assert.equal(error.diagnostics.phase, 'body');
  assert.ok(Object.isFrozen(error.diagnostics));
  assert.ok(!JSON.stringify(error).includes('NEVER_SURFACE'));
  assert.match(f.state().notice, /Original response: network.*reading the response body.*200/);
  assert.equal(f.state().pending, null);
  assert.equal(f.state().game.revision, 8);
});

test('invalid JSON remains malformed and a matching receipt can independently confirm commitment', async (t) => {
  const f = await setup(t);
  f.afterNext('POST', npc, () => new Response('{broken', { headers: { 'Content-Type': 'application/json' } }));
  await f.controller.stepNpc();
  assert.equal(f.errors[0].kind, 'malformed');
  assert.equal(f.errors[0].diagnostics.phase, 'body');
  assert.equal(f.state().pending, null);
  assert.match(f.state().notice, /Original response: malformed/);
});

test('a server-side commit followed by 503 is reconciled without hiding the original response failure', async (t) => {
  const f = await setup(t);
  f.afterNext('POST', npc, () => failure(503));
  await f.controller.stepNpc();
  assert.equal(f.state().pending, null);
  assert.equal(f.state().game.revision, 8);
  assert.match(f.state().notice, /confirmed committed.*Original response: unavailable/);
  assert.equal(f.posts().length, 1);
});

test('a committed transfer with a lost response restores soldiers, ownership and the original explanation', async (t) => {
  const f = await setup(t);
  const board = f.mock.games.get(id);
  Object.assign(board, { phase: 'post_attack' });
  Object.assign(board.countries[1], { soldiers: 3 });
  Object.assign(board.countries[2], { soldiers: 2, owner_id: 'npc-1' });
  await f.controller.refresh();
  f.afterNext('POST', npc, () => {
    // Script an authoritative transfer response/history, not a second engine.
    Object.assign(board, { current_turn: 1, turn_sequence: 1, phase: 'post_attack' });
    board.countries[1].soldiers = 1; board.countries[2].soldiers = 4;
    const entry = f.mock.histories.get(id).at(-1);
    entry.npc_decision.action = { type: 'transfer', source_id: 'vatican-city', target_id: 'france', amount: 2 };
    entry.npc_decision.reason = 'transfer';
    entry.npc_decision.explanation = 'Synthetic authoritative explanation: consolidate two soldiers while keeping one at the source.';
    entry.events = [{ type: 'transferred', actor_id: 'npc-1', round: 1, turn_sequence: 1,
      source_id: 'vatican-city', target_id: 'france', amount: 2 }];
    throw new TypeError('Offline transfer response lost');
  });
  await f.controller.fastForward();
  assert.equal(f.state().pending, null);
  assert.equal(f.state().game.revision, 8);
  assert.equal(f.state().game.countries[1].soldiers, 1);
  assert.equal(f.state().game.countries[2].soldiers, 4);
  assert.equal(f.state().game.countries[2].owner_id, 'npc-1');
  assert.equal(f.state().events[0].events[0].amount, 2);
  assert.match(f.state().events[0].npc_decision.explanation, /consolidate two/);
  assert.equal(f.state().fastForward, false);
  assert.equal(f.posts().length, 1);
});

test('read-only recovery preserves actual dice order and casualties without calculating replacements', async (t) => {
  const f = await setup(t);
  f.afterNext('POST', npc, () => {
    const entry = f.mock.histories.get(id).at(-1);
    entry.npc_decision.action = { type: 'roll' }; entry.npc_decision.reason = 'continue';
    entry.events = [{ type: 'dice_exchange', actor_id: 'npc-1', round: 1, turn_sequence: 1,
      source_id: 'vatican-city', target_id: 'france', attacker_dice: [6, 2], defender_dice: [1, 5],
      attacker_losses: 1, defender_losses: 1 }];
    throw new TypeError('Offline dice response lost');
  });
  await f.controller.stepNpc();
  const event = f.state().events[0].events[0];
  assert.deepEqual(event.attacker_dice, [6, 2]);
  assert.deepEqual(event.defender_dice, [1, 5]);
  assert.equal(event.attacker_losses, 1);
  assert.equal(event.defender_losses, 1);
  assert.equal(f.state().pending, null);
  assert.equal(f.posts().length, 1);
});

const mismatches = [
  ['unrelated advanced revision', (entry) => { entry.revision = 9; }],
  ['human receipt', (entry) => { entry.actor.kind = 'human'; }],
  ['different actor', (entry) => { entry.actor.player_id = 'npc-2'; }],
  ['different evaluation actor', (entry) => { entry.npc_decision.evaluation.actor_id = 'npc-2'; }],
  ['different expected revision', (entry) => { entry.npc_decision.evaluation.revision = 6; }],
  ['different turn sequence', (entry) => { entry.npc_decision.evaluation.turn_sequence = 2; }],
  ['different action identity', (entry) => { entry.action_id = 'npc-unrelated'; }],
  ['missing decision evidence', (entry) => { entry.npc_decision = null; }],
];
for (const [name, tamper] of mismatches) {
  test(`read-only reconciliation cannot clear pending for ${name}`, async (t) => {
    const f = await setup(t);
    f.afterNext('POST', npc, () => {
      tamper(f.mock.histories.get(id).at(-1));
      f.mock.games.get(id).revision = 9;
      throw new TypeError('Offline interrupted reply');
    });
    await f.controller.stepNpc();
    const pending = f.state().pending;
    assert.equal(pending.kind, 'npc');
    assert.equal(pending.operation.gameId, id);
    assert.equal(pending.operation.command.expected_revision, 7);
    assert.equal(pending.account.id, 'account-1');
    assert.deepEqual(pending.observation, { actorId: 'npc-1', turnSequence: 1 });
    assert.ok(Object.isFrozen(pending.observation));
    assert.equal(f.state().game.revision, 7);
    assert.equal(f.state().npcAttempts, 1);
    assert.equal(f.posts().length, 1);
    assert.ok(!f.requests.some((request) => request.path === `/games/${id}`));
    const count = f.requests.length;
    await f.controller.poll(); await f.controller.stepNpc(); await f.controller.fastForward();
    assert.equal(f.requests.length, count);
    assert.equal(f.state().pending, pending);
  });
}

for (const field of ['after_revision', 'next_after_revision']) {
  test(`a malformed confirmation page ${field} cannot resolve the original request`, async (t) => {
    const f = await setup(t);
    f.disconnect();
    f.afterNext('GET', events, async (response) => {
      const page = await response.json(); page[field] = 99; return json(page);
    });
    await f.controller.stepNpc();
    assert.equal(f.state().pending.kind, 'npc');
    assert.equal(f.state().game.revision, 7);
    assert.equal(f.posts().length, 1);
  });
}

test('an empty receipt page never treats a newer board revision as proof of the original move', async (t) => {
  const f = await setup(t);
  f.disconnect();
  f.afterNext('GET', events, () => json({ events: [], after_revision: 7, next_after_revision: 7, has_more: false }));
  await f.controller.stepNpc();
  assert.equal(f.mock.games.get(id).revision, 8);
  assert.equal(f.state().game.revision, 7);
  assert.equal(f.state().pending.kind, 'npc');
  assert.equal(f.posts().length, 1);
});

for (const condition of ['503', 'timeout', 'old state', 'wrong game']) {
  test(`matching receipt plus ${condition} board read preserves pending until a complete confirmation`, async (t) => {
    const f = await setup(t);
    const old = structuredClone(f.mock.games.get(id));
    f.disconnect();
    f.afterNext('GET', `/games/${id}`, (response, init) => {
      if (condition === '503') return failure(503);
      if (condition === 'timeout') return new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => reject(new DOMException('Offline read timeout', 'AbortError')), { once: true });
      });
      if (condition === 'old state') return json(old);
      return json({ ...old, _id: '000000000000000000000002', revision: 8 });
    });
    await f.controller.stepNpc();
    const pending = f.state().pending;
    assert.equal(pending.kind, 'npc');
    assert.equal(f.state().game.revision, 7);
    assert.equal(f.state().error.startsWith('The connection was interrupted'), true);
    assert.equal(f.state().confirmingPending, false);
    await f.controller.checkPendingNpc();
    assert.equal(f.state().pending, null);
    assert.equal(f.state().game.revision, 8);
    assert.equal(f.posts().length, 1);
    assert.equal(f.state().npcAttempts, 1);
  });
}

test('receipt read failure and CSRF preparation failure retain the same operation and account', async (t) => {
  const f = await setup(t);
  f.disconnect(); f.afterNext('GET', events, () => failure(503));
  await f.controller.stepNpc();
  const saved = f.state().pending;
  assert.equal(saved.operation.command.expected_revision, 7);
  f.afterNext('GET', '/auth/csrf', () => failure(503));
  await f.controller.retryPending();
  assert.equal(f.state().pending, saved);
  await f.controller.poll();
  assert.equal(f.posts().length, 1);
  await f.controller.checkPendingNpc();
  assert.equal(f.state().pending, null);
  assert.equal(f.posts().length, 1);
});

test('confirmation 429 preserves Retry-After despite the original uncertain POST error', async (t) => {
  const f = await setup(t);
  f.disconnect(); f.afterNext('GET', events, () => failure(429, { 'Retry-After': '60' }));
  await f.controller.stepNpc();
  const saved = f.state().pending;
  assert.ok(f.state().retryAt > Date.now());
  const count = f.requests.length;
  await f.controller.checkPendingNpc(); await f.controller.retryPending(); await f.controller.poll();
  assert.equal(f.requests.length, count);
  assert.equal(f.state().pending, saved);
});

test('a backend worker may finish after client cancellation; explicit read-only confirmation recovers without replay', async (t) => {
  const f = await setup(t);
  const work = f.hold('POST', npc, true);
  await f.controller.fastForward(); // Deadline expires while the synthetic worker remains held.
  assert.equal(work.started, true);
  assert.equal(f.errors[0].kind, 'timeout');
  const saved = f.state().pending;
  assert.equal(f.mock.games.get(id).revision, 7);
  work.release();
  await until(() => f.mock.games.get(id).revision === 8);
  assert.equal(f.state().game.revision, 7); // Late HTTP completion cannot update the controller.
  assert.equal(f.state().pending, saved);
  await f.controller.checkPendingNpc();
  assert.equal(f.state().pending, null);
  assert.equal(f.state().game.revision, 8);
  assert.equal(f.state().fastForward, false);
  assert.equal(f.posts().length, 1);
  assert.equal(f.mock.calls.filter((call) => call.path === npc).length, 1);
});

test('confirmation holds the mutation lock and Pause cannot schedule another NPC action', async (t) => {
  const f = await setup(t);
  f.disconnect(); const gate = f.hold('GET', events);
  const running = f.controller.fastForward();
  await until(() => gate.started);
  const saved = f.state().pending;
  assert.equal(f.state().confirmingPending, true);
  assert.equal(f.state().busy, true);
  assert.equal(f.state().fastForward, false);
  const count = f.requests.length;
  await f.controller.stepNpc(); await f.controller.fastForward(); await f.controller.retryPending(); await f.controller.checkPendingNpc();
  f.controller.pause();
  assert.equal(f.requests.length, count);
  assert.equal(f.state().pending, saved);
  gate.release(); await running;
  await sleep(700);
  assert.equal(f.posts().length, 1);
  assert.equal(f.state().pending, null);
  assert.equal(f.state().fastForward, false);
});

test('read-only confirmation remains available when the NPC POST allowance is exhausted', async (t) => {
  const f = await setup(t);
  f.controller.configureNpcBudget(1);
  f.disconnect(); f.afterNext('GET', events, () => failure(503));
  await f.controller.stepNpc();
  assert.equal(f.state().pending.kind, 'npc');
  await f.controller.retryPending();
  assert.equal(f.posts().length, 1);
  await f.controller.checkPendingNpc();
  assert.equal(f.state().pending, null);
  assert.equal(f.state().npcAttemptBudget, 1);
  assert.equal(f.state().npcAttempts, 1);
  await f.controller.fastForward();
  assert.equal(f.posts().length, 1);
});

test('same-account reauthentication does not replay and preserves identity until read-only confirmation', async (t) => {
  const f = await setup(t);
  f.disconnect(); f.afterNext('GET', events, () => failure(503));
  await f.controller.stepNpc();
  const saved = f.state().pending;
  f.afterNext('GET', '/auth/csrf', () => failure(401));
  await f.controller.retryPending();
  assert.equal(f.state().session, null);
  assert.equal(f.state().pending, saved);
  await f.controller.authenticate(credentials, false);
  assert.equal(f.state().session.user.id, saved.account.id);
  assert.equal(f.state().pending, saved);
  assert.equal(f.posts().length, 1);
  await f.controller.checkPendingNpc();
  assert.equal(f.state().pending, null);
  assert.equal(f.posts().length, 1);
});

test('public confirmation also works with an expired session without an authenticated request', async (t) => {
  const f = await setup(t);
  f.disconnect(); f.afterNext('GET', events, () => failure(503));
  await f.controller.stepNpc();
  f.afterNext('GET', '/auth/csrf', () => failure(401));
  await f.controller.retryPending();
  const count = f.requests.length;
  await f.controller.checkPendingNpc();
  assert.equal(f.state().session, null);
  assert.equal(f.state().owner, false);
  assert.equal(f.state().pending, null);
  assert.ok(f.requests.slice(count).every((request) => request.method === 'GET' && request.credentials === 'omit' && !request.csrfPresent));
  assert.equal(f.posts().length, 1);
});

test('targeted receipt confirmation does not skip partially loaded history or duplicate committed events', async (t) => {
  const history = Array.from({ length: 105 }, (_, i) => ({ revision: i + 1, action_id: `history-${i}`,
    actor: { player_id: 'human', kind: 'human' }, committed_at: '2026-10-31T00:00:00Z',
    events: [], npc_decision: null }));
  const f = await setup(t, { revision: 105, history });
  assert.equal(f.state().eventCursor, 100);
  f.disconnect(); await f.controller.stepNpc();
  assert.equal(f.state().pending, null);
  assert.equal(f.state().game.revision, 106);
  assert.equal(f.state().eventCursor, 100);
  assert.equal(f.state().moreEvents, true);
  assert.equal(f.state().events.at(-1).revision, 106);
  await f.controller.moreHistory();
  assert.equal(f.state().eventCursor, 106);
  assert.equal(f.state().events.length, 106);
  assert.equal(f.state().moreEvents, false);
  assert.equal(new Set(f.state().events.map((entry) => entry.revision)).size, 106);
});

test('background read 503 is separate from confirmed NPC success and keeps controls/authoritative evidence', async (t) => {
  const f = await setup(t);
  f.afterNext('GET', `/games/${id}`, () => failure(503));
  await f.controller.poll();
  assert.ok(f.state().refreshError);
  assert.equal(f.state().pending, null);
  assert.equal(f.state().owner, true);
  assert.equal(f.state().busy, false);
  await f.controller.stepNpc();
  assert.equal(f.state().game.revision, 8);
  assert.equal(f.state().refreshError, null);
  assert.equal(f.posts().length, 1);
  assert.ok(f.state().events[0].npc_decision.explanation);
});

test('disposing during receipt confirmation prevents the next board read and all state application', async (t) => {
  const f = await setup(t);
  f.disconnect(); const gate = f.hold('GET', events);
  const running = f.controller.stepNpc();
  await until(() => gate.started);
  f.controller.dispose(); const disposed = f.state();
  gate.release(); await running;
  assert.equal(f.state(), disposed);
  assert.ok(!f.requests.some((request) => request.path === `/games/${id}`));
  assert.equal(f.posts().length, 1);
});

test('a stale background board response cannot overwrite a recovered NPC state or restart fast-forward', async (t) => {
  const f = await setup(t);
  const read = f.hold('GET', `/games/${id}`);
  const polling = f.controller.poll();
  await until(() => read.started);
  f.disconnect();
  await f.controller.fastForward();
  assert.equal(f.state().game.revision, 8);
  const recovered = f.state().game;
  read.release(); await polling;
  assert.equal(f.state().game, recovered);
  assert.equal(f.state().game.revision, 8);
  assert.equal(f.state().pending, null);
  assert.equal(f.state().fastForward, false);
  assert.equal(f.posts().length, 1);
});

test('a received old NPC receipt followed by a failed state refresh is reconciled instead of discarded', async (t) => {
  const f = await setup(t);
  f.afterNext('POST', npc, async (response) => {
    // Another authoritative update becomes visible while the original response
    // is delayed. Its receipt is still valid; its subsequent state read fails.
    f.mock.games.get(id).revision = 9;
    await f.api.getGame(id);
    f.afterNext('GET', `/games/${id}`, () => failure(503));
    f.afterNext('GET', events, () => failure(503));
    return response;
  });
  await f.controller.stepNpc();
  assert.equal(f.errors[0].code, 'committed_state_unavailable');
  assert.equal(f.state().pending.kind, 'npc');
  assert.match(f.state().error, /receipt was received.*board could not be refreshed/);
  await f.controller.checkPendingNpc();
  assert.equal(f.state().pending, null);
  assert.equal(f.state().game.revision, 9);
  assert.match(f.state().notice, /confirmed committed/);
  assert.equal(f.posts().length, 1);
  assert.equal(f.state().events[0].revision, 8);
});

test('confirmation respects route identity when a newer cached action state omits its optional ID', async (t) => {
  const f = await setup(t);
  f.disconnect(); f.afterNext('GET', events, () => failure(503));
  await f.controller.stepNpc();
  const read = f.hold('GET', `/games/${id}`);
  const checking = f.controller.checkPendingNpc();
  await until(() => read.started); // The held read captured revision 8.
  f.mock.games.get(id).revision = 9;
  f.afterNext('GET', `/games/${id}`, async (response) => {
    const value = await response.json(); delete value._id; return json(value);
  });
  await f.api.getGame(id);
  read.release(); await checking;
  assert.equal(f.state().pending, null);
  assert.equal(f.state().game.revision, 9);
  assert.equal(f.posts().length, 1);
});

test('a timed-out error body keeps observed 409 headers diagnostic-only', async () => {
  const http = new HttpClient({ timeoutMs: 30, fetch: async () => new Response(new ReadableStream({ start() {} }), {
    status: 409, headers: { 'Content-Type': 'application/json' },
  }) });
  await assert.rejects(http.request('/games/offline/actions', { method: 'POST', parse: (value) => value }), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.kind, 'timeout');
    assert.equal(error.status, undefined);
    assert.equal(error.uncertain, true);
    assert.equal(error.diagnostics.responseStatus, 409);
    assert.equal(error.diagnostics.phase, 'body');
    return true;
  });
});
