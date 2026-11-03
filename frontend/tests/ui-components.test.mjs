import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { request } from 'node:http';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { assertIntegerRange, numberForKey, numberFromInput, stepNumber } from '../src/ui/number.ts';
import { startComponentPreview } from '../scripts/preview-components.mjs';

let vite, components;
before(async () => {
  vite = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
    server: { middlewareMode: true, hmr: false, ws: false }, logLevel: 'silent',
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  components = await vite.ssrLoadModule('/src/ui/components.tsx');
});
after(async () => { await vite?.close(); });
const render = (name, props) => renderToStaticMarkup(createElement(components[name], props));

test('buttons are named native controls with a safe non-submit default and all three variants', () => {
  for (const variant of ['primary', 'secondary', 'quiet']) {
    const html = render('Button', { variant, children: 'Select fixture' });
    assert.match(html, /<button\b[^>]*type="button"/);
    assert.match(html, new RegExp(`geo-button--${variant}`));
    assert.match(html, />Select fixture<\/button>/);
    assert.doesNotMatch(html, /disabled=""/);
  }
  assert.match(render('Button', { type: 'submit', children: 'Explicit form submission' }), /type="submit"/);
});

test('disabled button explains the missing condition and preserves caller description', () => {
  const html = render('Button', { disabled: true, disabledReason: 'Choose a fixture first.',
    'aria-describedby': 'existing-help', children: 'Selection required' });
  assert.match(html, /disabled=""/);
  const reason = html.match(/id="([^"]+)"[^>]*>Choose a fixture first\./)?.[1];
  assert.ok(reason);
  assert.ok(html.includes(`aria-describedby="existing-help ${reason}"`));
});

test('loading button is disabled, busy and has a meaningful visible accessible name', () => {
  const html = render('Button', { loading: true, loadingLabel: 'Preparing fixture…', children: 'Prepare' });
  assert.match(html, /disabled=""/);
  assert.match(html, /aria-busy="true"/);
  assert.match(html, />Preparing fixture…<\/button>/);
});

test('panel is a named section with the requested semantic heading level and escaped text', () => {
  const html = render('Panel', { title: '<script>fixture</script>', headingLevel: 3, children: 'Readable content' });
  const id = html.match(/<h3\b[^>]*id="([^"]+)"/)?.[1];
  assert.ok(id);
  assert.ok(html.includes(`aria-labelledby="${id}"`));
  assert.match(html, /&lt;script&gt;fixture&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /Readable content/);
});

test('status tones retain readable text rather than colour-only information', () => {
  for (const [tone, label] of Object.entries({ neutral: 'Round 4', success: 'Your turn', warning: 'Target', danger: 'Eliminated' })) {
    const html = render('StatusIndicator', { tone, children: label });
    assert.match(html, /role="status"/);
    assert.match(html, new RegExp(label));
    assert.match(html, /aria-hidden="true"/);
  }
});

test('status design uses one dot with plain text, no box, and semibold interface typography', async () => {
  const css = await readFile(new URL('../src/ui/components.css', import.meta.url), 'utf8');
  const status = css.match(/\.geo-status \{([^}]+)\}/)?.[1];
  assert.ok(status);
  assert.match(status, /background: none;/);
  assert.match(status, /border: 0;/);
  assert.match(status, /padding: 0;/);
  assert.doesNotMatch(status, /border-radius|box-shadow/);
  assert.match(status, /font-family: var\(--geo-font-body\)/);
  assert.match(status, /font-size: var\(--geo-body-sm-size\)/);
  assert.match(status, /font-weight: 600/);
  for (const variant of css.matchAll(/\.geo-status--\w+ \{([^}]+)\}/g)) {
    assert.doesNotMatch(variant[1], /background|border|shadow/);
  }
});

test('FROM and TARGET remain compact display labels and preview uses genuine game vocabulary', async () => {
  for (const label of ['From', 'Target']) {
    const html = render('StatusIndicator', { children: createElement('span', { className: 'geo-status__label' }, label) });
    assert.match(html, /role="status"/);
    assert.ok(html.includes(`class="geo-status__label">${label}</span>`));
    assert.doesNotMatch(html, /<button|tabindex|role="button"/);
  }
  const css = await readFile(new URL('../src/ui/components.css', import.meta.url), 'utf8');
  const labelStyle = css.match(/\.geo-status__label \{([^}]+)\}/)?.[1];
  assert.match(labelStyle, /font-size: var\(--geo-label-size\)/);
  assert.match(labelStyle, /letter-spacing: var\(--geo-label-tracking\)/);
  assert.match(labelStyle, /text-transform: uppercase/);
  const preview = await readFile(new URL('../src/dev/ComponentPreview.tsx', import.meta.url), 'utf8');
  const sample = preview.match(/<Panel title="Status indicators"[\s\S]*?<\/Panel>/)?.[0];
  assert.ok(sample);
  for (const label of ['Your turn', 'Round 4', 'From', 'Target', 'Playing', 'Eliminated']) assert.ok(sample.includes(`>${label}<`));
  assert.doesNotMatch(sample, /Waiting for a selection|Selection ready|Review the selection|Fixture action unavailable/);
  assert.match(sample, /geo-preview__statuses/);
});

test('restrained status colours meet 4.5:1 text contrast on approved Paper and Canvas surfaces', async () => {
  const tokens = await readFile(new URL('../src/ui/tokens.css', import.meta.url), 'utf8');
  const color = (name) => tokens.match(new RegExp(`--geo-${name}: (#[A-Fa-f0-9]{6});`))?.[1];
  function luminance(hex) {
    const channels = hex.slice(1).match(/../g).map((part) => parseInt(part, 16) / 255)
      .map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  }
  for (const ink of ['ink', 'forest', 'copper']) {
    for (const surface of ['paper', 'canvas']) {
      const a = luminance(color(ink)), b = luminance(color(surface));
      assert.ok((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) >= 4.5, `${ink} on ${surface}`);
    }
  }
});

test('segmented selection uses a named native radio group and a single checked option', () => {
  const html = render('SegmentedControl', { label: 'Fixture section', value: 'second', onChange() {},
    options: [{ value: 'first', label: 'First' }, { value: 'second', label: 'Second' },
      { value: 'third', label: 'Unavailable', disabled: true }] });
  assert.match(html, /<fieldset/);
  assert.match(html, /<legend[^>]*>Fixture section<\/legend>/);
  const radios = html.match(/<input\b[^>]*>/g);
  assert.equal(radios.length, 3);
  assert.ok(radios.every((input) => input.includes('type="radio"')));
  assert.equal(new Set(radios.map((input) => input.match(/name="([^"]+)"/)[1])).size, 1);
  assert.equal(radios.filter((input) => input.includes('checked=""')).length, 1);
  assert.match(radios[1], /checked=""/);
  assert.match(radios[2], /disabled=""/);
  assert.match(render('SegmentedControl', { label: 'Locked', value: 'a', onChange() {}, disabled: true,
    options: [{ value: 'a', label: 'A' }] }), /<fieldset[^>]*disabled=""/);
});

test('separate segmented controls have different native selection group names', () => {
  const html = renderToStaticMarkup(createElement('div', null, ...['One', 'Two'].map((label) =>
    createElement(components.SegmentedControl, { label, key: label, value: 'a', onChange() {}, options: [{ value: 'a', label: 'A' }] }))));
  const names = [...html.matchAll(/name="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(names).size, 2);
});

test('numeric stepper has linked name/help, explicit integer bounds and disabled boundary buttons', () => {
  const props = { label: 'Fixture amount', min: 0, max: 4, onChange() {} };
  const low = render('NumericStepper', { ...props, value: 0 });
  const id = low.match(/<input\b[^>]*id="([^"]+)"/)?.[1];
  assert.ok(id);
  assert.ok(low.includes(`for="${id}"`));
  assert.match(low, /type="number"[^>]*min="0"[^>]*max="4"[^>]*step="1"/);
  assert.match(low, /aria-label="Decrease Fixture amount"[^>]*disabled=""/);
  assert.doesNotMatch(low, /aria-label="Increase Fixture amount"[^>]*disabled=""/);
  const high = render('NumericStepper', { ...props, value: 4 });
  assert.match(high, /aria-label="Increase Fixture amount"[^>]*disabled=""/);
  const locked = render('NumericStepper', { ...props, value: 2, disabled: true });
  assert.equal((locked.match(/disabled=""/g) ?? []).length, 3);
});

test('numeric increment/decrement stay within limits, including zero-width and safe-integer boundaries', () => {
  assert.equal(stepNumber(0, 0, 4, -1), 0);
  assert.equal(stepNumber(4, 0, 4, 1), 4);
  assert.equal(stepNumber(2, 0, 4, 1), 3);
  assert.equal(stepNumber(2, 0, 4, -1), 1);
  assert.equal(stepNumber(0, 0, 0, 1), 0);
  assert.equal(stepNumber(Number.MAX_SAFE_INTEGER, 0, Number.MAX_SAFE_INTEGER, 1), Number.MAX_SAFE_INTEGER);
});

test('stepper keyboard behavior supports arrows/Home/End without changing unrelated keys', () => {
  assert.equal(numberForKey('ArrowUp', 2, 0, 4), 3);
  assert.equal(numberForKey('ArrowDown', 2, 0, 4), 1);
  assert.equal(numberForKey('Home', 2, 0, 4), 0);
  assert.equal(numberForKey('End', 2, 0, 4), 4);
  assert.equal(numberForKey('ArrowUp', 4, 0, 4), 4);
  assert.equal(numberForKey('ArrowDown', 0, 0, 4), 0);
  for (const key of ['Tab', 'Enter', 'Escape', 'a']) assert.equal(numberForKey(key, 2, 0, 4), undefined);
});

test('typed numeric values reject empty, fractional, exponent, unsafe and out-of-range entries', () => {
  for (const raw of ['', ' ', '1.5', '1e2', 'NaN', 'Infinity', '-1', '11', '9007199254740992']) {
    assert.equal(numberFromInput(raw, 0, 10), undefined, raw);
  }
  assert.equal(numberFromInput('0', 0, 10), 0);
  assert.equal(numberFromInput('10', 0, 10), 10);
});

test('invalid supplied values fail clearly instead of silently fabricating counts', () => {
  for (const [value, min, max] of [[2, 4, 0], [1.5, 0, 4], [5, 0, 4], [NaN, 0, 4], [0, 0, Infinity]]) {
    assert.throws(() => assertIntegerRange(value, min, max), RangeError);
  }
  assert.throws(() => render('NumericStepper', { label: 'Invalid', value: 5, min: 0, max: 4, onChange() {} }));
});

test('soldier tokens preserve large counts, country/owner identities and visible state labels', () => {
  for (const state of ['default', 'from', 'target', 'playing']) {
    const html = render('SoldierToken', { country: 'St. Vincent & Grenadines', owner: 'Japan NPC',
      soldiers: 1234567, kind: 'npc', faction: 4, state });
    assert.match(html, /1234567 soldiers/);
    assert.match(html, /St\. Vincent &amp; Grenadines/);
    assert.match(html, /Held by Japan NPC/);
    assert.match(html, /role="img"/);
    assert.match(html, /data-faction="4"/);
    if (state !== 'default') assert.match(html, new RegExp({ from: 'Attack from', target: 'Target', playing: 'Playing' }[state]));
  }
  assert.match(render('SoldierToken', { country: 'Brazil', owner: 'You', soldiers: 10, kind: 'human', faction: 0 }), /geo-token--human/);
});

test('selectable soldier tokens use native keyboard buttons; static tokens are not fake actions', () => {
  const props = { country: 'France', owner: 'France NPC', soldiers: 1, kind: 'npc', faction: 3 };
  assert.doesNotMatch(render('SoldierToken', props), /<button/);
  const html = render('SoldierToken', { ...props, onSelect() {}, disabled: true });
  assert.match(html, /<button[^>]*type="button"/);
  assert.match(html, /disabled=""/);
  assert.match(html, /1 soldier"/);
  assert.throws(() => render('SoldierToken', { ...props, soldiers: -1 }));
});

test('turn indicators name active, completed, upcoming and eliminated states without colour dependence', () => {
  for (const [state, label] of Object.entries({ active: 'Playing', completed: 'Turn taken', upcoming: 'Upcoming', eliminated: 'Eliminated' })) {
    const html = render('TurnIndicator', { name: 'Canada NPC', state });
    assert.match(html, new RegExp(label));
    if (state === 'active') assert.match(html, /aria-current="step"/);
    else assert.doesNotMatch(html, /aria-current/);
    if (state === 'eliminated') assert.match(html, /<s>Canada NPC<\/s>/);
  }
});

test('country progress always has ten segments and exact accessible counts from zero to ten', () => {
  for (const held of [0, 2, 10]) {
    const html = render('CountryProgress', { held });
    assert.match(html, /role="meter"[^>]*aria-label="Countries held"/);
    assert.ok(html.includes(`aria-valuenow="${held}"`));
    assert.match(html, /aria-valuemin="0"[^>]*aria-valuemax="10"/);
    assert.equal((html.match(/aria-hidden="true"/g) ?? []).length, 10);
    assert.equal((html.match(/geo-progress__segment--held/g) ?? []).length, held);
    assert.ok(html.includes(`${held} of 10 countries`));
  }
  for (const held of [-1, 11, 1.5, NaN]) assert.throws(() => render('CountryProgress', { held }));
});

test('CSS matches approved palette, readable type, focus/touch sizes and reduced motion without effects', async () => {
  const tokens = await readFile(new URL('../src/ui/tokens.css', import.meta.url), 'utf8');
  const colors = ['F7F4EC', 'FFFCF5', 'FAF3E4', 'F4EDDE', 'E2DAC8', '727974', '1E1B12', '1A3127',
    '30483D', '424844', '5C625D', '9A5440', 'CDE9DA', '7A2A1C', 'FBEAE6', 'C9DDD8', 'EBE4D3', 'CFC4AC', 'DDEAE5',
    '94701C', '46698A', '8C434E', '2F7A72', '76648A', '6B7531', '5F6A72', 'A0506E', '7A5A3A'];
  for (const color of colors) assert.ok(tokens.includes(`#${color}`), color);
  assert.match(tokens, /--geo-body-sm-size: 13px/);
  assert.match(tokens, /--geo-target: 44px/);
  assert.match(tokens, /--geo-primary-height: 48px/);
  assert.match(tokens, /--geo-focus-width: 3px/);
  assert.match(tokens, /--geo-focus-offset: 2px/);
  assert.match(tokens, /'Newsreader', Georgia/);
  assert.match(tokens, /'DM Sans', system-ui/);
  const css = await readFile(new URL('../src/ui/components.css', import.meta.url), 'utf8');
  assert.match(css, /:focus-visible/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /transition: none !important/);
  assert.match(css, /input:focus-visible \+ span/);
  assert.match(css, /@media \(max-width: 600px\)/);
  assert.doesNotMatch(css, /box-shadow|gradient\(/);
});

test('refined controls retain readable disabled states, target sizes and noncolour active cues', async () => {
  const css = await readFile(new URL('../src/ui/components.css', import.meta.url), 'utf8');
  assert.match(css, /padding: 10px var\(--geo-space-base\)/);
  assert.match(css, /geo-button--secondary \{ background: var\(--geo-paper\); border-color: var\(--geo-outline\)/);
  assert.match(css, /geo-button--secondary:hover:not\(:disabled\) \{ border-color: var\(--geo-ink\)/);
  assert.match(css, /geo-stepper__controls button:hover:not\(:disabled\).*border-color: var\(--geo-ink\)/);
  assert.match(css, /grid-template-columns: var\(--geo-target\) minmax\(0, 1fr\) var\(--geo-target\)/);
  assert.match(css, /input:checked \+ span \{ background: var\(--geo-paper\); border-color: var\(--geo-ink\); color: var\(--geo-ink\).*text-decoration: underline/);
  assert.match(css, /geo-button:disabled \{ background: var\(--geo-sand\); color: var\(--geo-muted\)/);
  assert.doesNotMatch(css, /geo-button:disabled[^}]*opacity/);
});

function localRequest(port, path, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = request({ hostname: '127.0.0.1', port, path, method }, (res) => {
      let body = ''; res.setEncoding('utf8'); res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body }));
    });
    req.on('error', reject); req.end();
  });
}

test('isolated preview defaults offline and refuses API calls, mutations and gameplay routes', async (t) => {
  const preview = await startComponentPreview({ port: 0 });
  t.after(() => preview.close());
  const port = preview.server.address().port;
  const page = await localRequest(port, '/');
  assert.equal(page.status, 200);
  assert.equal(page.headers['cache-control'], 'no-store');
  assert.match(page.body, /development fixtures/);
  assert.match(page.body, /src\/dev\/ComponentPreview\.tsx/);
  assert.doesNotMatch(page.body, /fonts\.google|src\/main|src\/App/);
  const module = await localRequest(port, '/src/dev/ComponentPreview.tsx');
  assert.equal(module.status, 200);
  // SSR alone would miss serving React's CommonJS files directly to a browser.
  assert.doesNotMatch(module.body, /from "\/node_modules\/react\//);
  const dependency = module.body.match(/from "([^"]+\.vite-components[^\"]+)"/)?.[1];
  assert.ok(dependency, 'React is served through the local ESM dependency optimizer');
  const esm = await localRequest(port, dependency);
  assert.equal(esm.status, 200);
  assert.match(esm.body, /export/);
  for (const [path, method] of [['/api', 'GET'], ['/api/countries', 'GET'], ['/api/auth/login', 'POST'],
    ['/api/games/fixture/npc-steps', 'POST'], ['/', 'POST'], ['/games/fixture', 'GET']]) {
    assert.equal((await localRequest(port, path, method)).status, 404, `${method} ${path}`);
  }
});

test('optional preview font loading uses named families, preconnect and swap without font binaries', async (t) => {
  const preview = await startComponentPreview({ port: 0, webFonts: true });
  t.after(() => preview.close());
  const page = await localRequest(preview.server.address().port, '/');
  assert.match(page.body, /data-web-fonts="true"/);
  assert.match(page.body, /rel="preconnect"/);
  assert.match(page.body, /DM\+Sans:wght@400;600;700/);
  assert.match(page.body, /Newsreader:ital,wght/);
  assert.match(page.body, /display=swap/);
  // This test reads local HTML only; it never follows the remote font links.
});

test('preview has a development guard and is not referenced by the production entry', async () => {
  const entry = await readFile(new URL('../src/main.tsx', import.meta.url), 'utf8');
  const app = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(entry + app, /ComponentPreview|src\/ui|dev\/components/);
  const preview = await readFile(new URL('../src/dev/ComponentPreview.tsx', import.meta.url), 'utf8');
  assert.match(preview, /if \(!import\.meta\.env\.DEV\)/);
  assert.doesNotMatch(preview, /from ['"].*(?:api|controller|App\.tsx)/);
  assert.match(preview, /development fixtures only/);
});
