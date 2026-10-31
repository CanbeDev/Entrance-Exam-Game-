import type { PublicGame } from './generated.ts';
import type { Parser } from './validation.ts';

export type ErrorKind = 'unauthenticated' | 'forbidden' | 'conflict' | 'rate_limited'
  | 'unavailable' | 'http' | 'network' | 'timeout' | 'malformed' | 'client';
export interface RequestDiagnostics {
  readonly elapsedMs: number;
  readonly phase: 'response' | 'body' | 'validation';
  readonly responseStatus?: number;
}
export class ApiError extends Error {
  readonly kind: ErrorKind;
  readonly status: number | undefined;
  readonly code: string;
  readonly retryAfterMs: number | undefined;
  readonly uncertain: boolean;
  readonly diagnostics?: RequestDiagnostics;
  latestState?: PublicGame;
  constructor(kind: ErrorKind, options: {
    status?: number; code?: string; retryAfterMs?: number; uncertain?: boolean; diagnostics?: RequestDiagnostics;
  } = {}) {
    super(`API request failed: ${kind}`);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = options.status;
    this.code = options.code ?? kind;
    this.retryAfterMs = options.retryAfterMs;
    this.uncertain = options.uncertain ?? false;
    this.diagnostics = options.diagnostics ? Object.freeze({ ...options.diagnostics }) : undefined;
  }
}

/** Exposed header only; callers pause explicitly. No automatic request replay. */
export function retryAfterMs(value: string | null, now = Date.now()): number | undefined {
  if (!value) return undefined;
  if (/^\d+$/.test(value.trim())) {
    const ms = Number(value) * 1000;
    return Number.isSafeInteger(ms) ? ms : undefined;
  }
  if (!/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), /.test(value)) return undefined;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.max(0, timestamp - now) : undefined;
}
function errorKind(status: number): ErrorKind {
  const categories: Partial<Record<number, ErrorKind>> = {
    401: 'unauthenticated', 403: 'forbidden', 409: 'conflict', 429: 'rate_limited', 503: 'unavailable',
  };
  return categories[status] ?? (status >= 500 ? 'unavailable' : 'http');
}

export interface HttpOptions {
  readonly fetch?: typeof globalThis.fetch;
  readonly timeoutMs?: number;
}
interface RequestOptions<T> {
  readonly method?: 'GET' | 'POST'; readonly body?: unknown;
  readonly headers?: Record<string, string>; readonly parse: Parser<T>;
  readonly anonymous?: boolean;
}

export class HttpClient {
  private readonly fetcher: typeof globalThis.fetch;
  private readonly timeout: number;
  onError?: (error: ApiError) => void;
  constructor(options: HttpOptions = {}) {
    this.fetcher = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.timeout = options.timeoutMs ?? 20_000;
    if (!Number.isFinite(this.timeout) || this.timeout <= 0) throw new ApiError('client');
  }

  async request<T>(path: string, options: RequestOptions<T>): Promise<T> {
    // API base is deliberately fixed. No caller can send cookies/tokens off-origin.
    if (!/^\/[a-zA-Z0-9_/?=&%+~.-]*$/.test(path) || path.includes('//')) {
      throw new ApiError('client', { code: 'invalid_api_path' });
    }
    const method = options.method ?? 'GET';
    const mutation = method === 'POST';
    const started = performance.now();
    let phase: RequestDiagnostics['phase'] = 'response';
    let responseStatus: number | undefined;
    const controller = new AbortController();
    let timedOut = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
        reject(new ApiError('timeout', { uncertain: mutation }));
      }, this.timeout);
    });
    const execute = async (): Promise<T> => {
      const headers: Record<string, string> = { Accept: 'application/json', ...options.headers };
      const body = options.body === undefined ? undefined : JSON.stringify(options.body);
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      // The browser owns Origin and Cookie. Never synthesize them in app code.
      const response = await this.fetcher(`/api${path}`, {
        method, headers, body, credentials: options.anonymous ? 'omit' : 'include', cache: 'no-store',
        redirect: 'error', signal: controller.signal,
      });
      responseStatus = response.status;
      phase = 'body';
      if (!response.ok) {
        let code: string | undefined;
        try {
          const payload = await response.json();
          const candidate = payload?.detail?.code;
          // Never surface raw response bodies, driver exceptions or user inputs.
          if (typeof candidate === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(candidate)) code = candidate;
        } catch { /* Public legacy errors may be strings or non-JSON. */ }
        throw new ApiError(errorKind(response.status), {
          status: response.status, code,
          retryAfterMs: retryAfterMs(response.headers.get('Retry-After')),
          uncertain: mutation && response.status >= 500,
        });
      }
      let value: unknown;
      if (response.status !== 204) {
        const contentType = response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase();
        if (!(contentType === 'application/json' || contentType?.endsWith('+json'))) {
          throw new ApiError('malformed', { status: response.status, uncertain: mutation });
        }
        try { value = await response.json(); }
        catch (cause) {
          if (cause instanceof TypeError || cause instanceof DOMException && cause.name === 'AbortError') {
            throw new ApiError(timedOut ? 'timeout' : 'network', { uncertain: mutation });
          }
          throw new ApiError('malformed', { status: response.status, uncertain: mutation });
        }
      }
      phase = 'validation';
      try { return options.parse(value); }
      catch {
        throw new ApiError('malformed', { status: response.status, uncertain: mutation });
      }
    };
    try {
      return await Promise.race([execute(), deadline]);
    } catch (cause) {
      const base = cause instanceof ApiError ? cause : new ApiError(timedOut ? 'timeout' : 'network', {
        uncertain: mutation,
      });
      // Header status is diagnostic only: a body timeout must not become a 409
      // or otherwise trigger protocol decisions for a completed HTTP response.
      const error = new ApiError(base.kind, { status: base.status, code: base.code,
        retryAfterMs: base.retryAfterMs, uncertain: base.uncertain,
        diagnostics: { elapsedMs: Math.round(performance.now() - started), phase,
          ...(responseStatus === undefined ? {} : { responseStatus }) } });
      this.onError?.(error);
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
}
