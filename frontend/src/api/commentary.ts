import type { BattleCommentary } from './contracts.ts';
import { ApiError } from './http.ts';

type Transport = (gameId: string, revision: number) => Promise<BattleCommentary>;
type Task = () => Promise<void>;

/** Separate queues: narration can never occupy the gameplay mutation lock. */
class BoundedQueue {
  private active = 0;
  private readonly waiting: Task[] = [];
  private readonly concurrency: number;
  constructor(concurrency: number) { this.concurrency = concurrency; }
  run<T>(work: () => Promise<T>): Promise<T> {
    if (this.waiting.length >= 128) return Promise.reject(new ApiError('client', { code: 'commentary_queue_full' }));
    return new Promise<T>((resolve, reject) => {
      const task = async () => {
        this.active++;
        try { resolve(await work()); } catch (error) { reject(error); }
        finally { this.active--; void this.waiting.shift()?.(); }
      };
      if (this.active < this.concurrency) void task();
      else this.waiting.push(task);
    });
  }
}

/** Per-page optimization only. The backend persists the billing/deduplication claim. */
export class BattleCommentaryRequests {
  private readonly reads = new BoundedQueue(2);
  private readonly writes = new BoundedQueue(1);
  private readonly reading = new Map<string, Promise<BattleCommentary>>();
  private readonly writing = new Map<string, Promise<BattleCommentary>>();
  private readonly cache = new Map<string, BattleCommentary>();
  private readonly attempted = new Set<string>();
  private readonly read: Transport;
  private readonly generate: Transport;
  constructor(read: Transport, generate: Transport) { this.read = read; this.generate = generate; }
  private identity(gameId: string, revision: number): string {
    if (!/^[a-f0-9]{24}$/.test(gameId) || !Number.isSafeInteger(revision) || revision < 1) {
      throw new ApiError('client', { code: 'invalid_commentary_identity' });
    }
    return `${gameId}:${revision}`;
  }
  private remember(key: string, gameId: string, revision: number, value: BattleCommentary): BattleCommentary {
    if (value.game_id !== gameId || value.revision !== revision) throw new ApiError('malformed');
    const previous = this.cache.get(key);
    // A GET started before generation must not replace ready output or pending work.
    const rank = { not_generated: 0, pending: 1, fallback: 2, ready: 3 };
    if (previous && rank[previous.status] > rank[value.status]) return previous;
    const copy = structuredClone(value);
    Object.freeze(copy.facts.attacker_dice); Object.freeze(copy.facts.defender_dice); Object.freeze(copy.facts.eliminated);
    Object.freeze(copy.facts); Object.freeze(copy);
    this.cache.delete(key); this.cache.set(key, copy);
    if (copy.status !== 'not_generated') this.attempted.delete(key);
    if (this.cache.size > 256) this.cache.delete(this.cache.keys().next().value!);
    return copy;
  }
  get(gameId: string, revision: number, refresh = false): Promise<BattleCommentary> {
    const key = this.identity(gameId, revision);
    const cached = this.cache.get(key);
    if (cached && (!refresh || cached.status === 'ready'
        || cached.status === 'fallback' && cached.reason !== 'interrupted')) return Promise.resolve(cached);
    const active = this.reading.get(key);
    if (active) return active;
    const request = this.reads.run(async () => this.remember(key, gameId, revision, await this.read(gameId, revision)))
      .finally(() => this.reading.delete(key));
    this.reading.set(key, request);
    return request;
  }
  request(gameId: string, revision: number, permitted: () => boolean = () => true): Promise<BattleCommentary> {
    const key = this.identity(gameId, revision);
    const active = this.writing.get(key);
    if (active) return active;
    const cached = this.cache.get(key);
    if (cached && cached.status !== 'not_generated') return Promise.resolve(cached);
    // An uncertain response must only be checked with GET, never automatically replayed.
    if (this.attempted.has(key)) return Promise.reject(new ApiError('client', { code: 'commentary_check_saved' }));
    if (this.attempted.size >= 256) return Promise.reject(new ApiError('client', { code: 'commentary_recovery_limit' }));
    this.attempted.add(key);
    const request = this.writes.run(async () => {
      if (!permitted()) {
        this.attempted.delete(key);
        throw new ApiError('client', { code: 'commentary_cancelled' });
      }
      return this.remember(key, gameId, revision, await this.generate(gameId, revision));
    })
      .finally(() => this.writing.delete(key));
    this.writing.set(key, request);
    return request;
  }
}
