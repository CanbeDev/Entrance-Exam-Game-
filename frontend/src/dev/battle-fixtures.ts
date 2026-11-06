// Deterministic battle UI fixtures only; not an engine and never imported by the app entry.
import type { AppState } from '../game/controller.ts';
import type { PublicCommittedAction, PublicGameEvent } from '../api/index.ts';
import { boardFixture } from './board-fixtures.ts';
export const battleModes = ['battle-ready','battle-inflight','battle-six','battle-many','battle-ties','battle-attacker-loss',
  'battle-defender-loss','battle-mixed','battle-repeated','battle-conquest','battle-stopped','battle-spectator','battle-pending','battle-missing','battle-large','battle-npc','battle-npc-fast-forward'] as const;
export type BattleMode = typeof battleModes[number];
export function battleFixture(mode: BattleMode): AppState {
  const state=boardFixture('attacking'), game=state.game!;
  let a=[6,4,3,2,2,1],d=[5,4,1,6,3,1];
  if(mode==='battle-many'){a=[6,2,4,1,5,3,6,2,4,1,5,3];d=[1,5,4,3,2,6,1,5,4,3,2,6];}
  if(mode==='battle-ties'||mode==='battle-repeated'){a=[1,2,3,4,5,6];d=[...a];}
  if(mode==='battle-attacker-loss'){a=[1,2,3];d=[6,5,4];}
  if(mode==='battle-defender-loss'){a=[6,5,4];d=[1,2,3];}
  if(mode==='battle-conquest'){a=[6,6];d=[1,2];}
  const al=a.filter((n,i)=>n<d[i]!).length,dl=d.filter((n,i)=>n<a[i]!).length;
  const source=mode==='battle-large'?1234567:mode==='battle-repeated'?7:10+a.length;
  const countries=game.countries!.map(c=>({...c, soldiers:c.id==='brazil'?source-al:c.id==='canada'?d.length-dl:c.soldiers}));
  const event:{-readonly [K in keyof PublicGameEvent]:PublicGameEvent[K]}={type:'dice_exchange',actor_id:'player-0',round:2,turn_sequence:11,source_id:'brazil',target_id:'canada',
    attacker_dice:a,defender_dice:d,attacker_losses:al,defender_losses:dl};
  const events:PublicGameEvent[]=[event];
  if(mode==='battle-conquest') {countries.find(c=>c.id==='canada')!.owner_id='player-0';countries.find(c=>c.id==='canada')!.soldiers=2;
    events.push({type:'conquered',actor_id:'player-0',round:2,turn_sequence:11,source_id:'brazil',target_id:'canada',amount:2});}
  if(mode==='battle-missing'){delete event.defender_dice;delete event.defender_losses;}
  state.game={...game,countries,phase:mode==='battle-conquest'||mode==='battle-stopped'?'post_attack':'attacking',
    battle:mode==='battle-conquest'||mode==='battle-stopped'?null:game.battle,attack_used:true};
  const entry:PublicCommittedAction={revision:12,action_id:'offline-battle-12',actor:{kind:'human',player_id:'player-0'},
    committed_at:'2026-11-02T00:00:00Z',events,npc_decision:null};
  state.events=[entry];state.lastResult={state:state.game,events};
  if(mode==='battle-ready'||mode==='battle-inflight'){state.events=[];state.lastResult=null;state.game={...state.game,countries:countries.map(c=>({...c,soldiers:c.id==='brazil'?10:c.id==='canada'?6:c.soldiers}))};}
  if(mode==='battle-inflight'||mode==='battle-pending'){
    state.busy=mode==='battle-inflight';state.pending={kind:'human',account:state.session!.user,
      operation:{gameId:state.gameId!,command:{action_id:'offline-unresolved-roll',expected_revision:12,action:{type:'roll'}}}};
  }
  if(mode==='battle-spectator'){state.owner=false;state.session=null;}
  if(mode==='battle-npc'||mode==='battle-npc-fast-forward'){
    state.game={...state.game,players:state.game.players!.map(player=>({...player,kind:player.id==='player-3'?'human' as const:'npc' as const}))};
    const decision=boardFixture('npc').events[0]!.npc_decision!;
    state.events=[{...entry,actor:{kind:'npc',player_id:'player-0'},npc_decision:{...decision,
      explanation:'Synthetic saved NPC decision: continue the recorded attack from Brazil against Canada.',
      evaluation:{...decision.evaluation,actor_id:'player-0'}}}];
    state.lastResult={state:state.game,events,npc_decision:state.events[0]!.npc_decision};
    state.fastForward=mode==='battle-npc-fast-forward';
  }
  if(mode==='battle-stopped'){
    state.game={...state.game,revision:13,turn_sequence:12,phase:'deciding',current_turn:0,battle:null};
    const stopped:PublicGameEvent={type:'attack_stopped',actor_id:'player-0',round:2,turn_sequence:11,source_id:'brazil',target_id:'canada'};
    state.events=[entry,{...entry,revision:13,action_id:'offline-stop-13',events:[stopped]}];state.lastResult={state:state.game,events:[stopped]};
  }
  return state;
}
export function advanceBattleFixture(state: AppState): AppState {
  const game=state.game!, battle=game.battle;
  if(!battle||state.pending)return state;
  const source=game.countries!.find(c=>c.id===battle.source_id)!,target=game.countries!.find(c=>c.id===battle.target_id)!;
  const length=Math.min(source.soldiers-1,target.soldiers);
  const prior=state.events.at(-1)?.events.find(e=>e.type==='dice_exchange');
  const repeat=prior?.attacker_dice?.length===length&&prior.defender_dice?.length===length&&prior.attacker_dice.every((n,i)=>n===prior.defender_dice![i]);
  const a=repeat?[...prior!.attacker_dice!]:Array.from({length},(_,i)=>[6,2,4,1][i%4]!),d=repeat?[...prior!.defender_dice!]:Array.from({length},(_,i)=>[1,5,4,3][i%4]!);
  const al=a.filter((n,i)=>n<d[i]!).length,dl=d.filter((n,i)=>n<a[i]!).length;
  const revision=game.revision!+1;
  const events:PublicGameEvent[]=[{type:'dice_exchange',actor_id:'player-0',round:game.round!,turn_sequence:game.turn_sequence!,source_id:source.id,target_id:target.id,
    attacker_dice:a,defender_dice:d,attacker_losses:al,defender_losses:dl}];
  const countries=game.countries!.map(c=>({...c,soldiers:c.id===source.id?c.soldiers-al:c.id===target.id?c.soldiers-dl:c.soldiers}));
  const conquered=countries.find(c=>c.id===target.id)!.soldiers===0;
  if(conquered){const c=countries.find(c=>c.id===target.id)!;c.soldiers=2;c.owner_id=source.owner_id;
    events.push({type:'conquered',actor_id:'player-0',round:game.round!,turn_sequence:game.turn_sequence!,source_id:source.id,target_id:target.id,amount:2});}
  const next={...game,revision,countries,phase:conquered?'post_attack' as const:'attacking' as const,battle:conquered?null:battle};
  const actor=game.players!.find(player=>player.id===source.owner_id)!;
  const decision=actor.kind==='npc'?state.events.at(-1)?.npc_decision:null;
  const entry:PublicCommittedAction={revision,action_id:`offline-battle-${revision}`,actor:{kind:actor.kind,player_id:actor.id},committed_at:'2026-11-02T00:00:01Z',events,npc_decision:decision};
  return {...state,game:next,events:[...state.events,entry],lastResult:{state:next,events,npc_decision:decision}};
}
