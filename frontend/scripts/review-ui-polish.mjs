// Explicit, offline presentation check using fresh Chrome profiles and inert screen fixtures.
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { startComponentPreview } from './preview-components.mjs';

const before = process.argv.includes('--before');
const phase = before ? 'before' : 'after';
const output = resolve('../output/ui-targeted-polish', phase);
await mkdir(output, { recursive: true });
const preview = await startComponentPreview({ port: 0, screens: true });
const board = await startComponentPreview({ port: 0, board: true });
let origin = `http://127.0.0.1:${preview.server.address().port}`;
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
        ready = await evaluate(`!window.__popupNavigation&&!!document.querySelector('main')&&document.querySelector('select')?.value===${JSON.stringify(fixture)}`);
        if (ready) break;
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      if (!ready) throw Error(`Fixture did not render: ${fixture}`);
      await evaluate(`document.querySelector('main').scrollIntoView({block:'start',behavior:'instant'});window.scrollTo(0,scrollY)`);
      await settle();
    };

    const shot = async (name,selector='main')=>{
      await evaluate('document.querySelector('+JSON.stringify(selector)+').scrollIntoView({block:"start",behavior:"instant"})');await settle();
      const {data}=await send('Page.captureScreenshot',{format:'png',fromSurface:true});
      await writeFile(resolve(output,name+'.png'),Buffer.from(data,'base64'));
    };
    const sizes=zoom===1?[[1440,900],[768,1024],[375,812]]:[[1440,900]];
    for(const [width,height] of sizes){
      if(zoom===1)await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
      const suffix=width+'-'+zoom*100+'percent';
      for(const [fixture,selector] of [['human','main'],['battle-six','.geo-live'],['battle-many','.geo-live'],['battle-npc-fast-forward','.geo-game-actions'],['npc','.geo-game-actions'],['npc-chronicle','.geo-game-history'],['battle-pending','.geo-recovery'],['spectator','main'],['completed','.geo-result']]){
        origin='http://127.0.0.1:'+board.server.address().port;
        await visit(fixture==='npc-chronicle'?'npc':fixture);
        const name=fixture+'-'+suffix;
        const metrics=await evaluate('(()=>{const main=document.querySelector("main").getBoundingClientRect();const box=s=>{const r=document.querySelector(s)?.getBoundingClientRect();return r?{top:r.top-main.top,width:r.width,height:r.height}:null;};return {viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio,scale:visualViewport.scale},header:box(".geo-global-header"),map:box(".geo-game-map"),actions:box("#game-actions"),live:box(".geo-live"),chronicle:box(".geo-chronicle"),battle:box(".geo-live .geo-battle:not(.geo-battle--active)"),overflow:document.documentElement.scrollWidth>innerWidth};})()');
        findings.push({name,...metrics});
        assert(!metrics.overflow,name+': no horizontal document overflow');
        if(zoom===2)assert(metrics.viewport.dpr===2&&metrics.viewport.scale===1&&metrics.viewport.width<=720,name+': native 200% page zoom');
        if(fixture==='battle-six'||fixture==='battle-many'){
          assert(await evaluate('(()=>{const a=Array.from(document.querySelectorAll(".geo-live [data-value]")).map(e=>e.dataset.value),b=Array.from(document.querySelector(".geo-chronicle__entry").querySelectorAll("[data-value]")).map(e=>e.dataset.value);return JSON.stringify(a)===JSON.stringify(b)&&a.length==='+ (fixture==='battle-six'?12:24)+';})()'),name+': every original ordered die matches Chronicle');
          assert(await evaluate('Array.from(document.querySelectorAll(".geo-live [data-pair]")).every(e=>{const a=e.querySelector(".geo-battle__dice").getBoundingClientRect(),b=e.querySelector(".geo-battle__pair-result").getBoundingClientRect();return a.right<=b.left+1&&e.scrollWidth<=e.clientWidth+1;})'),name+': dice and result columns do not overlap');
        }
        if(fixture==='npc'||fixture==='battle-npc-fast-forward'){
          assert(await evaluate('document.querySelector(".geo-live__perspective .geo-saved-justification").getBoundingClientRect().height>0'),name+': original saved reasoning visible');
          if(!before)assert(await evaluate('!document.querySelector(".geo-playback").textContent.includes("NPC")'),name+': rival terminology in controls');
        }
        if(fixture==='human'&&!before){
          assert(await evaluate('document.querySelectorAll("#game-actions").length===1'),name+': one action-control instance');
          await evaluate('document.querySelector("a[href=\\"#game-actions\\"]").focus()');
          await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});
          await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
          assert(await evaluate('document.activeElement.id==="game-actions"'),name+': existing action shortcut receives focus');
        }
        await shot(name,selector);
      }
      if(!before){
        origin='http://127.0.0.1:'+board.server.address().port;
        for(const fixture of ['battle-ready','battle-npc-fast-forward']){
          await visit(fixture);
          await evaluate('Array.from(document.querySelectorAll("button")).find(e=>e.textContent==="Preview one newly committed exchange").click()');await settle();
          assert(await evaluate('document.querySelector("[data-confirmed-revision]").dataset.confirmedRevision==="13"'),fixture+'-'+suffix+': live committed transition');
          assert(await evaluate('(()=>{const a=Array.from(document.querySelectorAll(".geo-live [data-value]")).map(e=>e.dataset.value),b=Array.from(document.querySelector(".geo-chronicle__entry").querySelectorAll("[data-value]")).map(e=>e.dataset.value);return a.length>0&&JSON.stringify(a)===JSON.stringify(b);})()'),fixture+'-'+suffix+': live and historical dice stay identical after transition');
          if(fixture==='battle-npc-fast-forward'){
            await evaluate('Array.from(document.querySelectorAll("button")).find(e=>e.textContent==="Collapse Chronicle").click()');await settle();
            assert(await evaluate('document.querySelector(".geo-live__perspective .geo-saved-justification").getBoundingClientRect().height>0'),suffix+': original reasoning survives Chronicle collapse');
            await evaluate('Array.from(document.querySelectorAll("button")).find(e=>e.textContent==="Pause rival turns").click()');await settle();
            assert(await evaluate('document.querySelector(".geo-playback__state").textContent.includes("Rival turns ready")'),suffix+': Pause stops progression without claiming activity');
          }
        }
      }
      origin='http://127.0.0.1:'+preview.server.address().port;
      for(const fixture of ['landing','new-campaign']){
        await visit(fixture);const name=fixture+'-'+suffix;
        const metrics=await evaluate('(()=>{const h=document.querySelector(".geo-global-header").getBoundingClientRect();return {height:h.height,overflow:document.documentElement.scrollWidth>innerWidth,width:innerWidth};})()');
        findings.push({name,header:metrics});assert(!metrics.overflow,name+': no horizontal document overflow');
        await shot(name);
        if(!before&&metrics.width<=600){
          const initial=await evaluate('document.querySelector(".geo-menu-toggle").getAttribute("aria-expanded")');assert(initial==='false',name+': mobile Menu starts collapsed');
          await evaluate('document.querySelector(".geo-menu-toggle").focus()');
          await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});
          await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await settle();
          assert(await evaluate('document.querySelector("#main-navigation").getBoundingClientRect().height>0&&Array.from(document.querySelectorAll("#main-navigation a")).every(e=>e.getBoundingClientRect().height>=44)'),name+': single navigation opens with full touch targets');
          await shot(name+'-menu-open');
          await evaluate('document.querySelector(".geo-menu-toggle").focus()');
          await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
          await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
          assert(await evaluate('document.activeElement===document.querySelector("#main-navigation a")'),name+': Tab enters navigation in visual order');
          assert(await evaluate('(()=>{const s=getComputedStyle(document.activeElement);return s.outlineWidth==="3px"&&s.outlineOffset==="2px";})()'),name+': keyboard focus is visible');
          await evaluate('document.querySelector("#main-navigation a").focus()');
          await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
          await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
          assert(await evaluate('document.activeElement.classList.contains("geo-menu-toggle")&&document.activeElement.getAttribute("aria-expanded")==="false"'),name+': Escape closes menu and restores focus');
          await shot(name+'-menu-closed');
        }
      }
    }
    if(!before){
      origin='http://127.0.0.1:'+board.server.address().port;await visit('refreshing');
      await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
      assert(await evaluate('getComputedStyle(document.querySelector(".geo-sync-indicator > span")).animationName==="none"'),'Reduced motion retained');
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
  const screenshots = (await import('node:fs/promises')).readdir(output).then(names=>names.filter(name=>name.endsWith('.png')).length);
  const screenshotCount = await screenshots;
  await writeFile(resolve(output, 'results.json'), JSON.stringify({ phase, screenshots: screenshotCount, checks, findings, errors, blocked }, null, 2));
  console.log(JSON.stringify({ phase, assertions: checks.length, passed: checks.length - failures.length, failed: failures.length, failures, screenshots: screenshotCount }));
  if (!before && failures.length) process.exitCode = 1;
} finally { await preview.close(); await board.close(); }
