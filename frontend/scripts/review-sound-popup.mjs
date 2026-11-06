// Explicit, offline presentation check using fresh Chrome profiles and inert screen fixtures.
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { startComponentPreview } from './preview-components.mjs';

const before = process.argv.includes('--before');
const phase = before ? 'before' : 'after';
const output = resolve('../output/ui-sound-popup', phase);
await mkdir(output, { recursive: true });
const preview = await startComponentPreview({ port: 0, screens: true });
const origin = `http://127.0.0.1:${preview.server.address().port}`;
const checks = [], findings = [], errors = [], blocked = [];
const assert = (pass, name) => checks.push({ name, pass: !!pass });

async function review(zoom) {
  const profile = await mkdtemp(resolve(tmpdir(), 'geopolitics-popup-'));
  if (zoom === 2) {
    // Chrome's native default page zoom (not pinch zoom or CSS transform).
    await mkdir(resolve(profile, 'Default'));
    await writeFile(resolve(profile, 'Default/Preferences'), JSON.stringify({
      partition: { default_zoom_level: { x: Math.log(zoom) / Math.log(1.2) } },
    }));
  }
  const browser = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless', '--disable-gpu', '--no-first-run', '--disable-background-networking',
    '--disable-component-update', '--disable-sync', '--disable-extensions', '--no-default-browser-check',
    `--user-data-dir=${profile}`, '--window-size=1440,900', '--remote-debugging-address=127.0.0.1',
    '--remote-debugging-port=0', 'about:blank',
  ], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
  let socket, nextId = 0;
  const pending = new Map(), handlers = new Map();
  const command = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++nextId;
    const timeout = setTimeout(() => { pending.delete(id); reject(Error(`Timed out: ${method}`)); }, 15000);
    pending.set(id, { resolve, reject, timeout });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  try {
    const endpoint = await new Promise((resolve, reject) => {
      let stderr = '';
      const timeout = setTimeout(() => reject(Error('Isolated Chrome did not start.')), 15000);
      browser.once('error', reject);
      browser.stderr.on('data', chunk => {
        stderr += chunk;
        const match = /DevTools listening on (ws:\/\/127\.0\.0\.1:\d+\/devtools\/browser\/[^\s]+)/.exec(stderr);
        if (match) { clearTimeout(timeout); resolve(match[1]); }
      });
    });
    socket = new WebSocket(endpoint);
    socket.addEventListener('message', ({ data }) => {
      const message = JSON.parse(data), task = pending.get(message.id);
      if (task) {
        pending.delete(message.id); clearTimeout(task.timeout);
        message.error ? task.reject(Error(message.error.message)) : task.resolve(message.result);
      } else handlers.get(message.method)?.(message.params);
    });
    await new Promise((resolve, reject) => {
      socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true });
    });
    const { targetId } = await command('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await command('Target.attachToTarget', { targetId, flatten: true });
    const send = (method, params) => command(method, params, sessionId);
    handlers.set('Fetch.requestPaused', async ({ requestId, request }) => {
      const allowed = request.url.startsWith(`${origin}/`) && request.method === 'GET';
      if (!allowed) blocked.push({ method: request.method, url: request.url });
      await send(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest', allowed ? { requestId } : { requestId, errorReason: 'BlockedByClient' });
    });
    handlers.set('Runtime.exceptionThrown', event => errors.push(event.exceptionDetails.text));
    await send('Fetch.enable', { patterns: [{ urlPattern: '*' }] });
    await send('Page.enable'); await send('Runtime.enable');
    const evaluate = async expression => {
      const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
      if (result.exceptionDetails) throw Error(result.exceptionDetails.text);
      return result.result.value;
    };
    const settle = () => evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
    const visit = async fixture => {
      await evaluate('window.__popupNavigation=true');
      await send('Page.navigate', { url: `${origin}/?fixture=${fixture}` });
      let ready = false;
      for (let i = 0; i < 100; i++) {
        ready = await evaluate(`!window.__popupNavigation&&!!document.querySelector('main')&&document.querySelector('[data-fixture]')?.value===${JSON.stringify(fixture)}`);
        if (ready) break;
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      if (!ready) throw Error(`Fixture did not render: ${fixture}`);
      await evaluate(`document.querySelector('main').scrollIntoView({block:'start',behavior:'instant'});window.scrollTo(0,scrollY);document.querySelector('.geo-sound summary').click()`);
      await settle();
    };
    const sizes = zoom === 1 ? [[1440, 900], [1280, 720], [768, 1024], [375, 812]] : [[1440, 900]];
    for (const [width, height] of sizes) {
      if (zoom === 1) await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
      for (const fixture of ['landing', 'connectivity']) {
        await visit(fixture);
        const name = `${fixture}-${width}x${height}-${zoom * 100}percent`;
        const value = await evaluate(`(()=>{
          const panel=document.querySelector('.geo-sound fieldset'), box=e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};};
          const controls=Array.from(panel.querySelectorAll('label,input,button,p,legend')).map(e=>({tag:e.tagName,...box(e),overflow:e.scrollWidth>e.clientWidth+1}));
          const r=box(panel),sample=document.elementFromPoint(Math.min(innerWidth-1,r.right-8),r.top+30);
          return {viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio,scale:visualViewport.scale},panel:r,controls,
            overflow:document.documentElement.scrollWidth>innerWidth,unobscured:panel.contains(sample),
            warning:!!Array.from(document.querySelectorAll('[role=alert]')).find(e=>e.textContent.includes('service is temporarily unavailable')),
            open:document.querySelector('.geo-sound').open};
        })()`);
        findings.push({ name, ...value });
        assert(value.open, `${name}: popup open`);
        assert(value.panel.left >= 0 && value.panel.right <= value.viewport.width && value.panel.top >= 0 && value.panel.bottom <= value.viewport.height, `${name}: entire popup inside viewport`);
        assert(!value.overflow, `${name}: no horizontal document overflow`);
        assert(value.unobscured, `${name}: popup above surrounding content`);
        assert(value.controls.every(r => r.left >= value.panel.left && r.right <= value.panel.right && !r.overflow), `${name}: labels, slider, checkbox and text fit`);
        assert(value.warning === (fixture === 'connectivity'), `${name}: correct service-warning state`);
        if (zoom === 2) assert(value.viewport.dpr === 2 && value.viewport.scale === 1 && value.viewport.width <= width / 2, `${name}: native Chrome 200% page zoom verified`);
        const { data } = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
        await writeFile(resolve(output, `${name}.png`), Buffer.from(data, 'base64'));
        // Keyboard use and persistence exercise the existing handlers; no audio is enabled.
        await evaluate(`document.querySelector('.geo-sound input[type=range]').focus()`);
        const oldVolume = await evaluate(`Number(document.querySelector('.geo-sound input[type=range]').value)`);
        await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowLeft', code: 'ArrowLeft', windowsVirtualKeyCode: 37 });
        await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowLeft', code: 'ArrowLeft', windowsVirtualKeyCode: 37 });
        assert(await evaluate(`Number(document.querySelector('.geo-sound input[type=range]').value)===${Math.max(0, oldVolume - 1)}&&JSON.parse(localStorage.getItem('geopolitics.sound.v1')).enabled===false`), `${name}: keyboard volume adjustment preserves muted preference`);
        await evaluate(`document.querySelector('.geo-sound summary').focus()`);
        await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', text: '\r', windowsVirtualKeyCode: 13 });
        await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
        assert(await evaluate(`!document.querySelector('.geo-sound').open`), `${name}: keyboard disclosure closes normally`);
        if (!before) {
          await evaluate(`localStorage.setItem('geopolitics.sound.v1',JSON.stringify({enabled:true,volume:0.35}))`);
          await visit(fixture);
          assert(await evaluate(`document.querySelector('.geo-sound button')?.textContent==='Enable playback in this tab'`), `${name}: restored preference still requires explicit tab activation`);
          assert(await evaluate(`(()=>{const p=document.querySelector('.geo-sound fieldset').getBoundingClientRect(),b=document.querySelector('.geo-sound button')?.getBoundingClientRect();return b&&p.left>=0&&p.right<=innerWidth&&p.top>=0&&p.bottom<=innerHeight&&b.left>=p.left&&b.right<=p.right&&b.top>=p.top&&b.bottom<=p.bottom&&document.documentElement.scrollWidth<=innerWidth;})()`), `${name}: expanded activation controls also fit without overflow`);
          const restored = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
          await writeFile(resolve(output, `${name}-restored-enabled.png`), Buffer.from(restored.data, 'base64'));
          // Restore only this fresh profile's preference; never activate or play audio.
          await evaluate(`localStorage.setItem('geopolitics.sound.v1',JSON.stringify({enabled:false,volume:0.35}))`);
        }
      }
    }
  } finally {
    for (const task of pending.values()) clearTimeout(task.timeout);
    socket?.close(); browser.kill();
  }
}
try {
  await review(1); await review(2);
  assert(errors.length === 0, 'No browser runtime exceptions');
  assert(blocked.length === 0, 'Only loopback fixture resources requested');
  const failures = checks.filter(check => !check.pass);
  const screenshots = findings.length * (before ? 1 : 2);
  await writeFile(resolve(output, 'results.json'), JSON.stringify({ phase, screenshots, checks, findings, errors, blocked }, null, 2));
  console.log(JSON.stringify({ phase, assertions: checks.length, passed: checks.length - failures.length, failed: failures.length, failures, screenshots }));
  if (!before && failures.length) process.exitCode = 1;
} finally { await preview.close(); }
