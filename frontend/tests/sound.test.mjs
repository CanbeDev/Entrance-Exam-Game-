import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { verifyRuntimeSounds } from '../scripts/verify-sound-assets.mjs';
import { SoundService } from '../src/sound/service.ts';
import { SoundLedger } from '../src/sound/events.ts';
import { defaults, volumeBound, parsePreferences, preferenceKey, loadPreferences, savePreferences } from '../src/sound/preferences.ts';
import { soundAssets, soundUrl } from '../src/sound/assets.ts';
function audio() {
  const calls=[];let now=0,unavailable=0;
  const service=new SoundService(url=>{const voice={url,volume:0,currentTime:0,onerror:null,play:async()=>{},pause(){this.paused=true;}};calls.push(voice);return voice;},()=>now,()=>unavailable++);
  return {service,calls,setTime:t=>{now=t;},failed:()=>unavailable};
}
function state(revision=4) {return {gameId:'a'.repeat(24),game:{revision,status:'active',players:[{id:'h',kind:'human'},{id:'n',kind:'npc'}]},session:{user:{id:'account'}},owner:true,pending:null,events:[],fastForward:false};}
function receipt(revision=5,type='attack_started') {return {revision,action_id:`saved-${revision}`,actor:{kind:'npc',player_id:'n'},events:[{type}]};}
test('sound defaults muted, creates no media until enabled and activated',()=>{
  const {service,calls}=audio();assert.deepEqual(defaults,{enabled:false,volume:.35});
  service.play('attack');service.activate();service.play('attack');assert.equal(calls.length,0);
  service.configure({enabled:true,volume:.3});service.play('attack');assert.equal(calls.length,1);
});
test('restored enabled preference cannot bypass tab activation',()=>{
  const {service,calls}=audio();service.configure({enabled:true,volume:.5});assert.equal(service.play('dice'),false);assert.equal(calls.length,0);
});
test('only enabled/volume are stored; corrupt or extra-field records fail closed',()=>{
  let stored;global.window={localStorage:{getItem:key=>{assert.equal(key,preferenceKey);return stored;},setItem:(key,value)=>{assert.equal(key,preferenceKey);stored=value;}}};
  try {savePreferences({enabled:true,volume:.42,ignored:'not persisted'});assert.equal(stored,'{"enabled":true,"volume":0.42}');assert.deepEqual(loadPreferences(),{enabled:true,volume:.42});
    for(const raw of ['bad','null','{}','{"enabled":true,"volume":0.5,"token":"x"}','{"enabled":"yes","volume":0.5}'])assert.deepEqual(parsePreferences(raw),defaults);
  }finally{delete global.window;}
});
test('storage denial and absence are harmless; volume is bounded',()=>{
  global.window={get localStorage(){throw Error('denied');}};try{assert.deepEqual(loadPreferences(),defaults);assert.doesNotThrow(()=>savePreferences(defaults));}finally{delete global.window;}
  for(const [value,result]of [[-1,0],[2,1],[NaN,.35],[Infinity,.35],[.4,.4]])assert.equal(volumeBound(value),result);
});
test('PUBLIC sound assets have exact mappings, portable URLs and reviewed manifest hashes',async()=>{
  assert.equal(Object.keys(soundAssets).length,18);
  for(const event of Object.keys(soundAssets))assert.match(soundUrl(event),/^\/assets\/sounds\/[a-zA-Z]+\.mp3$/);
  assert.equal((await verifyRuntimeSounds()).length,18);
});
test('one voice at a time; mute and zero volume stop current playback',()=>{
  const {service,calls,setTime}=audio();service.configure({enabled:true,volume:.8});service.activate();service.play('dice');setTime(200);service.play('attack');assert.equal(calls[0].paused,true);
  service.configure({enabled:false,volume:.8});assert.equal(calls[1].paused,true);assert.equal(service.play('conquer'),false);
  service.configure({enabled:true,volume:0});assert.equal(service.play('dice'),false);
});
test('missing asset and rejected autoplay do not throw or touch gameplay',async()=>{
  let count=0;const service=new SoundService(()=>{throw Error('missing');},()=>0,()=>count++);service.activate();service.configure({enabled:true,volume:.3});assert.doesNotThrow(()=>service.play('attack'));assert.equal(count,1);
  const rejected=new SoundService(()=>({volume:0,currentTime:0,onerror:null,play:()=>Promise.reject(Error('NotAllowedError')),pause(){}}),()=>0,()=>count++);
  rejected.activate();rejected.configure({enabled:true,volume:.3});rejected.play('attack');await Promise.resolve();await Promise.resolve();assert.equal(count,2);
});
test('stale media rejection cannot interrupt a newer voice',async()=>{
  const {service,calls,setTime}=audio();service.activate();service.configure({enabled:true,volume:.3});service.play('attack');const old=calls[0].onerror;
  setTime(200);service.play('transfer');old();assert.equal(calls[1].paused,undefined);
});
test('fast-forward uses cooldown and no sound queue; important completion remains audible',()=>{
  const {service,calls,setTime}=audio();service.activate();service.configure({enabled:true,volume:.3});
  service.play('npc',{rapid:true});setTime(650);assert.equal(service.play('npc',{rapid:true}),false);setTime(1200);service.play('npc',{rapid:true});
  assert.equal(calls.length,2);service.play('victory',{important:true});assert.equal(calls.length,3);service.stop();
});
test('dice is not cut by animation/Skip; natural completion may play one follow-up',()=>{
  const {service,calls,setTime}=audio();service.activate();service.configure({enabled:true,volume:.3});
  service.exchange('receipt','conquer',false,false);assert.equal(calls[0].url,soundUrl('dice'));service.finishDice('other');assert.equal(calls.length,1);
  calls[0].onended();assert.equal(calls[1].url,soundUrl('conquer'));service.finishDice('receipt');assert.equal(calls.length,2);
  setTime(200);service.exchange('skipped','tie',false,false);const current=calls.at(-1);service.finishDice('skipped');assert.equal(current.paused,undefined);current.onended();assert.equal(calls.at(-1),current);service.stop();
});
test('reduced-motion dice remains playable rather than being paused at time zero',()=>{
  const {service,calls}=audio();service.activate();service.configure({enabled:true,volume:.3});service.exchange('reduced','tie',false,true);
  assert.equal(calls.length,1);assert.equal(calls[0].url,soundUrl('dice'));assert.equal(calls[0].paused,undefined);calls[0].onended();assert.equal(calls.length,1);service.stop();
});
test('rapid dice never queues a delayed result, and newer playback cancels stale media completion',()=>{
  const {service,calls,setTime}=audio();service.activate();service.configure({enabled:true,volume:.3});service.exchange('rapid','conquer',true,false);calls[0].onended();assert.equal(calls.length,1);
  setTime(1500);service.exchange('older','conquer',false,false);const older=calls[1];service.play('pause',{important:true});older.onended();assert.equal(calls.length,3);assert.equal(calls[2].url,soundUrl('pause'));service.stop();
});
test('inspection reports mute, activation, loading, playing, ended and safe failures without side effects',async()=>{
  const {service,calls}=audio();let notifications=0;const off=service.subscribe(()=>notifications++);
  service.play('attack');assert.equal(service.inspect().phase,'muted');service.configure({enabled:true,volume:.3});service.play('attack');assert.equal(service.inspect().phase,'activation-required');
  service.activate();service.play('attack');assert.equal(service.inspect().phase,'loading');await Promise.resolve();assert.equal(service.inspect().phase,'playing');calls[0].onended();assert.equal(service.inspect().phase,'ended');assert.ok(notifications>0);off();service.stop();
  const rejected=new SoundService(()=>({volume:0,currentTime:0,onerror:null,play:()=>Promise.reject(new DOMException('Denied','NotAllowedError')),pause(){}}));rejected.activate();rejected.configure({enabled:true,volume:.3});rejected.play('attack');await Promise.resolve();await Promise.resolve();assert.equal(rejected.inspect().phase,'blocked');
});
test('historical load, duplicate receipts, backwards boards and remount baseline never replay',()=>{
  const ledger=new SoundLedger(),s=state();s.events=[receipt(4)];assert.deepEqual(ledger.observe(s),[]);
  s.game.revision=5;s.events.push(receipt());assert.equal(ledger.observe(s)[0].event,'attack');assert.deepEqual(ledger.observe(s),[]);
  s.game.revision=4;assert.deepEqual(ledger.observe(s),[]);s.game.revision=8;s.events.push(receipt(8));ledger.baseline(s);assert.deepEqual(ledger.observe(s),[]);
});
test('board advancing before history arrives does not lose the newly committed cue',()=>{
  const ledger=new SoundLedger(),s=state();ledger.observe(s);s.game.revision=5;assert.deepEqual(ledger.observe(s),[]);s.events=[receipt()];assert.equal(ledger.observe(s)[0].event,'attack');
});
test('uncertain writes are silent until matching committed history is definitively reconciled',()=>{
  const ledger=new SoundLedger(),s=state();ledger.observe(s);s.pending={kind:'npc'};s.game.revision=5;s.events=[receipt()];assert.deepEqual(ledger.observe(s),[]);
  s.pending=null;assert.equal(ledger.observe(s)[0].event,'attack');assert.deepEqual(ledger.observe(s),[]);
});
test('spectators, new account context, opening another game and missing identity produce no cue',()=>{
  const ledger=new SoundLedger(),s=state();ledger.observe(s);s.owner=false;s.game.revision=5;s.events=[receipt()];assert.deepEqual(ledger.observe(s),[]);s.owner=true;assert.deepEqual(ledger.observe(s),[]);
  s.session.user.id='other';s.game.revision=6;assert.deepEqual(ledger.observe(s),[]);s.gameId='b'.repeat(24);assert.deepEqual(ledger.observe(s),[]);s.game.revision=7;s.events=[{...receipt(7),action_id:''}];assert.deepEqual(ledger.observe(s),[]);
});
test('new human/NPC dice use exact receipt identity and one representative aftermath',()=>{
  const ledger=new SoundLedger(),s=state();ledger.observe(s);s.game.revision=5;s.fastForward=true;s.events=[receipt(5,'dice_exchange')];s.events[0].events[0].attacker_losses=0;s.events[0].events[0].defender_losses=0;
  assert.deepEqual(ledger.observe(s),[{event:'dice',id:`${s.gameId}:5:saved-5`,after:'tie',rapid:true}]);
  s.game.revision=6;s.events=[receipt(6,'dice_exchange')];s.events[0].events.push({type:'conquered'});assert.equal(ledger.observe(s)[0].after,'conquer');
});
test('only a new committed completion plays exactly victory or defeat; old completed loads stay silent',()=>{
  for(const winner of ['h','n']){const ledger=new SoundLedger(),s=state();ledger.observe(s);s.game={...s.game,revision:5,status:'completed',winner};s.events=[receipt(5,'victory')];assert.equal(ledger.observe(s)[0].event,winner==='h'?'victory':'defeat');assert.deepEqual(ledger.observe(s),[]);assert.deepEqual(new SoundLedger().observe(s),[]);}
});
test('new campaign sound requires observed creation; opening/resuming a game is silent',()=>{
  const ledger=new SoundLedger(),s=state();s.gameId=null;s.game=null;s.pending={kind:'create'};ledger.observe(s);s.pending=null;s.gameId='c'.repeat(24);s.game={revision:0};assert.equal(ledger.observe(s)[0].event,'campaign');assert.deepEqual(new SoundLedger().observe(s),[]);
});
test('all remaining committed event categories select truthful cues without changing state',()=>{
  for(const [type,cue]of [['transferred','transfer'],['allocated','allocate'],['turn_ended','endTurn'],['conquered','conquer'],['attack_started','attack']]){const ledger=new SoundLedger(),s=state();ledger.observe(s);s.game.revision=5;s.events=[receipt(5,type)];const before=JSON.stringify(s);assert.equal(ledger.observe(s)[0].event,cue);assert.equal(JSON.stringify(s),before);}
});
test('sound modules have no gameplay/network dependency or mutation submission',async()=>{
  for(const file of ['service.ts','assets.ts','preferences.ts','events.ts','SoundSettings.tsx']){const text=await readFile(new URL(`../src/sound/${file}`,import.meta.url),'utf8');assert.doesNotMatch(text,/\b(?:fetch|XMLHttpRequest|WebSocket|act|stepNpc|retryPending|generateBattleCommentary)\s*\(/);}
});
