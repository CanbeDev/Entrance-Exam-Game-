import { ApiError, GameApi } from '../api/index.ts';
import type { ActionCommand, ActionOutcome, CountryCatalog, CreationOperation, Credentials, GameFilters,
  HumanOperation, NpcOperation, PublicActionResult, PublicCommittedAction, PublicEventPage, PublicGame, PublicGameList, Session } from '../api/index.ts';
import { activeParticipant, playable } from './view.ts';

type Pending = { kind: 'create'; operation: CreationOperation } | { kind: 'human'; operation: HumanOperation }
  | { kind: 'npc'; operation: NpcOperation };
export interface AppState {
  ready: boolean; busy: boolean; session: Session | null; error: string | null; notice: string | null;
  refreshing: boolean; refreshError: string | null;
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
  private readGeneration = 0;
  private backgroundTask: Promise<void> | null = null;
  private ownerContext: { session: Session; gameId: string } | null = null;
  private state: AppState = {
    ready: false, busy: false, session: null, error: null, notice: null, catalog: null, games: null,
    refreshing: false, refreshError: null,
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
  dispose(): void { this.readGeneration++; this.pause(); this.stopped = true; this.listeners.clear(); }
  private clearOwner(): void { this.ownerContext = null; this.set({ owner: false }); }
  private ownsCurrentGame(): boolean {
    return !!this.api.currentSession && this.ownerContext?.session === this.api.currentSession
      && this.ownerContext.gameId === this.state.gameId && this.state.owner;
  }
  private syncSession(): void {
    const owner = this.ownsCurrentGame();
    if (!owner) this.ownerContext = null;
    this.set({ session: this.api.currentSession, owner });
  }
  private currentRead(generation: number, id: string, session: Session | null): boolean {
    return !this.stopped && generation === this.readGeneration && id === this.state.gameId
      && session === this.api.currentSession;
  }
  private applyGame(game: PublicGame): void {
    const revision = this.state.game?.revision;
    if (revision != null && (game.revision == null || game.revision < revision)) return;
    this.set({ game });
  }
  private applyEvents(page: PublicEventPage): void {
    const events = new Map(this.state.events.map((event) => [event.revision, event]));
    page.events.forEach((event) => events.set(event.revision, event));
    this.set({ events: [...events.values()].sort((a, b) => a.revision - b.revision),
      eventCursor: Math.max(this.state.eventCursor, page.next_after_revision),
      moreEvents: page.next_after_revision >= this.state.eventCursor ? page.has_more : this.state.moreEvents });
  }
  private fail(error: unknown): void {
    this.pause();
    const apiError = error instanceof ApiError ? error : undefined;
    if (apiError?.latestState) this.applyGame(apiError.latestState);
    if (!this.api.currentSession || apiError?.status === 403 && apiError.code !== 'csrf_rejected') this.clearOwner();
    const preserve = apiError?.uncertain && !['authentication_disabled', 'gameplay_writes_disabled', 'phase4_disabled'].includes(apiError.code)
      || apiError?.status === 429 || apiError?.code === 'csrf_rejected';
    this.set({ error: errorMessage(error), session: this.api.currentSession,
      owner: this.ownsCurrentGame(),
      pending: preserve ? this.state.pending : null,
      retryAt: apiError?.status === 429 ? Date.now() + (apiError.retryAfterMs ?? 60_000) : 0 });
  }
  private async run(work: () => Promise<void>, { retry = false, waitForRefresh = true }: {
    retry?: boolean; waitForRefresh?: boolean;
  } = {}): Promise<void> {
    if (this.state.busy || Date.now() < this.state.retryAt || this.stopped || this.state.pending && !retry) return;
    // Foreground intent supersedes background results, but mutations need not wait
    // for a slow public read. Auth/read workflows drain it to avoid overlapping
    // refreshes or a late read clearing a newly established API session.
    this.readGeneration++;
    this.set({ busy: true, error: null, notice: null, refreshError: null });
    try {
      if (waitForRefresh) await this.backgroundTask;
      if (!this.stopped) {
        this.set({ refreshError: null });
        await work();
      }
    } catch (error) { this.fail(error); }
    finally { this.syncSession(); this.set({ busy: false }); }
  }
  async initialize(id: string | null): Promise<void> {
    await this.run(async () => {
      this.clearOwner();
      try { this.set({ session: await this.api.restoreSession() }); } catch (error) { this.fail(error); }
      if (this.stopped) return;
      if (id) await this.loadGame(id);
      else if (this.api.currentSession) await this.loadDashboard();
    });
    this.set({ ready: true });
  }
  async authenticate(credentials: Credentials, register: boolean): Promise<void> {
    await this.run(async () => {
      this.clearOwner();
      this.set({ games: null });
      if (register) {
        await this.api.register(credentials);
        this.set({ notice: 'Account created. If login is interrupted, use Log in rather than registering again.' });
      }
      this.set({ session: await this.api.login(credentials), filters: {}, cursors: [undefined] });
      if (this.state.gameId) await this.checkOwner(this.state.gameId);
      else await this.loadDashboard();
    });
  }
  async logout(): Promise<void> {
    this.pause();
    await this.run(async () => {
      this.clearOwner();
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
    const session = this.api.currentSession;
    const generation = this.readGeneration;
    if (!this.ownsCurrentGame()) this.clearOwner();
    if (!session) return;
    // Public games have no ownership field. Check the authenticated owner's list,
    // independently of dashboard filters/pages; game-local actor IDs are not accounts.
    let cursor: string | undefined;
    const seen = new Set<string>();
    do {
      const page = await this.api.listGames({ cursor, limit: 100 });
      if (!this.currentRead(generation, id, session)) return;
      if (page.games.some((game) => game._id === id)) {
        this.ownerContext = { session, gameId: id };
        this.set({ owner: true }); return;
      }
      cursor = page.next_cursor ?? undefined;
      if (cursor && seen.has(cursor)) throw new ApiError('malformed');
      if (cursor) seen.add(cursor);
    } while (cursor);
    this.clearOwner();
  }
  private async loadGame(id: string): Promise<void> {
    this.pause();
    this.clearOwner();
    this.set({ gameId: id, game: null, owner: false, events: [], eventCursor: 0, moreEvents: false, lastResult: null });
    const game = await this.api.getGame(id);
    if (this.stopped) return;
    this.applyGame(game);
    await this.loadEvents();
    if (this.stopped) return;
    await this.checkOwner(id);
  }
  openGame(id: string): Promise<void> { return this.run(() => this.loadGame(id)); }
  private async loadEvents(): Promise<void> {
    if (!this.state.gameId) return;
    const page = await this.api.events(this.state.gameId, { after_revision: this.state.eventCursor, limit: 100 });
    if (!this.stopped) this.applyEvents(page);
  }
  moreHistory(): Promise<void> { return this.run(() => this.loadEvents()); }
  refresh(): Promise<void> {
    return this.run(async () => {
      if (this.state.gameId) {
        this.applyGame(await this.api.getGame(this.state.gameId));
        if (this.stopped) return;
        await this.loadEvents();
        if (this.stopped) return;
        await this.checkOwner(this.state.gameId);
      } else await this.loadDashboard();
    });
  }
  poll(): Promise<void> {
    if (this.stopped || !this.state.ready || !this.state.gameId || !this.state.game || this.state.busy
        || this.backgroundTask || this.state.refreshing || this.state.error || this.state.refreshError
        || this.state.fastForward || this.state.pending || Date.now() < this.state.retryAt) return Promise.resolve();
    const id = this.state.gameId;
    const generation = this.readGeneration;
    const session = this.api.currentSession;
    const cursor = this.state.eventCursor;
    this.set({ refreshing: true });
    this.backgroundTask = this.refreshBackground(generation, id, session, cursor);
    return this.backgroundTask;
  }
  private async refreshBackground(generation: number, id: string, session: Session | null, cursor: number): Promise<void> {
    try {
      const game = await this.api.getGame(id);
      if (!this.currentRead(generation, id, session)) return;
      const page = await this.api.events(id, { after_revision: cursor, limit: 100 });
      if (!this.currentRead(generation, id, session)) return;
      this.applyGame(game);
      this.applyEvents(page);
    } catch (error) {
      if (this.currentRead(generation, id, session)) {
        // Read failures must never discard a saved mutation or replay it. Pause
        // polling until explicit foreground intent; keep the last known board.
        if (error instanceof ApiError && error.status === 403) this.clearOwner();
        this.set({ refreshError: errorMessage(error),
          ...(error instanceof ApiError && error.status === 429
            ? { retryAt: Date.now() + (error.retryAfterMs ?? 60_000) } : {}) });
      } else if (!this.stopped && session && !this.api.currentSession) {
        // The API client clears its session on 401. Fail closed even if that
        // response arrived after a mutation invalidated this read generation.
        this.pause(); this.clearOwner();
        this.set({ refreshError: errorMessage(error) });
      }
      this.syncSession();
    } finally {
      this.backgroundTask = null;
      this.set({ refreshing: false });
    }
  }
  create(body: { game_name: string; starting_country_id: string }): Promise<void> {
    return this.run(async () => {
      if (!this.api.currentSession) return;
      this.set({ pending: { kind: 'create', operation: this.api.prepareCreation(body) } });
      await this.submitPending();
    }, { waitForRefresh: false });
  }
  private controls(kind: 'human' | 'npc'): boolean {
    return !!this.state.session && this.ownsCurrentGame() && !!this.state.game && playable(this.state.game)
      && activeParticipant(this.state.game)?.kind === kind;
  }
  act(action: ActionCommand['action']): Promise<void> {
    return this.run(async () => {
      if (!this.controls('human') || !this.state.gameId || !this.state.game) return;
      const command = { action_id: crypto.randomUUID(), expected_revision: this.state.game.revision!, action };
      this.set({ pending: { kind: 'human', operation: this.api.prepareAction(this.state.gameId, command) } });
      await this.submitPending();
    }, { waitForRefresh: false });
  }
  stepNpc(): Promise<void> {
    return this.run(async () => {
      if (!this.controls('npc') || !this.state.gameId || !this.state.game) return;
      this.set({ pending: { kind: 'npc', operation: this.api.prepareNpcStep(this.state.gameId, this.state.game.revision!) } });
      await this.submitPending();
    }, { waitForRefresh: false });
  }
  private async submitPending(): Promise<void> {
    const pending = this.state.pending;
    if (!pending) return;
    if (pending.kind === 'create') {
      const game = await this.api.createGame(pending.operation);
      if (this.api.currentSession) this.ownerContext = { session: this.api.currentSession, gameId: game._id! };
      this.set({ pending: null, gameId: game._id!, game, owner: true, events: [], eventCursor: 0,
        moreEvents: false, lastResult: null, notice: 'Game created. Share this page to let others watch.' });
      await this.loadEvents();
    } else {
      const outcome: ActionOutcome = pending.kind === 'human'
        ? await this.api.humanAction(pending.operation) : await this.api.npcStep(pending.operation);
      this.set({ pending: null, lastResult: outcome.response });
      this.applyGame(outcome.state);
      await this.loadEvents();
    }
  }
  retryPending(): Promise<void> {
    return this.run(async () => {
      if (!this.state.session) return;
      await this.api.refreshCsrf();
      await this.submitPending();
    }, { retry: true, waitForRefresh: false });
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
