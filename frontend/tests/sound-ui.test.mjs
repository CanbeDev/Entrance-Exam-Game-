import {before,after,test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';
import {soundAssets} from '../src/sound/assets.ts';
let vite,panel;
before(async()=>{vite=await createServer({configFile:false,root:fileURLToPath(new URL('../',import.meta.url)),server:{middlewareMode:true,hmr:false,ws:false},logLevel:'silent',optimizeDeps:{noDiscovery:true,include:[]}});panel=await vite.ssrLoadModule('/src/dev/SoundTestPanel.tsx');});
after(async()=>{await vite?.close();});
const read=path=>readFile(new URL(path,import.meta.url),'utf8');
test('offline panel lists all 18 real mappings and exposes accessible test/status/settings controls',()=>{
 const html=renderToStaticMarkup(createElement(panel.SoundTestPanel));
 assert.equal((html.match(/data-sound-event=/g)||[]).length,18);
 for(const[event,name]of Object.entries(soundAssets)){assert.ok(html.includes('Test '+event));assert.ok(html.includes(name));}
 assert.match(html,/role="status"/);assert.match(html,/href="#sound-settings"/);assert.match(html,/Stop test sound/);
});
test('diagnostic panel uses the existing service, explicit clicks and no gameplay/network implementation',async()=>{
 const source=await read('../src/dev/SoundTestPanel.tsx');assert.match(source,/pageSound\.play\(event, \{ important: true \}\)/);assert.match(source,/onClick=/);assert.match(source,/if \(!import\.meta\.env\.DEV\)/);
 assert.doesNotMatch(source,/new Audio|\b(?:fetch|act|stepNpc|retryPending|generateBattleCommentary)\s*\(/);
 for(const file of ['../src/main.tsx','../src/App.tsx','../src/sound/SoundSettings.tsx'])assert.doesNotMatch(await read(file),/SoundTestPanel|sound-test\.css|from ['"][^'"]*dev\//);
});
test('preview conquest/victory transitions include matching new receipt evidence rather than only a newer board',async()=>{
 const source=await read('../src/dev/BoardPreview.tsx');assert.match(source,/fixture\.events = \[\.\.\.base\.events, \{ revision: 13/);assert.match(source,/offline-preview-\$\{transition\}-13/);assert.match(source,/type: 'victory'/);assert.match(source,/type: 'conquered'/);
});
