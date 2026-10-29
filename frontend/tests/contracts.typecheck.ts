import type { ActionCommand, GameSetupRequest, NpcStepRequest, PublicActionResult } from '../src/api/contracts.ts';

const setup: GameSetupRequest = { game_name: 'Offline', starting_country_id: 'za' };
const npc: NpcStepRequest = { expected_revision: 1 };
const command: ActionCommand = { action_id: 'fixed', expected_revision: 1, action: { type: 'roll' } };
// @ts-expect-error The backend does not accept an attack alias.
const alias: ActionCommand = { action_id: 'fixed', expected_revision: 1, action: { type: 'attack' } };
// @ts-expect-error Transfers require amount.
const transfer: ActionCommand = { action_id: 'fixed', expected_revision: 1, action: { type: 'transfer', source_id: 'a', target_id: 'b' } };
// @ts-expect-error Setup must never accept client-computed soldiers.
const invalid: GameSetupRequest = { game_name: 'Offline', starting_country_id: 'za', soldiers: 10 };
const result: PublicActionResult = { state: { game_name: 'Offline' }, events: [] }; // _id is optional.
void [setup, npc, command, alias, transfer, invalid, result];
