import { before,after,test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createElement,isValidElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { fileURLToPath } from 'node:url';
let vite,facts,card,atlas,fixtures;
const read=path=>readFile(new URL(path,import.meta.url),'utf8');
before(async()=>{
  vite=await createServer({configFile:false,root:fileURLToPath(new URL('../',import.meta.url)),server:{middlewareMode:true,hmr:false,ws:false},logLevel:'silent',optimizeDeps:{noDiscovery:true,include:[]}});
  [facts,card,atlas,fixtures]=await Promise.all(['/src/country/facts.ts','/src/country/CountryCard.tsx','/src/map/AtlasMap.tsx','/src/dev/board-fixtures.ts'].map(path=>vite.ssrLoadModule(path)));
});
after(async()=>{await vite?.close();});
const render=(id,game)=>renderToStaticMarkup(createElement(card.CountryCard,{id,game,dismiss(){}}));
function* nodes(node){if(Array.isArray(node)){for(const n of node)yield*nodes(n);}else if(isValidElement(node)){yield node;yield*nodes(node.props.children);}}
test('reference matches all 195 exact canonical identities and populations with no invented rows',async()=>{
  const catalog=JSON.parse(await read('../../backend/app/data/countries.json'));
  assert.deepEqual(facts.canonicalCountries.map(c=>[c.id,c.name,c.population]),catalog.countries.map(c=>[c.id,c.name,c.population]));
  assert.equal(new Set(facts.canonicalCountries.map(c=>c.id)).size,195);
  for(const c of catalog.countries)assert.equal(facts.countryFacts(c.id).startingSoldiers,[5,10,25,50,75,100,125,150].filter(n=>c.population>n*1e6).length+1);
});
test('capital lookup uses exact ISO join from source; qualified entries stay unavailable',async()=>{
  const source=await read('../data/geonames-countryInfo.txt');
  const sourceRows=new Map(source.split(/\r?\n/).filter(s=>s&&!s.startsWith('#')).map(line=>{const f=line.split('\t');return[f[0].toLowerCase(),f[5].trim()];}));
  const flags=JSON.parse(await read('../src/flags/countries.json'));
  for(const c of facts.canonicalCountries)if(c.capital)assert.equal(c.capital,sourceRows.get(flags[c.id]));
  assert.equal(facts.countryFacts('uk').capital,'London');assert.equal(facts.countryFacts('singapore').capital,'Singapore');
  assert.equal(facts.countryFacts('south-africa').capital,null);assert.equal(facts.countryFacts('state-of-palestine').capital,null);
});
test('presentation aliases use existing flags without changing canonical geography or source IDs',()=>{
  for(const[a,b]of [['united-kingdom','uk'],['vatican-city','holy-see'],['eswatini','swaziland'],['cape-verde','cabo-verde']])assert.equal(facts.countryFacts(a).id,b);
  assert.equal(facts.countryFacts('unrecognised'),null);assert.equal(facts.countryFacts('congo').flag.src,'/assets/flags/cg.svg');assert.equal(facts.countryFacts('democratic-republic-of-the-congo').flag.src,'/assets/flags/cd.svg');
});
test('actual saved-game population and initial allocation remain separate from current soldiers',()=>{
  const game=fixtures.boardFixture('human').game;const c=game.countries.find(c=>c.id==='uk');c.population=12345;c.base_soldier_value=6;c.soldiers=234;
  const m=facts.countryFacts('uk',game);assert.equal(m.population,12345);assert.equal(m.startingSoldiers,6);assert.equal(m.currentSoldiers,234);
  const html=render('uk',game);assert.match(html,/Starting soldiers<\/dt><dd>6/);assert.match(html,/Current soldiers<\/dt><dd>234/);assert.match(html,/12,345/);
});
test('current owner kind and authoritative target/from flags do not follow country nationality',()=>{
  const game=fixtures.boardFixture('attacking').game;
  const uk=game.countries.find(c=>c.id==='uk');uk.owner_id=game.players.find(p=>p.kind==='human').id;
  assert.match(facts.countryFacts('uk',game).owner,/Human/);
  const target=game.battle.target_id;assert.equal(facts.countryFacts(target,game).target,true);assert.match(render(target,game),/TARGET/);
  assert.equal(facts.countryFacts(game.battle.source_id,game).from,true);game.status='completed';assert.equal(facts.countryFacts(target,game).target,false);
});
test('neutral countries never receive invented current soldiers, ownership or NPC status',()=>{
  const game=fixtures.boardFixture('human').game,m=facts.countryFacts('andorra',game),html=render('andorra',game);
  assert.equal(m.participating,false);assert.equal(m.currentSoldiers,null);assert.equal(m.owner,null);assert.match(html,/Neutral · Not participating/);assert.doesNotMatch(html,/Current soldiers|Held by|\(NPC\)/);
});
test('unavailable capital, missing saved values and unknown ID remain truthful',()=>{
  const html=render('south-africa');assert.doesNotMatch(html,/Capital reference/);
  assert.match(render('unknown'),/Country information is unavailable/);
  const game=fixtures.boardFixture('human').game,c=game.countries.find(c=>c.id==='uk');delete c.base_soldier_value;delete c.population;
  assert.equal(facts.countryFacts('uk',game).population,null);assert.equal(facts.countryFacts('uk',game).startingSoldiers,null);assert.match(render('uk',game),/Not recorded/);
});
test('card layout clamps to available width and remains inline on mobile',async()=>{
  for(const width of [0,200,375,768,1440])for(const x of [-100,0,2000]){const p=facts.cardPosition(x,width);assert.ok(p.left>=0);assert.ok(p.left+p.width<=width);}
  const css=await read('../src/country/country.css');assert.match(css,/@media \(max-width: 700px\)/);assert.match(css,/margin-inline-start: 0/);assert.doesNotMatch(css,/position:\s*(?:fixed|absolute)/);
  assert.match(render('saint-vincent-and-the-grenadines'),/St. Vincent &amp; Grenadines/);
});
test('keyboard-readable card supports explicit dismissal and shows only compact country information',()=>{
  const html=render('holy-see');assert.match(html,/tabindex="-1"/);assert.match(html,/Close country information/);assert.match(html,/Flag of Holy See/);assert.doesNotMatch(html,/<a\b|Military History|Read the history/);
});
test('information lookup and rendering do not alter game state or create any request',()=>{
  const game=fixtures.boardFixture('pending').game,before=JSON.stringify(game);
  for(const c of facts.canonicalCountries){facts.countryFacts(c.id,game);render(c.id,game);}assert.equal(JSON.stringify(game),before);
});
test('neutral map shapes invoke only the new informational callback; participating selection remains existing callback',async()=>{
  const game=fixtures.boardFixture('human').game;
  const selected=[],inspected=[];const {boardPresentation}=await vite.ssrLoadModule('/src/components/GameBoard.tsx');
  const props=boardPresentation(game,null,id=>selected.push(id)).atlas;
  const tree=atlas.AtlasContent({...props,onInspect:id=>inspected.push(id)});
  const neutral=[...nodes(tree)].find(n=>n.type==='path'&&n.props['data-inspectable']==='france');assert.ok(neutral);neutral.props.onClick();assert.deepEqual(inspected,['france']);assert.deepEqual(selected,[]);
  const token=[...nodes(tree)].find(n=>n.type==='button'&&n.props['data-map-country']==='uk');token.props.onClick();assert.deepEqual(selected,['uk']);
});
test('information sources and UI have no provider/gameplay networking or ownership decisions',async()=>{
  for(const path of ['../src/country/facts.ts','../src/country/CountryCard.tsx']){const text=await read(path);assert.doesNotMatch(text,/\b(?:fetch|XMLHttpRequest|WebSocket|act|stepNpc|retryPending|generateBattleCommentary)\s*\(/);}
});
