import { test } from 'node:test';
import assert from 'node:assert/strict';
import { GameApi } from '../src/api/index.ts';
import { GameController } from '../src/game/controller.ts';
import { createMockApi, fixtureUser, fixturePassword } from './mock-api.mjs';

const target = '000000000000000000000001';
const other = '000000000000000000000002';
const credentials = { username: fixtureUser, password: fixturePassword };
const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', ...headers },
});
const failure = (status, code, headers) => json({ detail: { code } }, status, headers);
async function until(check) {
  const deadline = Date.now() + 2000;
  while (!check()) {
    assert.ok(Date.now() < deadline, 'Offline fixture did not reach the expected state');
    await new Promise((resolve) => setTimeout(resolve, 2));
  }
}

// All requests terminate in the in-memory fixture. Holds return snapshots taken
// before release, allowing deterministic stale responses without network access.
async function setup(t, { login = true, id = target } = {}) {
  const mock = createMockApi({ seed: true });
  const delegate = mock.createFetch();
  const holds = [];
  const api = new GameApi({ fetch: async (path, init) => {
    const route = new URL(path, 'http://offline.invalid').pathname.replace(/^\/api/, '');
    const gate = holds.find((item) => !item.started && item.method === init.method && item.path === route);
    const response = await delegate(path, init);
    if (!gate) return response;
    gate.started = true;
    await gate.released;
    if (gate.error) throw gate.error;
    return gate.response ?? response;
  } });
  const controller = new GameController(api);
  t.after(() => { controller.dispose(); holds.forEach((gate) => gate.release()); });
  await controller.initialize(id);
  if (login) await controller.authenticate(credentials, false);
  mock.calls.length = 0;
  function hold(method, path, options = {}) {
    let release;
    const released = new Promise((resolve) => { release = resolve; });
    const gate = { method, path, ...options, started: false, released, release };
    holds.push(gate);
    return gate;
  }
  return { mock, api, controller, hold, state: () => controller.getSnapshot() };
}

test('routine polls use only public game/events reads, retain ownership and never set foreground busy', async (t) => {
  const { mock, controller, state } = await setup(t);
  const observed = [];
  const unsubscribe = controller.subscribe(() => observed.push(state()));
  await controller.poll();
  await controller.poll();
  unsubscribe();
  assert.deepEqual(mock.calls.map((call) => [call.method, call.path]), [
    ['GET', `/games/${target}`], ['GET', `/games/${target}/events?after_revision=0&limit=100`],
    ['GET', `/games/${target}`], ['GET', `/games/${target}/events?after_revision=0&limit=100`],
  ]);
  assert.ok(observed.some((snapshot) => snapshot.refreshing));
  assert.ok(observed.every((snapshot) => snapshot.owner && !snapshot.busy));
  assert.equal(state().refreshing, false);
});

test('a slow poll never overlaps another poll or blocks a move; its stale board cannot rewind the move', async (t) => {
  const { mock, api, controller, hold, state } = await setup(t);
  const read = hold('GET', `/games/${target}`);
  const polling = controller.poll();
  await until(() => read.started);
  assert.equal(state().busy, false);
  assert.equal(state().refreshing, true);
  await controller.poll();
  assert.equal(mock.calls.length, 1);
  const write = hold('POST', `/games/${target}/actions`);
  const moving = controller.act({ type: 'start_attack', source_id: 'south-africa', target_id: 'vatican-city' });
  await until(() => write.started);
  assert.equal(state().busy, true);
  await controller.act({ type: 'skip' });
  await controller.stepNpc();
  await controller.poll();
  assert.equal(mock.calls.filter((call) => call.method === 'POST').length, 1);
  write.release();
  await moving;
  const committed = state();
  assert.equal(committed.game.revision, 1);
  assert.equal(committed.game.phase, 'attacking');
  assert.equal(committed.eventCursor, 1);
  read.release();
  await polling;
  assert.equal(state().game, committed.game);
  assert.equal(state().lastResult, committed.lastResult);
  assert.equal(state().eventCursor, 1);
  assert.equal(api.cachedGame(target).revision, 1);
  assert.equal(state().busy, false);
  assert.equal(state().refreshing, false);
  assert.equal(mock.calls.filter((call) => call.path.includes('/events')).length, 1);
});

test('late polling event pages cannot replace committed history or rewind its cursor', async (t) => {
  const { mock, controller, hold, state } = await setup(t);
  const read = hold('GET', `/games/${target}/events`);
  const polling = controller.poll();
  await until(() => read.started);
  await controller.act({ type: 'start_attack', source_id: 'south-africa', target_id: 'vatican-city' });
  await controller.act({ type: 'roll' });
  assert.equal(state().game.revision, 2);
  read.release();
  await polling;
  assert.equal(state().eventCursor, 2);
  assert.deepEqual(state().events.map((event) => event.revision), [1, 2]);
  await controller.poll();
  assert.equal(state().eventCursor, 2);
  assert.deepEqual(state().events.map((event) => event.revision), [1, 2]);
  assert.ok(mock.calls.at(-1).path.includes('after_revision=2'));
});

test('a stale poll finishing during a move cannot unlock foreground busy or remove its pending operation', async (t) => {
  const { controller, hold, state } = await setup(t);
  const read = hold('GET', `/games/${target}`);
  const polling = controller.poll();
  await until(() => read.started);
  const write = hold('POST', `/games/${target}/actions`);
  const moving = controller.act({ type: 'skip' });
  await until(() => write.started);
  const saved = state().pending;
  read.release();
  await polling;
  assert.equal(state().refreshing, false);
  assert.equal(state().busy, true);
  assert.equal(state().pending, saved);
  assert.equal(state().game.revision, 0);
  write.release();
  await moving;
  assert.equal(state().game.revision, 1);
  assert.equal(state().busy, false);
  assert.equal(state().pending, null);
});

test('explicit refresh drains an existing poll then rechecks ownership once without overlapping refreshes', async (t) => {
  const { mock, controller, hold, state } = await setup(t);
  const read = hold('GET', `/games/${target}`);
  const polling = controller.poll();
  await until(() => read.started);
  const refreshing = controller.refresh();
  assert.equal(state().busy, true);
  assert.equal(state().owner, true);
  await controller.refresh();
  await controller.poll();
  assert.equal(mock.calls.length, 1);
  read.release();
  await Promise.all([polling, refreshing]);
  assert.deepEqual(mock.calls.map((call) => call.path), [
    `/games/${target}`, `/games/${target}`, `/games/${target}/events?after_revision=0&limit=100`, '/me/games?limit=100',
  ]);
  assert.equal(state().busy, false);
  assert.equal(state().owner, true);
});

test('game-page login checks ownership without loading a hidden dashboard or country catalog', async (t) => {
  const { mock, controller, state } = await setup(t, { login: false });
  assert.equal(state().owner, false);
  await controller.authenticate(credentials, false);
  assert.deepEqual(mock.calls.map((call) => call.path), ['/auth/login', '/auth/csrf', '/me/games?limit=100']);
  assert.equal(state().owner, true);
  assert.equal(state().games, null);
  assert.equal(state().catalog, null);
});

test('dashboard login still loads its list and catalog', async (t) => {
  const { mock, controller, state } = await setup(t, { login: false, id: null });
  await controller.authenticate(credentials, false);
  assert.deepEqual(mock.calls.map((call) => call.path), ['/auth/login', '/auth/csrf', '/me/games?limit=10', '/countries']);
  assert.equal(state().games.games.length, 10);
  assert.equal(state().catalog.countries.length, 10);
});

test('game entry requires ownership before enabling mutations even when ownership verification is slow', async (t) => {
  const { mock, controller, hold, state } = await setup(t);
  const read = hold('GET', '/me/games');
  const opening = controller.openGame(other);
  await until(() => read.started);
  assert.equal(state().gameId, other);
  assert.equal(state().owner, false);
  assert.equal(state().busy, true);
  await controller.act({ type: 'skip' });
  await controller.poll();
  assert.equal(mock.calls.filter((call) => call.method === 'POST').length, 0);
  read.release();
  await opening;
  assert.equal(state().owner, true);
  assert.equal(state().busy, false);
});

test('navigation invalidates a delayed poll before reading and checking the next game', async (t) => {
  const { mock, controller, hold, state } = await setup(t);
  const read = hold('GET', `/games/${target}/events`);
  const polling = controller.poll();
  await until(() => read.started);
  const opening = controller.openGame(other);
  assert.equal(state().busy, true);
  read.release();
  await Promise.all([polling, opening]);
  assert.equal(state().gameId, other);
  assert.equal(state().game._id, other);
  assert.equal(state().owner, true);
  assert.equal(state().eventCursor, 0);
  assert.equal(mock.calls.filter((call) => call.path === '/me/games?limit=100').length, 1);
});

test('explicit refresh revokes cached ownership if the authenticated list no longer contains the game', async (t) => {
  const { mock, controller, state } = await setup(t);
  await controller.poll();
  assert.equal(state().owner, true);
  mock.failNext('GET', '/me/games', () => json({ games: [], next_cursor: null }));
  await controller.refresh();
  assert.equal(state().owner, false);
  const count = mock.calls.length;
  await controller.act({ type: 'skip' });
  assert.equal(mock.calls.length, count);
});

test('logout and another account invalidate ownership; public polls never regain controls', async (t) => {
  const { mock, controller, state } = await setup(t);
  await controller.logout();
  assert.equal(state().owner, false);
  assert.equal(state().session, null);
  mock.calls.length = 0;
  await controller.poll();
  assert.ok(mock.calls.every((call) => call.method === 'GET' && call.path.startsWith('/games/')));
  await controller.authenticate({ username: 'different_fixture_user', password: fixturePassword }, true);
  assert.equal(state().session.user.username, 'different_fixture_user');
  assert.equal(state().owner, false);
  const count = mock.calls.length;
  await controller.act({ type: 'skip' });
  await controller.stepNpc();
  assert.equal(mock.calls.length, count);
});

test('session restoration rechecks ownership in the new session without dashboard or catalog requests', async (t) => {
  const { mock, controller, state } = await setup(t);
  const previous = state().session;
  await controller.initialize(target);
  assert.notEqual(state().session, previous);
  assert.equal(state().owner, true);
  assert.deepEqual(mock.calls.map((call) => call.path), [
    '/auth/me', '/auth/csrf', `/games/${target}`, `/games/${target}/events?after_revision=0&limit=100`, '/me/games?limit=100',
  ]);
});

test('background 401 clears ownership and session; a fresh login verifies ownership again', async (t) => {
  const { mock, controller, state } = await setup(t);
  mock.failNext('GET', `/games/${target}`, () => failure(401, 'authentication_required'));
  await controller.poll();
  assert.equal(state().session, null);
  assert.equal(state().owner, false);
  assert.match(state().refreshError, /session has ended/);
  assert.equal(state().error, null);
  await controller.act({ type: 'skip' });
  assert.equal(mock.calls.filter((call) => call.method === 'POST').length, 0);
  await controller.authenticate(credentials, false);
  assert.equal(state().owner, true);
  assert.equal(state().refreshError, null);
});

test('background 403 removes controls until explicit ownership verification', async (t) => {
  const { mock, controller, state } = await setup(t);
  mock.failNext('GET', `/games/${target}/events`, () => failure(403, 'game_not_owned'));
  await controller.poll();
  assert.ok(state().session);
  assert.equal(state().owner, false);
  assert.equal(state().busy, false);
  assert.match(state().refreshError, /permission/);
  await controller.refresh();
  assert.equal(state().owner, true);
  assert.equal(state().refreshError, null);
});

test('login drains an old unauthorized poll so its late 401 cannot clear the new session', async (t) => {
  const { mock, controller, hold, state } = await setup(t);
  const read = hold('GET', `/games/${target}`, { response: failure(401, 'authentication_required') });
  const polling = controller.poll();
  await until(() => read.started);
  const login = controller.authenticate(credentials, false);
  assert.equal(mock.calls.filter((call) => call.path === '/auth/login').length, 0);
  read.release();
  await Promise.all([polling, login]);
  assert.ok(state().session);
  assert.equal(state().owner, true);
  assert.equal(state().error, null);
  assert.equal(state().refreshError, null);
  await controller.poll();
  assert.equal(mock.calls.at(-1).path, `/games/${target}/events?after_revision=0&limit=100`);
});

test('background failures keep the board and controls, stop polling, and recover on explicit refresh', async (t) => {
  const { mock, controller, state } = await setup(t);
  const board = state().game;
  mock.failNext('GET', `/games/${target}`, () => failure(503, 'temporarily_unavailable'));
  await controller.poll();
  assert.equal(state().game, board);
  assert.equal(state().owner, true);
  assert.equal(state().busy, false);
  assert.equal(state().error, null);
  assert.match(state().refreshError, /temporarily unavailable/);
  const count = mock.calls.length;
  await controller.poll();
  assert.equal(mock.calls.length, count);
  await controller.refresh();
  assert.equal(state().refreshError, null);
  await controller.poll();
  assert.equal(mock.calls.at(-1).path, `/games/${target}/events?after_revision=0&limit=100`);
});

test('a delayed read failure never discards an uncertain committed move or changes its saved retry identity', async (t) => {
  const { mock, controller, hold, state } = await setup(t);
  const read = hold('GET', `/games/${target}/events`, { response: failure(503, 'temporarily_unavailable') });
  const polling = controller.poll();
  await until(() => read.started);
  // Commit in the mock, then lose the response. A retry must replay its receipt.
  const write = hold('POST', `/games/${target}/actions`, { error: new Error('offline fixture disconnect') });
  const moving = controller.act({ type: 'skip' });
  await until(() => write.started);
  write.release();
  await moving;
  const saved = state().pending;
  const message = state().error;
  assert.equal(saved.kind, 'human');
  assert.equal(mock.games.get(target).revision, 1);
  read.release();
  await polling;
  assert.equal(state().pending, saved);
  assert.equal(state().error, message);
  assert.equal(state().refreshError, null);
  const count = mock.calls.length;
  await controller.poll();
  await controller.act({ type: 'skip' });
  assert.equal(mock.calls.length, count);
  await controller.retryPending();
  assert.equal(state().pending, null);
  assert.equal(state().game.revision, 1);
  assert.equal(state().events.length, 1);
  assert.equal(mock.histories.get(target).length, 1);
  const submissions = mock.calls.filter((call) => call.path.endsWith('/actions'));
  assert.equal(submissions.length, 2);
  assert.equal(submissions[0].action_id, submissions[1].action_id);
  assert.equal(submissions[0].expected_revision, submissions[1].expected_revision);
  assert.equal(mock.calls.filter((call) => call.path === '/auth/csrf').length, 1);
});

test('a move can recover from a background read error without an ownership rescan', async (t) => {
  const { mock, controller, state } = await setup(t);
  mock.failNext('GET', `/games/${target}`, () => { throw new Error('offline read disconnect'); });
  await controller.poll();
  assert.ok(state().refreshError);
  await controller.act({ type: 'skip' });
  assert.equal(state().game.revision, 1);
  assert.equal(state().refreshError, null);
  assert.equal(mock.calls.filter((call) => call.path.startsWith('/me/games')).length, 0);
});

test('background rate limiting respects Retry-After without repeated requests or automatic mutation retries', async (t) => {
  const { mock, controller, state } = await setup(t);
  mock.failNext('GET', `/games/${target}`, () => failure(429, 'rate_limited', { 'Retry-After': '60' }));
  await controller.poll();
  assert.ok(state().retryAt > Date.now());
  assert.equal(state().busy, false);
  assert.equal(state().pending, null);
  const count = mock.calls.length;
  await controller.poll();
  await controller.refresh();
  await controller.act({ type: 'skip' });
  assert.equal(mock.calls.length, count);
});

test('polling stays paused between fast-forward steps and resumes after Pause', async (t) => {
  const { mock, controller, state } = await setup(t);
  await controller.act({ type: 'skip' });
  await controller.fastForward();
  assert.equal(state().fastForward, true);
  assert.equal(state().busy, false);
  const count = mock.calls.length;
  await controller.poll();
  assert.equal(mock.calls.length, count);
  controller.pause();
  await controller.poll();
  assert.equal(state().fastForward, false);
  assert.equal(mock.calls.length, count + 2);
});

test('disposing during a slow poll prevents state updates and subsequent event requests', async (t) => {
  const { mock, controller, hold, state } = await setup(t);
  const read = hold('GET', `/games/${target}`);
  const polling = controller.poll();
  await until(() => read.started);
  controller.dispose();
  const disposed = state();
  read.release();
  await polling;
  await controller.poll();
  assert.equal(state(), disposed);
  assert.equal(mock.calls.length, 1);
});
