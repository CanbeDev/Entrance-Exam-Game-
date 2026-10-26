# Phase 4 startup and controlled deployment

`app.main:app` now defines routes without loading `.env`, importing `app.database`
or creating a client. FastAPI lifespan loads validated process configuration,
creates an owned client with bounded timeouts, pings the database, reads readiness
metadata, then composes the existing `build_phase4_context` services and an
explicitly injected public game repository. Blocking initialization/close run in a
thread pool. Failure/shutdown clears context/read dependencies and closes the
client, including initialization failure after client creation. Exceptions use
fixed categories, never URI/driver/request values.

Missing/invalid configuration or a failed ping aborts startup. Both write flags
default false. With writes disabled, unavailable Phase 4 readiness leaves public
reads available and emits only a fixed readiness warning. With either flag enabled,
startup refuses to publish services unless readiness passes. Gameplay requires
authentication; authentication requires a nonempty trusted-origin list. Existing
repository index checks still run before each enabled write.

Readiness uses `hello`, index information and collection metadata only. It requires
sessions, replica-set/sharded topology, a writable server, wire version at least 8,
the eight exact manifest indexes, and five exact strict/error validators. It never
creates collections/indexes/validators, runs transactions or scans historical data.
It cannot prove transaction privileges, audit old records or replace separately
authorized disposable verification. `/health` keeps its existing ping-only
response: healthy does not mean Phase 4 is activated or its schema is ready.

## Process configuration (proposed, not applied to Render)

| Variable | Contract/default |
| --- | --- |
| `MONGODB_URI` | Required secret; approved target and credentials supplied privately. Remote targets require verified TLS. No insecure certificate/proxy/file overrides or unacknowledged writes. |
| `MONGODB_DB_NAME` | Required explicit existing database; no default/fallback. 1-38 ASCII letters, digits, `_` or `-`. |
| `PHASE4_AUTH_WRITES_ENABLED` | `false` by default; only literal `true`/`false`. Keep `false` until separately approved activation. |
| `PHASE4_GAMEPLAY_WRITES_ENABLED` | `false` by default; requires auth gate. Keep `false` until separately approved activation. |
| `PHASE4_TRUSTED_ORIGINS` | JSON array, default `[]`; distinct exact origins, no paths, wildcard, credentials or trailing slash. Public origins require HTTPS; loopback HTTP allowed for tooling only. |
| `PHASE4_IDLE_SECONDS` | Positive integer, default `1800`; cannot exceed absolute lifetime. |
| `PHASE4_ABSOLUTE_SECONDS` | Positive integer, default `43200`. |
| `PHASE4_MAX_BODY_BYTES` | Positive integer, default `16384`. |
| `PHASE4_LOGIN_ACCOUNT_LIMIT` | Positive integer, default `10`. |
| `PHASE4_LOGIN_IP_LIMIT` | Positive integer, default `30`. |
| `PHASE4_REGISTER_IP_LIMIT` | Positive integer, default `5`. |
| `PHASE4_GAMEPLAY_LIMIT` | Positive integer, default `120`. |
| `PORT` | Provided by Render for the proposed server command. |

Unknown `PHASE4_` names fail validation to catch typos. Limits accept up to nine
ASCII digits. No credentials/environment values are logged. Local execution must
supply process settings explicitly; implicit `.env` loading is intentionally absent
from web startup. Legacy local tools retain their existing database module and
must not be run accidentally against configured Atlas data.

The browser contract remains `__Host-geopolitics_session`, Secure, HttpOnly,
SameSite=Lax, Path=/, no Domain, and `X-CSRF-Token` for authenticated mutations.
There is no configurable cookie/CSRF bypass or session-signing secret to invent:
sessions use the existing opaque-token/hash storage. POST Origin checks still
apply. Credentialed CORS is limited to the exact trusted origins, GET/POST and
Content-Type/X-CSRF-Token/Idempotency-Key headers. Untrusted/duplicate origins get
no CORS credential headers. Prefer same-origin HTTPS. CORS does not make Lax
cookies work for arbitrary cross-site frontend/backend domains; that architecture
needs a separate review. Do not weaken cookie flags to work around it.

Forwarded client IP headers remain untrusted application input. Separately verify
Render/Uvicorn proxy trust and HTTPS termination before activation; do not blindly
trust every forwarded sender. Shared account limits remain in place.

## Staged plan (each external/configuration change needs approval)

1. Review this local patch and isolated results. The 23-case Atlas TEST validator
   integration run verifies repositories/services under real validators. The
   separate one-case read-only Atlas TEST startup smoke verifies closed-gate
   lifespan wiring and shutdown without provisioning. Neither proves deployment
   of the new code to Render or production readiness.
2. Separately authorize a TEST-only deployment/configuration check. Confirm the
   Linux Python/dependency/Argon2 build and approved database identity, TLS, network
   access and least-privilege roles. Supply secrets privately. Start with both
   write flags false, review fixed readiness warnings and test public endpoints.
   Proposed command from `backend`: `uvicorn app.main:app --host 0.0.0.0 --port "$PORT"`.
3. Before production, separately approve read-only inspection and any required
   database maintenance. Review legacy data, uniqueness conflicts, all five strict
   validators/eight indexes and transaction permissions on a session-capable
   replica set/sharded deployment. Existing custom validators need review; startup
   never replaces them. The operational provisioner remains loopback-only.
4. Review origins/proxy/session/CSRF behavior over actual browser HTTPS. After
   explicit approval enable authentication first and verify registration, login,
   expiry/logout, CSRF, rate limits and owner denial using designated accounts.
   Gameplay stays disabled during this stage.
5. Only after further approval enable gameplay and verify idempotent creation,
   human/NPC actions, receipts/events, conflicts and resumability. Watch errors
   without logging bodies/tokens. Roll back activation by closing gates and
   redeploying the last reviewed release; do not revert/delete persisted games.

No Render settings, credentials, production data, write gates or deployment were
changed by this local work. Frontend, visible battles/fast-forward, LLM commentary
and submission packaging remain mandatory project work.

Latest isolated verification (2026-10-26): **757 passed, 0 failed/errors, 44 skipped,
1 existing warning in 13.78s; exit code 0**. The separate Atlas TEST validator
integration passed **23 tests, 0 failed/errors/skipped in 101.80s; exit code 0**.
The separately authorized read-only Atlas TEST startup smoke passed **1 test,
0 failed/errors/skipped, 2 deprecation warnings in 347.96s; exit code 0**. Both
write gates stayed disabled, all four public endpoints returned 200, shutdown
closed the client and no database was created or provisioned. Protected readiness
was `indexes_not_ready`. The smoke elapsed time includes interactive prompts;
it does not isolate startup latency. See [Testing](TESTING.md) for the safe
isolated invocation and the distinctions between these verification runs.
