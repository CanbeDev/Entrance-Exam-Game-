import type { PublicGame, PublicParticipant } from '../api/index.ts';

export function activeParticipant(game: PublicGame): PublicParticipant | undefined {
  const id = game.current_turn == null ? undefined : game.turn_order?.[game.current_turn];
  return game.players?.find((player) => player.id === id);
}
export function playable(game: PublicGame): boolean {
  return game.schema_version === 3 && game.status === 'active' && game.revision != null && !!game.phase;
}
export function participantName(game: PublicGame, id: string | null | undefined): string {
  const player = game.players?.find((item) => item.id === id);
  if (!player) return id ?? 'Unknown';
  const country = game.countries?.find((item) => item.id === player.starting_country_id);
  return `${player.kind === 'human' ? 'Human' : 'NPC'} — ${country?.name ?? player.starting_country_id}`;
}
