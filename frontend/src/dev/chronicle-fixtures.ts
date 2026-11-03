import { boardFixture } from './board-fixtures.ts';
import { battleFixture } from './battle-fixtures.ts';
import type { PublicCommittedAction } from '../api/index.ts';

export const chronicleModes = ['npc-paused', 'npc-confirming', 'chronicle-many', 'chronicle-missing', 'chronicle-commentary', 'recovery-login'] as const;
export type ChronicleMode = typeof chronicleModes[number];
export function chronicleFixture(mode: ChronicleMode) {
  const state = mode.startsWith('chronicle-') ? battleFixture('battle-six') : boardFixture(mode === 'npc-paused' ? 'npc' : 'pending');
  if (mode === 'npc-confirming') { state.busy = true; state.confirmingPending = true; }
  if (mode === 'recovery-login') { state.session = null; state.owner = false; }
  if (mode === 'chronicle-many') {
    const battle = state.events[0]!;
    const decision = boardFixture('npc').events[0]!.npc_decision!;
    state.events = Array.from({ length: 125 }, (_, index): PublicCommittedAction => ({
      revision: index + 1, action_id: `offline-history-${index + 1}`, actor: battle.actor,
      committed_at: '2026-11-02T12:00:00Z',
      events: [{ type: 'transferred', actor_id: battle.actor.player_id, round: Math.floor(index / 10) + 1,
        turn_sequence: index, source_id: 'norway', target_id: 'australia', amount: index + 1 }],
    }));
    state.events = [...state.events, { ...battle, actor: { kind: 'npc', player_id: 'player-3' }, revision: 126, action_id: 'offline-history-battle-126',
      events: battle.events.map(event => ({ ...event, actor_id: 'player-3', source_id: 'norway', target_id: 'australia' })),
      npc_decision: { ...decision, explanation: 'Synthetic fixture reasoning: Saint Vincent and the Grenadines holds the recorded position. This long explanation exercises wrapping; it is not a prediction of a future NPC decision. '.repeat(4) } }];
    state.game = { ...state.game!, revision: 126 }; state.moreEvents = true;
  }
  if (mode === 'chronicle-missing') {
    state.events = [{ ...state.events[0]!, committed_at: '', npc_decision: null,
      events: [{ type: 'dice_exchange', actor_id: 'player-3', round: 2, turn_sequence: 10, source_id: 'norway' }] }];
  }
  return state;
}
