// Synthetic local presentation fixtures, never imported by the production entry.
import type { AppState } from '../game/controller.ts';
import type { PageScreen } from '../components/screen-view.ts';
import catalog from '../../../backend/app/data/countries.json';
import { boardFixture } from './board-fixtures.ts';

export const screenModes = ['landing','registration','registration-error','auth-error','library','empty','new-campaign','country-selected',
  'rules','watch','invalid-watch','game-unavailable','victory','defeat','eliminated','spectator','loading','connectivity','pending','recovery-login'] as const;
export type ScreenMode = typeof screenModes[number];
export function screenFixture(mode: ScreenMode): { state: AppState; screen: PageScreen } {
  const boardMode = mode === 'victory' ? 'completed' : mode === 'defeat' ? 'npc-victory' : mode === 'eliminated' ? 'eliminated'
    : mode === 'spectator' ? 'spectator' : mode === 'pending' || mode === 'recovery-login' ? 'pending' : 'human';
  const state = boardFixture(boardMode);
  state.notice = null;
  state.catalog = { population_snapshot: { dataset_id: catalog.dataset_id, source_url: catalog.source_url,
    population_year: catalog.population_year, retrieved_on: catalog.retrieved_on, source_sha256: catalog.source_sha256 },
    countries: catalog.countries.map(country => ({ id: country.id, name: country.name, population: country.population,
      base_soldier_value: [5,10,25,50,75,100,125,150].filter(millions => country.population > millions * 1_000_000).length + 1 })) };
  const gameModes = ['victory','defeat','eliminated','spectator','pending','recovery-login','game-unavailable'];
  if (!gameModes.includes(mode)) { state.gameId = null; state.game = null; state.events = []; state.lastResult = null; state.owner = false; }
  if (['landing','registration','registration-error','auth-error','watch','invalid-watch','rules','loading','connectivity'].includes(mode)) state.session = null;
  state.games = { games: [], next_cursor: null };
  if (mode === 'library') state.games = { games: [
    { _id: '000000000000000000000101', game_name: 'Offline fixture · Southern crossings', status: 'active', round: 4, updated_at: '2026-11-01T12:00:00Z' },
    { _id: '000000000000000000000102', game_name: 'Offline fixture · A long campaign around Saint Vincent and the Grenadines', status: 'completed', round: 12 },
    { _id: '000000000000000000000103', game_name: 'Offline fixture · Northern passage', status: 'waiting' },
  ], next_cursor: '000000000000000000000104' };
  if (mode === 'auth-error') state.error = 'Your session has ended or the credentials were not accepted. Please log in.';
  if (mode === 'connectivity') { state.error = 'The service is temporarily unavailable. Please try again later.'; state.games = null; }
  if (mode === 'loading') { state.ready = false; state.busy = true; }
  if (mode === 'game-unavailable') { state.game = null; state.error = 'The game could not be loaded.'; }
  if (mode === 'recovery-login') { state.session = null; state.owner = false; }
  return { state, screen: mode === 'rules' ? 'rules' : mode === 'watch' ? 'watch' : mode === 'invalid-watch' ? 'invalid'
    : mode === 'new-campaign' || mode === 'country-selected' ? 'new' : 'home' };
}
