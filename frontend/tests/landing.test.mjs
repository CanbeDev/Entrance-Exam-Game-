import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

let vite, landing, auth, watch, app, fixtures;
before(async () => {
  vite = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false }, logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] } });
  [landing, auth, watch, app, fixtures] = await Promise.all(['/src/components/Landing.tsx', '/src/components/AuthForm.tsx',
    '/src/components/WatchEntry.tsx', '/src/App.tsx', '/src/dev/screen-fixtures.ts'].map(p => vite.ssrLoadModule(p)));
});
after(async () => { await vite?.close(); });
const render = node => renderToStaticMarkup(node);
const page = disabled => render(createElement(landing.Landing, {
  account: createElement(auth.AuthForm, { disabled, registrationInvitation: true, onSubmit() {} }),
  watch: createElement(watch.WatchEntry, { disabled, origin: 'https://example.invalid', open() {} }),
}));

test('public campaign and observation CTAs target the single original auth and watch surfaces', () => {
  const html = page(false);
  assert.match(html, /href="#command-access">Begin your campaign/);
  assert.match(html, /href="#observation">Watch a campaign/);
  assert.match(html, /id="command-access" tabindex="-1"/);
  assert.match(html, /id="observation" tabindex="-1"/);
  for (const name of ['username', 'password', 'game_id']) assert.equal((html.match(new RegExp(`name="${name}"`, 'g')) ?? []).length, 1);
  assert.match(html, /href="\/rules"/);
  assert.doesNotMatch(html, /Forgot Password|Remember Me|<iframe/);
});

test('atlas retains every exact bundled geographic path; decorative grid is separately labelled', async () => {
  const data = JSON.parse(await readFile(new URL('../src/map/mapData.generated.json', import.meta.url), 'utf8'));
  const html = page(false), countries = html.match(/<g class="geo-landing__countries">([\s\S]*?)<\/g>/)[1];
  assert.deepEqual([...countries.matchAll(/<path d="([^"]+)"/g)].map(m => m[1]), data.paths.map(p => p.d));
  assert.match(html, /Decorative colours, not a live campaign/);
  assert.match(html, /class="geo-landing__grid" aria-hidden="true"/);
  assert.doesNotMatch(html, /data-map-country=|data-confirmed-revision=/);
});

test('public landing excludes fixture demonstration and placeholder feature cards without mounting gameplay', async () => {
  const html = page(false);
  assert.doesNotMatch(html, /Offline fixture|campaign-preview\.png|geo-landing__preview|Built for commanders|geo-landing__feature-grid/);
  const source = await readFile(new URL('../src/components/Landing.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /from ['"][^'"]*(?:dev\/|controller|SoundSettings|History|GameBoard)|\b(?:fetch|setInterval|setTimeout|stepNpc|generateBattleCommentary|Math\.random)\s*\(/);
  assert.equal((html.match(/<li>/g) ?? []).length, 4);
});

test('auth constraints, disabled state and original spectator parsing remain visible through composition', () => {
  const enabled = page(false), disabled = page(true);
  assert.match(enabled, /minLength="3" maxLength="32" pattern="\[a-zA-Z0-9_\]\+"/);
  assert.match(enabled, /autoComplete="current-password"/);
  assert.equal((disabled.match(/<fieldset disabled=""/g) ?? []).length, 2);
  assert.match(disabled, /Game link or ID/);
  assert.match(enabled, /only its authenticated owner can issue orders/);
});

test('landing refinement preserves decorative engravings and a single attributed epigraph without a floating login', () => {
  const html = page(false);
  assert.doesNotMatch(html, /geo-landing__login|>Log in<\/a>/);
  assert.match(html, /Every order shapes the world\.<br\/>Every roll changes its fate\./);
  assert.equal((html.match(/<blockquote /g) ?? []).length, 1);
  assert.match(html, /“Know the enemy and know yourself\.”/);
  assert.match(html, /Sun Tzu, <cite>The Art of War<\/cite>, Chapter 3<span>Concise English rendering/);
  const icons = [...html.matchAll(/<svg class="geo-landing-symbol"[^>]*>/g)];
  assert.ok(icons.length > 10);
  assert.ok(icons.every(([tag]) => tag.includes('aria-hidden="true"') && tag.includes('focusable="false"')));
});

test('public header contains exactly one outlined login navigation action and one original account form', () => {
  const { state, screen } = fixtures.screenFixture('landing');
  const html = render(createElement(app.AppView, { state, screen, controller: { api: {}, getSnapshot: () => state }, now: 0, origin: 'https://example.invalid' }));
  const header = html.match(/<header class="geo-global-header">([\s\S]*?)<\/header>/)[1];
  assert.match(header, /<nav[^>]*id="main-navigation"[\s\S]*class="geo-header-login" href="#command-access"/);
  assert.match(header, /class="geo-header-login__icon"[^>]*aria-hidden="true"[^>]*focusable="false"/);
  assert.equal((header.match(/>Log in<\/a>/g) ?? []).length, 1);
  assert.equal((html.match(/class="geo-header-login"/g) ?? []).length, 1);
  assert.equal((html.match(/name="username"/g) ?? []).length, 1);
  assert.doesNotMatch(html, /geo-landing__login/);
});

test('registration invitation is landing-only presentation and never appears in registration or recovery mode', () => {
  const props = { disabled: false, onSubmit() {} };
  const standard = render(createElement(auth.AuthForm, props));
  const invitation = render(createElement(auth.AuthForm, { ...props, registrationInvitation: true }));
  assert.equal(standard, invitation.replace('<p class="geo-auth__invitation">New to Geopolitics?</p>', ''));
  assert.match(invitation, /type="submit">Log in<\/button><p class="geo-auth__invitation">New to Geopolitics\?<\/p><button class="geo-screen-link" type="button">Create an account/);
  for (const mode of [{ initialRegister: true }, { recoveryUsername: 'original_owner' }]) {
    assert.doesNotMatch(render(createElement(auth.AuthForm, { ...props, ...mode, registrationInvitation: true })), /geo-auth__invitation/);
  }
  for (const mode of ['landing', 'connectivity']) {
    const { state, screen } = fixtures.screenFixture(mode);
    const html = render(createElement(app.AppView, { state, screen, controller: { api: {}, getSnapshot: () => state }, now: 0, origin: 'https://example.invalid' }));
    assert.match(html, /New to Geopolitics\?/);
  }
});

test('landing remains excluded during saved-request recovery and authenticated campaign screens', () => {
  for (const mode of ['pending', 'recovery-login', 'library', 'new-campaign', 'spectator']) {
    const { state, screen } = fixtures.screenFixture(mode);
    const html = render(createElement(app.AppView, { state, screen, controller: { api: {}, getSnapshot: () => state }, now: 0, origin: 'https://example.invalid' }));
    assert.doesNotMatch(html, /geo-landing--public|Command a nation/);
  }
});
