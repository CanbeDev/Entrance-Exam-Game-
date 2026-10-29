// Local-only browser smoke server: no production proxy and no database imports.
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
import { createMockApi } from './mock-api.mjs';

const mock = createMockApi({ seed: true });
const server = await createServer({ configFile: false,
  root: fileURLToPath(new URL('../', import.meta.url)),
  server: { host: '127.0.0.1', port: 5174, strictPort: true },
  plugins: [{ name: 'offline-smoke-only',
    transformIndexHtml: { order: 'pre', handler: () => [{ tag: 'p', attrs: { role: 'note' },
      children: 'OFFLINE SMOKE FIXTURE — scripted data; no production connection.', injectTo: 'body-prepend' }] },
    configureServer(vite) {
      vite.middlewares.use(async (req, res, next) => {
        if (!req.url.startsWith('/api/')) return next();
        let body = '';
        for await (const chunk of req) body += chunk;
        try {
          const response = await mock.handle(req.url, { method: req.method, headers: req.headers, body: body || undefined });
          res.statusCode = response.status;
          response.headers.forEach((value, key) => res.setHeader(key, value));
          res.end(await response.text());
        } catch { res.writeHead(503, { 'Content-Type': 'application/json' }); res.end('{"detail":{"code":"fixture_failure"}}'); }
      });
    },
  }],
});
await server.listen();
console.log('Offline smoke fixture ready: http://127.0.0.1:5174');
process.on('SIGINT', async () => { await server.close(); process.exit(0); });
