import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
import { developmentProxy } from './proxy.config.mjs';

const cert = process.env.LOCAL_HTTPS_CERT;
const key = process.env.LOCAL_HTTPS_KEY;
if (!!cert !== !!key) throw new Error('Supply both existing local HTTPS certificate and key paths');

export default defineConfig({
  server: {
    host: '127.0.0.1', port: 5173, strictPort: true,
    proxy: developmentProxy(process.env.LOCAL_API_TARGET),
    ...(cert && key ? { https: { cert: readFileSync(cert), key: readFileSync(key) } } : {}),
  },
});
