// Untyped OpenAPI responses supplemented from the actual FastAPI route/service code.
import type { PublicPopulationSnapshot, UserPublic, PublicActionResult, PublicGame } from './generated.ts';
export type * from './generated.ts';

export interface LoginResponse { readonly user: UserPublic; readonly expires_at: string }
export interface CsrfResponse { readonly csrf_token: string }
export interface CountryCatalog {
  readonly population_snapshot: PublicPopulationSnapshot;
  readonly countries: ReadonlyArray<{
    readonly id: string; readonly name: string; readonly population: number;
    readonly base_soldier_value: number;
  }>;
}
export interface HomeResponse { readonly message: string }
export interface HealthResponse { readonly status: 'healthy'; readonly database: 'connected' }
export interface Session { readonly user: UserPublic; readonly expiresAt?: string }
export interface GameFilters {
  readonly status?: 'waiting' | 'active' | 'completed';
  readonly query?: string; readonly cursor?: string; readonly limit?: number;
}
export interface EventFilters { readonly after_revision?: number; readonly limit?: number }
export interface ActionOutcome {
  /** Use this authoritative state for rendering; an old replay cannot rewind it. */
  readonly state: PublicGame;
  /** Original server receipt, including its historical events/evidence. */
  readonly response: PublicActionResult;
  readonly staleResponse: boolean;
}
