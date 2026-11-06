import type { PublicActionResult, PublicCommittedAction, PublicGame, PublicGameEvent, PublicNpcDecision } from '../api/index.ts';
import { participantCountryName } from './refresh-view.ts';

export function phaseLabel(game: PublicGame): string {
  switch (game.phase) {
    case 'allocating': return 'Deploy reinforcements';
    case 'attacking': return 'Battle underway';
    case 'deciding': return 'Issue your orders';
    case 'post_attack': return 'Transfer or end turn';
    case 'finished': return 'Campaign complete';
    default: return 'Phase not recorded';
  }
}

export interface CommittedDisplay {
  revision: number;
  events: readonly PublicGameEvent[];
  actorId: string | null;
  decision: PublicNpcDecision | null;
}
/** Detached display adapter: never invents a receipt, actor or request identity. */
export function committedDisplays(game: PublicGame, latest: PublicActionResult | null | undefined,
  receipts: readonly PublicCommittedAction[]) {
  if (!Number.isSafeInteger(game.revision)) return { latest: null, npc: null, exchange: null };
  const candidates: CommittedDisplay[] = receipts.filter(entry => Number.isSafeInteger(entry.revision)
    && entry.revision <= game.revision!).map(entry => ({ revision: entry.revision, events: entry.events,
    actorId: entry.actor.player_id, decision: entry.npc_decision ?? null }));
  if (latest && !(game._id && latest.state._id && game._id !== latest.state._id)
    && Number.isSafeInteger(latest.state.revision) && latest.state.revision! <= game.revision!
    && !candidates.some(entry => entry.revision === latest.state.revision))
    candidates.push({ revision: latest.state.revision!, events: latest.events,
      actorId: latest.events[0]?.actor_id ?? null, decision: latest.npc_decision ?? null });
  candidates.sort((a, b) => b.revision - a.revision);
  return { latest: candidates[0] ?? null, npc: candidates.find(entry => entry.decision) ?? null,
    exchange: candidates.find(entry => entry.events.some(event => event.type === 'dice_exchange')) ?? null };
}

export function actionSummary(game: PublicGame, event: PublicGameEvent): string {
  const name = participantCountryName(game, event.actor_id);
  const country = (id: string | null | undefined) => game.countries?.find(item => item.id === id)?.name ?? id ?? 'Country not recorded';
  switch (event.type) {
    case 'allocated': return `${name} placed reinforcements${event.allocations?.length
      ? `: ${event.allocations.map(item => `${country(item.country_id)} +${item.amount}`).join(', ')}` : ''}.`;
    case 'attack_started': return `${name} attacked ${country(event.target_id)} from ${country(event.source_id)}.`;
    case 'dice_exchange': return `${country(event.source_id)} → ${country(event.target_id)}: attacker losses ${event.attacker_losses ?? 'not recorded'}, defender losses ${event.defender_losses ?? 'not recorded'}.`;
    case 'conquered': return `${name} conquered ${country(event.target_id)}${event.amount != null ? `; reward ${event.amount} soldiers` : ''}.`;
    case 'transferred': return `${name} transferred ${event.amount ?? 'an unrecorded number of'} soldiers from ${country(event.source_id)} to ${country(event.target_id)}.`;
    case 'attack_stopped': return `${name} stopped the attack.`;
    case 'attack_failed': return `${name} ended the attack without conquering the target.`;
    case 'eliminated': return `${event.player_id ? participantCountryName(game, event.player_id) : 'An unrecorded participant'} was eliminated.`;
    case 'victory': return `${name} won the campaign.`;
    case 'turn_ended': return `${name} ended its turn.`;
    case 'turn_started': return `${name}'s turn began.`;
  }
}

/** Only identifies a later eligible slot in this saved round; never predicts a wrap. */
export function nextSavedParticipant(game: PublicGame): string | null {
  const order = game.turn_order;
  if (game.status !== 'active' || !order || !Number.isInteger(game.current_turn) || game.current_turn! < 0
    || game.current_turn! >= order.length || new Set(order).size !== order.length
    || order.length !== 10 || !game.players || game.players.length !== 10 || new Set(game.players.map(player => player.id)).size !== 10 || game.countries?.length !== 10
    || new Set(game.countries.map(country => country.id)).size !== 10
    || game.countries.some(country => !game.players!.some(player => player.id === country.owner_id))
    || order.some(id => !game.players!.some(player => player.id === id))) return null;
  return order.slice(game.current_turn! + 1).find(id => game.countries!.some(country => country.owner_id === id)) ?? null;
}
