import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createElement, isValidElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
let vite, results, presentation, flags, fixtures, controls, ui, atlas, board;
const root = new URL('../', import.meta.url);
const read = path => readFile(new URL(path, root), 'utf8');
const json = async path => JSON.parse(await read(path));
before(async () => {
  vite=await createServer({ configFile:false,root:fileURLToPath(root),server:{middlewareMode:true,hmr:false,ws:false},
    logLevel:'silent',optimizeDeps:{noDiscovery:true,include:[]} });
  [results,presentation,flags,fixtures,controls,ui,atlas,board]=await Promise.all([
    '/src/components/ResultPoster.tsx','/src/components/presentation.ts','/src/flags/flags.ts','/src/dev/board-fixtures.ts',
    '/src/components/Controls.tsx','/src/ui/components.tsx','/src/map/AtlasMap.tsx','/src/components/GameBoard.tsx',
  ].map(path=>vite.ssrLoadModule(path)));
});
after(async()=>{await vite?.close();});
function* nodes(node){if(Array.isArray(node)){for(const n of node)yield*nodes(n);}else if(isValidElement(node)){yield node;yield*nodes(node.props.children);}}
const render=(name,props)=>renderToStaticMarkup(createElement(results[name],props));
const game=mode=>fixtures.boardFixture(mode).game;

test('195 canonical flag mappings resolve to existing licensed, pinned and safe SVG bytes',async()=>{
  const catalog=await json('../backend/app/data/countries.json'), mapping=await json('src/flags/countries.json'), manifest=await json('public/assets/flags/manifest.json');
  assert.deepEqual(Object.keys(mapping).sort(),catalog.countries.map(c=>c.id).sort());
  assert.equal(Object.keys(mapping).length,195); assert.equal(new Set(Object.values(mapping)).size,195);
  assert.equal(manifest.version,'7.3.2');
  assert.equal((await readdir(new URL('public/assets/flags/',root))).filter(n=>n.endsWith('.svg')).length,195);
  for(const c of catalog.countries){
    const flag=flags.countryFlag(c.id);assert.equal(flag.src,`/assets/flags/${mapping[c.id]}.svg`);
    const svg=await read(`public${flag.src}`);assert.match(svg,/<svg\b/);assert.match(svg,/viewBox=/);
    assert.equal(createHash('sha256').update(svg).digest('hex'),manifest.countries[c.id].sha256);
    assert.doesNotMatch(svg,/<script|<foreignObject|\son\w+\s*=|(?:href|src)\s*=\s*["'](?:https?:|\/\/|data:)/i);
  }
  assert.match(await read('public/assets/flags/LICENSE'),/MIT License/);
});

test('unusual canonical names and presentation aliases map to distinct correct national flags',()=>{
  for(const [id,code]of Object.entries({'holy-see':'va','vatican-city':'va','czechia':'cz','czech-republic':'cz',
    'state-of-palestine':'ps',palestine:'ps',swaziland:'sz',eswatini:'sz','cabo-verde':'cv','brunei-darussalam':'bn',
    congo:'cg','democratic-republic-of-the-congo':'cd','north-korea':'kp','south-korea':'kr',uk:'gb',us:'us',
    'saint-vincent-and-the-grenadines':'vc','sao-tome-and-principe':'st'}))assert.equal(flags.countryFlag(id).src,`/assets/flags/${code}.svg`);
});

test('winner flag follows participant home identity rather than the last conquered country',()=>{
  const g=game('completed');const r=presentation.campaignResult(g);
  assert.equal(r.name,'Brazil');assert.equal(r.flag.src,'/assets/flags/br.svg');
  const holy=presentation.campaignResult(game('victory-holy-see'));
  assert.equal(holy.name,'Holy See');assert.equal(holy.flag.src,'/assets/flags/va.svg');
  assert.equal(holy.winner.id,'player-0');
});

test('missing mappings and failed image loads become named fallbacks without image retry or a broken img',()=>{
  for(const id of ['not-a-country','__proto__','constructor','../../auth/me','https://invalid.example/flag',null])assert.equal(flags.countryFlag(id),null);
  const missing=render('ResultFlagView',{src:null,name:'Unknown',failed:false,onError(){}});
  assert.match(missing,/Flag unavailable for Unknown/);assert.doesNotMatch(missing,/<img/);
  let errors=0;
  const image=results.ResultFlagView({src:'/assets/flags/br.svg',name:'Brazil',failed:false,onError:()=>errors++});
  assert.equal(image.props.alt,'Flag of Brazil');image.props.onError();assert.equal(errors,1);
  const failed=render('ResultFlagView',{src:'/assets/flags/br.svg',name:'Brazil',failed:true,onError(){}});
  assert.doesNotMatch(failed,/<img/);assert.match(failed,/National flag unavailable/);
});

test('human victory, spectator result and NPC victory use truthful distinct headings',()=>{
  const human=render('ResultPoster',{game:game('completed'),owner:true});
  assert.match(human,/id="campaign-result-outcome">Victory/);assert.match(human,/World Conqueror/);assert.match(human,/The world is yours/);assert.match(human,/Human winner/);
  const npc=render('ResultPoster',{game:game('npc-victory'),owner:true});
  assert.match(npc,/Campaign Over/);assert.match(npc,/Norway has won/);assert.match(npc,/Rival winner/);assert.doesNotMatch(npc,/The world is yours|World Conqueror/);
  const spectator=render('ResultPoster',{game:game('completed'),owner:false});
  assert.match(spectator,/Brazil has won/);assert.doesNotMatch(spectator,/The world is yours/);
});

test('poster count, total and round use actual supplied records rather than constant ten',()=>{
  const full=game('completed');
  const partial={...full,countries:full.countries.slice(0,7),round:8};
  const r=presentation.campaignResult(partial);assert.equal(r.held,7);assert.equal(r.total,7);assert.equal(r.allTen,false);
  const html=render('ResultPoster',{game:partial,owner:true});
  assert.match(html,/geo-result__number">7/);assert.match(html,/of 7 participating countries held/);assert.match(html,/Round 8/);
  assert.doesNotMatch(html,/The world is yours|Holds all ten/);
  const unknown=render('ResultPoster',{game:game('result-incomplete'),owner:true});
  assert.match(unknown,/Winner not recorded/);assert.match(unknown,/Territorial outcome not recorded/);assert.doesNotMatch(unknown,/geo-result__number|World Conqueror/);
});

test('remaining soldiers are summed exactly and missing or ambiguous data is not fabricated',()=>{
  const g=game('completed');g.countries.forEach(c=>c.soldiers=Number.MAX_SAFE_INTEGER);
  assert.equal(presentation.campaignResult(g).soldiers,(BigInt(Number.MAX_SAFE_INTEGER)*10n).toString());
  g.countries[0].soldiers=NaN;assert.equal(presentation.campaignResult(g).soldiers,null);
  const ambiguous={...g,players:[...g.players,g.players[0]]};assert.equal(presentation.campaignResult(ambiguous).winner,undefined);
});

test('active human elimination never shows a final poster',()=>{
  assert.equal(presentation.campaignResult(game('eliminated')),null);
  assert.equal(render('ResultPoster',{game:game('eliminated'),owner:true}),'');
});

test('completed poster keeps supported review navigation and suppresses leaving while pending',()=>{
  const props={game:game('completed'),owner:true,pending:true};
  const html=render('ResultPoster',props);
  assert.match(html,/href="#campaign-record"/);assert.doesNotMatch(html,/href="\/"|Watch replay|New campaign|<button/);
  assert.match(render('ResultPoster',{...props,pending:false}),/Return to My Games/);
});

test('completion entrance occurs only after an observed active revision advances; reload and rerender do not replay',()=>{
  const initial=presentation.observePresentation(null,game('human'));
  assert.equal(initial.celebrate,false);
  const completed={...game('completed'),revision:13};
  const next=presentation.observePresentation(initial.snapshot,completed);assert.equal(next.celebrate,true);
  assert.equal(presentation.observePresentation(next.snapshot,completed).celebrate,false);
  assert.equal(presentation.observePresentation(null,completed).celebrate,false);
  assert.equal(presentation.observePresentation(initial.snapshot,{...completed,revision:12}).celebrate,false);
});

test('conquest highlight requires a new ownership snapshot and matching committed conquest evidence',()=>{
  const initial=presentation.observePresentation(null,game('human')).snapshot;
  const conquered={...game('conquest'),revision:13};
  const event={type:'conquered',target_id:'canada',source_id:'brazil',actor_id:'player-0',round:2,turn_sequence:11,amount:2};
  assert.deepEqual(presentation.observePresentation(initial,conquered).captured,[]);
  const next=presentation.observePresentation(initial,conquered,[event]);assert.deepEqual(next.captured,['canada']);
  assert.deepEqual(presentation.observePresentation(next.snapshot,conquered,[event]).captured,[]);
  assert.deepEqual(presentation.observePresentation(null,conquered,[event]).captured,[]);
  assert.deepEqual(presentation.observePresentation(initial,conquered,[{...event,actor_id:'player-2'}]).captured,[]);
});

test('animation completion changes presentation only and cannot submit or duplicate a request',()=>{
  let settled=0,requests=0;const fetch=globalThis.fetch;globalThis.fetch=()=>{requests++;throw Error('No network');};
  try{
    const poster=results.ResultPoster({game:game('completed'),owner:true,celebrate:true,onSettled:()=>settled++});
    poster.props.onAnimationEnd({target:1,currentTarget:2});assert.equal(settled,0);
    poster.props.onAnimationEnd({target:1,currentTarget:1});assert.equal(settled,1);
    render('ResultPoster',{game:game('completed'),owner:true,celebrate:true});assert.equal(requests,0);
  }finally{globalThis.fetch=fetch;}
});

test('final map retains real participating ownership and neutral world geography',()=>{
  const g=game('completed'),p=board.boardPresentation(g,null,()=>{}).atlas;
  const paths=[...nodes(atlas.AtlasContent(p))].filter(e=>e.type==='path');
  assert.ok(paths.filter(e=>e.props['data-country']).every(e=>e.props.fill==='var(--geo-forest)'));
  assert.ok(paths.filter(e=>!e.props['data-country']).every(e=>e.props.fill==='var(--geo-land)'));
  assert.equal(paths.length,470);
});

test('attack comparison is directional, retains exact counts and uses name-only visible options',()=>{
  const state=fixtures.boardFixture();
  const element=controls.HumanControlsView({game:state.game,disabled:false,act(){},draft:{...controls.emptyControlDraft(),sourceId:'brazil',targetId:'canada'},onDraft(){}});
  const html=renderToStaticMarkup(element);
  assert.match(html,/aria-label="Attacking"/);assert.match(html,/One attack per turn/);assert.match(html,/dice exchanges/);
  const option=[...nodes(element)].find(e=>e.type==='option'&&e.props.value==='canada');
  assert.equal(option.props.children,'Canada');assert.equal(option.props['aria-label'],'Canada, 11 soldiers');
});

test('transfer explanations distinguish ownership eligibility from insufficient movable soldiers',()=>{
  const h=fixtures.boardFixture();const show=game=>controls.HumanControlsView({game,disabled:false,act(){},draft:controls.emptyControlDraft(),onDraft(){}});
  assert.match(renderToStaticMarkup(show(h.game)),/Hold at least two countries/);
  const two=game('conquest');two.countries.filter(c=>c.owner_id==='player-0').forEach(c=>c.soldiers=1);
  assert.match(renderToStaticMarkup(show(two)),/An owned source needs at least two soldiers/);
});

test('conquest reward and optional transfer remain distinct; reinforcement readiness uses the supplied total',()=>{
  const c=fixtures.boardFixture('conquest');
  const html=renderToStaticMarkup(createElement(controls.HumanControls,{game:c.game,disabled:false,latest:c.lastResult,act(){}}));
  assert.match(html,/Conquest reward: 2 soldiers added/);assert.match(html,/separate from any optional transfer/);assert.doesNotMatch(html,/Confirm conquest/);
  const a=fixtures.boardFixture('allocating'),calls=[];
  const element=controls.HumanControlsView({game:a.game,disabled:false,act:x=>calls.push(x),draft:{...controls.emptyControlDraft(),allocations:{brazil:4}},onDraft(){}});
  assert.equal([...nodes(element)].find(e=>e.props.className==='geo-command__budget').props['data-valid'],true);
  [...nodes(element)].find(e=>e.type==='form').props.onSubmit({preventDefault(){}});
  assert.deepEqual(calls,[{type:'allocate',allocations:[{country_id:'brazil',amount:4}]}]);
});

test('pending and spectator locks survive visual callbacks and new result presentation',()=>{
  const s=fixtures.boardFixture('pending'),calls=[];
  const element=controls.GameplayControls({game:s.game,owner:true,disabled:true,pending:true,busy:false,fastForward:false,
    act:x=>calls.push(x),step:()=>calls.push('step'),fast:()=>calls.push('fast'),pause:()=>calls.push('pause')});
  [...nodes(element)].filter(e=>e.type===ui.Button).forEach(e=>e.props.onClick?.());assert.deepEqual(calls,[]);
  assert.match(renderToStaticMarkup(element),/New moves are locked/);
  const spectator=controls.GameplayControls({game:s.game,owner:false,disabled:false,fastForward:false,act(){},step(){},fast(){},pause(){}});
  assert.equal([...nodes(spectator)].filter(e=>e.type===ui.Button).length,0);
});

test('motion is bounded, reduced-motion aware, listener-cleaned and never uses gameplay timers',async()=>{
  const poster=await read('src/components/result-poster.css'),button=await read('src/components/controls.css'),map=await read('src/map/atlas.css'),shell=await read('src/components/game-shell.css');
  for(const css of [poster,button,map,shell]){assert.match(css,/prefers-reduced-motion: reduce/);assert.doesNotMatch(css,/\binfinite\b/);}
  assert.match(poster,/geo-result-reveal 1000ms/);assert.match(poster,/object-fit: contain/);assert.match(button,/transform 140ms/);
  const source=await read('src/components/GameBoard.tsx');assert.match(source,/removeEventListener\('change', update\)/);
  assert.doesNotMatch(source,/setTimeout|setInterval|controller\.act|controller\.stepNpc/);
  const turn=renderToStaticMarkup(createElement(ui.TurnIndicator,{name:'Norway NPC',state:'active'}));
  assert.match(turn,/aria-current="step"/);assert.match(turn,/Playing/);
});

test('refined Brazil poster separates full flag artwork from count and gives the result a clear headline',()=>{
  const poster=results.ResultPoster({game:game('completed'),owner:true});
  assert.equal(poster.props['data-flag-layout'],'rectangular');
  const children=[...nodes(poster)], art=children.find(e=>e.props.className==='geo-result__art');
  assert.ok(art);assert.equal([...nodes(art)].some(e=>e.props.className==='geo-result__number'),false);
  assert.equal(children.find(e=>e.props.className==='geo-result__headline').props.children,'Victory');
  assert.equal(children.find(e=>e.type===results.ResultFlag).props.src,'/assets/flags/br.svg');
  assert.match(poster.props['aria-labelledby'],/campaign-result-outcome campaign-result-title/);
});

test('Nepal uses the irregular composition while Holy See uses the bright-flag treatment',()=>{
  const nepal=results.ResultPoster({game:game('victory-nepal'),owner:true});
  assert.equal(nepal.props['data-flag-layout'],'irregular');
  assert.equal([...nodes(nepal)].find(e=>e.type===results.ResultFlag).props.src,'/assets/flags/np.svg');
  const holy=results.ResultPoster({game:game('victory-holy-see'),owner:true});
  assert.equal(holy.props['data-flag-layout'],'bright');
  const html=render('ResultPoster',{game:game('npc-victory'),owner:true});
  assert.match(html,/Campaign Over/);assert.match(html,/Norway/);assert.doesNotMatch(html,/World Conqueror/);
});

test('result soldier formatting adds separators without losing large integer precision',()=>{
  assert.equal(results.formatResultSoldiers('1234693'),'1,234,693');
  assert.equal(results.formatResultSoldiers('0'),'0');
  assert.equal(results.formatResultSoldiers('90071992547409910'),'90,071,992,547,409,910');
  const g=game('completed');g.countries.forEach((c,i)=>c.soldiers=i===0?1234693:0);
  const html=render('ResultPoster',{game:g,owner:true});
  assert.match(html,/1,234,693 soldiers/);assert.doesNotMatch(html,/>1234693 soldiers/);
});

test('long winner names remain complete and unavailable statistics are omitted',()=>{
  const g=game('victory-long-name'), name=g.countries.find(c=>c.id===g.players[0].starting_country_id).name;
  const poster=results.ResultPoster({game:g,owner:true});
  assert.equal([...nodes(poster)].find(e=>e.props.id==='campaign-result-title').props.children,name);
  const unavailable=render('ResultPoster',{game:game('result-incomplete'),owner:true});
  assert.doesNotMatch(unavailable,/Round \d|0 soldiers|In the winner&#x27;s countries/);
  assert.match(unavailable,/Territorial outcome not recorded/);
});

test('review navigation remains primary, destinations are unchanged and pending suppresses leaving',()=>{
  const list=[...nodes(results.ResultPoster({game:game('completed'),owner:true}))];
  const links=list.filter(e=>e.type==='a');assert.equal(links.length,2);
  assert.equal(links.filter(e=>e.props.className==='geo-result__primary').length,1);
  assert.equal(links[0].props.href,'#campaign-record');assert.equal(links[1].props.href,'/');
  const pending=[...nodes(results.ResultPoster({game:game('completed'),owner:true,pending:true}))].filter(e=>e.type==='a');
  assert.deepEqual(pending.map(e=>e.props.href),['#campaign-record']);
});

test('preview campaign names are natural while offline safety notices stay outside the poster',async()=>{
  for(const mode of ['completed','victory-nepal','victory-holy-see','npc-victory','result-incomplete','result-missing-flag']){
    const html=render('ResultPoster',{game:game(mode),owner:true});assert.doesNotMatch(html,/OFFLINE|STAGE 4|fixture/i);
  }
  assert.match(fixtures.boardFixture().notice,/OFFLINE PRESENTATION FIXTURE/);
  const source=await read('src/dev/BoardPreview.tsx');assert.match(source,/isolated development fixtures only/);
});

test('poster CSS preserves entire flag geometry, stacks at tablet/mobile and uses contrast-safe count surfaces',async()=>{
  const css=await read('src/components/result-poster.css');
  assert.match(css,/object-fit: contain/);assert.match(css,/block-size: auto; aspect-ratio: 4 \/ 3/);
  assert.doesNotMatch(css,/object-fit: cover|rotate\(|text-overflow: ellipsis|white-space: nowrap/);
  assert.match(css,/max-width: 860px/);assert.match(css,/max-width: 450px/);
  assert.match(css,/geo-result__achievement[^}]*background: var\(--geo-parchment\)/);
  assert.match(css,/geo-result__number[^}]*color: var\(--geo-ink\)/);
  assert.match(css,/min-block-size: 48px/);assert.match(css,/outline: 3px solid var\(--geo-ink\); outline-offset: 2px/);
  assert.match(css,/overflow-wrap: anywhere/);assert.match(css,/prefers-reduced-motion/);
  assert.doesNotMatch(css,/geo-result__identity[^}]*background:/);
});
