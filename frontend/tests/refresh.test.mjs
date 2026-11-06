import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement, isValidElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { synchronization, npcActivity, participantCountryName } from '../src/components/refresh-view.ts';

let vite, app, fixtures, history, sound;
before(async () => {
  vite = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false }, logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] } });
  [app, fixtures, history, sound] = await Promise.all(['/src/App.tsx', '/src/dev/board-fixtures.ts',
    '/src/components/History.tsx', '/src/sound/SoundSettings.tsx'].map(path => vite.ssrLoadModule(path)));
});
after(async () => { await vite?.close(); });
const html = element => renderToStaticMarkup(element);
function* nodes(node) {
  if (Array.isArray(node)) { for (const child of node) yield* nodes(child); }
  else if (isValidElement(node)) { yield node; yield* nodes(node.props.children); }
}
function composition(mode, extra = {}) {
  const state = { ...fixtures.boardFixture(mode), notice: null, ...extra }, calls = [];
  const controller = { api: {}, getSnapshot: () => state, refresh: () => calls.push('refresh'),
    checkPendingNpc: () => calls.push('confirm'), retryPending: () => calls.push('retry') };
  return { state, calls, tree: app.AppView({ state, controller, now: 0, origin: 'http://offline.invalid' }) };
}

test('sync distinguishes settled, refresh, restoration, errors and uncertain submitted moves', () => {
  const idle = { ready: true, busy: false, refreshing: false, refreshError: null, error: null, pending: null, confirmingPending: false };
  assert.equal(synchronization(idle).tone, 'idle');
  for (const patch of [{ refreshing: true }, { busy: true }, { ready: false }, { confirmingPending: true }])
    assert.equal(synchronization({ ...idle, ...patch }).tone, 'refreshing');
  for (const patch of [{ error: 'failure' }, { refreshError: 'delayed' }, { pending: {} }])
    assert.equal(synchronization({ ...idle, ...patch }).tone, 'problem');
  const { tree } = composition('human', { refreshing: true });
  assert.match(html(tree), /class="geo-sync-indicator" data-state="refreshing" role="status" tabindex="0"/);
  assert.match(html(tree), /Updating game/);
  assert.doesNotMatch(html(tree), /class="geo-recovery"/);
});

test('pending recovery still invokes only explicit read-only confirmation and identical saved retry', () => {
  const { tree, calls } = composition('pending');
  const buttons = [...nodes(tree)].filter(n => n.type === 'button');
  buttons.find(n => n.props.children === 'Check committed outcome (read only)').props.onClick();
  assert.deepEqual(calls, ['confirm']);
  buttons.find(n => n.props.children === 'Retry saved request').props.onClick();
  assert.deepEqual(calls, ['confirm', 'retry']);
  const text = html(tree);
  for (const copy of ['Confirming your move', 'New moves are locked', 'do not reload', 'expected revision 12', 'Saved request details']) assert.ok(text.includes(copy));
  assert.doesNotMatch(text, /My Games \/ Home/);
});

test('routine status remains available in a secondary disclosure; failed refresh exposes it', () => {
  const settled = composition('human');
  assert.match(html(settled.tree), /<details class="geo-sync-tools"><summary>Game status/);
  [...nodes(settled.tree)].find(n => n.type === 'button' && n.props.children === 'Check game status').props.onClick();
  assert.deepEqual(settled.calls, ['refresh']);
  assert.match(html(composition('refresh-error').tree), /class="geo-sync-tools" open=""/);
});

test('spectator login reuses existing auth and registration, while landing is not labelled spectator', () => {
  const text = html(composition('spectator').tree);
  assert.match(text, /id="spectator-title">Spectator view/);
  assert.match(text, /Explore the world, follow battles and watch decisions unfold/);
  assert.match(text, /Log in to play/); assert.match(text, /Create an account/);
  assert.doesNotMatch(text, /Step · Advance one rival move|Launch attack|Generate commentary/);
  const landing = html(composition('human', { gameId: null, game: null, session: null }).tree);
  assert.doesNotMatch(landing, /id="spectator-title"/); assert.match(landing, /current-password/);
});

test('NPC copy uses original participant identity after home ownership changes, with truthful phase wording', () => {
  const game = structuredClone(fixtures.boardFixture('npc').game);
  game.countries.find(c => c.id === 'norway').owner_id = 'player-0';
  assert.equal(participantCountryName(game, 'player-3'), 'Norway');
  for (const [phase, text] of [['allocating', 'preparing its forces'], ['attacking', 'at war'],
    ['post_attack', 'concluding its turn'], ['deciding', 'making its next move'], [undefined, 'making its next move']]) {
    game.phase = phase; assert.equal(npcActivity(game, 'player-3'), `Norway is ${text}.`);
  }
  assert.equal(participantCountryName(game, 'missing'), 'Participant');
});

test('saved perspective preserves escaped full explanation and receipt actor identity', () => {
  const { state } = composition('npc');
  state.events[0].npc_decision.explanation = '<script>Saved technical reasoning</script>';
  state.game.countries.find(c => c.id === 'norway').owner_id = 'player-0';
  const text = html(createElement(history.History, { game: state.game, events: state.events, latest: null, more: false,
    disabled: false, loadMore() {}, api: {}, gameId: state.gameId, canGenerateCommentary: false,
    commentaryAccountId: null, liveCommentaryAllowed: false, canStartCommentary: () => false }));
  assert.match(text, /Norway’s Strategy/); assert.match(text, /class="geo-saved-justification"/);
  assert.doesNotMatch(text, /<summary>View detailed reasoning/);
  assert.match(text, /&lt;script&gt;Saved technical reasoning&lt;\/script&gt;/);
  assert.doesNotMatch(text, /NPC Strategy|<script>/);
});

test('sound icon starts muted and exposes named pressed state and volume disclosure', () => {
  const text = html(createElement(sound.SoundSettings));
  assert.match(text, /aria-pressed="false" aria-label="Sound off. Enable sound"/);
  assert.match(text, /title="Sound off. Enable sound"/);
  assert.match(text, /Sound settings/); assert.match(text, /Effects volume/);
  assert.match(text, /type="range" min="0" max="100" step="1" value="35"/);
});

test('roster removes only redundant home labels and retains original participant after conquest', () => {
  const ordinary = html(composition('human').tree);
  assert.match(ordinary, /Any rival country can be attacked regardless of distance/);
  assert.doesNotMatch(ordinary, /Home participant: Norway \(Rival\)/);
  const { state } = composition('human');
  state.game.countries.find(country => country.id === 'norway').owner_id = 'player-0';
  const conquered = html(app.AppView({ state, controller: { api: {} }, now: 0, origin: 'http://offline.invalid' }));
  assert.match(conquered, /Home participant: Norway \(Rival\)/);
  assert.match(conquered, /Norway, held by Brazil \(Human\), 13 soldiers/);
});
