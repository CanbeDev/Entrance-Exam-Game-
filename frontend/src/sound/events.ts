import type { AppState } from '../game/controller.ts';
import type { SoundEvent } from './assets.ts';
export interface Cue { event: SoundEvent; id?: string; after?: SoundEvent; rapid?: boolean; important?: boolean }
/** Page lifetime ledger, independent of React remounts; no requests or rules. */
export class SoundLedger {
  private positions = new Map<string, number>();
  private lastGame: string | null = null;
  private creating = false;
  baseline(state: AppState): void {
    if (state.gameId && Number.isSafeInteger(state.game?.revision)) {
      const key = `${state.session?.user.id ?? 'spectator'}:${state.gameId}`;
      this.positions.set(key, Math.max(this.positions.get(key) ?? 0, state.game!.revision!));
    }
  }
  observe(state: AppState): Cue[] {
    const created = this.creating && !state.pending && !!state.gameId && state.gameId !== this.lastGame;
    this.creating = state.pending?.kind === 'create'; this.lastGame = state.gameId;
    const game = state.game;
    if (!game || !state.gameId || !Number.isSafeInteger(game.revision)) return [];
    const key = `${state.session?.user.id ?? 'spectator'}:${state.gameId}`;
    const old = this.positions.get(key), revision = game.revision!;
    if (old === undefined || !state.owner || !state.session) this.positions.set(key, Math.max(old ?? revision, revision));
    if (!state.owner || !state.session || state.pending) return [];
    if (created && revision === 0) return [{ event: 'campaign', important: true }];
    if (old === undefined || revision <= old) return [];
    const entry = state.events.filter(e => e.revision > old && e.revision <= revision).at(-1);
    if (!entry?.action_id) return [];
    this.positions.set(key, entry.revision);
    const events = entry.events, has = (type: string) => events.some(e => e.type === type);
    const id = `${state.gameId}:${entry.revision}:${entry.action_id}`;
    // A completed-state load alone is insufficient: require a new victory event.
    if (has('victory') && game.status === 'completed' && game.winner) {
      const winner = game.players?.find(p => p.id === game.winner);
      if (winner) return [{ event: winner.kind === 'human' ? 'victory' : 'defeat', important: true }];
    }
    const dice = events.find(e => e.type === 'dice_exchange');
    if (dice) {
      const after = has('conquered') ? 'conquer' : (dice.defender_losses ?? 0) > 0 ? 'defenderLoss'
        : (dice.attacker_losses ?? 0) > 0 ? 'attackerLoss' : dice.attacker_losses === 0 && dice.defender_losses === 0 ? 'tie' : undefined;
      return [{ event: 'dice', id, after, rapid: state.fastForward }];
    }
    const event: SoundEvent | undefined = has('conquered') ? 'conquer' : has('attack_started') ? 'attack'
      : has('transferred') ? 'transfer' : has('allocated') ? 'allocate' : has('turn_ended') ? 'endTurn'
      : entry.actor.kind === 'npc' ? 'npc' : undefined;
    return event ? [{ event, rapid: state.fastForward }] : [];
  }
}
