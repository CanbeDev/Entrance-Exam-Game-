// Explicit, offline presentation check using fresh Chrome profiles and inert screen fixtures.
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { startComponentPreview } from './preview-components.mjs';

const before = process.argv.includes('--before');
const phase = before ? 'before' : 'after';
const output = resolve('../output/ui-header-login', phase);
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
      await evaluate(`document.querySelector('main').scrollIntoView({block:'start',behavior:'instant'});window.scrollTo(0,scrollY);void 0`);
      await settle();
    };

    const shot=async(name,selector='main',full=false)=>{
      await evaluate('document.querySelector('+JSON.stringify(selector)+').scrollIntoView({block:"start",behavior:"instant"})');await settle();
      await evaluate('Promise.all(document.querySelector(".geo-landing").getAnimations({subtree:true}).map(a=>a.finished.catch(()=>{})))');
      const clip=full?await evaluate('(()=>{const e=document.querySelector("main"),r=e.getBoundingClientRect();return {x:0,y:r.top+scrollY,width:innerWidth,height:r.height,scale:1};})()'):undefined;
      const {data}=await send('Page.captureScreenshot',{format:'png',fromSurface:true,captureBeyondViewport:full,...(clip?{clip}:{})});
      await writeFile(resolve(output,name+'.png'),Buffer.from(data,'base64'));
    };
    const enter = async () => {
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await settle();
    };
    const revealLogin = async () => {
      await evaluate('document.querySelector(".geo-global-header").scrollIntoView({block:"start",behavior:"instant"})');
      if(await evaluate('document.querySelector(".geo-menu-toggle").getClientRects().length>0&&document.querySelector(".geo-menu-toggle").getAttribute("aria-expanded")==="false"')){
        await evaluate('document.querySelector(".geo-menu-toggle").focus()');await enter();
      }
      await evaluate('document.querySelector(".geo-header-login").focus()');
    };
    const sizes=zoom===1?[[1440,900],[768,1024],[375,812]]:[[1440,900]];
    for(const[width,height]of sizes){
      if(zoom===1)await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
      await visit('landing');
      await evaluate('Promise.all(document.querySelector(".geo-landing").getAnimations({subtree:true}).map(a=>a.finished.catch(()=>{})))');
      const name=width+'-'+zoom*100+'percent';
      const metrics=await evaluate('(()=>{const box=s=>{const r=document.querySelector(s).getBoundingClientRect();return {top:r.top,left:r.left,right:r.right,width:r.width,height:r.height};};return {viewport:{width:innerWidth,height:innerHeight,dpr:devicePixelRatio,scale:visualViewport.scale},hero:box(".geo-landing__hero"),access:box("#command-access"),observation:box("#observation"),preview:box(".geo-landing__preview"),loginShortcut:box(document.querySelector(".geo-menu-toggle").getClientRects().length?".geo-menu-toggle":".geo-header-login"),overflow:document.documentElement.scrollWidth>innerWidth};})()');
      findings.push({name,...metrics});assert(!metrics.overflow,name+': no horizontal overflow');
      assert(metrics.loginShortcut.top<metrics.viewport.height&&metrics.loginShortcut.height>=44,name+': login or existing mobile Menu is immediately reachable');
      assert(await evaluate('document.querySelectorAll("a.geo-header-login").length===1&&document.querySelectorAll(".geo-global-header a").length===5&&!document.querySelector(".geo-landing__login")'),name+': one login navigation action, none floating over hero');
      if(zoom===2)assert(metrics.viewport.dpr===2&&metrics.viewport.scale===1&&metrics.viewport.width<=720,name+': native 200% page zoom');
      assert(await evaluate('document.querySelectorAll(".geo-landing__countries path").length===470'),name+': all original geography paths');
      assert(await evaluate('document.querySelectorAll(".geo-landing__orders li").length===4&&document.querySelectorAll(".geo-landing-symbol:not([aria-hidden=true])").length===0'),name+': Four Orders and decorative icons');
      assert(await evaluate('document.querySelectorAll("input[name=username]").length===1&&document.querySelectorAll("input[name=password]").length===1&&document.querySelectorAll("input[name=game_id]").length===1'),name+': one existing auth and spectator form');
      assert(await evaluate('document.querySelector(".geo-landing__preview-label").textContent.includes("Not a live campaign")'),name+': static preview clearly labelled');
      await shot('hero-'+name);
      assert(await evaluate('Array.from(document.querySelector("#landing-title").children).every(e=>e.getBoundingClientRect().height<=parseFloat(getComputedStyle(e).lineHeight)*1.15)'),name+': original two-line headline composition fits');
      const decoration=await evaluate('(()=>{const s=".geo-landing__watermark,.geo-landing__atlas-seal,.geo-landing__preview-engraving";const decorations=[...document.querySelectorAll(s)],controls=[...document.querySelectorAll(".geo-landing a,.geo-landing input,.geo-landing button,#landing-title,.geo-landing__lead,.geo-landing__tagline,.geo-landing__geography")];return {noninteractive:decorations.every(e=>getComputedStyle(e).pointerEvents==="none"&&e.getAttribute("aria-hidden")==="true"||getComputedStyle(e).pointerEvents==="none"&&!!e.closest("[aria-hidden=true]")),overlap:decorations.some(e=>{const a=e.getBoundingClientRect();return controls.some(c=>{const b=c.getBoundingClientRect();return a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;});}),heroDice:document.querySelectorAll(".geo-landing__watermark svg,.geo-landing__atlas-seal>svg:first-child").length};})()');
      findings.push({name:name+'-decoration',...decoration});
      assert(decoration.noninteractive&&!decoration.overlap&&decoration.heroDice===3,name+': three decorative hero dice occupy reserved space without control or text overlap');
      assert(await evaluate('document.querySelectorAll(".geo-landing__epigraph blockquote").length===1&&document.querySelector(".geo-landing__epigraph").textContent.includes("Concise English rendering")'),name+': one attributed concise epigraph');
      await shot('epigraph-'+name,'.geo-landing__epigraph');
      await revealLogin();
      const header=await evaluate('(()=>{const h=document.querySelector(".geo-global-header").getBoundingClientRect(),brand=document.querySelector(".geo-brand").getBoundingClientRect(),nav=document.querySelector(".geo-main-navigation").getBoundingClientRect(),links=[...document.querySelectorAll(".geo-main-navigation a")].map(e=>e.getBoundingClientRect()),sound=document.querySelector(".geo-sound>summary").getBoundingClientRect(),status=document.querySelector(".geo-sync-indicator").getBoundingClientRect();return {width:h.width,height:h.height,linksInside:links.every(r=>r.left>=h.left&&r.right<=h.right),brandAndNavigationSameRow:Math.abs((brand.top+brand.height/2)-(nav.top+nav.height/2))<=3,singleNavigationRow:nav.height<=Math.max(...links.map(r=>r.height))+2,utilitiesAligned:Math.abs((sound.top+sound.height/2)-(status.top+status.height/2))<=3,utilitiesSeparated:sound.right<=status.left,overflow:document.documentElement.scrollWidth>innerWidth};})()');
      findings.push({name:name+'-header',...header});
      assert(header.linksInside&&!header.overflow&&header.utilitiesAligned&&header.utilitiesSeparated,name+': navigation, sound and status fit with aligned separate controls');
      if(metrics.viewport.width>600)assert(header.singleNavigationRow&&header.brandAndNavigationSameRow,name+': desktop/tablet branding and navigation stay on one row');
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9,modifiers:8});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
      assert(await evaluate('document.activeElement.matches(".geo-header-login")&&getComputedStyle(document.activeElement).outlineWidth==="3px"&&getComputedStyle(document.activeElement).outlineOffset==="2px"'),name+': keyboard header login has a strong visible focus ring');
      await shot('login-shortcut-focus-'+name);
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await settle();
      assert(await evaluate('document.activeElement.id==="command-access"'),name+': outlined login shortcut opens original command access by keyboard');
      assert(await evaluate('document.querySelector("[name=password]").minLength===1&&document.querySelector("[name=password]").autocomplete==="current-password"&&document.querySelector(".geo-main-navigation").dataset.expanded==="false"'),name+': header login selects existing login mode and closes mobile navigation');
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
      assert(await evaluate('document.activeElement.matches(".geo-landing__text-link[href=\\"/rules\\"]")'),name+': Tab follows the command-access reading order');
      await shot('login-'+name,'#command-access');
      assert(await evaluate('document.querySelector(".geo-auth__invitation").textContent==="New to Geopolitics?"&&document.querySelectorAll(".geo-auth__invitation").length===1&&getComputedStyle(document.querySelector(".geo-auth__invitation")).display!=="none"'),name+': single readable registration invitation by the real toggle');
      assert(await evaluate('(()=>{const p=document.querySelector(".geo-auth__invitation"),b=p.nextElementSibling,r=e=>{const range=document.createRange();range.selectNodeContents(e);return range.getBoundingClientRect();},a=r(p),c=r(b);return Math.abs(a.top-c.top)<2||c.top>=a.bottom;})()'),name+': registration invitation and action have aligned or clearly wrapped text');
      await shot('registration-invitation-'+name,'.geo-landing__account');
      await evaluate('window.__sameAccountForm=document.querySelector(".geo-auth form");window.__beforeNavigation=document.querySelector("[data-preview-callback]").textContent;document.querySelector(".geo-landing__primary").focus()');await enter();
      assert(await evaluate('document.activeElement.id==="command-access"&&document.querySelector("[name=password]").minLength===15&&document.querySelector("[name=password]").autocomplete==="new-password"'),name+': Begin campaign navigates directly to existing registration mode');
      assert(await evaluate('window.__sameAccountForm===document.querySelector(".geo-auth form")&&window.__beforeNavigation===document.querySelector("[data-preview-callback]").textContent'),name+': choosing registration neither remounts the form nor submits authentication');
      await shot('begin-registration-'+name,'#command-access');
      await revealLogin();await enter();
      assert(await evaluate('document.querySelector("[name=password]").minLength===1&&!!document.querySelector(".geo-auth__invitation")&&window.__sameAccountForm===document.querySelector(".geo-auth form")&&window.__beforeNavigation===document.querySelector("[data-preview-callback]").textContent'),name+': returning-user login restores existing login mode without remount or submission');
      await evaluate('Array.from(document.querySelectorAll(".geo-auth button")).find(e=>e.textContent==="Create an account").focus()');
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await settle();
      assert(await evaluate('document.querySelector("[name=password]").minLength===15&&document.querySelector("[name=password]").autocomplete==="new-password"'),name+': original registration mode and password policy');
      assert(await evaluate('!document.querySelector(".geo-auth__invitation")'),name+': invitation disappears in actual registration mode');
      await shot('registration-'+name,'#command-access');
      await evaluate('(()=>{for(const[name,value]of [["username","local_demo"],["password","x".repeat(16)]]){const e=document.querySelector(".geo-auth [name="+name+"]");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(e,value);e.dispatchEvent(new Event("input",{bubbles:true}));}document.querySelector(".geo-auth form").requestSubmit();})()');await settle();
      assert(await evaluate('document.querySelector("[data-preview-callback]").textContent.includes("register and log in")'),name+': registration invokes the original inert auth callback');
      await evaluate('Array.from(document.querySelectorAll(".geo-auth button")).find(e=>e.textContent==="Use an existing account").click()');await settle();
      await evaluate('document.querySelector(".geo-auth form").requestSubmit()');await settle();
      assert(await evaluate('document.querySelector(".geo-auth [role=alert]").textContent.includes("username and password requirements")'),name+': original invalid-form feedback');
      await shot('login-validation-'+name,'#command-access');
      await evaluate('(()=>{for(const[name,value]of [["username","local_demo"],["password","x".repeat(16)]]){const e=document.querySelector(".geo-auth [name="+name+"]");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(e,value);e.dispatchEvent(new Event("input",{bubbles:true}));}document.querySelector(".geo-auth form").requestSubmit();})()');await settle();
      assert(await evaluate('document.querySelector("[data-preview-callback]").textContent.includes("Offline callback: log in.")'),name+': login invokes the original inert auth callback');
      await evaluate('document.querySelector(".geo-landing__primary").focus()');await enter();
      assert(await evaluate('document.querySelector("[name=password]").minLength===15'),name+': Begin campaign still selects registration after parent rerender');
      await revealLogin();await enter();
      assert(await evaluate('document.querySelector("[name=password]").minLength===1'),name+': header login still selects login after parent rerender');
      await visit('landing');
      await evaluate('document.querySelector(".geo-landing__secondary").focus()');
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',text:'\r',windowsVirtualKeyCode:13});
      await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await settle();
      assert(await evaluate('document.activeElement.id==="observation"'),name+': Watch campaign focuses original spectator entry');
      await shot('spectator-'+name,'#observation');
      await evaluate('(()=>{const e=document.querySelector("[name=game_id]");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(e,"not-a-game");e.dispatchEvent(new Event("input",{bubbles:true}));document.querySelector(".geo-watch form").requestSubmit();})()');await settle();
      assert(await evaluate('document.querySelector(".geo-watch [role=alert]").textContent.includes("24-character game ID")'),name+': original spectator validation');
      await shot('spectator-validation-'+name,'#observation');
      await evaluate('(()=>{const e=document.querySelector("[name=game_id]");Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(e,"000000000000000000000042");e.dispatchEvent(new Event("input",{bubbles:true}));document.querySelector(".geo-watch form").requestSubmit();})()');await settle();
      assert(await evaluate('document.querySelector("[data-preview-callback]").textContent.includes("open public game")'),name+': valid spectator ID invokes original inert callback');
      await visit('landing');
      await evaluate('document.querySelector(".geo-landing__preview").scrollIntoView();new Promise((resolve,reject)=>{const e=document.querySelector(".geo-landing__preview img");if(e.complete&&e.naturalWidth)resolve();else {e.onload=resolve;e.onerror=()=>reject(Error("Preview image failed"));}})');
      assert(await evaluate('document.querySelector(".geo-landing__preview img").naturalWidth===1440'),name+': local demonstration image loads');
      const contrast=await evaluate('(()=>{const rgb=s=>s.match(/[0-9.]+/g).slice(0,3).map(Number),lum=a=>a.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);const samples=[[".geo-landing__eyebrow","rgb(247, 244, 236)"],[".geo-landing__primary","rgb(48, 72, 61)"],[".geo-landing__observation p","rgb(26, 49, 39)"],[".geo-watch input","rgb(26, 49, 39)"],[".geo-watch button","rgb(211, 183, 117)"]];return samples.map(([selector,bg])=>{const fg=getComputedStyle(document.querySelector(selector)).color,a=lum(rgb(fg)),b=lum(rgb(bg));return {selector,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};});})()');
      assert(contrast.every(sample=>sample.ratio>=4.5),name+': representative text contrast at least 4.5 to 1');
      findings.push({name:name+'-contrast',samples:contrast});
      await shot('campaign-preview-'+name,'.geo-landing__preview');
      await shot('full-landing-'+name,'main',true);
      await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
      assert(await evaluate('Array.from(document.querySelectorAll(".geo-landing__brief,#landing-title>*,.geo-landing__map,.geo-landing__cta")).every(e=>getComputedStyle(e).animationName==="none"&&getComputedStyle(e).opacity==="1")'),name+': reduced motion leaves content immediately visible');
      await send('Emulation.setEmulatedMedia',{features:[]});
      await visit('connectivity');await shot('service-unavailable-'+name);
      assert(await evaluate('Array.from(document.querySelectorAll("[role=alert]")).some(e=>e.textContent.includes("temporarily unavailable"))&&document.documentElement.scrollWidth<=innerWidth'),name+': real service warning remains visible without overflow');
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
  const screenshots = (await (await import('node:fs/promises')).readdir(output)).filter(name=>name.endsWith('.png')).length;
  await writeFile(resolve(output, 'results.json'), JSON.stringify({ phase, screenshots, checks, findings, errors, blocked }, null, 2));
  console.log(JSON.stringify({ phase, assertions: checks.length, passed: checks.length - failures.length, failed: failures.length, failures, screenshots }));
  if (!before && failures.length) process.exitCode = 1;
} finally { await preview.close(); }
