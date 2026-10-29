import { ApiError, GameApi } from '../api/index.ts';
import type { ActionCommand, ActionOutcome, CountryCatalog, CreationOperation, Credentials, GameFilters,
  HumanOperation, NpcOperation, PublicActionResult, PublicCommittedAction, PublicGame, PublicGameList, Session } from '../api/index.ts';
import { activeParticipant, playable } from './view.ts';

type Pending = { kind: 'create'; operation: CreationOperation } | { kind: 'human'; operation: HumanOperation }
  | { kind: 'npc'; operation: NpcOperation };
export interface AppState {
  ready: boolean; busy: boolean; session: Session | null; error: string | null; notice: string | null;
  catalog: CountryCatalog | null; games: PublicGameList | null; filters: GameFilters;
  cursors: Array<string | undefined>; gameId: string | null; game: PublicGame | null; owner: boolean;
  events: readonly PublicCommittedAction[]; eventCursor: number; moreEvents: boolean;
  lastResult: PublicActionResult | null; pending: Pending | null; retryAt: number; fastForward: boolean;
}

export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Unable to complete the request. Please refresh and try again.';
  if (error.status === 401) return 'Your session has ended or the credentials were not accepted. Please log in.';
  if (error.code === 'csrf_rejected' || error.code === 'csrf_not_initialized') return 'Your session needs refreshing. Please log in again or retry the saved request.';
  if (error.status === 403) return 'You do not have permission to perform this action.';
  if (error.code === 'username_unavailable') return 'That username is unavailable. Choose another or log in.';
  if (error.status === 409) return 'The game changed or this move is no longer valid. The latest available board has been loaded; review it before choosing again.';
  if (error.status === 429) return 'Too many requests. Please wait before trying again.';
  if (error.code === 'authentication_disabled' || error.code === 'phase4_disabled') return 'Account services are currently unavailable.';
  if (error.code === 'gameplay_writes_disabled') return 'Gameplay is currently unavailable. You can still view the board.';
  if (error.status === 422 || error.kind === 'client') return 'Check the form values and try again.';
  if (error.kind === 'timeout' || error.kind === 'network') return 'The connection was interrupted. A submitted move may already have completed.';
  if (error.kind === 'malformed') return 'The service returned an unexpected response. Refresh before continuing.';
  return 'The service is temporarily unavailable. Please try again later.';
}

/** UI orchestration only: no battle, ownership, soldier or NPC decisions live here. */
export class GameController {
  readonly api: GameApi;
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private stopped = false;
  private state: AppState = {
    ready: false, busy: false, session: null, error: null, notice: null, catalog: null, games: null,
    filters: {}, cursors: [undefined], gameId: null, game: null, owner: false,
    events: [], eventCursor: 0, moreEvents: false, lastResult: null, pending: null, retryAt: 0, fastForward: false,
  };
  constructor(api = new GameApi()) { this.api = api; }
  getSnapshot = (): AppState => this.state;
  subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  private set(patch: Partial<AppState>): void {
    if (this.stopped) return;
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  dispose(): void { this.pause(); this.stopped = true; this.listeners.clear(); }
  private fail(error: unknown): void {
    this.pause();
    const apiError = error instanceof ApiError ? error : undefined;
    if (apiError?.latestState) this.set({ game: apiError.latestState });
    const preserve = apiError?.uncertain && !['authentication_disabled', 'gameplay_writes_disabled', 'phase4_disabled'].includes(apiError.code)
      || apiError?.status === 429 || apiError?.code === 'csrf_rejected';
    this.set({ error: errorMessage(error), session: this.api.currentSession,
      owner: !!this.api.currentSession && this.state.owner && !(apiError?.status === 403 && apiError.code !== 'csrf_rejected'),
      pending: preserve ? this.state.pending : null,
      retryAt: apiError?.status === 429 ? Date.now() + (apiError.retryAfterMs ?? 60_000) : 0 });
  }
  private async run(work: () => Promise<void>, retry = false): Promise<void> {
    if (this.state.busy || Date.now() < this.state.retryAt || this.stopped || this.state.pending && !retry) return;
    this.set({ busy: true, error: null, notice: null });
    try { await work(); } catch (error) { this.fail(error); }
    finally { this.set({ busy: false, session: this.api.currentSession }); }
  }
  async initialize(id: string | null): Promise<void> {
    await this.run(async () => {
      try { this.set({ session: await this.api.restoreSession() }); } catch (error) { this.fail(error); }
      if (id) await this.loadGame(id);
      else if (this.api.currentSession) await this.loadDashboard();
    });
    this.set({ ready: true });
  }
  async authenticate(credentials: Credentials, register: boolean): Promise<void> {
    await this.run(async () => {
      this.set({ owner: false, games: null });
      if (register) {
        await this.api.register(credentials);
        this.set({ notice: 'Account created. If login is interrupted, use Log in rather than registering again.' });
      }
      this.set({ session: await this.api.login(credentials), filters: {}, cursors: [undefined] });
      await this.loadDashboard();
      if (this.state.gameId) await this.checkOwner(this.state.gameId);
    });
  }
  async logout(): Promise<void> {
    this.pause();
    await this.run(async () => {
      try { await this.api.logout(); }
      finally { this.set({ session: null, owner: false, games: null, pending: null }); }
    });
  }
  private async loadDashboard(): Promise<void> {
    if (!this.api.currentSession) return;
    const cursor = this.state.cursors.at(-1);
    const games = await this.api.listGames({ ...this.state.filters, cursor, limit: 10 });
    this.set({ games });
    if (!this.state.catalog) this.set({ catalog: await this.api.countries() });
  }
  dashboard(filters?: GameFilters): Promise<void> {
    return this.run(async () => {
      if (filters) this.set({ filters, cursors: [undefined] });
      await this.loadDashboard();
    });
  }
  page(next: boolean): Promise<void> {
    return this.run(async () => {
      if (next && this.state.games?.next_cursor) this.set({ cursors: [...this.state.cursors, this.state.games.next_cursor] });
      else if (!next && this.state.cursors.length > 1) this.set({ cursors: this.state.cursors.slice(0, -1) });
      await this.loadDashboard();
    });
  }
  private async checkOwner(id: string): Promise<void> {
    if (!this.api.currentSession) { this.set({ owner: false }); return; }
    // Public games have no ownership field. Check the authenticated owner's list,
    // independently of dashboard filters/pages; game-local actor IDs are not accounts.
    let cursor: string | undefined;
    const seen = new Set<string>();
    do {
      const page = await this.api.listGames({ cursor, limit: 100 });
      if (page.games.some((game) => game._id === id)) { this.set({ owner: true }); return; }
      cursor = page.next_cursor ?? undefined;
      if (cursor && seen.has(cursor)) throw new ApiError('malformed');
      if (cursor) seen.add(cursor);
    } while (cursor);
    this.set({ owner: false });
  }
  private async loadGame(id: string): Promise<void> {
    this.pause();
    this.set({ gameId: id, game: null, owner: false, events: [], eventCursor: 0, moreEvents: false, lastResult: null });
    this.set({ game: await this.api.getGame(id) });
    await this.loadEvents();
    await this.checkOwner(id);
  }
  openGame(id: string): Promise<void> { return this.run(() => this.loadGame(id)); }
  private async loadEvents(): Promise<void> {
    if (!this.state.gameId) return;
    const page = await this.api.events(this.state.gameId, { after_revision: this.state.eventCursor, limit: 100 });
    const events = new Map(this.state.events.map((event) => [event.revision, event]));
    page.events.forEach((event) => events.set(event.revision, event));
    this.set({ events: [...events.values()].sort((a, b) => a.revision - b.revision),
      eventCursor: page.next_after_revision, moreEvents: page.has_more });
  }
  moreHistory(): Promise<void> { return this.run(() => this.loadEvents()); }
  refresh(): Promise<void> {
    return this.run(async () => {
      if (this.state.gameId) {
        this.set({ game: await this.api.getGame(this.state.gameId) });
        await this.loadEvents();
        await this.checkOwner(this.state.gameId);
      } else await this.loadDashboard();
    });
  }
  poll(): void {
    if (this.state.gameId && !this.state.error && !this.state.fastForward && !this.state.pending) void this.refresh();
  }
  create(body: { game_name: string; starting_country_id: string }): Promise<void> {
    return this.run(async () => {
      if (!this.api.currentSession) return;
      this.set({ pending: { kind: 'create', operation: this.api.prepareCreation(body) } });
      await this.submitPending();
    });
  }
  private controls(kind: 'human' | 'npc'): boolean {
    return !!this.state.session && this.state.owner && !!this.state.game && playable(this.state.game)
      && activeParticipant(this.state.game)?.kind === kind;
  }
  act(action: ActionCommand['action']): Promise<void> {
    return this.run(async () => {
      if (!this.controls('human') || !this.state.gameId || !this.state.game) return;
      const command = { action_id: crypto.randomUUID(), expected_revision: this.state.game.revision!, action };
      this.set({ pending: { kind: 'human', operation: this.api.prepareAction(this.state.gameId, command) } });
      await this.submitPending();
    });
  }
  stepNpc(): Promise<void> {
    return this.run(async () => {
      if (!this.controls('npc') || !this.state.gameId || !this.state.game) return;
      this.set({ pending: { kind: 'npc', operation: this.api.prepareNpcStep(this.state.gameId, this.state.game.revision!) } });
      await this.submitPending();
    });
  }
  private async submitPending(): Promise<void> {
    const pending = this.state.pending;
    if (!pending) return;
    if (pending.kind === 'create') {
      const game = await this.api.createGame(pending.operation);
      this.set({ pending: null, gameId: game._id!, game, owner: true, events: [], eventCursor: 0,
        moreEvents: false, lastResult: null, notice: 'Game created. Share this page to let others watch.' });
      await this.loadEvents();
    } else {
      const outcome: ActionOutcome = pending.kind === 'human'
        ? await this.api.humanAction(pending.operation) : await this.api.npcStep(pending.operation);
      this.set({ pending: null, game: outcome.state, lastResult: outcome.response });
      await this.loadEvents();
    }
  }
  retryPending(): Promise<void> {
    return this.run(async () => {
      if (!this.state.session) return;
      await this.api.refreshCsrf();
      await this.submitPending();
    }, true);
  }
  pause(): void { clearTimeout(this.timer); this.set({ fastForward: false }); }
  async fastForward(): Promise<void> {
    if (!this.controls('npc') || this.state.busy || this.state.pending) return;
    this.set({ fastForward: true });
    const next = async (): Promise<void> => {
      if (!this.state.fastForward || !this.controls('npc')) { this.pause(); return; }
      await this.stepNpc();
      if (!this.state.fastForward || this.state.error || !this.controls('npc')) { this.pause(); return; }
      this.timer = setTimeout(() => { void next(); }, 650);
    };
    await next();
  }
}
