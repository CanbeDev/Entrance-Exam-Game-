import reference from './reference.generated.json';
import { countryFlag } from '../flags/flags.ts';
import type { PublicGame } from '../api/index.ts';
export function countryFacts(id: string, game?: PublicGame) {
  const canonicalId = countryFlag(id)?.canonicalId;
  const record = reference.countries.find(c => c.id === canonicalId);
  if (!record) return null;
  const current = game?.countries?.find(c => c.id === canonicalId);
  const owner = current && game?.players?.find(p => p.id === current.owner_id);
  const ownerHome = owner && reference.countries.find(c => c.id === owner.starting_country_id);
  // An incomplete participant's values stay unavailable, never silently replaced
  // by catalog values from another snapshot.
  return { id: record.id, name: current?.name ?? record.name, flag: countryFlag(record.id),
    capital: record.capital, capitalSource: reference.capitalSource,
    population: current ? current.population ?? null : record.population,
    startingSoldiers: current ? current.base_soldier_value ?? null : record.startingSoldiers,
    currentSoldiers: current?.soldiers ?? null,
    participating: !!current, owner: owner ? `${ownerHome?.name ?? owner.starting_country_id} (${owner.kind === 'human' ? 'Human' : 'Rival'})` : null,
    target: !!current && game?.status === 'active' && game.phase === 'attacking' && game.battle?.target_id === canonicalId,
    from: !!current && game?.status === 'active' && game.phase === 'attacking' && game.battle?.source_id === canonicalId,
    snapshot: current ? 'Saved game' : reference.dataset };
}
export const canonicalCountries = reference.countries;
/** Presentation-only pinning. Card remains outside the map's horizontal scroller. */
export function cardPosition(anchorX: number, width: number) {
  const cardWidth = Math.min(320, Math.max(0, width));
  return { left: Math.max(0, Math.min(Math.max(0, width - cardWidth), anchorX - cardWidth / 2)), width: cardWidth };
}
