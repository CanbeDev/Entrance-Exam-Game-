import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';

let vite, header, controls, live, battle, fixtures, battles;
before(async () => {
  vite = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false }, logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] } });
  [header, controls, live, battle, fixtures, battles] = await Promise.all([
    '/src/components/HeaderNavigation.tsx', '/src/components/Controls.tsx', '/src/components/LiveGameplay.tsx',
    '/src/components/BattleExchange.tsx', '/src/dev/board-fixtures.ts', '/src/dev/battle-fixtures.ts',
  ].map(path => vite.ssrLoadModule(path)));
});
after(async () => { await vite?.close(); });
const html = element => renderToStaticMarkup(element);

test('mobile disclosure retains one named navigation and removes destinations during pending recovery', () => {
  const text = html(createElement(header.HeaderNavigation, { available: true, landing: true }));
  assert.match(text, /aria-expanded="false" aria-controls="main-navigation">Menu/);
  assert.equal((text.match(/<nav /g) ?? []).length, 1);
  for (const href of ['/', '/new', '/rules', '/watch', '#command-access'])
    assert.equal((text.match(new RegExp(`href="${href}"`, 'g')) ?? []).length, 1);
  assert.equal(html(createElement(header.HeaderNavigation, { available: false, landing: true })), '');
});

test('battle headings describe forces while exact remaining, lost and prior counts identify soldiers', () => {
  const state = battles.battleFixture('battle-six'), entry = state.events[0];
  const text = html(createElement(battle.BattleExchangeView, { game: state.game, entry, index: 0,
    counts: { attackerBefore: 1234567, attackerAfter: 1234565, defenderBefore: 6, defenderAfter: 4 },
    rolling: false, skip() {}, settled() {} }));
  assert.match(text, /Attacking forces/); assert.match(text, /Defending forces/);
  assert.match(text, /1,234,565<\/strong><p>soldiers after this exchange/);
  assert.match(text, /2 soldiers lost/); assert.match(text, /1,234,567 soldiers/);
  assert.equal((text.match(/data-pair=/g) ?? []).length, 6);
  assert.doesNotMatch(text, /1,234,565 forces|Victory/);
});

test('commander labels preserve original identity and the entire escaped saved explanation without rewriting NPC words', () => {
  const state = fixtures.boardFixture('npc');
  state.events[0].npc_decision.explanation = 'Original NPC reasoning <script>saved</script>\nSecond recorded line.';
  state.game.countries.find(c => c.id === 'norway').owner_id = 'player-0';
  const before = JSON.stringify(state);
  const text = html(createElement(live.SavedNpcDecision, { game: state.game, committed: state.events, latest: null }));
  assert.match(text, /Norway’s Strategy/); assert.match(text, /Commander’s decision/);
  assert.ok(text.includes('Original NPC reasoning &lt;script&gt;saved&lt;/script&gt;\nSecond recorded line.'));
  assert.doesNotMatch(text, /<script>|<details/);
  assert.equal(JSON.stringify(state), before);
});

test('rival status reflects readiness, dispatch and uncertainty without inventing a completed move', () => {
  const { game } = fixtures.boardFixture('npc');
  const render = patch => html(createElement(controls.GameplayControls, { game, owner: true, disabled: false,
    fastForward: false, busy: false, pending: false, act() {}, step() {}, fast() {}, pause() {}, ...patch }));
  assert.match(render({}), /Rival turns ready/);
  assert.doesNotMatch(render({}), /is making its next move|Advancing a rival move|Pause rival turns/);
  assert.match(render({ busy: true, fastForward: true }), /Advancing a rival move/);
  const pending = render({ pending: true });
  assert.match(pending, /Awaiting confirmation/); assert.match(pending, /New moves are locked/);
  assert.doesNotMatch(pending, /Rival turn concluded|Victory/);
});
