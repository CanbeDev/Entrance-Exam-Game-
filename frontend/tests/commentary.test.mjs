import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { BattleCommentaryRequests } from '../src/api/commentary.ts';
import { NewBattleCommentary } from '../src/api/live-commentary.ts';
import { ApiError, GameApi } from '../src/api/index.ts';
import { GameController } from '../src/game/controller.ts';
import { fixtureGame, fixturePassword, fixtureUser, createMockApi } from './mock-api.mjs';
import { id, credentials, csrf, json, login, token, result } from './helpers.mjs';

const value = (revision = 2, status = 'ready', kind = 'human') => ({ game_id: id, revision,
  action_id: `battle-${revision}`, status, source: status === 'ready' ? 'groq' : 'deterministic',
  text: status === 'ready' ? 'The attack struck hard; the defenders held their ground.' : 'A committed battle took place.', reason: null,
  facts: { attacker: 'South Africa', defender: 'France', attacker_dice: [6, 2], defender_dice: [5, 3],
    attacker_losses: 1, defender_losses: 1, conquered: false, eliminated: [], round: 1, actor_kind: kind },
});
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
const tick = () => new Promise((done) => setImmediate(done));

test('commentary retrieval caches and deduplicates stable game/revision identities', async () => {
  let reads = 0, writes = 0;
  const gate = deferred();
  const client = new BattleCommentaryRequests(async () => { reads++; await gate.promise; return value(); }, async () => { writes++; return value(); });
  const first = client.get(id, 2), second = client.get(id, 2);
  assert.equal(first, second);
  assert.equal(reads, 1);
  gate.resolve(); const response = await first;
  assert.equal(await client.get(id, 2), response);
  assert.equal(await client.get(id, 2, true), response);
  assert.ok(Object.isFrozen(response.facts.attacker_dice));
  assert.equal(reads, 1); assert.equal(writes, 0);
});

test('commentary queues bound reads to two and generation to one independently', async () => {
  let readActive = 0, readMax = 0, writeActive = 0, writeMax = 0;
  const readsGate = deferred(), writesGate = deferred();
  const client = new BattleCommentaryRequests(async (_game, revision) => {
    readActive++; readMax = Math.max(readMax, readActive); await readsGate.promise; readActive--; return value(revision, 'not_generated');
  }, async (_game, revision) => {
    writeActive++; writeMax = Math.max(writeMax, writeActive); await writesGate.promise; writeActive--; return value(revision);
  });
  const reads = [1, 2, 3, 4].map((revision) => client.get(id, revision));
  const writes = [5, 6, 7].map((revision) => client.request(id, revision));
  assert.equal(readActive, 2); assert.equal(writeActive, 1);
  writesGate.resolve(); await Promise.all(writes);
  assert.equal(readActive, 2); // Narration reads have not blocked the write queue.
  readsGate.resolve(); await Promise.all(reads);
  assert.equal(readMax, 2); assert.equal(writeMax, 1);
});

test('duplicate owner generation shares one POST and persisted terminal output is not regenerated', async () => {
  let writes = 0; const gate = deferred();
  const client = new BattleCommentaryRequests(async () => value(2, 'not_generated'), async () => { writes++; await gate.promise; return value(); });
  await client.get(id, 2);
  const first = client.request(id, 2), second = client.request(id, 2);
  assert.equal(first, second); assert.equal(writes, 1);
  gate.resolve(); const response = await first;
  assert.equal(await client.request(id, 2), response);
  assert.equal(writes, 1);
});

test('uncertain generation never replays automatically or on a repeated request; GET reconciles it', async () => {
  let writes = 0;
  const client = new BattleCommentaryRequests(async () => value(), async () => { writes++; throw new ApiError('timeout', { uncertain: true }); });
  await assert.rejects(client.request(id, 2), { kind: 'timeout' });
  await assert.rejects(client.request(id, 2), { code: 'commentary_check_saved' });
  assert.equal(writes, 1);
  const recovered = await client.get(id, 2, true);
  assert.equal(recovered.status, 'ready');
  assert.equal(await client.request(id, 2), recovered);
  assert.equal(writes, 1);
});

test('a stale read cannot overwrite newly generated narration', async () => {
  const gate = deferred();
  const client = new BattleCommentaryRequests(async () => { await gate.promise; return value(2, 'not_generated'); }, async () => value());
  const read = client.get(id, 2);
  const generated = await client.request(id, 2);
  gate.resolve(); assert.equal(await read, generated);
  assert.equal((await client.get(id, 2)).status, 'ready');
});

test('saved pending commentary is checked with GET rather than another POST', async () => {
  let reads = 0, writes = 0;
  const client = new BattleCommentaryRequests(async () => ++reads === 1 ? value(2, 'pending') : value(), async () => { writes++; return value(); });
  await client.get(id, 2);
  assert.equal((await client.request(id, 2)).status, 'pending');
  assert.equal(writes, 0);
  assert.equal((await client.get(id, 2, true)).status, 'ready');
  assert.equal(reads, 2);
});

test('saved games load persisted fallback after a new page without billable generation', async () => {
  let writes = 0;
  const newPage = new BattleCommentaryRequests(async () => value(2, 'fallback'), async () => { writes++; return value(); });
  assert.equal((await newPage.get(id, 2)).status, 'fallback');
  assert.equal((await newPage.request(id, 2)).status, 'fallback');
  assert.equal(writes, 0);
});

test('commentary rejects invalid routes and mismatched response identities', async () => {
  let calls = 0;
  const client = new BattleCommentaryRequests(async () => { calls++; return value(3); }, async () => value());
  assert.throws(() => client.get('https://example.invalid', 2), { kind: 'client' });
  assert.throws(() => client.get(id, -1), { kind: 'client' });
  assert.equal(calls, 0);
  await assert.rejects(client.get(id, 2), { kind: 'malformed' });
});

test('API commentary GET is anonymous; POST uses existing session/CSRF and exact committed revision', async () => {
  const calls = [];
  const api = new GameApi({ fetch: async (path, init) => {
    calls.push({ path, ...init });
    if (path === '/api/auth/login') return login();
    if (path === '/api/auth/csrf') return token();
    return json(value(2, init.method === 'POST' ? 'ready' : 'not_generated'));
  } });
  await api.battleCommentary(id, 2);
  await assert.rejects(api.generateBattleCommentary(id, 2), { status: 401 });
  assert.equal(calls.length, 1);
  await api.login(credentials);
  await api.generateBattleCommentary(id, 2);
  assert.equal(calls[0].path, `/api/games/${id}/commentary/2`);
  assert.equal(calls[0].credentials, 'omit');
  assert.equal(new Headers(calls[0].headers).has('X-CSRF-Token'), false);
  const post = calls.at(-1);
  assert.equal(post.method, 'POST'); assert.equal(post.credentials, 'include');
  assert.equal(post.headers['X-CSRF-Token'], csrf);
  assert.deepEqual(JSON.parse(post.body), {});
  assert.equal(api.cachedGame(id), undefined);
});

test('a hanging commentary request cannot serialize or delay authoritative human/NPC requests', async () => {
  const gate = deferred();
  const api = new GameApi({ timeoutMs: 1000, fetch: async (path) => {
    if (path === '/api/auth/login') return login();
    if (path === '/api/auth/csrf') return token();
    if (path.includes('/commentary/')) { await gate.promise; return json(value()); }
    if (path.endsWith('/actions')) return json(result(1));
    if (path.endsWith('/npc-steps')) return json(result(2));
    throw new Error('Unexpected isolated request');
  } });
  await api.login(credentials);
  let narrationDone = false;
  const narration = api.generateBattleCommentary(id, 2).finally(() => { narrationDone = true; });
  await tick();
  await api.humanAction(api.prepareAction(id, { action_id: 'human-battle', expected_revision: 0, action: { type: 'skip' } }));
  await api.npcStep(api.prepareNpcStep(id, 1));
  assert.equal(narrationDone, false);
  assert.equal(api.cachedGame(id).revision, 2);
  gate.resolve(); await narration;
  assert.equal(api.cachedGame(id).revision, 2);
});

for (const paused of [false, true]) {
test(`commentary failure preserves saved NPC identity, cap and ${paused ? 'explicit Pause' : 'active confirmation intent'}`, async (t) => {
  const gameId = '000000000000000000000001';
  const mock = createMockApi({ seed: true });
  mock.games.set(gameId, { ...fixtureGame(gameId), current_turn: 1 });
  const delegate = mock.createFetch();
  const api = new GameApi({ fetch: async (path, init) => {
    if (path.includes('/commentary/')) throw new TypeError('Private provider failure must not surface');
    return delegate(path, init);
  } });
  const controller = new GameController(api); t.after(() => controller.dispose());
  await controller.initialize(gameId);
  await controller.authenticate({ username: fixtureUser, password: fixturePassword }, false);
  controller.configureNpcBudget(1);
  mock.failNext('POST', `/games/${gameId}/npc-steps`, () => { throw new TypeError('Offline NPC interruption'); });
  await controller.fastForward();
  assert.equal(controller.getSnapshot().fastForward, true);
  if (paused) controller.pause();
  const before = controller.getSnapshot();
  assert.ok(before.pending);
  await assert.rejects(api.generateBattleCommentary(gameId, 1), { kind: 'network' });
  const after = controller.getSnapshot();
  assert.equal(after, before);
  assert.equal(after.pending, before.pending);
  assert.equal(after.npcAttempts, 1);
  assert.equal(after.npcAttemptBudget, 1);
  assert.equal(after.fastForward, !paused);
});
}

test('real commentary UI renders human/NPC narration, fallback/loading and spectator safety beside unchanged dice', async () => {
  const server = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false }, logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    const { BattleCommentaryView } = await server.ssrLoadModule('/src/components/BattleCommentary.tsx');
    const { History } = await server.ssrLoadModule('/src/components/History.tsx');
    const game = fixtureGame(id);
    const entry = { revision: 2, action_id: 'battle-2', actor: { player_id: 'human', kind: 'human' }, committed_at: '2026-10-31T12:00:00Z',
      events: [{ type: 'dice_exchange', actor_id: 'human', round: 1, turn_sequence: 1, source_id: 'south-africa', target_id: 'france',
        attacker_dice: [6, 2], defender_dice: [5, 3], attacker_losses: 1, defender_losses: 1 }], npc_decision: null };
    const render = (display, canGenerate = false) => renderToStaticMarkup(createElement(BattleCommentaryView,
      { game, entry, display: { commentary: null, error: null, requested: false, loading: false, ...display }, canGenerate, generate() {}, check() {} }));
    for (const kind of ['human', 'npc']) {
      const ready = render({ commentary: value(2, 'ready', kind) });
      assert.match(ready, /<h5>Commentary<\/h5>/); assert.doesNotMatch(ready, /AI Commentary|LLM-generated|Groq|Written by AI/i); assert.match(ready, /defenders held their ground/);
      assert.doesNotMatch(ready, /Generate commentary/);
    }
    assert.match(render({ loading: true }), /Loading commentary.*Gameplay remains available/);
    assert.match(render({ commentary: value(2, 'fallback') }), /Saved battle summary/s);
    assert.match(render({ commentary: value(2, 'pending') }), /Check saved commentary/);
    assert.match(render({ commentary: value(2, 'not_generated') }, true), /Generate commentary/);
    assert.doesNotMatch(render({ commentary: value(2, 'not_generated') }), /Generate commentary/);
    assert.match(render({ commentary: value(2, 'not_generated') }), /Check saved commentary/);
    const escaped = render({ commentary: { ...value(), text: '<script>alert(1)</script>' } });
    assert.match(escaped, /&lt;script&gt;/);
    assert.doesNotMatch(escaped, /<script>/);
    const chronicle = "South Africa's assault met France's stubborn resistance. The contest remained balanced, leaving both sides searching for an advantage in a tense, unresolved exchange.";
    const narration = render({ commentary: { ...value(), text: chronicle } });
    assert.match(narration, /<h5>Commentary<\/h5>/);
    assert.match(narration, /stubborn resistance/);
    assert.match(narration, /tense, unresolved exchange/);
    const failed = render({ error: 'Saved commentary is unavailable.' });
    assert.match(failed, /Commentary could not be confirmed/); assert.doesNotMatch(failed, /South Africa attacked France/);
    const history = renderToStaticMarkup(createElement(History, { game, events: [entry], latest: null, more: false,
      disabled: false, loadMore() {}, api: {}, gameId: id, canGenerateCommentary: false,
      commentaryAccountId: null, liveCommentaryAllowed: false, canStartCommentary: () => false }));
    assert.match(history, /Attacker dice: 6, 2. Defender dice: 5, 3/);
    assert.match(history, /Attacker losses: 1/); assert.match(history, /Defender losses: 1/);
    assert.match(history, /Commentary for move 2/);
    assert.doesNotMatch(history, /Generate commentary/);
    assert.doesNotMatch(history, /Commentary for new battles/);
    const owner = renderToStaticMarkup(createElement(History, { game, events: [entry], latest: null, more: false,
      disabled: false, loadMore() {}, api: {}, gameId: id, canGenerateCommentary: true,
      commentaryAccountId: 'fixture-owner', liveCommentaryAllowed: true, canStartCommentary: () => true }));
    assert.match(owner, /Commentary for new battles/);
    assert.match(owner, /checked=""/);
  } finally { await server.close(); }
});

const committed = (revision, type = 'dice_exchange') => ({ revision, action_id: `battle-${revision}`,
  events: [{ type }] });

function liveFixture({ initial = 7, generate, permitted = () => true } = {}) {
  const entries = new Map(), posts = [], reads = [], updates = [];
  const read = async (_game, after) => {
    reads.push(after);
    const events = [...entries.values()].filter((entry) => entry.revision > after).sort((a, b) => a.revision - b.revision).slice(0, 100);
    return { after_revision: after, next_after_revision: events.at(-1)?.revision ?? after,
      events, has_more: events.length === 100 };
  };
  const requests = new BattleCommentaryRequests(async (_game, revision) => value(revision), async (_game, revision) => {
    posts.push(revision); return generate ? generate(revision) : value(revision);
  });
  const live = new NewBattleCommentary((game, revision, permission) => requests.request(game, revision, permission),
    (revision, display) => updates.push([revision, display]), read, initial, permitted);
  return { live, entries, posts, reads, updates };
}

test('live narration defaults on for the owner and narrates newly committed human and NPC exchanges once', async () => {
  const f = liveFixture();
  f.live.contextChanged(id, 'owner', true);
  assert.equal(f.live.active, true);
  f.entries.set(8, { ...committed(8), actor: { kind: 'human', player_id: 'human' } });
  f.entries.set(9, { ...committed(9), actor: { kind: 'npc', player_id: 'npc-1' } });
  f.live.observe(9); await tick();
  assert.deepEqual(f.posts, [8, 9]);
  assert.equal(f.updates.at(-1)[1].entry.actor.kind, 'npc');
  f.live.observe(9); await tick();
  assert.deepEqual(f.posts, [8, 9]);
});

test('saved-game reload or remount never generates the historical backlog', async () => {
  for (let mount = 0; mount < 3; mount++) {
    const f = liveFixture({ initial: 200 });
    for (let rev = 1; rev <= 200; rev++) f.entries.set(rev, committed(rev));
    f.live.contextChanged(id, 'owner', true); f.live.observe(200); await tick();
    assert.deepEqual(f.reads, []); assert.deepEqual(f.posts, []);
    f.live.dispose();
  }
});

test('manual opt-out cancels queued work and re-enabling does not backfill missed exchanges', async () => {
  const gate = deferred();
  const f = liveFixture({ generate: async (revision) => { await gate.promise; return value(revision); } });
  f.live.contextChanged(id, 'owner', true);
  f.entries.set(8, committed(8)); f.entries.set(9, committed(9)); f.live.observe(9);
  await tick(); assert.deepEqual(f.posts, [8]);
  f.live.disable(); gate.resolve(); await tick();
  assert.deepEqual(f.posts, [8]);
  assert.equal(f.updates.at(-1)[1].commentary.status, 'ready');
  assert.equal(f.live.enable(9), true);
  f.entries.set(10, committed(10)); f.live.observe(10); await tick();
  assert.deepEqual(f.posts, [8, 10]);
});

test('spectators, non-owners and unresolved NPC recovery never start generation', async () => {
  let allowed = false;
  const f = liveFixture({ permitted: () => allowed });
  f.entries.set(8, committed(8));
  f.live.contextChanged(id, null, false); f.live.observe(8); await tick();
  assert.deepEqual(f.posts, []);
  f.live.contextChanged(id, 'owner', false); f.live.observe(8); await tick();
  assert.deepEqual(f.posts, []);
  f.entries.set(9, committed(9));
  f.live.contextChanged(id, 'owner', true); f.live.observe(9); await tick();
  assert.deepEqual(f.posts, []); // The dispatch-time controller snapshot still says pending.
  allowed = true; f.live.observe(9); await tick();
  assert.deepEqual(f.posts, [9]);
});

test('account and game changes discard old live responses and unsent work', async () => {
  for (const changed of ['account', 'game']) {
    const gate = deferred();
    const f = liveFixture({ generate: async (revision) => { await gate.promise; return value(revision); } });
    f.live.contextChanged(id, 'owner', true);
    f.entries.set(8, committed(8)); f.entries.set(9, committed(9)); f.live.observe(9); await tick();
    const count = f.updates.length;
    f.live.contextChanged(changed === 'game' ? '000000000000000000000099' : id,
      changed === 'account' ? 'other-owner' : 'owner', true);
    gate.resolve(); await tick();
    assert.deepEqual(f.posts, [8]);
    assert.equal(f.updates.length, count);
  }
});

test('uncertain live narration is not automatically replayed and later exchanges remain independent', async () => {
  const f = liveFixture({ generate: async (revision) => {
    if (revision === 8) throw new ApiError('timeout', { uncertain: true });
    return value(revision);
  } });
  f.live.contextChanged(id, 'owner', true);
  f.entries.set(8, committed(8)); f.entries.set(9, committed(9)); f.live.observe(9); await tick();
  f.live.observe(9); await tick();
  assert.deepEqual(f.posts, [8, 9]);
  assert.match(f.updates.findLast(([revision]) => revision === 8)[1].error, /Check saved commentary/);
});

test('new exchanges beyond 16 and historical display pages remain eligible with bounded receipt reads', async () => {
  const f = liveFixture({ initial: 500 });
  f.live.contextChanged(id, 'owner', true);
  for (let revision = 501; revision <= 625; revision++) f.entries.set(revision, committed(revision));
  f.live.observe(625); await tick();
  assert.equal(f.posts.length, 125);
  assert.equal(f.posts.at(-1), 625);
  assert.deepEqual(f.reads, [500, 600]);
  f.live.observe(625); await tick();
  assert.equal(f.posts.length, 125);
});

test('unconfirmed revisions, non-dice actions and empty receipt pages cannot trigger generation', async () => {
  const f = liveFixture();
  f.live.contextChanged(id, 'owner', true);
  f.live.observe(8); await tick();
  assert.deepEqual(f.posts, []);
  f.entries.set(8, committed(8, 'attack_started'));
  f.entries.set(9, committed(9)); f.entries.set(10, committed(10));
  f.live.observe(9); await tick();
  assert.deepEqual(f.posts, [9]); // Receipt 10 exists but its board revision is not yet confirmed.
  f.live.observe(10); await tick();
  assert.deepEqual(f.posts, [9, 10]); // Separate rolls in the same attack.
});

test('transient pending state pauses live work and resumes without replaying an already submitted receipt', async () => {
  const gate = deferred(); let allowed = true;
  const f = liveFixture({ permitted: () => allowed,
    generate: async (revision) => { await gate.promise; return value(revision); } });
  f.live.contextChanged(id, 'owner', true);
  f.entries.set(8, committed(8)); f.entries.set(9, committed(9)); f.live.observe(9); await tick();
  allowed = false; f.live.contextChanged(id, 'owner', false);
  gate.resolve(); await tick();
  assert.deepEqual(f.posts, [8]);
  allowed = true; f.live.contextChanged(id, 'owner', true); f.live.observe(9); await tick();
  assert.deepEqual(f.posts, [8, 9]);
});

test('an in-flight response cannot rewind the new baseline after owner toggles narration', async () => {
  const gate = deferred();
  const f = liveFixture({ generate: async (revision) => { await gate.promise; return value(revision); } });
  f.live.contextChanged(id, 'owner', true);
  f.entries.set(8, committed(8)); f.live.observe(8); await tick();
  f.live.disable(); f.live.enable(40);
  gate.resolve(); await tick();
  f.entries.set(41, committed(41)); f.live.observe(41); await tick();
  assert.deepEqual(f.posts, [8, 41]);
  assert.deepEqual(f.reads, [7, 40]);
});

test('disposing the view stops further work and late component updates', async () => {
  const gate = deferred();
  const f = liveFixture({ generate: async (revision) => { await gate.promise; return value(revision); } });
  f.live.contextChanged(id, 'owner', true);
  f.entries.set(8, committed(8)); f.entries.set(9, committed(9)); f.live.observe(9); await tick();
  f.live.dispose(); const count = f.updates.length;
  gate.resolve(); await tick();
  assert.deepEqual(f.posts, [8]); assert.equal(f.updates.length, count);
});

test('successful narration does not accumulate a lifetime 256-request cutoff', async () => {
  let posts = 0;
  const requests = new BattleCommentaryRequests(async (_game, revision) => value(revision), async (_game, revision) => {
    posts++; return value(revision);
  });
  for (let revision = 1; revision <= 300; revision++) await requests.request(id, revision);
  assert.equal(posts, 300);
});

test('a spectator can check narration completed after its initial read without generating it', async () => {
  let generated = false, reads = 0, writes = 0;
  const spectator = new BattleCommentaryRequests(async () => {
    reads++; return value(2, generated ? 'ready' : 'not_generated');
  }, async () => { writes++; throw new Error('Spectators must never generate'); });
  assert.equal((await spectator.get(id, 2)).status, 'not_generated');
  generated = true; // Another authorized page completed the provider request.
  assert.equal((await spectator.get(id, 2, true)).status, 'ready');
  assert.equal(reads, 2);
  assert.equal(writes, 0);
});

test('browser cancellation after commentary submission is reconciled by GET without replay', async () => {
  let posts = 0, stored = null;
  const api = new GameApi({ timeoutMs: 30, fetch: async (path, init) => {
    if (path === '/api/auth/login') return login();
    if (path === '/api/auth/csrf') return token();
    if (init.method === 'POST') {
      posts++; stored = value();
      return new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => reject(new DOMException('Offline cancellation', 'AbortError')), { once: true });
      });
    }
    assert.equal(init.credentials, 'omit');
    return json(stored);
  } });
  await api.login(credentials);
  await assert.rejects(api.generateBattleCommentary(id, 2), { kind: 'timeout' });
  await assert.rejects(api.generateBattleCommentary(id, 2), { code: 'commentary_check_saved' });
  assert.equal((await api.battleCommentary(id, 2, true)).status, 'ready');
  assert.equal(posts, 1);
  assert.equal(api.cachedGame(id), undefined);
});
