import { test } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

test('recovery login renders a fixed original username, password login and no registration control', async () => {
  // Compile the real component locally. No browser, listener or API is started.
  const server = await createServer({ configFile: false,
    root: fileURLToPath(new URL('../', import.meta.url)), server: { middlewareMode: true, hmr: false },
    logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] },
  });
  try {
    const { AuthForm } = await server.ssrLoadModule('/src/components/AuthForm.tsx');
    const render = (props) => renderToStaticMarkup(createElement(AuthForm, { onSubmit() {}, ...props }));
    const recovery = render({ disabled: false, recoveryUsername: 'fixture_owner' });
    assert.match(recovery, /Log in to recover the saved request/);
    const username = recovery.match(/<input\b[^>]*name="username"[^>]*>/)?.[0];
    assert.ok(username);
    assert.match(username, /readOnly=""/i);
    assert.match(username, /value="fixture_owner"/);
    assert.match(recovery, /type="password"[^>]*minLength="1"/);
    assert.doesNotMatch(recovery, /Create an account|Register and log in|disabled=""/);
    assert.match(render({ disabled: true, recoveryUsername: 'fixture_owner' }), /disabled=""/);
    assert.match(render({ disabled: false }), /Create an account/);
  } finally { await server.close(); }
});
