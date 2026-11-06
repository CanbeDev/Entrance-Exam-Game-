import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement, isValidElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { readFile } from 'node:fs/promises';
import { GameApi } from '../src/api/index.ts';
import { GameController } from '../src/game/controller.ts';
import { createMockApi, fixtureUser, fixturePassword } from './mock-api.mjs';
let vite, controls, ui, fixtures, app;
before(async () => {
  vite = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false }, logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] } });
  [controls, ui, fixtures, app] = await Promise.all(['/src/components/Controls.tsx', '/src/ui/components.tsx',
    '/src/dev/board-fixtures.ts', '/src/App.tsx'].map(path => vite.ssrLoadModule(path)));
});
after(async () => { await vite?.close(); });
function* nodes(node) {
  if (Array.isArray(node)) { for (const child of node) yield* nodes(child); }
  else if (isValidElement(node)) { yield node; yield* nodes(node.props.children); }
}
const event = () => ({ preventDefault() {} });
const render = element => renderToStaticMarkup(element);
function human(mode = 'human', patch = {}, extra = {}) {
  const state = fixtures.boardFixture(mode), commands = [], drafts = [];
  const draft = { ...controls.emptyControlDraft(), ...patch };
  const props = { game: state.game, latest: state.lastResult, disabled: false, act: action => commands.push(action),
    draft, onDraft: next => drafts.push(next), ...extra };
  const element = controls.HumanControlsView(props), list = [...nodes(element)];
  return { state, props, element, list, commands, drafts,
    button: label => list.find(e => e.type === ui.Button && e.props.children === label),
    submit: index => list.filter(e => e.type === 'form')[index ?? 0].props.onSubmit(event()) };
}
function npc(mode = 'npc', extra = {}) {
  const state = fixtures.boardFixture(mode), calls = [];
  const props = { game: state.game, owner: state.owner, disabled: state.busy || !!state.pending || state.fastForward,
    pending: !!state.pending, busy: state.busy, fastForward: state.fastForward,
    act: action => calls.push(action), step: () => calls.push('step'), fast: () => calls.push('fast'), pause: () => calls.push('pause'), ...extra };
  const element = controls.GameplayControls(props);
  return { props, element, calls, buttons: [...nodes(element)].filter(e => e.type === ui.Button) };
}
const primaries = list => list.filter(e => e.type === ui.Button && (e.props.variant ?? 'primary') === 'primary');

test('human has exactly one primary, explicit empty choices and legal source/enemy options', () => {
  const h = human(); assert.equal(primaries(h.list).length, 1);
  assert.equal(h.button('Launch attack').props.disabled, true);
  const selects = h.list.filter(e => e.type === 'select');
  assert.equal(selects[0].props.value, ''); assert.equal(selects[1].props.value, '');
  const sourceOptions = [...nodes(selects[0])].filter(e => e.type === 'option' && e.props.value);
  const targets = [...nodes(selects[1])].filter(e => e.type === 'option' && e.props.value);
  assert.deepEqual(sourceOptions.map(e => e.props.value), ['brazil']);
  assert.equal(targets.length, 9); assert.ok(targets.every(e => e.props.value !== 'brazil'));
  selects[0].props.onChange({ target: { value: 'brazil' } });
  assert.equal(h.drafts[0].sourceId, 'brazil'); assert.deepEqual(h.commands, []);
});

test('attacker then target selection changes only the local draft and enables one explicit attack', () => {
  const attacker = human('human', { sourceId: 'brazil' });
  assert.equal(attacker.button('Launch attack').props.disabled, true);
  assert.match(render(attacker.element), /Choose a rival target/);
  const select = attacker.list.find(e => e.type === 'select' && e.props.name === 'target');
  select.props.onChange({ target: { value: 'singapore' } }); assert.deepEqual(attacker.commands, []);
  const selected = human('human', attacker.drafts[0]);
  assert.equal(selected.button('Launch attack').props.disabled, false); selected.submit();
  assert.deepEqual(selected.commands, [{ type: 'start_attack', source_id: 'brazil', target_id: 'singapore' }]);
});

test('invalid, owned, missing and one-soldier attack choices never submit commands', () => {
  for (const [mode, draft] of [['human', { sourceId: 'canada', targetId: 'brazil' }],
    ['human', { sourceId: 'brazil', targetId: 'brazil' }], ['human', { sourceId: 'brazil', targetId: 'missing' }],
    ['no-attack-source', { sourceId: 'brazil', targetId: 'canada' }]]) {
    const h = human(mode, draft); h.submit(); assert.deepEqual(h.commands, []); assert.equal(h.button('Launch attack').props.disabled, true);
  }
});

test('busy/uncertain/disabled human commands and input updates are inert', () => {
  const h = human('human', { sourceId: 'brazil', targetId: 'canada' }, { disabled: true, disabledReason: 'Resolve saved request.' });
  h.submit(); h.button('Skip turn').props.onClick();
  h.list.find(e => e.type === 'select').props.onChange({ target: { value: 'brazil' } });
  assert.deepEqual(h.commands, []); assert.deepEqual(h.drafts, []);
  assert.match(render(h.element), /Resolve saved request/);
});

test('attack phase preserves exact roll/stop commands, locked pair and uncapped textual dice preview', () => {
  const h = human('attacking');
  assert.equal(primaries(h.list).length, 1); assert.equal(h.button('Roll battle dice').props.disabled, false);
  h.button('Roll battle dice').props.onClick(); h.button('End assault and turn').props.onClick();
  assert.deepEqual(h.commands, [{ type: 'roll' }, { type: 'stop_attack' }]);
  assert.match(render(h.element), /Next exchange: 9 dice each side/);
  assert.doesNotMatch(render(h.element), /Choose an attacking country|Transfer forces<\/button>/);
  const missing = human('attacking', {}, { game: { ...h.state.game, battle: null } });
  assert.equal(missing.button('Roll battle dice').props.disabled, true);
  missing.button('Roll battle dice').props.onClick(); assert.deepEqual(missing.commands, []);
});

test('local transfer view uses one primary and preserves positive owned-source bounds and exact payload', () => {
  const h = human('conquest', { mode: 'transfer', transferSourceId: 'brazil', transferTargetId: 'canada', amount: 9 });
  assert.equal(primaries(h.list).length, 1);
  const stepper = h.list.find(e => e.type === ui.NumericStepper);
  assert.equal(stepper.props.min, 1); assert.equal(stepper.props.max, 9); assert.equal(stepper.props.value, 9);
  h.submit(); assert.deepEqual(h.commands, [{ type: 'transfer', source_id: 'brazil', target_id: 'canada', amount: 9 }]);
  h.button('End turn').props.onClick(); assert.deepEqual(h.commands.at(-1), { type: 'end_turn' });
  assert.match(render(h.element), /Conquest reward: 2 soldiers added/);
  assert.match(render(h.element), /separate from any optional transfer/);
});

test('same-country, enemy, zero and excessive transfers are non-destructive', () => {
  for (const draft of [{ transferTargetId: 'brazil', amount: 1 }, { transferTargetId: 'uk', amount: 1 },
    { transferTargetId: 'canada', amount: 0 }, { transferTargetId: 'canada', amount: 10 }]) {
    const h = human('conquest', { mode: 'transfer', transferSourceId: 'brazil', ...draft });
    h.submit(); assert.deepEqual(h.commands, []); assert.equal(h.button('Transfer forces').props.disabled, true);
  }
});

test('transfer navigation is local and choosing a smaller source safely clamps the draft amount', () => {
  const h = human('conquest'); h.button('Transfer forces').props.onClick();
  assert.equal(h.drafts[0].mode, 'transfer'); assert.deepEqual(h.commands, []);
  const transfer = human('conquest', { mode: 'transfer', transferSourceId: 'canada', transferTargetId: 'brazil', amount: 10 });
  transfer.list.filter(e => e.type === 'select')[0].props.onChange({ target: { value: 'brazil' } });
  assert.equal(transfer.drafts[0].amount, 9); assert.equal(transfer.drafts[0].transferTargetId, '');
  transfer.button('Back to end turn').props.onClick(); assert.deepEqual(transfer.commands, []);
});

test('post-attack exposes end-turn, optional transfer and no new attack or conquest confirmation', () => {
  for (const mode of ['conquest', 'failed-attack']) {
    const h = human(mode); assert.equal(primaries(h.list).length, 1);
    assert.ok(h.button('End turn')); assert.equal(h.button('Launch attack'), undefined);
    h.button('End turn').props.onClick(); assert.deepEqual(h.commands, [{ type: 'end_turn' }]);
    assert.doesNotMatch(render(h.element), /Confirm conquest/);
    if (mode === 'failed-attack') assert.doesNotMatch(render(h.element), /was conquered/);
  }
});

test('reinforcement uses supplied pool, exact allocation payload and no competing award calculation', () => {
  const h = human('allocating', { allocations: { brazil: 1, canada: 3 } });
  assert.equal(primaries(h.list).length, 1); assert.equal(h.button('Deploy reinforcements').props.disabled, false);
  h.submit(); assert.deepEqual(h.commands, [{ type: 'allocate', allocations: [{ country_id: 'brazil', amount: 1 }, { country_id: 'canada', amount: 3 }] }]);
  assert.match(render(h.element), /0 remaining/);
  assert.ok(h.list.filter(e => e.type === ui.NumericStepper).every(e => e.props.max === 4));
  const serverPool = human('allocating', { allocations: { brazil: 7 } }, { game: { ...h.state.game, pending_reinforcements: 7 } });
  serverPool.submit(); assert.deepEqual(serverPool.commands, [{ type: 'allocate', allocations: [{ country_id: 'brazil', amount: 7 }] }]);
});

test('incomplete, over-budget, fractional or missing reinforcement values cannot submit', () => {
  for (const allocations of [{}, { brazil: 3 }, { brazil: 5 }, { brazil: 1.5, canada: 2.5 }, { brazil: -1, canada: 5 }]) {
    const h = human('allocating', { allocations }); h.submit(); assert.deepEqual(h.commands, []);
    assert.equal(h.button('Deploy reinforcements').props.disabled, true);
  }
  assert.match(render(human('missing-budget').element), /budget is not available/);
  const state = fixtures.boardFixture('allocating');
  assert.match(render(human('allocating', {}, { game: { ...state.game, round: 1 } }).element), /round-two-or-later/);
});

test('NPC Step and Fast-forward call the existing callbacks once, while Pause remains enabled in flight', () => {
  const ready = npc(); assert.equal(primaries([...nodes(ready.element)]).length, 1);
  ready.buttons.find(b => b.props.children === 'Step · Advance one rival move').props.onClick();
  ready.buttons.find(b => b.props.children === 'Fast-forward rivals').props.onClick(); assert.deepEqual(ready.calls, ['step', 'fast']);
  const running = npc('npc-in-flight');
  assert.equal(primaries([...nodes(running.element)]).length, 1);
  running.buttons.find(b => b.props.children === 'Step · Advance one rival move').props.onClick();
  running.buttons.find(b => b.props.children === 'Fast-forward rivals').props.onClick();
  const pause = running.buttons.find(b => b.props.children === 'Pause rival turns');
  assert.equal(pause.props.disabled, undefined); pause.props.onClick(); assert.deepEqual(running.calls, ['pause']);
  assert.match(render(running.element), /already submitted action may still finish/);
});

test('spectator, eliminated, finished and incomplete variants have truthful availability', () => {
  const spectator = npc('spectator'); assert.equal(spectator.buttons.length, 0);
  assert.match(render(spectator.element), /Spectator view/);
  const eliminated = npc('eliminated'); assert.equal(eliminated.buttons.length, 2);
  assert.match(render(eliminated.element), /game is still active/);
  const complete = npc('completed'); assert.equal(complete.buttons.length, 0); assert.match(render(complete.element), /Winner/);
  for (const game of [{ game_name: 'Legacy' }, { ...fixtures.boardFixture().game, countries: [] },
    { ...fixtures.boardFixture().game, turn_order: [] }]) {
    const incomplete = npc('human', { game }); assert.equal(incomplete.buttons.length, 0);
    assert.match(render(incomplete.element), /viewing only/);
  }
});

test('unresolved requests retain original App recovery buttons and prevent replacement NPC actions', () => {
  const p = npc('pending'); p.buttons.forEach(b => b.props.onClick()); assert.deepEqual(p.calls, []);
  assert.match(render(p.element), /New moves are locked/);
  const state = fixtures.boardFixture('pending');
  const stub = { api: {}, getSnapshot: () => state, checkPendingNpc() {}, retryPending() {}, configureNpcBudget() {} };
  const html = render(app.AppView({ state, controller: stub, now: 0, origin: 'http://offline.invalid' }));
  assert.match(html, /Check committed outcome \(read only\)/); assert.match(html, /Retry saved request/);
  assert.match(html, /expected revision 12/); assert.doesNotMatch(html, /My Games \/ Home/);
});

test('rendering and local selection never call fetch or mutate the supplied game', () => {
  const fetch = globalThis.fetch; let requests = 0;
  globalThis.fetch = () => { requests++; throw new Error('No request permitted'); };
  try {
    const h = human(), before = JSON.stringify(h.state.game); render(h.element);
    h.list.find(e => e.type === 'select').props.onChange({ target: { value: 'brazil' } });
    assert.deepEqual(h.commands, []); assert.equal(requests, 0); assert.equal(JSON.stringify(h.state.game), before);
  } finally { globalThis.fetch = fetch; }
});

test('rapid panel submissions produce one POST through the unchanged controller mutation lock', async () => {
  const mock = createMockApi();
  const controller = new GameController(new GameApi({ fetch: mock.createFetch() }));
  try {
    await controller.authenticate({ username: fixtureUser, password: fixturePassword }, false);
    await controller.create({ game_name: 'Offline rapid interaction', starting_country_id: 'south-africa' });
    const state = controller.getSnapshot(), pending = [];
    const h = human('human', { sourceId: 'south-africa', targetId: 'vatican-city' },
      { game: state.game, act: action => pending.push(controller.act(action)) });
    h.submit(); h.submit(); await Promise.all(pending);
    const posts = mock.calls.filter(c => c.method === 'POST' && c.path.endsWith('/actions'));
    assert.equal(posts.length, 1); assert.equal(posts[0].expected_revision, 0); assert.ok(posts[0].action_id);
    assert.equal(controller.getSnapshot().game.revision, 1);
  } finally { controller.dispose(); }
});

test('same revision keeps drafts local without effects or map-selection coupling; responsive controls remain native', async () => {
  const h = human('human', { sourceId: 'brazil', targetId: 'canada' });
  const rerender = controls.HumanControlsView({ ...h.props, game: { ...h.state.game } });
  const selects = [...nodes(rerender)].filter(e => e.type === 'select');
  assert.deepEqual(selects.map(e => e.props.value), ['brazil', 'canada']);
  const source = await readFile(new URL('../src/components/Controls.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /useEffect|\.focus\(|fetch\(|new GameController|randomUUID|setTimeout|setInterval/);
  const css = await readFile(new URL('../src/components/controls.css', import.meta.url), 'utf8');
  assert.match(css, /minmax\(0, 1fr\)/); assert.match(css, /min-block-size: 44px/);
  assert.match(css, /prefers-reduced-motion/); assert.doesNotMatch(css, /position: fixed|overflow: hidden/);
});
