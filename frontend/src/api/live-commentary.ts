import type { BattleCommentary, PublicCommittedAction, PublicEventPage } from './contracts.ts';
import { ApiError } from './http.ts';

export interface LiveCommentaryUpdate {
  commentary: BattleCommentary | null;
  loading: boolean;
  error: string | null;
  requested: boolean;
  entry?: PublicCommittedAction;
}
type Generate = (gameId: string, revision: number, permitted: () => boolean) => Promise<BattleCommentary>;
type Read = (gameId: string, afterRevision: number) => Promise<PublicEventPage>;

/** One bounded receipt page and one generation at a time, independent of history UI. */
export class NewBattleCommentary {
  private context: { gameId: string; accountId: string | null; allowed: boolean } | null = null;
  private enabled = true;
  private optedOut = false;
  private generation = 0;
  private cursor: number;
  private target: number;
  private task: Promise<void> | null = null;
  private stalled = false;
  private readonly generate: Generate;
  private readonly update: (revision: number, display: LiveCommentaryUpdate) => void;
  private readonly read: Read;
  private readonly permitted: () => boolean;
  constructor(generate: Generate, update: (revision: number, display: LiveCommentaryUpdate) => void,
    read: Read, initialRevision: number, permitted: () => boolean = () => true) {
    this.generate = generate; this.update = update; this.read = read; this.permitted = permitted;
    this.cursor = this.target = initialRevision;
  }
  get active(): boolean { return this.enabled; }
  contextChanged(gameId: string, accountId: string | null, allowed: boolean): void {
    if (this.context && (this.context.gameId !== gameId || this.context.accountId !== accountId)) {
      this.generation++; this.cursor = this.target;
      this.enabled = !this.optedOut;
    }
    this.context = { gameId, accountId, allowed };
    if (allowed) this.stalled = false;
    this.kick();
  }
  enable(revision: number): boolean {
    if (!this.context?.accountId || !this.context.allowed || !Number.isSafeInteger(revision) || revision < 0) return false;
    this.cursor = this.target = Math.max(this.cursor, revision);
    this.generation++; this.enabled = true; this.optedOut = false; this.stalled = false;
    return true;
  }
  disable(): void { this.enabled = false; this.optedOut = true; this.generation++; }
  dispose(): void { this.disable(); this.context = null; }
  observe(revision: number): void {
    if (!Number.isSafeInteger(revision) || revision < 0) return;
    this.target = Math.max(this.target, revision);
    this.stalled = false;
    this.kick();
  }
  private available(): boolean {
    return this.enabled && !!this.context?.accountId && !!this.context.allowed && this.permitted();
  }
  private kick(): void {
    if (this.task || this.stalled || !this.available() || this.cursor >= this.target) return;
    const task = this.run();
    this.task = task;
    void task.finally(() => {
      if (this.task === task) this.task = null;
      this.kick();
    });
  }
  private async run(): Promise<void> {
    const context = this.context!;
    const generation = this.generation;
    const current = () => this.context?.gameId === context.gameId && this.context.accountId === context.accountId;
    const permitted = () => current() && generation === this.generation && this.available();
    try {
      while (permitted() && this.cursor < this.target) {
        const after = this.cursor;
        const page = await this.read(context.gameId, after);
        if (!permitted()) { this.stalled = true; return; }
        let previous = after;
        if (page.after_revision !== after || page.events.length > 100
            || page.events.some((entry) => { const invalid = entry.revision !== previous + 1; previous = entry.revision; return invalid; })
            || page.next_after_revision !== previous) throw new ApiError('malformed');
        if (!page.events.length) { this.stalled = true; return; }
        for (const entry of page.events) {
          if (!permitted()) { this.stalled = true; return; }
          if (entry.revision > this.target) break;
          if (entry.events.some((event) => event.type === 'dice_exchange')) {
            this.update(entry.revision, { entry, commentary: null, loading: true, error: null, requested: false });
            try {
              const commentary = await this.generate(context.gameId, entry.revision, permitted);
              if (!current()) return;
              if (commentary.action_id !== entry.action_id) throw new ApiError('malformed');
              this.update(entry.revision, { entry, commentary, loading: false, error: null, requested: true });
            } catch (error) {
              if (!current()) return;
              const cancelled = error instanceof ApiError && error.code === 'commentary_cancelled';
              this.update(entry.revision, { entry, commentary: null, loading: false, requested: !cancelled,
                error: cancelled ? null : 'AI commentary could not be confirmed. Check saved commentary; gameplay is unaffected.' });
              if (cancelled) { this.stalled = true; return; }
            }
          }
          this.cursor = Math.max(this.cursor, entry.revision);
        }
      }
    } catch {
      if (current()) this.update(0, { commentary: null, loading: false, requested: false,
        error: 'New battle commentary could not be loaded. Gameplay is unaffected; Refresh game to check again.' });
      this.stalled = true;
    }
  }
}
