// Synthetic Stage 4 presentation fixtures ONLY; never imported by the app entry.
import type { AppState } from '../game/controller.ts';
import type { BattleCommentary, PublicCommittedAction, PublicGame } from '../api/index.ts';
import catalog from '../../../backend/app/data/countries.json';

export const boardModes = ['human', 'refreshing', 'attacking', 'conquest', 'allocating', 'npc', 'eliminated', 'completed',
  'spectator', 'refresh-error', 'pending', 'loading', 'legacy', 'npc-fast-forward', 'npc-in-flight',
  'pending-human', 'no-attack-source', 'missing-budget', 'failed-attack', 'victory-nepal', 'victory-holy-see',
  'npc-victory', 'result-incomplete', 'result-missing-flag', 'spectator-result', 'victory-long-name'] as const;
export type BoardMode = typeof boardModes[number];
export const boardGameId = '000000000000000000000042';
const ids = ['brazil', 'canada', 'uk', 'norway', 'australia', 'holy-see', 'bahrain', 'seychelles', 'singapore', 'saint-vincent-and-the-grenadines'];
export function boardFixture(mode: BoardMode = 'human'): AppState {
  const countries = ids.map((id, i) => {
    const country = catalog.countries.find(c => c.id === id)!;
    return { id, name: country.name, population: country.population, base_soldier_value: i % 9 + 1,
      soldiers: i === 9 ? 1234567 : 10 + i, owner_id: `player-${i}` };
  });
  const players = ids.map((id, i) => ({ id: `player-${i}`, starting_country_id: id, kind: i ? 'npc' as const : 'human' as const }));
  let game: PublicGame = { _id: boardGameId, game_name: 'Campaign of the Southern Cross', schema_version: 3,
    countries, players, turn_order: ['player-3', 'player-0', 'player-7', 'player-1', 'player-2', 'player-4', 'player-5', 'player-6', 'player-8', 'player-9'],
    current_turn: 1, round: 2, turn_sequence: 11, revision: 12, status: 'active', phase: 'deciding',
    pending_reinforcements: 0, attack_used: false, battle: null };
  if (mode === 'attacking') game = { ...game, phase: 'attacking', attack_used: true, battle: { source_id: ids[0], target_id: ids[1] } };
  if (mode === 'conquest' || mode === 'allocating') {
    countries[1].owner_id = 'player-0';
    game = { ...game, phase: mode === 'conquest' ? 'post_attack' : 'allocating', attack_used: mode === 'conquest', pending_reinforcements: mode === 'allocating' ? 4 : 0 };
  }
  if (['npc', 'pending', 'eliminated', 'npc-fast-forward', 'npc-in-flight'].includes(mode)) game = { ...game, current_turn: 0 };
  if (mode === 'no-attack-source') countries[0].soldiers = 1;
  if (mode === 'missing-budget') game = { ...game, phase: 'allocating', pending_reinforcements: null };
  if (mode === 'failed-attack') game = { ...game, phase: 'post_attack', attack_used: true };
  if (mode === 'eliminated') countries[0].owner_id = 'player-3';
  if (['completed', 'victory-nepal', 'victory-holy-see', 'npc-victory', 'result-missing-flag', 'spectator-result', 'victory-long-name'].includes(mode)) {
    const winner = mode === 'npc-victory' ? 'player-3' : 'player-0';
    if (mode === 'victory-nepal') {
      const nepal = catalog.countries.find(c => c.id === 'nepal')!;
      countries[0] = { ...countries[0], id: nepal.id, name: nepal.name, population: nepal.population };
      players[0]!.starting_country_id = 'nepal';
    }
    if (mode === 'victory-holy-see') { players[0]!.starting_country_id = 'holy-see'; players[5]!.starting_country_id = 'brazil'; }
    if (mode === 'victory-long-name') { players[0]!.starting_country_id = ids[9]!; players[9]!.starting_country_id = 'brazil'; }
    if (mode === 'result-missing-flag') {
      countries[0] = { ...countries[0], id: 'unrecorded-country', name: 'Unrecorded country' };
      players[0]!.starting_country_id = 'unrecorded-country';
    }
    countries.forEach(c => c.owner_id = winner);
    game = { ...game, status: 'completed', phase: 'finished', winner, current_turn: null };
  }
  if (mode === 'result-incomplete') game = { game_name: 'Campaign archive', status: 'completed' };
  if (mode === 'legacy') game = { game_name: 'Offline incomplete historical fixture' };
  const account = { id: 'offline-account', username: 'offline_fixture_owner' };
  const entry: PublicCommittedAction = { revision: 12, action_id: 'offline-dice-exchange',
    actor: { player_id: 'player-3', kind: 'npc' }, committed_at: '2026-11-01T00:00:00Z',
    events: [{ type: 'dice_exchange', actor_id: 'player-3', round: 2, turn_sequence: 10,
      source_id: ids[3], target_id: ids[4], attacker_dice: [6, 2], defender_dice: [1, 5], attacker_losses: 1, defender_losses: 1 }],
    npc_decision: { strategy_version: 'offline-fixture', action: { type: 'roll' }, reason: 'continue',
      explanation: 'Synthetic fixture explanation: continue this example battle.',
      evaluation: { actor_id: 'player-3', revision: 11, round: 2, turn_sequence: 10,
        concentration: 0, defensive_exposure: 0, countries: [], participants: [], attacks: [] } } };
  return { ready: mode !== 'loading', busy: mode === 'loading' || mode === 'npc-in-flight', session: mode === 'spectator' || mode === 'spectator-result' ? null : { user: account },
    error: mode === 'pending' || mode === 'pending-human' ? 'Offline uncertain-response fixture. No request was sent.' : null,
    notice: 'OFFLINE PRESENTATION FIXTURE — no production connection or gameplay engine.',
    refreshing: mode === 'refreshing', refreshError: mode === 'refresh-error' ? 'Offline refresh failure' : null,
    catalog: null, games: null, filters: {}, cursors: [undefined], gameId: boardGameId,
    game: mode === 'loading' ? null : game, owner: mode !== 'spectator' && mode !== 'spectator-result', events: mode === 'legacy' ? [] : [entry],
    eventCursor: 12, moreEvents: false, lastResult: mode === 'conquest' ? { state: game, events: [{ type: 'conquered',
      actor_id: 'player-0', round: 2, turn_sequence: 11, source_id: 'brazil', target_id: 'canada', amount: 2 }] } : null,
    retryAt: 0, fastForward: mode === 'npc-fast-forward' || mode === 'npc-in-flight',
    npcAttempts: 0, npcAttemptBudget: 3, confirmingPending: false,
    pending: mode === 'pending' || mode === 'npc-in-flight' ? { kind: 'npc', account, operation: { gameId: boardGameId, command: { expected_revision: 12 } },
      observation: { actorId: 'player-3', turnSequence: 11 } } : mode === 'pending-human' ? { kind: 'human', account,
      operation: { gameId: boardGameId, command: { action_id: 'offline-saved-human-action', expected_revision: 12,
        action: { type: 'start_attack', source_id: 'brazil', target_id: 'canada' } } } } : null };
}
export function fixtureNarration(): BattleCommentary {
  return { game_id: boardGameId, revision: 12, action_id: 'offline-dice-exchange', status: 'fallback', source: 'deterministic',
    reason: 'offline_fixture', text: 'Offline deterministic fixture narration; no LLM request was made.',
    facts: { actor_kind: 'npc', attacker: 'Norway', defender: 'Australia', attacker_dice: [6, 2], defender_dice: [1, 5],
      attacker_losses: 1, defender_losses: 1, conquered: false, eliminated: [], round: 2 } };
}
