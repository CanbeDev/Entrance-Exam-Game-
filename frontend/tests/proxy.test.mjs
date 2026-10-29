import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer as createHttpServer, request as httpRequest } from 'node:http';
import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { developmentProxy, stripApiPrefix } from '../proxy.config.mjs';

test('development proxy strips exactly one /api prefix and keeps query strings', () => {
  for (const [input, expected] of [
    ['/api/countries', '/countries'], ['/api/games/abc/events?after_revision=4&limit=20', '/games/abc/events?after_revision=4&limit=20'],
    ['/api', '/'], ['/api/', '/'], ['/api?test=1', '/?test=1'],
    ['/api/api/countries', '/api/countries'], ['/apiculture', '/apiculture'],
  ]) assert.equal(stripApiPrefix(input), expected);
  const rules = developmentProxy();
  const [pattern, options] = Object.entries(rules)[0];
  assert.ok(new RegExp(pattern).test('/api/auth/login'));
  assert.ok(!new RegExp(pattern).test('/apiary'));
  assert.equal(options.target, 'http://127.0.0.1:8000');
  assert.equal(options.changeOrigin, false);
  assert.equal(options.secure, true);
  assert.equal(options.cookieDomainRewrite, undefined);
  assert.equal(options.cookiePathRewrite, undefined);
  assert.throws(() => developmentProxy('https://entrance-exam-game.onrender.com'), /loopback/);
});

test('Vercel API rewrite precedes SPA fallback, has the approved backend and disables API caching', async () => {
  const config = JSON.parse(await readFile(new URL('../vercel.json', import.meta.url), 'utf8'));
  assert.deepEqual(config.rewrites[0], {
    source: '/api/:path*', destination: 'https://entrance-exam-game.onrender.com/:path*',
  });
  const fallback = new RegExp(`^${config.rewrites[1].source}$`);
  assert.ok(fallback.test('/games/local-id'));
  assert.ok(!fallback.test('/api/auth/login'));
  assert.equal(config.rewrites[1].destination, '/index.html');
  const headers = Object.fromEntries(config.headers[0].headers.map((x) => [x.key, x.value]));
  assert.equal(headers['Cache-Control'], 'no-store');
  assert.equal(headers['x-vercel-enable-rewrite-caching'], '0');
  assert.ok(!JSON.stringify(config).includes('vercel.app')); // No invented frontend hostname.
});

async function filesBelow(directory) {
  const result = [];
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const path = new URL(item.name + (item.isDirectory() ? '/' : ''), directory);
    result.push(...(item.isDirectory() ? await filesBelow(path) : [path]));
  }
  return result;
}
test('application networking stays in src/api and tokens never use browser storage', async () => {
  for (const path of await filesBelow(new URL('../src/', import.meta.url))) {
    const text = await readFile(path, 'utf8');
    assert.ok(!/\b(?:localStorage|sessionStorage|indexedDB)\b/.test(text), path.pathname);
    if (!path.pathname.includes('/src/api/')) {
      assert.ok(!/\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|axios)\b/.test(text), path.pathname);
    }
    assert.ok(!/VITE_/.test(text), path.pathname);
  }
});

function request(port, path, { method = 'GET', headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const outgoing = httpRequest({ hostname: '127.0.0.1', port, path, method, headers }, (response) => {
      let text = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => { text += chunk; });
      response.on('end', () => resolve({ status: response.statusCode, headers: response.headers, text }));
    });
    outgoing.on('error', reject);
    if (body) outgoing.write(body);
    outgoing.end();
  });
}

test('actual Vite loopback proxy preserves Origin, cookies, CSRF, Set-Cookie, no-store and SPA navigation', async () => {
  // Both listeners are ephemeral loopback mocks; the real backend is never loaded.
  const { createServer } = await import('vite');
  const received = [];
  const cookie = '__Host-geopolitics_session=offline-fixture; Secure; HttpOnly; SameSite=Lax; Path=/';
  const upstream = createHttpServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      received.push({ path: req.url, method: req.method, headers: req.headers, body });
      res.writeHead(200, { 'Content-Type': 'application/json', 'Set-Cookie': cookie, 'Cache-Control': 'no-store' });
      res.end(JSON.stringify({ forwarded: true }));
    });
  });
  await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));
  let server;
  try {
    server = await createServer({ configFile: false, root: fileURLToPath(new URL('../', import.meta.url)),
      server: { host: '127.0.0.1', port: 0, proxy: developmentProxy(`http://127.0.0.1:${upstream.address().port}`) },
      logLevel: 'silent', optimizeDeps: { noDiscovery: true, include: [] },
    });
    await server.listen();
    const port = server.httpServer.address().port;
    const origin = `https://localhost:${port}`;
    const response = await request(port, '/api/auth/login?sample=1', { method: 'POST',
      headers: { Origin: origin, Cookie: '__Host-geopolitics_session=offline-fixture',
        'X-CSRF-Token': 'offline-csrf', 'Idempotency-Key': 'offline-key', 'Content-Type': 'application/json' },
      body: '{"offline":true}',
    });
    assert.equal(response.status, 200);
    assert.equal(received[0].path, '/auth/login?sample=1');
    assert.equal(received[0].headers.origin, origin);
    assert.equal(received[0].headers.cookie, '__Host-geopolitics_session=offline-fixture');
    assert.equal(received[0].headers['x-csrf-token'], 'offline-csrf');
    assert.equal(received[0].headers['idempotency-key'], 'offline-key');
    assert.equal(received[0].body, '{"offline":true}');
    assert.deepEqual(response.headers['set-cookie'], [cookie]);
    assert.equal(response.headers['cache-control'], 'no-store');
    const spa = await request(port, '/games/offline-game', { headers: { Accept: 'text/html' } });
    assert.equal(spa.status, 200);
    assert.match(spa.text, /id="root"/);
    assert.equal(received.length, 1);
  } finally {
    await server?.close();
    await new Promise((resolve, reject) => upstream.close((error) => error ? reject(error) : resolve()));
  }
});
