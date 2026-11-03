import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createElement, isValidElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { chronicleEntries, chronicleWindow, receiptRound, receiptTime } from '../src/components/chronicle-view.ts';

let vite, history, app, controls, fixtures, chronicle;
before(async () => {
  vite = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false }, logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] } });
  [history, app, controls, fixtures, chronicle] = await Promise.all([
    '/src/components/History.tsx', '/src/App.tsx', '/src/components/Controls.tsx', '/src/dev/board-fixtures.ts', '/src/dev/chronicle-fixtures.ts',
  ].map(path => vite.ssrLoadModule(path)));
});
after(async () => { await vite?.close(); });
const html = element => renderToStaticMarkup(element);
function* nodes(node) {
  if (Array.isArray(node)) { for (const child of node) yield* nodes(child); }
  else if (isValidElement(node)) { yield node; yield* nodes(node.props.children); yield* nodes(node.props.actions); yield* nodes(node.props.history); }
}
function renderHistory(state) {
  return html(createElement(history.History, { game: state.game, events: state.events, latest: state.lastResult,
    more: state.moreEvents, disabled: false, loadMore() { throw Error('No reads during render'); },
    api: { generateBattleCommentary() { throw Error('No generation'); }, events() { throw Error('No rendering fetch'); } },
    gameId: state.gameId, canGenerateCommentary: false, commentaryAccountId: null, liveCommentaryAllowed: false, canStartCommentary: () => false }));
}
test('Chronicle merges live and committed receipts once, prefers committed facts and keeps inputs unchanged', () => {
  const entry = fixtures.boardFixture().events[0], original = JSON.stringify(entry);
  const entries = chronicleEntries([entry], [{ ...entry, action_id: 'unpreferred-live-copy' }, { ...entry, revision: 13, action_id: 'new-live-entry' }]);
  assert.deepEqual(entries.map(e => e.revision), [13, 12]); assert.equal(entries[1], entry); assert.equal(JSON.stringify(entry), original);
});
test('history windows bound the DOM to 20 receipts and expose every loaded record without network calls', () => {
  const entries = chronicleEntries(chronicle.chronicleFixture('chronicle-many').events, []);
  const seen = [];
  for (let page = 0; page <= chronicleWindow(entries, 0).last; page++) {
    const window = chronicleWindow(entries, page); assert.ok(window.entries.length <= 20); seen.push(...window.entries);
  }
  assert.equal(seen.length, 126); assert.equal(new Set(seen.map(e => e.revision)).size, 126);
  assert.equal(chronicleWindow(entries, 999).page, 6); assert.equal(chronicleWindow([], 5).page, 0);
});
test('large Chronicle renders only one expanded battle and defers historical detail reads', () => {
  const result = renderHistory(chronicle.chronicleFixture('chronicle-many'));
  assert.equal((result.match(/data-receipt=/g) || []).length, 20);
  assert.equal((result.match(/class="geo-battle"/g) || []).length, 1);
  assert.equal((result.match(/aria-label="Commentary for move/g) || []).length, 1);
  assert.match(result, /Earlier loaded moves/); assert.doesNotMatch(result, /Latest submitted move|Load more history/);
});
test('latest returned move is not duplicated once its committed receipt is present', () => {
  const state = fixtures.boardFixture(); state.lastResult = { state: state.game, events: state.events[0].events };
  const result = renderHistory(state);
  assert.doesNotMatch(result, /Latest submitted move/); assert.equal((result.match(/data-pair=/g) || []).length, 2);
  state.lastResult = { ...state.lastResult, state: { ...state.game, revision: 13 } };
  assert.match(renderHistory(state), /Latest submitted move/);
});
test('saved reasoning stays distinct and escaped, while missing historical facts are not fabricated', () => {
  const state = fixtures.boardFixture(); state.events[0].npc_decision.explanation = '<script>unsafe</script>';
  const result = renderHistory(state);
  assert.match(result, /Recorded NPC reasoning/); assert.match(result, /&lt;script&gt;unsafe/); assert.doesNotMatch(result, /<script>/);
  const partial = renderHistory(chronicle.chronicleFixture('chronicle-missing'));
  assert.doesNotMatch(partial, /<time|Recorded NPC reasoning/); assert.match(partial, /not recorded/);
  assert.equal(receiptTime(''), null); assert.equal(receiptTime('unknown'), null);
  assert.equal(receiptTime('2026-11-02T00:00:00Z'), '2026-11-02 00:00:00 UTC');
  assert.equal(receiptRound({ events: [] }), null);
});
test('Chronicle collapse uses native accessible state without unmounting the live narration owner', async () => {
  const result = renderHistory(fixtures.boardFixture());
  assert.match(result, /aria-expanded="true" aria-controls="chronicle-content"/);
  assert.match(result, /Collapse Chronicle/); assert.match(result, /Committed moves, latest first/);
  const source = await readFile(new URL('../src/components/History.tsx', import.meta.url), 'utf8');
  assert.match(source, /id="chronicle-content" hidden=\{collapsed\}/);
  assert.match(source, /if \(expanded\) setVisited\(true\)/);
  assert.doesNotMatch(source, /setVisited\(false\)|new GameController|setInterval|setTimeout/);
});
test('normal App composition exposes no acceptance configuration but retains configured-limit locks', () => {
  const state = fixtures.boardFixture('pending'); state.npcAttempts = state.npcAttemptBudget;
  const controller = { getSnapshot: () => state, api: {} };
  const tree = app.AppView({ state, controller, now: 0, origin: 'https://example.invalid' });
  const result = html(tree); assert.doesNotMatch(result, /Optional NPC acceptance limit|name="npc_limit"|Set limit/);
  const list = [...nodes(tree)];
  assert.equal(list.find(n => n.type === 'button' && n.props.children === 'Retry saved request').props.disabled, true);
  assert.equal(list.find(n => n.type === 'button' && n.props.children === 'Check committed outcome (read only)').props.disabled, false);
  assert.equal(list.find(n => n.type === controls.GameplayControls).props.npcLimitReached, true);
});
test('exhausted cap disables Step/Fast-forward handlers while Pause still invokes only the existing callback', () => {
  const calls = [], state = fixtures.boardFixture('npc');
  const element = controls.GameplayControls({ game: state.game, owner: true, disabled: false, fastForward: true,
    npcLimitReached: true, step: () => calls.push('step'), fast: () => calls.push('fast'), pause: () => calls.push('pause'), act() {} });
  const buttons = [...nodes(element)].filter(n => typeof n.props.onClick === 'function');
  buttons.forEach(button => button.props.onClick()); assert.deepEqual(calls, ['pause']);
  assert.match(html(element), /already submitted action may still finish/);
});
test('pending recovery prioritizes public confirmation and retains same-account login without auto replay', () => {
  const state = chronicle.chronicleFixture('recovery-login'), calls = [];
  const tree = app.AppView({ state, controller: { api: {}, checkPendingNpc: () => calls.push('read'), retryPending: () => calls.push('retry') }, now: 0, origin: 'https://example.invalid' });
  const buttons = [...nodes(tree)].filter(n => n.type === 'button');
  buttons.find(n => n.props.children === 'Check committed outcome (read only)').props.onClick();
  assert.deepEqual(calls, ['read']); assert.equal(buttons.find(n => n.props.children === 'Retry saved request').props.disabled, true);
  const result = html(tree); assert.match(result, /Signing in does not automatically retry/); assert.match(result, /do not reload/);
});
test('quiet synchronization retains ten-country board and foreground refresh handler independently of background reads', () => {
  const state = fixtures.boardFixture(); state.refreshing = true; const calls = [];
  const tree = app.AppView({ state, controller: { api: {}, refresh: () => calls.push('refresh') }, now: 0, origin: 'https://example.invalid' });
  const button = [...nodes(tree)].find(n => n.type === 'button' && n.props.children === 'Check game status');
  assert.equal(button.props.disabled, false); button.props.onClick(); assert.deepEqual(calls, ['refresh']);
  const result = html(tree); assert.match(result, /Updating game/); assert.equal((result.match(/data-map-country=/g) || []).length, 10);
});
test('production entry graph excludes developer preview/configuration and adds no request scheduler', async () => {
  const files = await Promise.all(['main.tsx','App.tsx','components/History.tsx','components/Controls.tsx'].map(p => readFile(new URL(`../src/${p}`, import.meta.url), 'utf8')));
  assert.doesNotMatch(files.join('\n'), /from ['"][^'"]*(?:dev\/|fixtures|NpcAcceptanceTools)/);
  assert.doesNotMatch(files[1], /configureNpcBudget/);
  assert.equal((files[1].match(/new GameController/g) || []).length, 1);
  assert.equal((files[1].match(/controller\.poll\(\)/g) || []).length, 1);
  assert.equal((files[2].match(/new NewBattleCommentary/g) || []).length, 1);
  const css = await readFile(new URL('../src/components/chronicle.css', import.meta.url), 'utf8');
  assert.match(css, /prefers-reduced-motion/); assert.match(css, /max-width: 600px/);
});
