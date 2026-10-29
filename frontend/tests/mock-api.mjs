// Scripted HTTP fixtures for UI tests only. This is NOT a game engine or auth service.
// No runtime application file imports this module; there is no external I/O here.
export const fixturePassword = 'Offline fixture only 12345!';
export const fixtureUser = 'fixture_owner';
const csrf = 'm'.repeat(43);
const definitions = [
  ['south-africa', 'South Africa', 60000000, 5], ['vatican-city', 'Vatican City', 800, 1],
  ['france', 'France', 66000000, 5], ['germany', 'Germany', 84000000, 6],
  ['japan', 'Japan', 123000000, 7], ['india', 'India', 1400000000, 9],
  ['brazil', 'Brazil', 210000000, 9], ['canada', 'Canada', 40000000, 4],
  ['kenya', 'Kenya', 55000000, 5], ['australia', 'Australia', 27000000, 4],
];
export function fixtureGame(id, name = 'Offline game') {
  return {
    _id: id, game_name: name, status: 'active', schema_version: 3, revision: 0,
    round: 1, current_turn: 0, turn_sequence: 0, phase: 'deciding',
    pending_reinforcements: 0, attack_used: false, battle: null,
    countries: definitions.map(([id, name, population, base], i) => ({ id, name, population,
      base_soldier_value: base, soldiers: base, owner_id: i ? `npc-${i}` : 'human' })),
    players: definitions.map(([id], i) => ({ id: i ? `npc-${i}` : 'human', kind: i ? 'npc' : 'human', starting_country_id: id })),
    turn_order: definitions.map((_, i) => i ? `npc-${i}` : 'human'),
  };
}
const json = (body, status = 200, headers = {}) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', ...headers },
});
const fail = (status, code) => json({ detail: { code } }, status);

export function createMockApi({ seed = false } = {}) {
  const users = new Map([[fixtureUser, { id: 'account-1', username: fixtureUser, password: fixturePassword }]]);
  const sessions = new Map();
  const games = new Map();
  const owners = new Map();
  const receipts = new Map();
  const creations = new Map();
  const histories = new Map();
  const calls = []; // Method/path and command identity only; never credentials/cookies/CSRF.
  let fault;
  let counter = 0;
  let sessionCounter = 0;
  function addGame(owner, name) {
    const id = (++counter).toString(16).padStart(24, '0');
    const game = fixtureGame(id, name);
    games.set(id, game); owners.set(id, owner); histories.set(id, []);
    return game;
  }
  if (seed) for (let i = 1; i <= 12; i++) addGame('account-1', `Saved game ${i}`);
  function userFrom(cookie) { return sessions.get(/(?:^|;\s*)offline_fixture_session=([^;]+)/.exec(cookie ?? '')?.[1]); }

  async function handle(path, init = {}) {
    const method = init.method ?? 'GET';
    const url = new URL(path, 'http://offline.invalid');
    const route = url.pathname.replace(/^\/api(?=\/|$)/, '') || '/';
    const headers = new Headers(init.headers);
    const user = userFrom(headers.get('Cookie'));
    const body = init.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, path: route + url.search,
      ...(body?.action_id ? { action_id: body.action_id, expected_revision: body.expected_revision } : {}),
      ...(headers.has('Idempotency-Key') ? { key: headers.get('Idempotency-Key') } : {}) });
    if (fault?.path === route && fault.method === method) { const active = fault; fault = undefined; return active.response(); }
    if (route === '/countries') return json({
      population_snapshot: { dataset_id: 'OFFLINE-SCRIPTED-FIXTURE', source_url: 'https://example.invalid/fixture',
        population_year: 2025, retrieved_on: '2026-10-29', source_sha256: 'f'.repeat(64) },
      countries: definitions.map(([id, name, population, base_soldier_value]) => ({ id, name, population, base_soldier_value })),
    });
    if (method === 'POST' && route === '/auth/register') {
      if (users.has(body.username)) return fail(409, 'username_unavailable');
      const account = { id: `account-${users.size + 1}`, username: body.username, password: body.password };
      users.set(body.username, account);
      return json({ id: account.id, username: account.username }, 201);
    }
    if (method === 'POST' && route === '/auth/login') {
      const account = users.get(body.username);
      if (!account || account.password !== body.password) return fail(401, 'invalid_credentials');
      const token = `fixture-${++sessionCounter}`;
      sessions.set(token, account);
      // Distinct, non-production HTTP-only fixture cookie. Secure/__Host behavior
      // remains Stage E HTTPS acceptance, never weakened in backend code.
      return json({ user: { id: account.id, username: account.username }, expires_at: '2027-01-01T00:00:00Z' }, 200,
        { 'Set-Cookie': `offline_fixture_session=${token}; HttpOnly; SameSite=Lax; Path=/` });
    }
    if (route.startsWith('/auth/') || route === '/me/games' || method === 'POST') {
      if (!user) return fail(401, 'authentication_required');
    }
    if (method === 'POST' && headers.get('X-CSRF-Token') !== csrf) return fail(403, 'csrf_rejected');
    if (route === '/auth/me') return json({ id: user.id, username: user.username });
    if (route === '/auth/csrf') return json({ csrf_token: csrf });
    if (route === '/auth/logout') {
      const match = /offline_fixture_session=([^;]+)/.exec(headers.get('Cookie') ?? '');
      if (match) sessions.delete(match[1]);
      return new Response(null, { status: 204, headers: { 'Set-Cookie': 'offline_fixture_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0' } });
    }
    if (route === '/me/games') {
      const query = url.searchParams.get('query')?.toLowerCase() ?? '';
      const status = url.searchParams.get('status');
      const cursor = url.searchParams.get('cursor');
      const limit = Number(url.searchParams.get('limit') ?? 20);
      const list = [...games.values()].filter((game) => owners.get(game._id) === user.id
        && game.game_name.toLowerCase().includes(query) && (!status || game.status === status))
        .sort((a, b) => b._id.localeCompare(a._id)).filter((game) => !cursor || game._id < cursor);
      const page = list.slice(0, limit).map((game) => ({ _id: game._id, game_name: game.game_name, status: game.status,
        round: game.round, phase: game.phase, revision: game.revision }));
      return json({ games: page, next_cursor: list.length > limit ? page.at(-1)._id : null });
    }
    if (route === '/games' && method === 'POST') {
      const key = `${user.id}:${headers.get('Idempotency-Key')}`;
      if (!creations.has(key)) creations.set(key, structuredClone(addGame(user.id, body.game_name)));
      return json(creations.get(key), 201);
    }
    const match = /^\/games\/([a-f0-9]{24})(?:\/(actions|npc-steps|events))?$/.exec(route);
    if (!match || !games.has(match[1])) return fail(404, 'game_not_found');
    const [_, id, operation] = match;
    const game = games.get(id);
    if (!operation && method === 'GET') return json(game);
    if (operation === 'events') {
      const after = Number(url.searchParams.get('after_revision') ?? 0);
      const limit = Number(url.searchParams.get('limit') ?? 20);
      const entries = histories.get(id).filter((event) => event.revision > after);
      const page = entries.slice(0, limit);
      return json({ events: page, after_revision: after, next_after_revision: page.at(-1)?.revision ?? after, has_more: entries.length > limit });
    }
    if (method !== 'POST' || owners.get(id) !== user.id) return fail(403, 'game_not_owned');
    const key = `${id}:${operation === 'actions' ? body.action_id : `npc-${body.expected_revision}`}`;
    if (receipts.has(key)) return json(receipts.get(key));
    if (body.expected_revision !== game.revision) return fail(409, 'revision_conflict');
    const actor = game.players[game.current_turn];
    const event = { type: 'turn_ended', actor_id: actor.id, round: game.round, turn_sequence: game.turn_sequence };
    let decision = null;
    if (operation === 'npc-steps') {
      if (actor.kind !== 'npc') return fail(409, 'invalid_game_action');
      // A scripted skip receipt exercises the UI; it does not claim NPC strategy.
      decision = { strategy_version: 'offline-fixture', action: { type: 'skip' }, reason: 'skip',
        explanation: 'Offline fixture: this NPC skipped its turn. The real backend supplies strategic explanations.',
        evaluation: { actor_id: actor.id, revision: game.revision, turn_sequence: game.turn_sequence, round: game.round,
          countries: [], participants: [], attacks: [], defensive_exposure: 0, concentration: 0 } };
      game.current_turn = (game.current_turn + 1) % 10;
      if (game.current_turn === 0) { game.round = 2; game.phase = 'allocating'; game.pending_reinforcements = game.countries[1].owner_id === 'human' ? 4 : 2; }
    } else {
      if (actor.kind !== 'human') return fail(409, 'invalid_game_action');
      const action = body.action;
      switch (action.type) {
        case 'start_attack':
          game.phase = 'attacking'; game.attack_used = true;
          game.battle = { source_id: action.source_id, target_id: action.target_id };
          Object.assign(event, { type: 'attack_started', ...game.battle });
          break;
        case 'roll':
          Object.assign(event, { type: 'dice_exchange', ...game.battle, attacker_dice: [6], defender_dice: [1], attacker_losses: 0, defender_losses: 1 });
          game.countries[1] = { ...game.countries[1], owner_id: 'human', soldiers: 2 };
          game.phase = 'post_attack'; game.battle = null;
          break;
        case 'transfer':
          game.countries[0].soldiers = 4; game.countries[1].soldiers = 3;
          Object.assign(event, { type: 'transferred', source_id: action.source_id, target_id: action.target_id, amount: action.amount });
          break;
        case 'allocate':
          game.countries[0].soldiers = 8; game.pending_reinforcements = 0; game.phase = 'deciding';
          Object.assign(event, { type: 'allocated', allocations: action.allocations });
          break;
        case 'skip': case 'end_turn': case 'stop_attack':
          game.current_turn = game.countries[1].owner_id === 'human' ? 2 : 1;
          game.phase = 'deciding'; game.attack_used = false; game.battle = null;
          if (action.type === 'stop_attack') event.type = 'attack_stopped';
          break;
        default: return fail(409, 'invalid_game_action');
      }
    }
    game.revision++;
    game.turn_sequence++;
    const response = { state: structuredClone(game), events: [event], npc_decision: decision };
    delete response.state._id;
    receipts.set(key, structuredClone(response));
    histories.get(id).push({ revision: game.revision, action_id: body.action_id ?? `npc-${body.expected_revision}`, actor: { player_id: actor.id, kind: actor.kind },
      committed_at: '2026-10-29T12:00:00Z', events: [event], npc_decision: decision });
    return json(response);
  }
  return { handle, calls, games, histories, addGame,
    failNext(method, path, response) { fault = { method, path, response }; },
    createFetch() {
      let cookie = '';
      return async (path, init = {}) => {
        const response = await handle(path, { ...init, headers: { ...init.headers, Cookie: cookie } });
        if (response.headers.has('Set-Cookie')) cookie = response.headers.get('Set-Cookie').split(';')[0];
        return response;
      };
    },
  };
}
