import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { committedDisplays, actionSummary, nextSavedParticipant, phaseLabel } from '../src/components/gameplay-view.ts';

let vite, live, board, fixtures, battles, history;
before(async () => {
  vite = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false }, logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] } });
  [live, board, fixtures, battles, history] = await Promise.all(['/src/components/LiveGameplay.tsx', '/src/components/GameBoard.tsx',
    '/src/dev/board-fixtures.ts', '/src/dev/battle-fixtures.ts', '/src/components/History.tsx'].map(path => vite.ssrLoadModule(path)));
});
after(async () => { await vite?.close(); });
const html = element => renderToStaticMarkup(element);
const renderLive = state => html(createElement(live.LiveGameplay, { game: state.game, latest: state.lastResult, committed: state.events, pending: !!state.pending }));
const renderNpc = state => html(createElement(live.SavedNpcDecision, { game: state.game, latest: state.lastResult, committed: state.events }));

test('committed snapshot adapter prefers exact receipts, rejects future revisions and does not mutate inputs', () => {
  const state = battles.battleFixture('battle-six'), before = JSON.stringify(state);
  const receipt = state.events[0];
  const display = committedDisplays(state.game, { ...state.lastResult, events: [] }, [receipt, { ...receipt, revision: 99 }]);
  assert.equal(display.latest.revision, 12); assert.deepEqual(display.latest.events, receipt.events);
  assert.equal(JSON.stringify(state), before);
  assert.deepEqual(committedDisplays({ game_name: 'Legacy' }, state.lastResult, state.events), { latest: null, npc: null, exchange: null });
});

test('confirmed result alone is usable without inventing actor, receipt ID or timestamp', () => {
  const state = battles.battleFixture('battle-six');
  const display = committedDisplays(state.game, state.lastResult, []);
  assert.equal(display.latest.actorId, 'player-0'); assert.equal(display.latest.revision, 12);
  assert.equal('action_id' in display.latest, false); assert.equal('committed_at' in display.latest, false);
  assert.equal(committedDisplays(state.game, { ...state.lastResult, state: { ...state.game, _id: 'another-game' } }, []).latest, null);
});

test('live view shows every ordered die for six and twelve pairs with confirmed loss fields', () => {
  for (const mode of ['battle-six', 'battle-many']) {
    const state = battles.battleFixture(mode), text = renderLive(state);
    assert.equal((text.match(/data-pair=/g) || []).length, mode === 'battle-six' ? 6 : 12);
    const values = [...text.matchAll(/data-value="(\d+)"/g)].map(match => Number(match[1]));
    const event = state.events[0].events[0];
    assert.deepEqual(values, event.attacker_dice.flatMap((die, index) => [die, event.defender_dice[index]]));
    assert.match(text, /Latest confirmed exchange/); assert.ok(text.includes(`Attacker losses: ${event.attacker_losses}`));
    assert.ok(text.includes(`Defender losses: ${event.defender_losses}`));
  }
});

test('pending roll without a confirmed result never fabricates dice or success', () => {
  const state = battles.battleFixture('battle-inflight'), text = renderLive(state);
  assert.match(text, /awaiting confirmation/); assert.match(text, /Brazil: 10 soldiers/);
  assert.doesNotMatch(text, /data-value=|Latest confirmed exchange|conquered/);
});

test('pending operation can show only its previous confirmed outcome, explicitly labelled', () => {
  const text = renderLive(battles.battleFixture('battle-pending'));
  assert.match(text, /Previous confirmed result. The outstanding action is not confirmed/);
  assert.match(text, /Move 12/); assert.doesNotMatch(text, /Move 13/);
});

test('conquest keeps committed reward separate from casualties and after-reward stationed soldiers', () => {
  const text = renderLive(battles.battleFixture('battle-conquest'));
  assert.match(text, /Brazil conquered Canada; reward 2 soldiers/);
  assert.match(text, /Conquest reward: 2 soldiers added separately/);
  assert.match(text, /After conquest reward: 2 soldiers stationed here/);
  assert.match(text, /Defender losses: 2/);
});

test('older saved exchange survives turn changes without borrowing current board counts', () => {
  const state = battles.battleFixture('battle-stopped'), text = renderLive(state);
  assert.match(text, /Most recent saved exchange · Move 12/); assert.match(text, /Move 13/);
  assert.match(text, /Soldier count not recorded for this exchange/);
  assert.doesNotMatch(text, /soldiers after this exchange<\/p>/);
});

test('latest saved NPC reason remains visible independently of historical entry expansion', () => {
  for (const mode of ['npc', 'npc-fast-forward', 'npc-in-flight']) {
    const state = fixtures.boardFixture(mode), text = renderNpc(state);
    assert.match(text, /Norway’s Strategy/); assert.match(text, /Synthetic fixture explanation: continue this example battle/);
    const perspective = text.match(/<aside class="geo-live__perspective"[\s\S]*?<\/aside>/)?.[0];
    assert.ok(perspective); assert.doesNotMatch(perspective, /<details|hidden=/);
    assert.match(text, /Commander’s decision · Move 12/);
  }
});

test('justification is escaped, uses original home participant and is never AI-rewritten', () => {
  const state = fixtures.boardFixture('npc');
  state.game.countries.find(country => country.id === 'norway').owner_id = 'player-0';
  state.events[0].npc_decision.explanation = '<script>original reason</script>';
  const text = renderNpc(state);
  assert.match(text, /Norway’s Strategy/); assert.match(text, /&lt;script&gt;original reason&lt;\/script&gt;/);
  assert.doesNotMatch(text, /<script>|Generate commentary/);
});

test('event summaries preserve actor/target distinction, allocations and eliminated participant identity', () => {
  const game = fixtures.boardFixture().game, event = { actor_id: 'player-3', round: 2, turn_sequence: 10 };
  assert.equal(actionSummary(game, { ...event, type: 'eliminated', player_id: 'player-1' }), 'Canada was eliminated.');
  assert.equal(actionSummary(game, { ...event, type: 'allocated', allocations: [{ country_id: 'norway', amount: 2 }] }), 'Norway placed reinforcements: Norway +2.');
  assert.equal(actionSummary(game, { ...event, type: 'transferred', source_id: 'norway', target_id: 'canada', amount: 3 }), 'Norway transferred 3 soldiers from Norway to Canada.');
  assert.match(actionSummary(game, { ...event, type: 'dice_exchange' }), /attacker losses not recorded, defender losses not recorded/);
});

test('next slot skips eliminated participants within the recorded round and does not guess a wrap', () => {
  const game = structuredClone(fixtures.boardFixture().game);
  assert.equal(nextSavedParticipant(game), 'player-7');
  game.countries.find(country => country.owner_id === 'player-7').owner_id = 'player-0';
  assert.equal(nextSavedParticipant(game), 'player-1');
  game.current_turn = 9; assert.equal(nextSavedParticipant(game), null);
  for (const patch of [{ current_turn: -1 }, { countries: [] }, { turn_order: ['player-0'] }, { status: 'completed' }])
    assert.equal(nextSavedParticipant({ ...game, ...patch }), null);
});

test('phase wording maps supported phases without inventing transfer or confirmation state', () => {
  const game = fixtures.boardFixture().game;
  for (const [phase, text] of [['allocating','Deploy reinforcements'],['attacking','Battle underway'],
    ['post_attack','Transfer or end turn'],['deciding','Issue your orders'],['finished','Campaign complete']])
    assert.equal(phaseLabel({ ...game, phase }), text);
  assert.equal(phaseLabel({ ...game, phase: null }), 'Phase not recorded');
});

test('board presents one control slot and matching map, actions, roster, history DOM order', () => {
  const state = fixtures.boardFixture('human');
  const text = html(createElement(board.GameBoardContent, { game: state.game, owner: true, selectedId: null,
    onSelect() {}, actions: createElement('button', null, 'Single action slot'), history: createElement('div', null, 'History slot'), committed: state.events }));
  assert.equal((text.match(/Single action slot/g) || []).length, 1);
  assert.ok(text.indexOf('geo-game-map') < text.indexOf('id="game-actions"'));
  assert.ok(text.indexOf('id="game-actions"') < text.indexOf('id="countries-title"'));
  assert.ok(text.indexOf('id="countries-title"') < text.indexOf('geo-game-history'));
  assert.match(text, /href="#game-actions"/); assert.match(text, /href="#history-title"/);
  assert.match(text, /<details class="geo-turn-strip"><summary/);
  assert.match(text, /aria-valuenow="1"/);
});

test('snapshot display rendering has no network/audio effects and preserves all inputs', () => {
  const originalFetch = globalThis.fetch, state = battles.battleFixture('battle-many'), before = JSON.stringify(state);
  globalThis.fetch = () => { throw Error('No request permitted'); };
  try { renderLive(state); renderLive(state); assert.equal(JSON.stringify(state), before); }
  finally { globalThis.fetch = originalFetch; }
});
