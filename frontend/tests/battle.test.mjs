import { after,before,test } from 'node:test';import assert from 'node:assert/strict';
import {createElement,isValidElement} from 'react';import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';import {fileURLToPath} from 'node:url';import {readFile} from 'node:fs/promises';
import {dicePairs,exchangeCounts,exchangeIdentity,createExchangeLedger,mergeCounts,newlyObservedExchange} from '../src/components/battle-view.ts';
let vite,battle,fixtures,commentary,history;
before(async()=>{vite=await createServer({configFile:false,root:fileURLToPath(new URL('../',import.meta.url)),server:{middlewareMode:true,hmr:false,ws:false},logLevel:'silent',optimizeDeps:{noDiscovery:true,include:[]}});
[battle,fixtures,commentary,history]=await Promise.all(['/src/components/BattleExchange.tsx','/src/dev/battle-fixtures.ts','/src/components/BattleCommentary.tsx','/src/components/History.tsx'].map(p=>vite.ssrLoadModule(p)));});
after(async()=>{await vite?.close();});
function*nodes(n){if(Array.isArray(n)){for(const c of n)yield*nodes(c);}else if(isValidElement(n)){yield n;yield*nodes(n.props.children);}}
function view(mode='battle-six',rolling=false){const s=fixtures.battleFixture(mode),entry=s.events[0],calls=[];
const props={game:s.game,entry,index:0,counts:exchangeCounts(entry,entry.events[0],s.game),rolling,skip:()=>calls.push('skip'),settled:()=>calls.push('settled')};
return{state:s,props,calls,element:battle.BattleExchangeView(props)};}
const html=element=>renderToStaticMarkup(element);

test('pip faces render exactly one through six backend pips with accessible side/value names',()=>{
for(let value=1;value<=6;value++){const markup=html(createElement(battle.Die,{value,side:'Attacker'}));
assert.equal((markup.match(/data-pip="true"/g)||[]).length,value);assert.match(markup,new RegExp(`Attacker rolled ${value}`));}
assert.match(html(createElement(battle.Die,{value:null,side:'Defender'})),/Defender die not recorded/);
});
test('all six and twelve pairs remain in saved order without sorting, caps or input mutation',()=>{
for(const mode of ['battle-six','battle-many']){const v=view(mode),event=v.props.entry.events[0],before=JSON.stringify(event),pairs=dicePairs(event);
assert.equal(pairs.length,mode==='battle-many'?12:6);assert.deepEqual(pairs.map(p=>p.attacker),event.attacker_dice);assert.deepEqual(pairs.map(p=>p.defender),event.defender_dice);
assert.equal((html(v.element).match(/data-pair=/g)||[]).length,pairs.length);assert.equal(JSON.stringify(event),before);}
});
test('ties, attacker casualties and defender casualties use indexed pairs and the committed summary fields',()=>{
for(const [mode,label]of [['battle-ties','Tie — no loss'],['battle-attacker-loss','Attacker loses 1'],['battle-defender-loss','Defender loses 1']]){
const v=view(mode),pairs=dicePairs(v.props.entry.events[0]);assert.ok(pairs.every(p=>p.result===label));
assert.ok(html(v.element).includes(`Attacker losses: ${v.props.entry.events[0].attacker_losses}`));}
const v=view('battle-ties');assert.match(html(v.element),/6 ties — no loss/);assert.match(html(v.element),/Defender losses: 0/);
});
test('missing dice/losses show partial results and never fabricated faces or default zero losses',()=>{
const v=view('battle-missing'),pairs=dicePairs(v.props.entry.events[0]);assert.ok(pairs.every(p=>p.defender===null&&p.result==='Result not recorded'));
assert.match(html(v.element),/Defender losses: not recorded/);assert.match(html(v.element),/Ties not fully recorded/);
const partial={...v.props.entry.events[0],attacker_dice:[6,2],defender_dice:[1]};assert.equal(dicePairs(partial)[1].defender,null);
});
test('latest exact-revision counts derive safely from the committed board and losses; later boards are not reused',()=>{
const v=view(),e=v.props.entry.events[0],counts=v.props.counts;assert.equal(counts.attackerBefore,counts.attackerAfter+e.attacker_losses);assert.equal(counts.defenderBefore,counts.defenderAfter+e.defender_losses);
const older=exchangeCounts(v.props.entry,e,{...v.props.game,revision:99});assert.equal(older.attackerAfter,null);assert.equal(older.defenderBefore,null);
});
test('conquest zero after-exchange and separately applied reward/current board are never conflated',()=>{
const v=view('battle-conquest');assert.equal(v.props.counts.defenderAfter,0);assert.equal(v.props.counts.defenderBefore,2);assert.equal(v.props.counts.defenderCurrent,2);
assert.match(html(v.element),/Conquest reward: 2 soldiers added separately/);assert.match(html(v.element),/After conquest reward: 2 soldiers/);
});
test('adjacent before-snapshot and cached counts survive later revision display without guessing historical state',()=>{
const v=view();const previous={...v.props.game,revision:11,countries:v.props.game.countries.map(c=>({...c,soldiers:c.id==='brazil'?30:c.id==='canada'?20:c.soldiers}))};
const derived=exchangeCounts(v.props.entry,v.props.entry.events[0],{...v.props.game,revision:99},previous);
assert.equal(derived.attackerBefore,30);assert.equal(derived.attackerAfter,28);
const unknown=exchangeCounts(v.props.entry,v.props.entry.events[0],{...v.props.game,revision:99});assert.deepEqual(mergeCounts(derived,unknown),derived);
const multi={...v.props.entry,events:[...v.props.entry.events,...v.props.entry.events]};assert.equal(exchangeCounts(multi,multi.events[0],v.props.game).attackerBefore,null);
});
test('receipt identity distinguishes repeated identical dice by revision, action and event index',()=>{
const state=fixtures.battleFixture('battle-repeated'),next=fixtures.advanceBattleFixture(state),old=state.events[0],fresh=next.events.at(-1);
assert.deepEqual(fresh.events[0].attacker_dice,old.events[0].attacker_dice);assert.notEqual(exchangeIdentity(state.gameId,old,0),exchangeIdentity(state.gameId,fresh,0));
assert.notEqual(exchangeIdentity(state.gameId,old,0),exchangeIdentity(state.gameId,old,1));
});
test('animation ledger claims a new exchange once; initial history, refetch, reparent and reduced motion do not replay',()=>{
const ledger=createExchangeLedger(12);assert.equal(ledger.claim('old',12,true),false);assert.equal(ledger.claim('new',13,true),true);
assert.equal(ledger.claim('new',13,true),false);assert.equal(ledger.claim('reduced',14,false),false);assert.equal(ledger.claim('reduced',14,true),false);
assert.equal(createExchangeLedger(null).claim('unknown',13,true),false);
assert.equal(newlyObservedExchange(13,13,12),true);assert.equal(newlyObservedExchange(13,14,12),true);
assert.equal(newlyObservedExchange(13,20,20),false);assert.equal(newlyObservedExchange(21,20,19),false);
});
test('rolling/skip/settle are presentation callbacks and do not fetch, alter dice or issue another roll',()=>{
const fetch=globalThis.fetch;let requests=0;globalThis.fetch=()=>{requests++;throw Error('No requests');};
try{const v=view('battle-six',true),before=JSON.stringify(v.props.entry),list=[...nodes(v.element)];
list.find(n=>n.type==='button').props.onClick();list.find(n=>n.props.className==='geo-battle__pairs').props.onAnimationEnd({animationName:'geo-die-roll'});
assert.deepEqual(v.calls,['skip','settled']);assert.equal(JSON.stringify(v.props.entry),before);assert.equal(requests,0);assert.match(html(v.element),/Saved dice values/);
}finally{globalThis.fetch=fetch;}
});
test('in-flight current battle contains no fabricated result and keeps known counts',()=>{
const state=fixtures.battleFixture('battle-inflight'),text=html(createElement(battle.ActiveBattle,{game:state.game,pending:true}));
assert.match(text,/awaiting confirmation/);assert.doesNotMatch(text,/data-value=|rolled [1-6]/);assert.match(text,/Brazil: 10 soldiers/);
assert.equal(html(createElement(battle.ActiveBattle,{game:fixtures.battleFixture('battle-stopped').game})), '');
});
test('commentary presentation preserves saved prose, clean label and existing explicit callbacks only',()=>{
const v=view(),calls=[];const value={status:'ready',source:'groq',text:'The defenders held their ground.',action_id:v.props.entry.action_id};
const element=commentary.BattleCommentaryView({game:v.props.game,entry:v.props.entry,display:{commentary:value,loading:false,error:null,requested:false},canGenerate:false,generate:()=>calls.push('generate'),check:()=>calls.push('check')});
const text=html(element);assert.match(text,/<h5>Commentary<\/h5>/);assert.match(text,/The defenders held their ground/);assert.doesNotMatch(text,/AI Commentary|AI-generated|Written by AI|LLM|Groq/i);assert.deepEqual(calls,[]);
const missing=commentary.BattleCommentaryView({game:v.props.game,entry:v.props.entry,display:{commentary:{status:'not_generated'},loading:false,error:null,requested:false},canGenerate:true,generate:()=>calls.push('generate'),check:()=>calls.push('check')});
assert.doesNotMatch(html(missing),/geo-commentary/);[...nodes(missing)].find(e=>e.type==='button'&&e.props.children==='Check saved commentary').props.onClick();assert.deepEqual(calls,['check']);
});
test('History keeps one saved commentary panel and all committed facts without rendering requests',()=>{
const v=view(),api={generateBattleCommentary(){throw Error('No generation during render');},events(){throw Error('No read during render');}};
const text=html(createElement(history.History,{game:v.props.game,events:[v.props.entry],latest:null,more:false,disabled:false,loadMore(){},api,gameId:v.state.gameId,
canGenerateCommentary:false,commentaryAccountId:null,liveCommentaryAllowed:false,canStartCommentary:()=>false}));
assert.equal((text.match(/aria-label="Commentary for move 12"/g)||[]).length,1);assert.equal((text.match(/data-pair=/g)||[]).length,6);
assert.doesNotMatch(text,/Generate commentary|Commentary for new battles/);
});
test('large values format legibly and all pair faces retain fixed readable size at responsive breakpoints',async()=>{
assert.match(html(view('battle-large').element),/1,234,565/);
const css=await readFile(new URL('../src/components/battle.css',import.meta.url),'utf8');assert.match(css,/inline-size: 44px; block-size: 44px/);assert.match(css,/max-width: 700px/);assert.match(css,/overflow-y: auto/);assert.match(css,/prefers-reduced-motion: reduce/);assert.match(css,/visibility: visible/);
assert.match(css,/geo-die-roll 650ms/);assert.doesNotMatch(css,/infinite/);
});
test('battle presentation introduces no randomness, gameplay timers or alternate controller',async()=>{
const source=await readFile(new URL('../src/components/BattleExchange.tsx',import.meta.url),'utf8');
assert.doesNotMatch(source,/Math\.random|randomUUID|setTimeout|setInterval|new GameController|\.act\(|\.stepNpc\(/);
assert.match(source,/removeEventListener\('change'/);assert.match(source,/setRolling\(false\)/);
});
