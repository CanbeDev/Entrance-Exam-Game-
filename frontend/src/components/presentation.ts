import type { PublicGame, PublicGameEvent } from '../api/index.ts';
import map from '../map/mapData.generated.json';
import { countryFlag } from '../flags/flags.ts';

export function campaignResult(game: PublicGame) {
  if (game.status !== 'completed') return null;
  const matches = game.players?.filter(p => p.id === game.winner) ?? [];
  const winner = matches.length === 1 ? matches[0] : undefined;
  const flag = countryFlag(winner?.starting_country_id);
  const name = winner ? game.countries?.find(c => c.id === winner.starting_country_id)?.name
    ?? map.countries.find(c => c.id === flag?.canonicalId)?.name ?? winner.starting_country_id : null;
  const countries = game.countries;
  const known = !!winner && !!countries?.length && new Set(game.players!.map(p => p.id)).size === game.players!.length
    && new Set(countries.map(c => c.id)).size === countries.length
    && countries.every(c => !!c.owner_id && game.players?.some(p => p.id === c.owner_id));
  const held = known ? countries!.filter(c => c.owner_id === winner!.id) : null;
  const soldiersKnown = held?.every(c => Number.isSafeInteger(c.soldiers) && c.soldiers >= 0);
  return { winner, flag, name, held: held?.length ?? null, total: known ? countries!.length : null,
    allTen: known && countries!.length === 10 && held!.length === 10,
    soldiers: held && soldiersKnown ? held.reduce((sum, c) => sum + BigInt(c.soldiers), 0n).toString() : null,
    round: Number.isSafeInteger(game.round) && game.round! > 0 ? game.round : null };
}
export interface PresentationSnapshot { status: PublicGame['status']; revision: number | null; owners: Readonly<Record<string, string>> }
export function observePresentation(previous: PresentationSnapshot | null, game: PublicGame, events: readonly PublicGameEvent[] = []) {
  const snapshot: PresentationSnapshot = { status: game.status, revision: game.revision ?? null,
    owners: Object.fromEntries((game.countries ?? []).map(c => [c.id, c.owner_id])) };
  const advanced = previous?.revision != null && snapshot.revision != null && snapshot.revision > previous.revision;
  const captured = advanced ? events.filter(e => e.type === 'conquered' && e.target_id
    && previous.owners[e.target_id] && previous.owners[e.target_id] !== snapshot.owners[e.target_id]
    && snapshot.owners[e.target_id] === e.actor_id).map(e => e.target_id!) : [];
  return { snapshot, celebrate: !!advanced && previous?.status === 'active' && game.status === 'completed', captured: [...new Set(captured)] };
}
