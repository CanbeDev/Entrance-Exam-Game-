import type {
  ActionCommand, ActionOutcome, CountryCatalog, Credentials, CsrfResponse, EventFilters,
  GameFilters, GameSetupRequest, HealthResponse, HomeResponse, LoginResponse, NpcStepRequest,
  PublicEventPage, PublicGame, PublicGameList, Session, UserPublic,
} from './contracts.ts';
import { ApiError, HttpClient } from './http.ts';
import type { HttpOptions } from './http.ts';
import { catalogSchema, component, csrfSchema, loginSchema, parser } from './validation.ts';

export interface CreationOperation { readonly key: string; readonly body: GameSetupRequest }
export interface HumanOperation { readonly gameId: string; readonly command: ActionCommand }
export interface NpcOperation { readonly gameId: string; readonly command: NpcStepRequest }

function validate<T>(check: (value: unknown) => T, value: unknown): T {
  try { return check(value); }
  catch { throw new ApiError('client', { code: 'invalid_request' }); }
}
function cloneFrozen<T>(value: T): T {
  const freeze = (item: unknown): void => {
    if (item !== null && typeof item === 'object') {
      Object.values(item).forEach(freeze);
      Object.freeze(item);
    }
  };
  const copy: T = structuredClone(value);
  freeze(copy);
  return copy;
}
function identifier(value: string): string {
  if (!/^[a-zA-Z0-9_-]{1,128}$/.test(value)) throw new ApiError('client', { code: 'invalid_identifier' });
  return value;
}
function gameId(value: string): string {
  if (!/^[a-fA-F0-9]{24}$/.test(value)) throw new ApiError('client', { code: 'invalid_game_id' });
  return value.toLowerCase();
}
function integer(value: number, min: number, max = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isSafeInteger(value) || value < min || value > max) throw new ApiError('client', { code: 'invalid_request' });
  return value;
}
function query(filters: Record<string, unknown>): string {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined) params.set(key, String(value));
  });
  const encoded = params.toString();
  return encoded ? `?${encoded}` : '';
}

/** One client per browser session; all session/CSRF state is memory-only. */
export class GameApi {
  private readonly http: HttpClient;
  #csrf: string | undefined;
  private session: Session | null = null;
  private readonly states = new Map<string, PublicGame>();
  private readonly inFlight = new Set<string>();
  private authBusy = false;
  constructor(options: HttpOptions = {}) {
    this.http = new HttpClient(options);
    this.http.onError = (error) => {
      if (error.status === 401) this.clearSession();
      if (error.code === 'csrf_rejected') this.#csrf = undefined;
    };
  }
  get currentSession(): Session | null { return this.session; }
  private clearSession(): void { this.session = null; this.#csrf = undefined; }
  private csrfHeaders(): Record<string, string> {
    if (!this.#csrf) throw new ApiError('client', { code: 'csrf_not_initialized' });
    return { 'X-CSRF-Token': this.#csrf };
  }
  private async authOperation<T>(operation: () => Promise<T>): Promise<T> {
    if (this.authBusy) throw new ApiError('client', { code: 'authentication_in_flight' });
    this.authBusy = true;
    try { return await operation(); } finally { this.authBusy = false; }
  }

  home(): Promise<HomeResponse> {
    return this.http.request('/', { parse: parser<HomeResponse>({ type: 'object', required: ['message'],
      properties: { message: { type: 'string' } } }) });
  }
  health(): Promise<HealthResponse> {
    return this.http.request('/health', { parse: parser<HealthResponse>({ type: 'object', required: ['status', 'database'],
      properties: { status: { const: 'healthy' }, database: { const: 'connected' } } }) });
  }
  countries(): Promise<CountryCatalog> {
    return this.http.request('/countries', { parse: parser<CountryCatalog>(catalogSchema) });
  }
  register(credentials: Credentials): Promise<UserPublic> {
    const body = cloneFrozen(validate(component('Credentials'), credentials));
    return this.http.request('/auth/register', { method: 'POST', body, parse: component('UserPublic') });
  }
  private async initializeSession(user: UserPublic, expiresAt?: string): Promise<Session> {
    await this.refreshCsrf();
    this.session = Object.freeze({ user: cloneFrozen(user), ...(expiresAt ? { expiresAt } : {}) });
    return this.session;
  }
  async refreshCsrf(): Promise<void> {
    const result = await this.http.request('/auth/csrf', { parse: parser<CsrfResponse>(csrfSchema) });
    this.#csrf = result.csrf_token;
  }
  login(credentials: Credentials): Promise<Session> {
    return this.authOperation(async () => {
      this.clearSession();
      const body = cloneFrozen(validate(component('Credentials'), credentials));
      const result = await this.http.request('/auth/login', {
        method: 'POST', body, parse: parser<LoginResponse>(loginSchema),
      });
      return this.initializeSession(result.user, result.expires_at);
    });
  }
  async signUp(credentials: Credentials): Promise<Session> {
    await this.register(credentials); // Registration intentionally does not authenticate.
    return this.login(credentials); // Login obtains CSRF before resolving the session.
  }
  currentUser(): Promise<UserPublic> {
    return this.http.request('/auth/me', { parse: component('UserPublic') });
  }
  restoreSession(): Promise<Session | null> {
    return this.authOperation(async () => {
      this.clearSession();
      try { return await this.initializeSession(await this.currentUser()); }
      catch (error) {
        this.clearSession();
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    });
  }
  logout(): Promise<void> {
    return this.authOperation(async () => {
      try {
        await this.http.request('/auth/logout', { method: 'POST', headers: this.csrfHeaders(), parse: (value) => {
          if (value !== undefined) throw new Error();
        } });
      } finally {
        // Failures still propagate; clearing memory is not proof of server revocation.
        this.clearSession();
      }
    });
  }
  listGames(filters: GameFilters = {}): Promise<PublicGameList> {
    if (filters.status !== undefined && !['waiting', 'active', 'completed'].includes(filters.status)) {
      throw new ApiError('client', { code: 'invalid_game_filter' });
    }
    if (filters.query !== undefined && (typeof filters.query !== 'string' || filters.query.length > 100)) {
      throw new ApiError('client', { code: 'invalid_game_filter' });
    }
    return this.http.request(`/me/games${query({ status: filters.status, query: filters.query,
      cursor: filters.cursor === undefined ? undefined : gameId(filters.cursor),
      limit: filters.limit === undefined ? undefined : integer(filters.limit, 1, 100) })}`, {
      parse: component('PublicGameList'),
    });
  }

  prepareCreation(body: GameSetupRequest, key: string = crypto.randomUUID()): CreationOperation {
    return cloneFrozen({ key: identifier(key), body: validate(component('GameSetupRequest'), body) });
  }
  async createGame(operation: CreationOperation): Promise<PublicGame> {
    const prepared = this.prepareCreation(operation.body, operation.key);
    return this.serial(`create:${prepared.key}`, async () => {
      const state = await this.http.request('/games', { method: 'POST', body: prepared.body,
        headers: { ...this.csrfHeaders(), 'Idempotency-Key': prepared.key }, parse: component('PublicGame') });
      if (!state._id || !/^[a-fA-F0-9]{24}$/.test(state._id)) throw new ApiError('malformed', { uncertain: true });
      const id = gameId(state._id);
      const previous = this.states.get(id);
      if (previous?.revision != null && state.revision != null && previous.revision > state.revision) {
        return this.getGame(id);
      }
      return this.remember(id, state);
    });
  }
  cachedGame(id: string): PublicGame | undefined { return this.states.get(gameId(id)); }
  private remember(id: string, state: PublicGame): PublicGame {
    if (state._id && state._id.toLowerCase() !== id) throw new ApiError('malformed');
    const previous = this.states.get(id);
    if (previous?.revision != null && (state.revision == null || previous.revision > state.revision)) return previous;
    const snapshot = cloneFrozen(state);
    this.states.set(id, snapshot);
    return snapshot;
  }
  async getGame(id: string): Promise<PublicGame> {
    id = gameId(id);
    const state = await this.http.request(`/games/${id}`, { parse: component('PublicGame') });
    return this.remember(id, state);
  }
  events(id: string, filters: EventFilters = {}): Promise<PublicEventPage> {
    return this.http.request(`/games/${gameId(id)}/events${query({
      after_revision: filters.after_revision === undefined ? undefined : integer(filters.after_revision, 0),
      limit: filters.limit === undefined ? undefined : integer(filters.limit, 1, 100),
    })}`, { parse: component('PublicEventPage') });
  }
  prepareAction(id: string, command: ActionCommand): HumanOperation {
    return cloneFrozen({ gameId: gameId(id), command: validate(component('ActionCommand'), command) });
  }
  prepareNpcStep(id: string, expectedRevision: number): NpcOperation {
    return cloneFrozen({ gameId: gameId(id), command: { expected_revision: integer(expectedRevision, 0) } });
  }
  private async serial<T>(key: string, operation: () => Promise<T>): Promise<T> {
    if (this.inFlight.has(key)) throw new ApiError('client', { code: 'mutation_in_flight' });
    this.inFlight.add(key);
    try { return await operation(); } finally { this.inFlight.delete(key); }
  }
  private async mutate(id: string, path: string, body: unknown, beforePost?: () => void): Promise<ActionOutcome> {
    return this.serial(id, async () => {
      try {
        const headers = this.csrfHeaders();
        beforePost?.();
        const response = await this.http.request(path, { method: 'POST', body,
          headers, parse: component('PublicActionResult') });
        // Keep route identity separately: receipt.state can legitimately omit _id.
        if (response.state.revision == null) throw new ApiError('malformed', { uncertain: true });
        const previous = this.states.get(id);
        const staleResponse = previous?.revision != null && response.state.revision < previous.revision;
        const state = staleResponse ? await this.getGame(id) : this.remember(id, response.state);
        return Object.freeze({ state, response: cloneFrozen(response), staleResponse });
      } catch (error) {
        if (error instanceof ApiError && error.kind === 'malformed' && !error.uncertain) {
          throw new ApiError('malformed', { status: error.status, uncertain: true });
        }
        if (error instanceof ApiError && error.status === 409) {
          try { error.latestState = await this.getGame(id); } catch { /* Keep the original conflict; caller sees no invented state. */ }
        }
        throw error;
      }
    });
  }
  humanAction(operation: HumanOperation): Promise<ActionOutcome> {
    const prepared = this.prepareAction(operation.gameId, operation.command);
    return this.mutate(prepared.gameId, `/games/${prepared.gameId}/actions`, prepared.command);
  }
  npcStep(operation: NpcOperation, beforePost?: () => void): Promise<ActionOutcome> {
    const prepared = this.prepareNpcStep(operation.gameId, operation.command.expected_revision);
    return this.mutate(prepared.gameId, `/games/${prepared.gameId}/npc-steps`, prepared.command, beforePost);
  }
}
