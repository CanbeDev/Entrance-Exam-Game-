import { test } from 'node:test';
import assert from 'node:assert/strict';
import { GameApi } from '../src/api/index.ts';
import { GameController } from '../src/game/controller.ts';
import { createMockApi, fixturePassword, fixtureUser, fixtureGame } from './mock-api.mjs';

const credentials = { username: 'new_fixture_user', password: fixturePassword };
function setup(options) {
  const mock = createMockApi(options);
  const fetch = mock.createFetch();
  const controller = new GameController(new GameApi({ fetch }));
  return { mock, controller, fetch, state: () => controller.getSnapshot() };
}
const requestError = (status, code, retry) => new Response(JSON.stringify({ detail: { code } }), {
  status, headers: { 'Content-Type': 'application/json', ...(retry ? { 'Retry-After': retry } : {}) },
});
async function until(check, max = 8000) {
  const deadline = Date.now() + max;
  while (!check()) {
    if (Date.now() > deadline) throw new Error('Offline fixture did not reach the expected state');
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

test('functional journey: register, create, battle, transfer, NPC fast-forward, allocation, resume and logout', async () => {
  const { mock, controller, state, fetch } = setup();
  try {
    await controller.initialize(null);
    assert.equal(state().session, null);
    await controller.authenticate(credentials, true);
    assert.equal(state().session.user.username, credentials.username);
    assert.equal(state().games.games.length, 0);
    await controller.create({ game_name: 'UI journey', starting_country_id: 'south-africa' });
    assert.equal(state().game.countries.length, 10);
    assert.equal(state().owner, true);
    const id = state().gameId;
    await controller.act({ type: 'start_attack', source_id: 'south-africa', target_id: 'vatican-city' });
    assert.equal(state().game.phase, 'attacking');
    await controller.act({ type: 'roll' });
    assert.equal(state().game.phase, 'post_attack');
    assert.deepEqual(state().lastResult.events[0].attacker_dice, [6]);
    assert.equal(state().game.countries[1].owner_id, 'human');
    await controller.act({ type: 'transfer', source_id: 'south-africa', target_id: 'vatican-city', amount: 1 });
    assert.equal(state().game.countries[0].soldiers, 4);
    await controller.act({ type: 'end_turn' });
    await controller.stepNpc();
    assert.ok(state().events.some((event) => event.npc_decision?.explanation));
    await controller.fastForward();
    await until(() => !state().fastForward);
    assert.equal(state().game.phase, 'allocating');
    assert.equal(state().game.pending_reinforcements, 4);
    await controller.act({ type: 'allocate', allocations: [{ country_id: 'south-africa', amount: 4 }] });
    assert.equal(state().game.phase, 'deciding');
    const reload = new GameController(new GameApi({ fetch }));
    await reload.initialize(id);
    assert.equal(reload.getSnapshot().session.user.username, credentials.username);
    assert.equal(reload.getSnapshot().owner, true);
    assert.equal(reload.getSnapshot().game.revision, state().game.revision);
    assert.equal(reload.getSnapshot().events.length, state().events.length);
    await reload.logout();
    assert.equal(reload.getSnapshot().session, null);
    assert.equal(reload.getSnapshot().owner, false);
    reload.dispose();
    assert.ok(mock.calls.some((call) => call.path === '/auth/logout'));
  } finally { controller.dispose(); }
});

test('saved-game search/filter/page and ownership verification are independent', async () => {
  const { mock, controller, state } = setup({ seed: true });
  try {
    await controller.authenticate({ username: fixtureUser, password: fixturePassword }, false);
    assert.equal(state().games.games.length, 10);
    assert.ok(state().games.next_cursor);
    await controller.page(true);
    assert.equal(state().games.games.length, 2);
    await controller.page(false);
    assert.equal(state().cursors.length, 1);
    await controller.dashboard({ query: 'Saved game 12', status: 'active' });
    assert.equal(state().games.games.length, 1);
    assert.equal(state().games.games[0].game_name, 'Saved game 12');
    for (let i = 0; i < 100; i++) mock.addGame('account-1', `Extra ${i}`);
    const target = '000000000000000000000001';
    await controller.openGame(target);
    assert.equal(state().owner, true);
    assert.ok(mock.calls.some((call) => call.path.includes('/me/games?cursor=') && call.path.includes('limit=100')));
  } finally { controller.dispose(); }
});

test('anonymous spectators see public state and events; stepping and human methods never POST', async () => {
  const { mock, controller, state } = setup({ seed: true });
  try {
    await controller.initialize('000000000000000000000001');
    assert.equal(state().game.countries.length, 10);
    assert.equal(state().owner, false);
    await controller.act({ type: 'skip' });
    await controller.stepNpc();
    await controller.fastForward();
    assert.equal(mock.calls.filter((call) => call.method === 'POST').length, 0);
  } finally { controller.dispose(); }
});

test('a different logged-in account does not acquire controls from the game-local human ID', async () => {
  const { mock, controller, state } = setup({ seed: true });
  try {
    await controller.authenticate(credentials, true);
    await controller.openGame('000000000000000000000001');
    assert.equal(state().game.players[0].id, 'human');
    assert.equal(state().owner, false);
    const count = mock.calls.length;
    await controller.act({ type: 'skip' });
    assert.equal(mock.calls.length, count);
  } finally { controller.dispose(); }
});

test('uncertain submissions lock new mutations and explicit retry reuses the saved operation', async () => {
  const { mock, controller, state } = setup();
  try {
    await controller.authenticate(credentials, true);
    await controller.create({ game_name: 'Retry fixture', starting_country_id: 'south-africa' });
    const route = `/games/${state().gameId}/actions`;
    mock.failNext('POST', route, () => { throw new Error('offline fixture disconnect'); });
    await controller.act({ type: 'skip' });
    const pending = state().pending;
    assert.equal(pending.kind, 'human');
    const count = mock.calls.length;
    await controller.act({ type: 'skip' });
    assert.equal(mock.calls.length, count);
    await controller.retryPending();
    assert.equal(state().pending, null);
    const submissions = mock.calls.filter((call) => call.path === route);
    assert.equal(submissions[0].action_id, submissions[1].action_id);
    assert.equal(submissions[0].expected_revision, submissions[1].expected_revision);
  } finally { controller.dispose(); }
});

test('409 adopts the refetched board and requires a fresh user choice without replay', async () => {
  const { mock, controller, state } = setup();
  try {
    await controller.authenticate(credentials, true);
    await controller.create({ game_name: 'Conflict fixture', starting_country_id: 'south-africa' });
    mock.games.get(state().gameId).revision = 5;
    await controller.act({ type: 'skip' });
    assert.equal(state().game.revision, 5);
    assert.equal(state().pending, null);
    assert.match(state().error, /review/i);
    assert.equal(mock.calls.filter((call) => call.path.endsWith('/actions')).length, 1);
  } finally { controller.dispose(); }
});

test('403 removes owner controls; 401 clears the session; disabled writes leave no retry loop', async () => {
  const { mock, controller, state } = setup();
  try {
    await controller.authenticate(credentials, true);
    await controller.create({ game_name: 'Access fixture', starting_country_id: 'south-africa' });
    const route = `/games/${state().gameId}/actions`;
    mock.failNext('POST', route, () => requestError(403, 'game_not_owned'));
    await controller.act({ type: 'skip' });
    assert.equal(state().owner, false);
    await controller.refresh();
    mock.failNext('POST', route, () => requestError(503, 'gameplay_writes_disabled'));
    await controller.act({ type: 'skip' });
    assert.equal(state().pending, null);
    assert.match(state().error, /Gameplay is currently unavailable/);
    mock.failNext('POST', route, () => requestError(401, 'authentication_required'));
    await controller.act({ type: 'skip' });
    assert.equal(state().owner, false);
    assert.equal(state().session, null);
  } finally { controller.dispose(); }
});

test('429 preserves the operation and Retry-After pauses new requests', async () => {
  const { mock, controller, state } = setup();
  try {
    await controller.authenticate(credentials, true);
    await controller.create({ game_name: 'Limit fixture', starting_country_id: 'south-africa' });
    mock.failNext('POST', `/games/${state().gameId}/actions`, () => requestError(429, 'rate_limited', '60'));
    await controller.act({ type: 'skip' });
    assert.ok(state().retryAt > Date.now());
    assert.ok(state().pending);
    const count = mock.calls.length;
    await controller.retryPending();
    assert.equal(mock.calls.length, count);
  } finally { controller.dispose(); }
});

test('pause stops future NPC actions and event history is deduplicated by committed revision', async () => {
  const { mock, controller, state } = setup();
  try {
    await controller.authenticate(credentials, true);
    await controller.create({ game_name: 'Pause fixture', starting_country_id: 'south-africa' });
    await controller.act({ type: 'skip' });
    await controller.fastForward();
    controller.pause();
    const count = mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 750));
    assert.equal(mock.calls.length, count);
    await controller.refresh();
    assert.equal(new Set(state().events.map((event) => event.revision)).size, state().events.length);
  } finally { controller.dispose(); }
});

test('completed and unsupported historical games never submit actions', async () => {
  const { mock, controller, state } = setup({ seed: true });
  try {
    await controller.authenticate({ username: fixtureUser, password: fixturePassword }, false);
    const target = '000000000000000000000001';
    const completed = fixtureGame(target);
    completed.status = 'completed'; completed.phase = 'finished'; completed.winner = 'human';
    mock.games.set(target, completed);
    await controller.openGame(target);
    assert.equal(state().owner, true);
    const count = mock.calls.length;
    await controller.act({ type: 'skip' });
    await controller.stepNpc();
    assert.equal(mock.calls.length, count);
    mock.games.set(target, { _id: target, game_name: 'Historical', status: 'waiting', countries: [], players: [] });
    await controller.refresh();
    await controller.act({ type: 'skip' });
    assert.equal(state().game.status, 'completed'); // A legacy response cannot rewind a versioned cached game.
  } finally { controller.dispose(); }
});

test('routine polling does not transiently remove verified owner forms and reset user selections', async () => {
  const { controller, state } = setup();
  try {
    await controller.authenticate(credentials, true);
    await controller.create({ game_name: 'Stable controls fixture', starting_country_id: 'south-africa' });
    const observed = [];
    const unsubscribe = controller.subscribe(() => observed.push(state().owner));
    await controller.refresh();
    unsubscribe();
    assert.ok(observed.length > 0);
    assert.ok(observed.every(Boolean));
  } finally { controller.dispose(); }
});

test('duplicate registration explains the account conflict without a misleading game-revision error', async () => {
  const { controller, state } = setup();
  try {
    await controller.authenticate({ username: fixtureUser, password: fixturePassword }, true);
    assert.match(state().error, /username is unavailable/);
    assert.equal(state().session, null);
  } finally { controller.dispose(); }
});
