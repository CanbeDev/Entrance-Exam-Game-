import type { AppState } from '../game/controller.ts';
import type { PublicGame } from '../api/index.ts';

/** Original participant identity, independent of the current owner of its home. */
export function participantCountryName(game: PublicGame, id: string | null | undefined): string {
  const player = game.players?.find(item => item.id === id);
  return player ? game.countries?.find(country => country.id === player.starting_country_id)?.name
    ?? player.starting_country_id : 'Participant';
}

export function npcActivity(game: PublicGame, id: string): string {
  const name = participantCountryName(game, id);
  switch (game.phase) {
    case 'allocating': return `${name} is preparing its forces.`;
    case 'attacking': return `${name} is at war.`;
    case 'post_attack': return `${name} is concluding its turn.`;
    default: return `${name} is making its next move.`;
  }
}

export function synchronization(state: Pick<AppState, 'ready' | 'busy' | 'refreshing' | 'refreshError' | 'error' | 'pending' | 'confirmingPending'>) {
  if (state.refreshError || state.error || state.pending && !state.busy && !state.confirmingPending)
    return { tone: 'problem', text: state.pending ? 'Move confirmation needed. Use the recovery controls.' : 'Connection needs attention. Review the message below.' };
  if (!state.ready || state.busy || state.refreshing || state.confirmingPending)
    return { tone: 'refreshing', text: !state.ready ? 'Restoring session…' : state.pending
      ? 'Confirming your submitted move. Keep this page open.' : 'Updating game…' };
  return { tone: 'idle', text: 'Settled. The last confirmed state is shown.' };
}
