import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { request } from 'node:http';
import { createElement, isValidElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { startComponentPreview } from '../scripts/preview-components.mjs';

let vite, app, board, atlas, controls, history, fixtures, ui;
before(async () => {
  vite = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false }, logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] } });
  [app, board, atlas, controls, history, fixtures, ui] = await Promise.all([
    vite.ssrLoadModule('/src/App.tsx'), vite.ssrLoadModule('/src/components/GameBoard.tsx'),
    vite.ssrLoadModule('/src/map/AtlasMap.tsx'), vite.ssrLoadModule('/src/components/Controls.tsx'),
    vite.ssrLoadModule('/src/components/History.tsx'), vite.ssrLoadModule('/src/dev/board-fixtures.ts'),
    vite.ssrLoadModule('/src/ui/components.tsx'),
  ]);
});
after(async () => { await vite?.close(); });
function* nodes(node) {
  if (Array.isArray(node)) { for (const child of node) yield* nodes(child); }
  else if (isValidElement(node)) {
    yield node; yield* nodes(node.props.children); yield* nodes(node.props.actions); yield* nodes(node.props.history);
  }
}
const calls = [];
const controller = {
  getSnapshot: () => currentState,
  api: { battleCommentary() { calls.push('commentary read'); return Promise.resolve(fixtures.fixtureNarration()); },
    generateBattleCommentary() { calls.push('commentary generate'); return Promise.resolve(fixtures.fixtureNarration()); },
    events() { calls.push('events'); return Promise.resolve({ events: [], has_more: false, after_revision: 12, next_after_revision: null }); } },
  act: action => calls.push(action), stepNpc: () => calls.push('step'), fastForward: () => calls.push('fast'),
  pause: () => calls.push('pause'), refresh: () => calls.push('refresh'), checkPendingNpc: () => calls.push('check'),
  retryPending: () => calls.push('retry'), logout: () => calls.push('logout'), moreHistory: () => calls.push('more'),
  authenticate: () => calls.push('authenticate'), initialize: () => calls.push('initialize'),
};
let currentState;
const tree = state => { currentState = state; return app.AppView({ state, controller, now: 0, origin: 'http://offline.invalid' }); };
const render = state => renderToStaticMarkup(tree(state));
const gameNodes = state => [...nodes(tree(state))];
const boardRender = game => renderToStaticMarkup(createElement(board.GameBoard, { game }));
const escaped = text => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#x27;');

test('real game-shaped state drives ten map countries and exactly one ten-country left roster', () => {
  const state = fixtures.boardFixture();
  const html = render(state);
  assert.equal((html.match(/data-map-country=/g) ?? []).length, 10);
  assert.equal((html.match(/data-roster-country=/g) ?? []).length, 10);
  assert.equal((html.match(/class="geo-atlas__roster"/g) ?? []).length, 1);
  for (const c of state.game.countries) {
    assert.ok(html.includes(escaped(c.name)));
    assert.ok(html.includes(`${c.soldiers} soldiers`));
    assert.ok(html.includes(escaped(`held by ${state.game.countries.find(home => home.id === state.game.players.find(p => p.id === c.owner_id).starting_country_id).name}`)));
  }
  assert.match(html, /geo-game-roster/); assert.match(html, /geo-game-map/);
  assert.match(html, /geo-game-actions/); assert.match(html, /geo-game-history/);
});

test('mock conquest updates map fragments and roster owner without changing country identity', () => {
  const original = fixtures.boardFixture().game;
  const conquered = { ...original, countries: original.countries.map(c => c.id === 'australia' ? { ...c, owner_id: 'player-0', soldiers: 999 } : c) };
  const p = board.boardPresentation(conquered, 'australia', () => {}).atlas;
  const paths = [...nodes(atlas.AtlasContent(p))].filter(e => e.type === 'path' && e.props['data-country'] === 'australia');
  assert.ok(paths.length > 1); assert.ok(paths.every(e => e.props.fill === 'var(--geo-forest)'));
  const html = boardRender(conquered);
  assert.match(html, /Australia, held by Brazil \(Human\), 999 soldiers/);
  assert.match(html, /Home participant: Australia \(NPC\)/);
  assert.ok(html.includes('Australia')); assert.equal(board.boardPresentation(conquered, null, () => {}).humanHeld, 2);
  assert.equal(board.boardPresentation(original, null, () => {}).humanHeld, 1);
});

test('turn strip uses saved randomized order and derives current, taken, upcoming and eliminated truthfully', () => {
  const game = fixtures.boardFixture('conquest').game;
  const html = boardRender(game);
  assert.deepEqual([...html.matchAll(/data-turn-player="([^"]+)"/g)].map(m => m[1]), game.turn_order);
  assert.match(html, /geo-turn--completed/); assert.match(html, /geo-turn--active/);
  assert.match(html, /geo-turn--upcoming/);
  const eliminated = html.match(/data-turn-player="player-1">([\s\S]*?)<\/li>/)[1];
  assert.match(eliminated, /geo-turn--eliminated/); assert.doesNotMatch(eliminated, /aria-current|Playing/);
  assert.match(html, /Round 2/);
});

test('human elimination keeps active match and owner NPC continuation controls', () => {
  const state = fixtures.boardFixture('eliminated'), html = render(state);
  assert.equal(state.game.status, 'active'); assert.match(html, /remaining NPCs can finish/);
  assert.match(html, /Advance one NPC action/); assert.doesNotMatch(html, /This game is complete/);
  assert.equal(board.boardPresentation(state.game, null, () => {}).humanHeld, 0);
});

test('spectators and other accounts see game/history without mutation or generation controls', () => {
  for (const state of [fixtures.boardFixture('spectator'), { ...fixtures.boardFixture(), owner: false }]) {
    const html = render(state);
    assert.match(html, /Spectator view/); assert.match(html, /data-map-country/); assert.match(html, /Committed history/);
    assert.doesNotMatch(html, /Start attack|Skip turn|Advance one NPC action|Generate commentary|Optional NPC acceptance limit/);
    const props = gameNodes(state).find(e => e.type === controls.GameplayControls).props;
    assert.equal(props.owner, false);
    const h = gameNodes(state).find(e => e.type === history.History).props;
    assert.equal(h.canGenerateCommentary, false); assert.equal(h.liveCommentaryAllowed, false);
  }
});

test('map and separately placed roster select exactly the same country and never call a service', () => {
  calls.length = 0;
  const state = fixtures.boardFixture(), selections = [];
  const onSelect = id => selections.push(id);
  const p = board.boardPresentation(state.game, 'australia', onSelect).atlas;
  const mapNodes = [...nodes(atlas.AtlasContent(p))], rosterNodes = [...nodes(atlas.AtlasRoster(p))];
  const button = mapNodes.find(e => e.props['data-map-country'] === 'australia');
  const row = rosterNodes.find(e => e.props['data-roster-country'] === 'australia');
  const soldier = [...nodes(row)].find(e => e.props.onSelect);
  button.props.onClick(); soldier.props.onSelect();
  assert.deepEqual(selections, ['australia', 'australia']); assert.deepEqual(calls, []);
  assert.equal(button.props['aria-pressed'], true); assert.equal(row.props['data-selected'], true);
});

test('active battle alone supplies FROM/TARGET and attack line; local inspection invents no attack', () => {
  const state = fixtures.boardFixture('attacking');
  const p = board.boardPresentation(state.game, 'singapore', () => {}).atlas;
  assert.deepEqual(p.battle, { source_id: 'brazil', target_id: 'canada', preview: false });
  assert.equal(p.fromId, 'brazil'); assert.equal(p.targetId, 'canada'); assert.equal(p.selectedId, 'singapore');
  const quiet = board.boardPresentation(fixtures.boardFixture().game, 'canada', () => {}).atlas;
  assert.equal(quiet.battle, null); assert.equal(quiet.targetId, undefined);
  assert.equal(board.boardPresentation({ ...state.game, status: 'completed', phase: 'finished' }, null, () => {}).atlas.battle, null);
  const capturedHome = fixtures.boardFixture('eliminated').game;
  capturedHome.countries.find(c => c.id === 'norway').owner_id = 'player-2';
  assert.equal(board.boardPresentation(capturedHome, null, () => {}).atlas.playingId, undefined);
});

test('existing owner action callbacks, revision key and Pause semantics survive shell composition', () => {
  calls.length = 0;
  const state = fixtures.boardFixture('npc'); state.fastForward = true; state.busy = true;
  const node = gameNodes(state).find(e => e.type === controls.GameplayControls);
  assert.equal(node.key, `${state.gameId}:${state.game.revision}`); assert.equal(node.props.owner, true); assert.equal(node.props.disabled, true);
  const buttons = [...nodes(controls.GameplayControls(node.props))].filter(e => e.type === 'button' || e.type === ui.Button);
  assert.equal(buttons[0].props.disabled, true); assert.equal(buttons[1].props.disabled, true);
  const pause = buttons.find(e => e.props.children === 'Pause NPC fast-forward');
  assert.equal(pause.props.disabled, undefined); pause.props.onClick(); assert.deepEqual(calls, ['pause']);
  node.props.act({ type: 'roll' }); node.props.step(); node.props.fast();
  assert.deepEqual(calls, ['pause', { type: 'roll' }, 'step', 'fast']);
});

test('uncertain NPC recovery stays visible, locks moves, hides home and preserves explicit read-only confirmation', () => {
  calls.length = 0;
  const state = fixtures.boardFixture('pending'), html = render(state);
  assert.match(html, /Unresolved request/); assert.match(html, /Original account: offline_fixture_owner/);
  assert.match(html, /expected revision 12/); assert.doesNotMatch(html, /My Games \/ Home/);
  assert.equal(gameNodes(state).find(e => e.type === controls.GameplayControls).props.disabled, true);
  const buttons = gameNodes(state).filter(e => e.type === 'button');
  buttons.find(e => e.props.children === 'Check committed outcome (read only)').props.onClick();
  assert.deepEqual(calls, ['check']);
  state.npcAttempts = 3;
  assert.equal(gameNodes(state).find(e => e.type === 'button' && e.props.children === 'Retry saved request').props.disabled, true);
  state.session = { user: { id: 'another-account', username: 'different-fixture' } };
  assert.equal(gameNodes(state).find(e => e.type === 'button' && e.props.children === 'Retry saved request').props.disabled, true);
  assert.match(render(state), /Log in to recover the saved request/);
  assert.equal(state.pending.operation.command.expected_revision, 12);
});

test('History is mounted once with stable account key and original live-commentary permissions', () => {
  const state = fixtures.boardFixture(), list = gameNodes(state);
  assert.equal(list.filter(e => e.type === history.History).length, 1);
  const node = list.find(e => e.type === history.History);
  assert.equal(node.key, `${state.gameId}:${state.session.user.id}`);
  assert.equal(node.props.api, controller.api); assert.equal(node.props.events, state.events);
  assert.equal(node.props.liveCommentaryAllowed, true); assert.equal(node.props.canStartCommentary(), true);
  currentState = { ...state, pending: fixtures.boardFixture('pending').pending };
  assert.equal(node.props.canStartCommentary(), false);
  const html = render(state);
  assert.equal((html.match(/id="history-title"/g) ?? []).length, 1);
  assert.equal((html.match(/aria-label="Commentary for move 12"/g) ?? []).length, 1);
  assert.match(html, /Synthetic fixture explanation/); assert.match(html, /Attacker dice: 6, 2/);
  assert.match(html, /Defender dice: 1, 5/); assert.match(html, /Attacker losses: 1/);
});

test('loading/error/background refresh preserve truthful last-known board without new requests', () => {
  calls.length = 0;
  assert.match(render(fixtures.boardFixture('loading')), /Restoring session/);
  const state = fixtures.boardFixture('refresh-error'); state.refreshing = true;
  const html = render(state);
  assert.match(html, /Updating game/); assert.match(html, /Game update failed/);
  assert.equal((html.match(/data-map-country=/g) ?? []).length, 10);
  assert.equal(gameNodes(state).find(e => e.type === controls.GameplayControls).props.disabled, false);
  assert.deepEqual(calls, []);
  state.game = null;
  assert.match(render(state), /No game data is available/);
});

test('legacy/missing/unknown country identities fail gracefully and never fabricate an atlas or turn', () => {
  const legacy = fixtures.boardFixture('legacy');
  const html = render(legacy);
  assert.match(html, /atlas is unavailable/); assert.match(html, /No country records/);
  assert.doesNotMatch(html, /data-map-country=|geo-turn--active|geo-turn--completed/);
  const bad = fixtures.boardFixture().game;
  bad.countries[0].id = 'unknown-country';
  assert.equal(board.boardPresentation(bad, null, () => {}).atlasAvailable, false);
  assert.match(boardRender(bad), /Available country records/);
  const partial = { ...fixtures.boardFixture().game, countries: fixtures.boardFixture().game.countries.slice(0, 1) };
  assert.equal(board.boardPresentation(partial, null, () => {}).humanHeld, null);
  assert.doesNotMatch(boardRender(partial), /geo-turn--eliminated|geo-turn--completed/);
});

test('reinforcement, conquest and completed variants reuse the existing legal phase controls', () => {
  assert.match(render(fixtures.boardFixture('allocating')), /Allocate 4 reinforcements/);
  const conquest = render(fixtures.boardFixture('conquest'));
  assert.match(conquest, /Transfer soldiers/); assert.match(conquest, /End turn/);
  assert.doesNotMatch(conquest, /Confirm conquest|Start attack/);
  const done = render(fixtures.boardFixture('completed'));
  assert.match(done, /This game is complete/); assert.match(done, /Winner/);
  assert.doesNotMatch(done, /Advance one NPC action|Skip turn|aria-current="step"/);
});

test('SSR presentation and selection perform zero fetches and preserve supplied state', () => {
  const state = fixtures.boardFixture(), original = JSON.stringify(state), fetch = globalThis.fetch;
  let requests = 0; globalThis.fetch = () => { requests++; throw new Error('No services permitted'); };
  try { render(state); assert.equal(requests, 0); assert.equal(JSON.stringify(state), original); }
  finally { globalThis.fetch = fetch; }
});

test('responsive shell keeps one stateful actions/history instance and scrolls atlas independently', async () => {
  const css = await readFile(new URL('../src/components/game-shell.css', import.meta.url), 'utf8');
  assert.match(css, /max-width: 1100px/); assert.match(css, /max-width: 600px/);
  assert.match(css, /grid-template-areas: 'map' 'actions' 'roster' 'history'/);
  assert.match(css, /minmax\(0, 1fr\)/); assert.match(css, /min-block-size: 44px/);
  assert.match(css, /outline: 3px solid var\(--geo-ink\); outline-offset: 2px/);
  assert.match(css, /prefers-reduced-motion/);
  assert.doesNotMatch(css, /position: fixed|overflow: hidden|display: none/);
  const source = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.match(source, /if \(state.pending\) window.addEventListener\('beforeunload'/);
  assert.equal((source.match(/<GameplayControls\b/g) ?? []).length, 1);
  assert.equal((source.match(/<History\b/g) ?? []).length, 1);
  assert.equal((source.match(/controller\.poll\(\)/g) ?? []).length, 1);
});

function local(port, path, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = request({ hostname: '127.0.0.1', port, path, method }, res => {
      let body = ''; res.setEncoding('utf8'); res.on('data', c => body += c);
      res.on('end', () => resolve({ status: res.statusCode, body }));
    }); req.on('error', reject); req.end();
  });
}
test('board preview serves isolated canonical fixtures and refuses API/POST requests', async t => {
  const preview = await startComponentPreview({ port: 0, board: true }); t.after(() => preview.close());
  const port = preview.server.address().port;
  const page = await local(port, '/'); assert.equal(page.status, 200);
  assert.match(page.body, /Stage 4 board preview/); assert.match(page.body, /src\/dev\/BoardPreview/);
  assert.doesNotMatch(page.body, /fonts\.google/);
  const component = await local(port, '/src/dev/BoardPreview.tsx'); assert.equal(component.status, 200);
  assert.match(component.body, /isolated development fixtures only/);
  for (const [path, method] of [['/api/countries','GET'], ['/api/games/fixture/npc-steps','POST'], ['/','POST']])
    assert.equal((await local(port, path, method)).status, 404);
  const entry = await readFile(new URL('../src/main.tsx', import.meta.url), 'utf8');
  const appSource = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(entry + appSource, /board-fixtures|BoardPreview/);
});
