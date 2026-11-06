import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement, isValidElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { request } from 'node:http';
import { presentationScreen, watchGameId, watchLink } from '../src/components/screen-view.ts';
import { startComponentPreview } from '../scripts/preview-components.mjs';
import { GameController } from '../src/game/controller.ts';
import { GameApi } from '../src/api/index.ts';
import { createMockApi, fixturePassword } from './mock-api.mjs';

let vite, app, auth, dashboard, rules, watch, fixtures, boardFixtures;
before(async () => {
  vite = await createServer({configFile:false,root:fileURLToPath(new URL('../',import.meta.url)),server:{middlewareMode:true,hmr:false,ws:false},logLevel:'silent',optimizeDeps:{noDiscovery:true,include:[]}});
  [app,auth,dashboard,rules,watch,fixtures,boardFixtures] = await Promise.all([
    '/src/App.tsx','/src/components/AuthForm.tsx','/src/components/Dashboard.tsx','/src/components/Rules.tsx',
    '/src/components/WatchEntry.tsx','/src/dev/screen-fixtures.ts','/src/dev/board-fixtures.ts',
  ].map(path=>vite.ssrLoadModule(path)));
});
after(async()=>{await vite?.close();});
const html=element=>renderToStaticMarkup(element);
const origin='https://example.invalid';
const gameId='000000000000000000000042';
function* nodes(node){if(Array.isArray(node)){for(const child of node)yield*nodes(child);}else if(isValidElement(node)){yield node;yield*nodes(node.props.children);yield*nodes(node.props.actions);yield*nodes(node.props.history);}}
function composition(mode,controller={api:{},getSnapshot:()=>fixtures.screenFixture(mode).state}){
  const {state,screen}=fixtures.screenFixture(mode);
  return app.AppView({state,screen,controller,now:0,origin});
}

test('presentation routes recognize only supported screens and preserve exact game route matching',()=>{
  for(const [path,screen] of [['/','home'],['/rules','rules'],['/rules/','rules'],['/new','new'],['/watch','watch'],[`/games/${gameId}`,'home'],['/games/not-an-id','invalid'],['/unknown','invalid']])assert.equal(presentationScreen(path),screen);
});
test('watch input accepts canonical IDs and same-site URLs while rejecting cross-site, credentials and schemes',()=>{
  for(const value of [gameId,gameId.toUpperCase(),`/games/${gameId}`,`${origin}/games/${gameId}/`])assert.equal(watchGameId(value,origin),gameId);
  for(const value of [`https://other.invalid/games/${gameId}`,`https://user:password@example.invalid/games/${gameId}`,`javascript:alert(1)`,`${origin}/games/${gameId}?x=1`,`${origin}/games/${gameId}#part`,'not-a-game'])assert.equal(watchGameId(value,origin),null);
  assert.equal(watchLink(origin,gameId),`${origin}/games/${gameId}`);assert.equal(watchLink(origin,'bad'),null);assert.equal(watchLink('javascript:x',gameId),null);
});
test('landing uses the real atlas geometry without fictional ownership, dice, soldiers or provider operations',()=>{
  const result=html(composition('landing'));
  assert.match(result,/Command a nation/);assert.match(result,/Conquer the world/);assert.match(result,/World map illustration; no campaign ownership is shown/);
  assert.equal((result.match(/<g class="geo-landing__countries">([\s\S]*?)<\/g>/)?.[1].match(/<path /g)||[]).length,470);assert.doesNotMatch(result,/data-map-country|offline_fixture_owner|Generate commentary|Forgot Password/i);
  assert.match(result,/name="username"/);assert.match(result,/current-password/);assert.match(result,/Game link or ID/);
});
test('registration retains exact username/password constraints and the original recovery identity',()=>{
  const registration=html(createElement(auth.AuthForm,{disabled:false,onSubmit(){},initialRegister:true}));
  assert.match(registration,/Register and log in/);assert.match(registration,/minLength="15" maxLength="128"/);assert.match(registration,/autoComplete="new-password"/);
  assert.match(registration,/pattern="\[a-zA-Z0-9_\]\+"/);assert.doesNotMatch(registration,/type="email"|Forgot|Reset password/);
  const recovery=html(createElement(auth.AuthForm,{disabled:false,onSubmit(){},initialRegister:true,recoveryUsername:'original_account'}));
  assert.match(recovery,/readOnly=""/);assert.match(recovery,/value="original_account"/);assert.match(recovery,/current-password/);assert.doesNotMatch(recovery,/Register and log in|Use an existing account/);
});
test('library shows only summary fields, uses existing pagination and omits unsupported outcome metrics',()=>{
  const result=html(composition('library'));
  assert.equal((result.match(/class="geo-campaign"/g)||[]).length,3);assert.match(result,/Resume/);assert.match(result,/View result/);assert.match(result,/Updated/);assert.match(result,/Not recorded/);
  assert.doesNotMatch(result,/Playing as|Countries held|Soldier totals|Victory|Defeat|strongest rival|Last played/);
  assert.match(result,/Copy watch link/);assert.match(result,/href="\/games\/000000000000000000000101"/);
  const {state}=fixtures.screenFixture('library');
  const links=[...nodes(dashboard.GameLibrary({state,controller:{},disabled:false,origin}))].filter(node=>node.type===watch.CopyWatchLink);
  assert.equal(links.length,3);assert.ok(links.every(link=>link.props.origin===origin));
});
test('library search dispatches exact supported server filters and pagination callbacks only',()=>{
  const state=fixtures.screenFixture('library').state,calls=[];
  const tree=dashboard.GameLibrary({state,controller:{dashboard:filter=>calls.push(filter),page:next=>calls.push(next)},disabled:false,origin});
  const original=globalThis.FormData;globalThis.FormData=class{get(name){return name==='query'?'southern':'';}};
  try{[...nodes(tree)].find(n=>n.type==='form').props.onSubmit({preventDefault(){},currentTarget:{}});}finally{globalThis.FormData=original;}
  assert.deepEqual(calls,[{query:'southern',status:undefined}]);
  [...nodes(tree)].find(n=>n.type==='button'&&n.props.children==='Next page').props.onClick();assert.deepEqual(calls.at(-1),true);
});
test('empty, filtered-empty, loading and connectivity states do not invent campaigns',()=>{
  assert.match(html(composition('empty')),/Your first campaign starts with one choice/);
  const state=fixtures.screenFixture('empty').state;state.filters={query:'missing'};
  assert.match(html(createElement(dashboard.GameLibrary,{state,controller:{},disabled:false})),/No campaigns match this search/);
  assert.match(html(composition('loading')),/Restoring session/);assert.match(html(composition('connectivity')),/temporarily unavailable/);
});
test('new campaign uses all 195 catalog IDs and server-supplied starting strengths without invented rivals',()=>{
  const {state}=fixtures.screenFixture('new-campaign');
  const result=html(createElement(dashboard.NewCampaign,{state,controller:{},disabled:false}));
  assert.equal((result.match(/<option /g)||[]).length,196);assert.match(result,/value="holy-see"/);assert.match(result,/Saint|St\./);
  assert.match(result,/not guaranteed to take the first turn/);assert.match(result,/Rivals appear after creation succeeds/);
  assert.doesNotMatch(result,/Your rivals are|value="vatican-city"/);assert.match(result,/disabled="" type="submit">Create game/);
});
test('unknown catalog leaves creation disabled and country selection cannot mutate state on render',()=>{
  const state=fixtures.screenFixture('new-campaign').state;state.catalog=null;let calls=0;
  const result=html(createElement(dashboard.NewCampaign,{state,controller:{create(){calls++;}},disabled:false}));
  assert.match(result,/<fieldset disabled=""/);assert.match(result,/catalog is unavailable/);assert.equal(calls,0);
});
test('rules retain paired unsorted dice, ties, immutable rewards, optional transfers and real round boundaries',()=>{
  const result=html(createElement(rules.Rules));
  for(const text of ['nine strategic rival','without sorting','There is no three-dice cap','Ties cause no loss','original population-based soldier value','reward is placed in the captured country','optional positive transfer','Round one has no reinforcements','two soldiers for every country','entire pool','no fixed round limit','spectators cannot play or generate narration','atmospheric narration'])assert.ok(result.includes(text),text);
  assert.match(result,/shared strategy/);assert.match(result,/at least one soldier/);assert.doesNotMatch(result,/adjacent countries only|three dice maximum|Replay/);
});
test('result and elimination refine messaging without replacing the Flag Poster or locking owner NPC continuation',()=>{
  const victory=html(composition('victory')),defeat=html(composition('defeat')),eliminated=html(composition('eliminated'));
  assert.match(victory,/World Conqueror/);assert.match(victory,/Flag of Brazil/);assert.match(victory,/Review campaign/);
  assert.match(defeat,/Defeat/);assert.match(defeat,/Flag of Norway/);assert.doesNotMatch(defeat,/The world is yours/);
  assert.match(eliminated,/Your participant has been eliminated/);assert.match(eliminated,/Step · Advance one rival move/);assert.doesNotMatch(eliminated,/geo-result__number/);
});
test('spectators retain saved history and public state without mutation or commentary generation controls',()=>{
  const result=html(composition('spectator'));
  assert.match(result,/Spectator view/);assert.match(result,/Committed history/);assert.match(result,/Commentary for move/);
  assert.doesNotMatch(result,/Launch attack|Step · Advance one rival move|Generate commentary|Commentary for new battles/);
  assert.equal((result.match(/data-map-country=/g)||[]).length,10);
});
test('pending navigation, fixed-account recovery, read-only confirmation and retry locks remain available',()=>{
  const result=html(composition('recovery-login'));
  assert.match(result,/Original account: offline_fixture_owner/);assert.match(result,/Check committed outcome \(read only\)/);
  const input=result.match(/<input\b[^>]*name="username"[^>]*>/)?.[0];
  assert.ok(input);assert.match(input,/readOnly=""/);assert.match(input,/value="offline_fixture_owner"/);
  assert.doesNotMatch(result,/My Games \/ Home|href="\/rules"|href="\/new"|href="\/watch"/);
  assert.match(result,/Signing in does not automatically retry/);
});
test('uncertain creation keeps recovery visible without landing or setup navigation, including session expiry',()=>{
  for(const expired of [false,true]){
    const {state}=fixtures.screenFixture('new-campaign');
    state.pending={kind:'create',account:state.session.user,operation:{key:'offline-create-key',body:{game_name:'Saved creation',starting_country_id:'brazil'}}};
    if(expired)state.session=null;
    const result=html(app.AppView({state,screen:'new',controller:{api:{}},now:0,origin}));
    assert.match(result,/Unresolved request/);assert.match(result,/Retry saved request/);
    assert.doesNotMatch(result,/href="\/(?:rules|new|watch)|Pick a country|Return to My Games/);
    if(expired)assert.match(result,/Log in to recover the saved request/);
  }
});
test('normal routes and footer expose credits, Rules and Watch while preserving stable board/commentary composition',async()=>{
  const result=html(composition('landing'));assert.match(result,/href="\/rules"/);assert.match(result,/href="\/watch"/);assert.match(result,/Skip to content/);
  assert.match(result,/UCT INF4001N 2027/);assert.match(result,/Simplemaps \(MIT\)/);assert.match(result,/Worldometer/);
  const source=await readFile(new URL('../src/App.tsx',import.meta.url),'utf8');
  assert.equal((source.match(/new GameController/g)||[]).length,1);assert.equal((source.match(/<History\b/g)||[]).length,1);
  assert.match(source,/key=\{`\$\{state.gameId\}:\$\{state.session\?\.user.id \?\? 'spectator'\}`\}/);
  assert.match(source,/if \(state.pending\) window.addEventListener\('beforeunload'/);
  assert.doesNotMatch(source,/screen === 'rules'.*initialize/);
});
test('registration and game creation remain serialized through the unchanged controller with an injected mock transport',async t=>{
  const mock=createMockApi(),controller=new GameController(new GameApi({fetch:mock.createFetch()}));t.after(()=>controller.dispose());
  await controller.initialize(null);await controller.authenticate({username:'stage8_fixture',password:fixturePassword},true);
  const country=controller.getSnapshot().catalog.countries[0].id;
  await Promise.all([controller.create({game_name:'Stage 8 offline',starting_country_id:country}),controller.create({game_name:'Duplicate',starting_country_id:country})]);
  assert.equal(mock.games.size,1);assert.equal(controller.getSnapshot().game.game_name,'Stage 8 offline');assert.equal(controller.getSnapshot().owner,true);
});
test('screen preview is development-only and refuses API requests and HTTP writes',async t=>{
  const preview=await startComponentPreview({port:0,screens:true});t.after(()=>preview.close());
  const local=(path,method='GET')=>new Promise((resolve,reject)=>{const req=request({hostname:'127.0.0.1',port:preview.server.address().port,path,method},res=>{let body='';res.on('data',chunk=>body+=chunk);res.on('end',()=>resolve({status:res.statusCode,body}));});req.on('error',reject);req.end();});
  const page=await local('/');assert.match(page.body,/ScreensPreview/);assert.match(page.body,/Stage 8 screens preview/);
  assert.equal((await local('/api/auth/login','POST')).status,404);assert.equal((await local('/api/countries')).status,404);
  assert.equal((await local('/','POST')).status,404);
  const entry=await readFile(new URL('../src/main.tsx',import.meta.url),'utf8');assert.doesNotMatch(entry,/ScreensPreview|screen-fixtures/);
});
