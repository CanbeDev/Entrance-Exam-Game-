import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { GameApi, ApiError } from '../src/api/index.ts';
import { HttpClient, retryAfterMs } from '../src/api/http.ts';
import { component } from '../src/api/validation.ts';
import { id, user, csrf, credentials, json, failure, login, token, game, result, queue, body } from './helpers.mjs';

test('register → login → CSRF uses exact paths, credentials, JSON, and no token storage', async () => {
  const mock = queue(json(user, 201), login(), token());
  const api = new GameApi(mock);
  const session = await api.signUp(credentials);
  assert.deepEqual(session.user, user);
  assert.deepEqual(mock.calls.map((x) => x.url), ['/api/auth/register', '/api/auth/login', '/api/auth/csrf']);
  assert.deepEqual(mock.calls.slice(0, 2).map(body), [credentials, credentials]);
  for (const call of mock.calls) {
    assert.equal(call.credentials, 'include');
    assert.equal(call.cache, 'no-store');
    assert.equal(call.redirect, 'error');
    assert.equal(call.headers.Cookie, undefined);
    assert.equal(call.headers.Origin, undefined);
  }
  assert.equal(mock.calls[0].headers['Content-Type'], 'application/json');
  assert.ok(!JSON.stringify(api.currentSession).includes(csrf));
  assert.ok(!JSON.stringify(api).includes(csrf));
  mock.done();
});

test('registration alone does not authenticate, and login accepts a short legacy password', async () => {
  const mock = queue(json(user, 201), login(), token());
  const api = new GameApi(mock);
  await api.register(credentials);
  assert.equal(api.currentSession, null);
  await api.login({ ...credentials, password: 'short' });
  assert.equal(body(mock.calls[1]).password, 'short');
});

test('session restoration fetches current account then CSRF; logout sends CSRF and clears memory', async () => {
  const mock = queue(json(user), token(), new Response(null, { status: 204 }));
  const api = new GameApi(mock);
  await api.restoreSession();
  await api.logout();
  assert.deepEqual(mock.calls.map((x) => x.url), ['/api/auth/me', '/api/auth/csrf', '/api/auth/logout']);
  assert.equal(mock.calls[2].headers['X-CSRF-Token'], csrf);
  assert.equal(mock.calls[2].body, undefined);
  assert.equal(api.currentSession, null);
  await assert.rejects(api.logout(), { code: 'csrf_not_initialized' });
});

test('anonymous restoration returns null; unavailable restoration propagates failure', async () => {
  const api = new GameApi(queue(failure(401, 'authentication_required'), failure(503, 'service_unavailable')));
  assert.equal(await api.restoreSession(), null);
  await assert.rejects(api.restoreSession(), { kind: 'unavailable', status: 503 });
});

test('CSRF initialization failure never publishes a partial session', async () => {
  const api = new GameApi(queue(login(), failure(503, 'service_unavailable')));
  await assert.rejects(api.login(credentials), { status: 503 });
  assert.equal(api.currentSession, null);
});

test('game filters encode search, status and pagination without arbitrary query keys', async () => {
  const mock = queue(json({ games: [], next_cursor: id }));
  const api = new GameApi(mock);
  const list = await api.listGames({ status: 'active', query: 'Cape & islands', cursor: id, limit: 10 });
  assert.equal(list.next_cursor, id);
  const parsed = new URL(mock.calls[0].url, 'https://offline.invalid');
  assert.equal(parsed.pathname, '/api/me/games');
  assert.deepEqual(Object.fromEntries(parsed.searchParams), { status: 'active', query: 'Cape & islands', cursor: id, limit: '10' });
  assert.throws(() => api.listGames({ limit: 101 }), ApiError);
});

test('catalog, home and health parse the actual untyped response shapes', async () => {
  const snapshot = { dataset_id: 'offline', source_url: 'https://example.invalid/populations', population_year: 2025,
    retrieved_on: '2026-10-01', source_sha256: 'a'.repeat(64) };
  const catalog = { population_snapshot: snapshot,
    countries: [{ id: 'za', name: 'South Africa', population: 60000000, base_soldier_value: 6 }] };
  const mock = queue(json(catalog), json({ message: 'Geopolitics Game API is running' }), json({ status: 'healthy', database: 'connected' }));
  const api = new GameApi(mock);
  assert.deepEqual(await api.countries(), catalog);
  assert.ok((await api.home()).message);
  assert.equal((await api.health()).status, 'healthy');
  assert.deepEqual(mock.calls.map((x) => x.url), ['/api/countries', '/api/', '/api/health']);
});

test('prepared creation snapshots body and key; explicit retry is byte-identical after uncertain failure', async () => {
  const mock = queue(login(), token(), () => { throw new Error('private network failure'); }, json(game(), 201));
  const api = new GameApi(mock);
  await api.login(credentials);
  const input = { game_name: 'Offline game', starting_country_id: 'south-africa' };
  const operation = api.prepareCreation(input, 'creation_fixed');
  input.game_name = 'Changed outside operation';
  assert.ok(Object.isFrozen(operation.body));
  await assert.rejects(api.createGame(operation), { kind: 'network', uncertain: true });
  assert.equal(mock.calls.length, 3); // No automatic retry.
  await api.createGame(operation);
  const calls = mock.calls.slice(2);
  assert.equal(calls[0].body, calls[1].body);
  assert.equal(calls[0].headers['Idempotency-Key'], 'creation_fixed');
  assert.equal(calls[1].headers['Idempotency-Key'], 'creation_fixed');
  assert.equal(calls[0].headers['X-CSRF-Token'], csrf);
  assert.equal(api.cachedGame(id).revision, 0);
});

test('protected mutation without initialized CSRF fails before any fetch', async () => {
  const mock = queue();
  const api = new GameApi(mock);
  await assert.rejects(api.createGame(api.prepareCreation({ game_name: 'Game', starting_country_id: 'za' })), {
    code: 'csrf_not_initialized',
  });
  assert.equal(mock.calls.length, 0);
});

test('every exact action payload is validated and sent with original action_id and expected_revision', async () => {
  const actions = [
    { type: 'start_attack', source_id: 'za', target_id: 'us' }, { type: 'roll' }, { type: 'stop_attack' },
    { type: 'transfer', source_id: 'za', target_id: 'us', amount: 2 },
    { type: 'allocate', allocations: [{ country_id: 'za', amount: 2 }] }, { type: 'skip' }, { type: 'end_turn' },
  ];
  const mock = queue(login(), token(), ...actions.map((_, i) => json(result(i + 1))));
  const api = new GameApi(mock);
  await api.login(credentials);
  for (const [i, action] of actions.entries()) {
    const command = { action_id: `action_${i}`, expected_revision: i, action };
    const operation = api.prepareAction(id, command);
    const outcome = await api.humanAction(operation);
    assert.deepEqual(body(mock.calls[i + 2]), command);
    assert.equal(outcome.state.revision, i + 1);
    assert.equal(mock.calls[i + 2].url, `/api/games/${id}/actions`);
  }
  assert.throws(() => api.prepareAction(id, { action_id: 'bad', expected_revision: 1, action: { type: 'attack' } }), ApiError);
  assert.throws(() => api.prepareAction(id, { action_id: 'bad', expected_revision: 1.5, action: { type: 'roll' } }), ApiError);
  assert.throws(() => api.prepareAction(id, { action_id: 'bad', expected_revision: 1, action: { source_id: 'za', target_id: 'us' } }), ApiError);
});

test('revision conflict refetches public authoritative state and does not resubmit the action', async () => {
  const mock = queue(login(), token(), failure(409, 'revision_conflict'), json(game(7)));
  const api = new GameApi(mock);
  await api.login(credentials);
  const op = api.prepareAction(id, { action_id: 'conflict_fixed', expected_revision: 0, action: { type: 'skip' } });
  await assert.rejects(api.humanAction(op), (error) => {
    assert.equal(error.status, 409);
    assert.equal(error.latestState.revision, 7);
    return true;
  });
  assert.equal(mock.calls.length, 4);
  assert.equal(mock.calls[3].url, `/api/games/${id}`);
  assert.equal(op.command.expected_revision, 0);
});

test('a failed conflict refresh preserves the original conflict', async () => {
  const api = new GameApi(queue(login(), token(), failure(409, 'action_id_conflict'), failure(503, 'service_unavailable')));
  await api.login(credentials);
  const op = api.prepareNpcStep(id, 0);
  await assert.rejects(api.npcStep(op), { status: 409, code: 'action_id_conflict', latestState: undefined });
});

test('an old receipt triggers a refetch; neither receipt nor stale GET rewinds newer cached state', async () => {
  const mock = queue(login(), token(), json(game(8)), json(result(2)), json(game(7)));
  const api = new GameApi(mock);
  await api.login(credentials);
  await api.getGame(id);
  const outcome = await api.npcStep(api.prepareNpcStep(id, 1));
  assert.equal(outcome.staleResponse, true);
  assert.equal(outcome.response.state.revision, 2);
  assert.equal(outcome.state.revision, 8);
  assert.equal(api.cachedGame(id).revision, 8);
  assert.equal(mock.calls[4].method, 'GET');
});

test('NPC request performs one action and retains explanation/evidence and event cursor', async () => {
  const decision = { strategy_version: 'balanced-v1', action: { type: 'skip' }, reason: 'skip', explanation: 'No acceptable attack.',
    evaluation: { actor_id: 'npc1', revision: 0, turn_sequence: 1, round: 1, countries: [], participants: [], attacks: [],
      defensive_exposure: 0, concentration: 0 }, projected_potential: null };
  const response = { ...result(), npc_decision: decision };
  const page = { events: [{ revision: 1, action_id: 'npc-fixed', actor: { player_id: 'npc1', kind: 'npc' },
    committed_at: '2026-10-29T10:00:00Z', events: [], npc_decision: decision }], after_revision: 0, next_after_revision: 1, has_more: false };
  const mock = queue(login(), token(), json(response), json(page));
  const api = new GameApi(mock);
  await api.login(credentials);
  const outcome = await api.npcStep(api.prepareNpcStep(id, 0));
  assert.deepEqual(body(mock.calls[2]), { expected_revision: 0 });
  assert.equal(mock.calls[2].url, `/api/games/${id}/npc-steps`);
  assert.equal(outcome.response.npc_decision.explanation, decision.explanation);
  assert.deepEqual(await api.events(id, { after_revision: 0, limit: 20 }), page);
  assert.equal(mock.calls[3].url, `/api/games/${id}/events?after_revision=0&limit=20`);
});

test('spectator game/event reads require no authentication or CSRF and never POST', async () => {
  const mock = queue(json(game()), json({ events: [], after_revision: 0, next_after_revision: 0, has_more: false }));
  const api = new GameApi(mock);
  await api.getGame(id);
  await api.events(id);
  assert.ok(mock.calls.every((x) => x.method === 'GET' && x.headers['X-CSRF-Token'] === undefined));
});

for (const [status, code, kind] of [[401, 'authentication_required', 'unauthenticated'], [403, 'game_not_owned', 'forbidden'],
  [409, 'revision_conflict', 'conflict'], [429, 'rate_limited', 'rate_limited'], [503, 'authentication_disabled', 'unavailable']]) {
  test(`HTTP ${status} exposes a safe typed error and never retries`, async () => {
    const mock = queue(failure(status, code, { 'Retry-After': '12' }));
    const client = new HttpClient(mock);
    await assert.rejects(client.request('/auth/me', { parse: component('UserPublic') }), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.kind, kind);
      assert.equal(error.status, status);
      assert.equal(error.code, code);
      assert.equal(error.retryAfterMs, 12000);
      return true;
    });
    assert.equal(mock.calls.length, 1);
  });
}

test('401 clears session and CSRF; an ownership 403 preserves the session', async () => {
  const mock = queue(login(), token(), failure(403, 'game_not_owned'), failure(401, 'authentication_required'));
  const api = new GameApi(mock);
  await api.login(credentials);
  await assert.rejects(api.listGames(), { status: 403 });
  assert.deepEqual(api.currentSession.user, user);
  await assert.rejects(api.currentUser(), { status: 401 });
  assert.equal(api.currentSession, null);
  await assert.rejects(api.npcStep(api.prepareNpcStep(id, 0)), { code: 'csrf_not_initialized' });
});

test('CSRF rejection removes the stale token until explicitly refreshed', async () => {
  const mock = queue(login(), token(), failure(403, 'csrf_rejected'), token(), json(result()));
  const api = new GameApi(mock);
  await api.login(credentials);
  const operation = api.prepareNpcStep(id, 0);
  await assert.rejects(api.npcStep(operation), { code: 'csrf_rejected' });
  await assert.rejects(api.npcStep(operation), { code: 'csrf_not_initialized' });
  assert.equal(mock.calls.length, 3);
  await api.refreshCsrf();
  await api.npcStep(operation);
});

test('Retry-After supports seconds, HTTP dates, missing/unreadable and malformed headers', () => {
  const now = Date.parse('2026-10-29T10:00:00Z');
  assert.equal(retryAfterMs('5', now), 5000);
  assert.equal(retryAfterMs('Thu, 29 Oct 2026 10:00:10 GMT', now), 10000);
  assert.equal(retryAfterMs('Thu, 29 Oct 2026 09:59:00 GMT', now), 0);
  assert.equal(retryAfterMs(null, now), undefined);
  assert.equal(retryAfterMs('nonsense', now), undefined);
  assert.equal(retryAfterMs('-1', now), undefined);
});

for (const [label, response] of [
  ['HTML instead of JSON', () => new Response('<html>unavailable</html>', { headers: { 'Content-Type': 'text/html' } })],
  ['invalid JSON', () => new Response('{', { headers: { 'Content-Type': 'application/json' } })],
  ['missing fields', () => json({ wrong: 'shape' })],
  ['wrong scalar type', () => json({ id: 9, username: 'test' })],
]) {
  test(`rejects malformed response: ${label}`, async () => {
    const api = new GameApi(queue(response()));
    await assert.rejects(api.currentUser(), { kind: 'malformed' });
  });
}

test('timeout covers hanging response bodies, sanitizes exceptions and does not retry mutations', async () => {
  const mock = queue(login(), token(), () => new Response(new ReadableStream({ start() {} }), {
    headers: { 'Content-Type': 'application/json' },
  }));
  const api = new GameApi({ ...mock, timeoutMs: 30 });
  await api.login(credentials);
  await assert.rejects(api.npcStep(api.prepareNpcStep(id, 0)), { kind: 'timeout', uncertain: true });
  assert.equal(mock.calls.length, 3);
  assert.ok(mock.calls[2].signal.aborted);
});

test('timeout covers a fetch implementation that never resolves', async () => {
  const api = new GameApi({ fetch: async () => new Promise(() => {}), timeoutMs: 10 });
  await assert.rejects(api.home(), { kind: 'timeout', uncertain: false });
});

test('server errors mark mutations uncertain; exceptions never disclose raw messages', async () => {
  const mock = queue(login(), token(), failure(503, 'service_unavailable'));
  const api = new GameApi(mock);
  await api.login(credentials);
  await assert.rejects(api.npcStep(api.prepareNpcStep(id, 0)), { uncertain: true, status: 503 });
  const client = new HttpClient({ fetch: async () => { throw new Error('sensitive driver message'); } });
  await assert.rejects(client.request('/health', { parse: (x) => x }), (error) => {
    assert.equal(error.kind, 'network');
    assert.ok(!JSON.stringify(error).includes('sensitive'));
    assert.ok(!error.message.includes('sensitive'));
    return true;
  });
});

test('concurrent human/NPC mutations for the same game are rejected before sending', async () => {
  let finish;
  const pending = new Promise((resolve) => { finish = resolve; });
  const mock = queue(login(), token(), () => pending);
  const api = new GameApi(mock);
  await api.login(credentials);
  const first = api.npcStep(api.prepareNpcStep(id, 0));
  await assert.rejects(api.humanAction(api.prepareAction(id, {
    action_id: 'human_fixed', expected_revision: 0, action: { type: 'skip' },
  })), { code: 'mutation_in_flight' });
  finish(json(result()));
  await first;
  assert.equal(mock.calls.length, 3);
});

test('network failure during logout propagates and clears local session without claiming revocation', async () => {
  const api = new GameApi(queue(login(), token(), () => { throw new Error('offline'); }));
  await api.login(credentials);
  await assert.rejects(api.logout(), { kind: 'network', uncertain: true });
  assert.equal(api.currentSession, null);
});

test('an explicit human-action retry retains its ID, revision and immutable payload', async () => {
  const mock = queue(login(), token(), () => { throw new Error('offline'); }, json(result()));
  const api = new GameApi(mock);
  await api.login(credentials);
  const command = { action_id: 'human_retry_fixed', expected_revision: 0,
    action: { type: 'transfer', source_id: 'za', target_id: 'us', amount: 1 } };
  const prepared = api.prepareAction(id, command);
  command.action.amount = 99;
  await assert.rejects(api.humanAction(prepared), { kind: 'network', uncertain: true });
  await api.humanAction(prepared);
  assert.equal(mock.calls[2].body, mock.calls[3].body);
  assert.equal(body(mock.calls[3]).action.amount, 1);
  assert.equal(body(mock.calls[3]).action_id, 'human_retry_fixed');
});

test('old game-creation replay retains the original key and never rewinds cached state', async () => {
  const mock = queue(login(), token(), json(game(8)), json(game(0), 201), json(game(9)));
  const api = new GameApi(mock);
  await api.login(credentials);
  await api.getGame(id);
  const state = await api.createGame(api.prepareCreation({ game_name: 'Offline', starting_country_id: 'za' }, 'creation-replay'));
  assert.equal(state.revision, 9);
  assert.equal(mock.calls[4].url, `/api/games/${id}`);
});

test('malformed mutation state identity is uncertain and cannot pollute the state cache', async () => {
  const bad = result();
  bad.state._id = 'fedcba987654321001234567';
  const api = new GameApi(queue(login(), token(), json(bad)));
  await api.login(credentials);
  await assert.rejects(api.npcStep(api.prepareNpcStep(id, 0)), { kind: 'malformed', uncertain: true });
  assert.equal(api.cachedGame(id), undefined);
});

test('runtime parsing rejects malformed nested events instead of exposing partial results', async () => {
  const bad = { ...result(), events: [{ type: 'invented_event', actor_id: 'npc', round: 1, turn_sequence: 1 }] };
  const api = new GameApi(queue(login(), token(), json(bad)));
  await api.login(credentials);
  await assert.rejects(api.npcStep(api.prepareNpcStep(id, 0)), { kind: 'malformed', uncertain: true });
});

test('a rejected login never attempts CSRF initialization', async () => {
  const mock = queue(failure(401, 'invalid_credentials'));
  const api = new GameApi(mock);
  await assert.rejects(api.login(credentials), { status: 401 });
  assert.equal(mock.calls.length, 1);
});

test('API-contract public response examples validate against the generated schema', async () => {
  const text = await readFile(new URL('../../docs/api-contract.md', import.meta.url), 'utf8');
  let checked = 0;
  for (const match of text.matchAll(/```json\r?\n([\s\S]*?)```/g)) {
    const sample = JSON.parse(match[1]);
    let name;
    if (sample?.state && Array.isArray(sample.events)) name = 'PublicActionResult';
    else if (sample?.game_name && Array.isArray(sample.countries)) name = 'PublicGame';
    else if (Array.isArray(sample?.games)) name = 'PublicGameList';
    else if (sample?.next_after_revision !== undefined) name = 'PublicEventPage';
    if (name) {
      component(name)(sample);
      checked++;
    }
  }
  assert.ok(checked >= 4, `Only ${checked} public examples were checked`);
});
