# Functional frontend (Phase 3)

The simple React interface now uses the Phase 2 client for registration/login,
session restoration/logout, owner-game search/filter/paging/resume, country
selection and creation, the ten-country board, phase-specific human controls,
NPC stepping/visible fast-forward, committed history and public viewing.
No Phase 4 design, audio or GroqCloud commentary has been added.

Phase 3 passed 54 automated tests, TypeScript checks and the production build.
On 2026-10-29, the user reported successful core manual browser acceptance against
the offline fixture. Automated Chrome testing was blocked before interaction
because Computer Use could not determine the current URL confidently enough to
enforce policy. Production browser acceptance remains pending. See
[Phase 3 report](../docs/FRONTEND_PHASE3_REPORT.md).
Stop for review before the next phase. The API/proxy notes below remain applicable.

## Safe local browser smoke procedure

From `frontend`, run `node tests/serve-smoke.mjs`, then open
`http://127.0.0.1:5174` manually. This distinct test server has no production
proxy/database configuration. Its banner identifies scripted offline fixtures;
they demonstrate UI integration and do not implement/verify the battle engine,
strategic NPCs or production authentication. It uses a distinct HTTP-only fixture
cookie, not the real Secure/__Host cookie. Do not enter real credentials.

1. Create an account with synthetic throwaway values. Confirm an empty My Games
   list, then create a game starting with South Africa.
2. Confirm all ten countries, soldiers, round and active participant. Start an
   attack against Vatican City, roll and inspect the returned dice/losses.
3. Transfer one soldier to the captured country, then end the turn. Advance an
   NPC action, inspect its visible fixture explanation, then fast-forward/pause.
   Resume fast-forward until the human allocation phase; allocate the shown full
   budget. No state is computed by React.
4. Reload the game URL: confirm session restoration, board and committed history.
   Return home; search/filter and resume the saved game.
5. Log out; confirm the shared URL still shows the board/history with no move
   controls. Logging in with another fixture account must not enable those controls.
6. For dashboard pagination, use the pre-seeded synthetic fixture account defined
   in `tests/mock-api.mjs`; it owns 12 saved fixtures. Check Next/Previous and search.
7. Stop the test server with Ctrl+C. All fixture data disappears with the process.

The user reported that core manual acceptance against this offline fixture passed.
This is separate from the blocked automated Chrome attempt. Controller equivalents
run in `npm.cmd test`. Production HTTPS cookies, exact Vercel Origin forwarding
and Stage E/F acceptance remain separately approved work.

## Local commands

Use Node 24+ and run from `frontend` (PowerShell uses `npm.cmd`):

```powershell
npm.cmd ci --ignore-scripts --no-audit --no-fund
npm.cmd run check:contracts
npm.cmd test
npm.cmd run build
```

Dependencies were installed with explicit user approval. `package-lock.json`
pins the installed graph. Tests use Node's built-in test runner, injected fetch
mocks and ephemeral loopback servers. No backend process, database client,
production service or account is used. `build` runs TypeScript before Vite and
does not need files outside this directory. Contract generation/checking and one
documentation-fixture test use the repository's `../docs` directory locally.

The Phase 1 plan artifact was not found in this checkout or local docs archive.
The user's phase boundaries control this implementation: Phase 2 API/proxy;
Phase 3 playable interface; Phase 4 visual design. No missing six-phase plan
details or prior approvals are invented.

## Contracts and endpoints

`scripts/generate-contracts.mjs` reads `../docs/openapi.json` without backend
imports/network. It produces 40 component types and runtime schemas, including
the source hash. Run `generate:api` after an approved schema change, then
`check:contracts`, tests and build. Action discriminators are required explicitly
on the wire. The small runtime validator supports the keywords used by this
export; it is not a general JSON Schema library.

OpenAPI has untyped auth/catalog/public responses and does not describe the whole
security contract. `contracts.ts` and parsers supplement it from actual routes,
services and public models. There is no commentary contract in this backend yet.

| Client method | Backend operation (browser adds `/api`) |
| --- | --- |
| `home` | `GET /` |
| `health` | `GET /health` |
| `countries` | `GET /countries` |
| `register` | `POST /auth/register` |
| `login` | `POST /auth/login`, then `GET /auth/csrf` |
| `currentUser` | `GET /auth/me` |
| `refreshCsrf` | `GET /auth/csrf` |
| `logout` | `POST /auth/logout` |
| `listGames` | `GET /me/games` with status/query/cursor/limit |
| `createGame` | `POST /games` with Idempotency-Key |
| `getGame` | `GET /games/{id}` |
| `events` | `GET /games/{id}/events` with after_revision/limit |
| `humanAction` | `POST /games/{id}/actions` |
| `npcStep` | `POST /games/{id}/npc-steps` (one action) |

Create one `GameApi` instance for the browser session. `signUp(credentials)`
performs register -> login -> CSRF; registration alone never logs in. Login does
not apply the registration minimum password length to existing credentials.
`restoreSession()` performs me -> CSRF and returns null on 401. Other failures
propagate. CSRF uses a private in-memory field, never browser storage or logs.
Authenticated POSTs require initialization. The browser supplies Origin/Cookie;
all requests use relative `/api`, credentials include, no-store and no redirects.
Authenticated GETs can update session/user fences on the server.

## Mutations, state and errors

Use `prepareCreation(body, key?)`, `prepareAction(gameId, command)` and
`prepareNpcStep(gameId, expectedRevision)` once per intended operation. Prepared
operations clone/freeze the payload. Keep the same object after an uncertain
response; explicitly resubmit it only when appropriate. No request is retried
automatically. Never replace an action ID/key/payload to force a second write.
Preparation does not contact any server.

One mutation per game may be in flight; overlapping human/NPC submissions fail
locally. Creation serializes by its idempotency key. For gameplay, render
`ActionOutcome.state`, and use `response.events`/`response.npc_decision` as the
original receipt evidence. Keep the route game ID separately, since action state
may omit `_id`. The client computes no dice, soldiers, ownership or NPC choices.

409 triggers one public-state refetch, then throws the original error with
`latestState` if available. It never resubmits the mutation. Older creation/action
receipts trigger a refetch; revision comparisons prevent a late GET or receipt
from overwriting newer cached state. Event pages remain evidence, not snapshots.

`ApiError` exposes kind, status, sanitized code, optional retryAfterMs, and
uncertain. 401 clears memory; 403 distinguishes ownership/Origin/CSRF rejection;
rejected CSRF requires explicit refresh. 429 supplies the exposed Retry-After
seconds/date delay without a retry loop. 503 preserves disabled/unavailable
codes. Network/timeout/malformed/server failures on POST are uncertain: a write
may have committed. Follow-up reads do not authorize a fresh mutation identity.
Failed logout clears local state but propagates failure; it does not prove server
revocation. Timeouts cover response parsing as well as fetch.

## Saved-request recovery and NPC acceptance limit

Local verification: 105 automated tests passed (75 existing plus 30 new), with
TypeScript, the production build and all 40 OpenAPI component checks passing.
This does not establish production recovery or browser acceptance of the patch.

An outstanding operation retains its original account, game, payload and action
ID/key/revision. Failed retry preparation, including expired sessions, keeps the
operation and blocks fresh mutations. Recovery login accepts only the original
account ID, checks ownership and never submits the operation. Use **Retry saved
request** explicitly; it refreshes CSRF and checks account/ownership again.
An unconfirmed retry rejection keeps the lock for review. Do not reload or leave
while a saved request remains: it exists only in page memory. A new deployment
does not migrate the pending operation from an already-open production tab.

On an owned game, open **Optional NPC acceptance limit** and enter a maximum
number of NPC POST attempts for this page. Zero blocks attempts; an unset limit
preserves normal fast-forward. Manual steps, fast-forward and retries share the
counter. CSRF/ownership preparation does not consume an attempt. Fast-forward
stops at the limit, a human turn, completion, Pause or an error. Pause lets an
already-submitted action settle and prevents further scheduling.

Changing the limit never resets attempts; reload does. This is a local acceptance
aid, not a server-enforced lifetime quota. Reconcile earlier attempts, including
failed attempts/retries, before setting a limit within the approved remaining
30-attempt Stage F allowance. Never assume 30 attempts remain. There is no
five-second manual Pause requirement. Production recovery/testing and deployment
still require separate approval; use the offline smoke fixture for local checks.

## Development proxy

`npm.cmd run dev` serves loopback only. `/api/*` defaults to a loopback API at
`http://127.0.0.1:8000`; tests substitute a mock. No real backend is started by
these commands. If manually running an approved local service, optional
`LOCAL_API_TARGET` must remain loopback. No VITE variable or backend secret is
needed. Existing trusted local certificate/key paths can be supplied through
`LOCAL_HTTPS_CERT` and `LOCAL_HTTPS_KEY`; no certificate is generated/installed.

Default HTTP development does not prove the Secure/__Host cookie works in a
browser. Use approved HTTPS for real session acceptance. The proxy preserves
Origin, Cookie, CSRF, response Set-Cookie and cookie attributes. TLS verification
remains enabled. No Domain/Path/cookie-security rewrite is configured.

## Vercel production configuration and remaining browser acceptance

Selected future Vercel Root Directory: `frontend`, Vite build, output `dist`.
`vercel.json` puts the `/api/:path*` rewrite before the SPA fallback and points to
the user-supplied existing Render base URL. It strips `/api`, excludes API paths
from SPA fallback, adds no-store and disables external rewrite caching. No Vercel
frontend hostname is invented. The hostname is not required for this source
configuration; it is required for the later exact trusted-origin setting.

The [Vercel rewrite documentation](https://vercel.com/docs/routing/rewrites)
supports external proxying with the original browser URL and documents cache
controls. It does not establish that this undeployed project's browser Origin
and session-cookie flow has passed. The configuration adds no Origin transform;
the required behavior is to forward the original Vercel Origin to Render.
[Vite's proxy documentation](https://vite.dev/config/server-options#server-proxy)
describes the development proxy mechanism. Its loopback forwarding is tested;
that test is not Vercel/browser proof.

After separately approved deployment/activation, verify through the actual Vercel
HTTPS origin: `/api` routing, original Origin accepted, login cookie accepted and
sent back, CSRF protection, reload restoration, logout deletion and no shared
caching. Preserve `Path=/`, Secure, HttpOnly, SameSite=Lax and no Domain. Do not
weaken cookie/Origin controls if forwarding fails. A successful auth flow with
only the actual Vercel origin trusted supplies acceptance evidence; no new
diagnostic endpoint/header logging is needed.

Keep origins `[]` and both protected-write gates false until separate approval.
Stage E enables auth only; gameplay stays false. Follow
[Stage E](../docs/STAGE_E_AUTH_ACTIVATION.md). Stage F gameplay uses new owned
games after authentication passes. The functional frontend and visible fast-forward
are implemented locally. Production acceptance, GroqCloud commentary and the
submission package remain mandatory later work.
