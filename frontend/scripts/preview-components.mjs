// Separate loopback preview. No app entry, proxy configuration, or service client.
import { createServer as createHttpServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

export async function startComponentPreview({ port = 5175, webFonts = false, board = false, screens = false } = {}) {
  const server = createHttpServer();
  const vite = await createServer({ configFile: false,
    root: fileURLToPath(new URL('../', import.meta.url)), appType: 'custom',
    cacheDir: 'node_modules/.vite-components',
    // Vite's browser client opens a socket even with hmr:false. Bind it to this
    // same loopback server so the isolated preview has no failed HMR promises.
    server: { middlewareMode: true, hmr: { server } },
    optimizeDeps: { noDiscovery: true,
      include: ['react', 'react-dom/client', 'react/jsx-runtime', 'react/jsx-dev-runtime'],
    }, logLevel: 'error',
  });
  const original = await readFile(new URL('../dev/components.html', import.meta.url), 'utf8');
  const template = screens ? original.replace('/src/dev/ComponentPreview.tsx', '/src/dev/ScreensPreview.tsx')
    .replace('Stage 2 component preview', 'Stage 8 screens preview') : board ? original.replace('/src/dev/ComponentPreview.tsx', '/src/dev/BoardPreview.tsx')
    .replace('Stage 2 component preview', 'Stage 4 board preview') : original;
  const fontLinks = '<link rel="preconnect" href="https://fonts.googleapis.com" />'
    + '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />'
    + '<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&amp;family=Newsreader:ital,wght@0,500;0,600;1,400&amp;display=swap" rel="stylesheet" />';
  server.on('request', async (req, res) => {
    const path = new URL(req.url, 'http://127.0.0.1').pathname;
    res.setHeader('Cache-Control', 'no-store');
    if (req.method !== 'GET' || path === '/api' || path.startsWith('/api/')) {
      res.writeHead(404); res.end('No application service is connected to this preview.'); return;
    }
    if (path === '/') {
      try {
        const html = template.replace('data-web-fonts="false"', `data-web-fonts="${webFonts}"`)
          .replace('<!-- WEB_FONTS -->', webFonts ? fontLinks : '');
        res.setHeader('Content-Type', 'text/html; charset=utf-8');
        res.end(await vite.transformIndexHtml('/', html));
      } catch { res.writeHead(500); res.end('The component preview could not be rendered.'); }
      return;
    }
    vite.middlewares(req, res, () => { res.writeHead(404); res.end('Preview resource not found.'); });
  });
  try {
    await new Promise((resolve, reject) => {
      server.once('error', reject); server.listen(port, '127.0.0.1', resolve);
    });
  } catch (error) { await vite.close(); throw error; }
  return { server, async close() {
    await vite.close();
    await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  } };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const preview = await startComponentPreview({ webFonts: process.argv.includes('--web-fonts'), board: process.argv.includes('--board'), screens: process.argv.includes('--screens') });
  console.log('Development component fixtures: http://127.0.0.1:5175');
  console.log(process.argv.includes('--web-fonts') ? 'Web fonts enabled; Google Fonts resources are requested by the browser.' : 'Offline mode: no external fonts or services.');
  process.on('SIGINT', async () => { await preview.close(); process.exit(0); });
}
