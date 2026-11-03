# Geopolitics frontend

The simple React interface now uses the Phase 2 client for registration/login,
session restoration/logout, owner-game search/filter/paging/resume, country
selection and creation, the ten-country board, phase-specific human controls,
NPC stepping/visible fast-forward, committed history and public viewing.
The UI redesign, world atlas, battle animation, GroqCloud commentary and optional
sound effects are implemented. Final connected acceptance of this working-tree
release is tracked in the [Stage 9 report](../docs/UI_STAGE9_ACCEPTANCE_REPORT.md).

Phase 3 passed 54 automated tests, TypeScript checks and the production build.
On 2026-10-29, the user reported successful core manual browser acceptance against
the offline fixture. Automated Chrome testing was blocked before interaction
because Computer Use could not determine the current URL confidently enough to
enforce policy. Production browser acceptance remains pending. See
[Phase 3 report](../docs/FRONTEND_PHASE3_REPORT.md).
These Phase 3 results are historical. Current Stage 9 checks pass 358 public frontend
tests, TypeScript, 43 contract components and the production build. The earlier
blocked Chrome attempt is separate from later direct-CDP offline fixture testing.

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

Public audio integrity is checked with `npm.cmd run check:sounds`; this uses the
18 prepared files and reviewed manifest without private source MP3s. Source-copy
verification is separate: privately supply the 19 originals at
`frontend/public/assets/audio/`, then run `npm.cmd run test:sound-sources`.
That explicit profile fails if sources are missing. Never deploy the private
verification directory or its build; deploy the reviewed Git package without originals.

Text-input checksums use canonical CRLF to preserve the existing identifiers on
LF and CRLF checkouts. Generated API types, country facts and map geometry are
unchanged. Run both map/reference `--check` scripts for offline data verification.

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
imports/network. It produces 43 component types and runtime schemas, including
the source hash. Run `generate:api` after an approved schema change, then
`check:contracts`, tests and build. Action discriminators are required explicitly
on the wire. The small runtime validator supports the keywords used by this
export; it is not a general JSON Schema library.

OpenAPI has untyped auth/catalog/public responses and does not describe the whole
security contract. `contracts.ts` and parsers supplement it from actual routes,
services and public models. Current contracts also include the implemented
saved-commentary read and owner-only generation routes.

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

Local verification: 141 automated tests passed, 0 failed/skipped (105 existing
plus 36 new), with TypeScript/build and all 40 contract checks passing. Tests use
short synthetic deadlines for fault injection; the real deadline stays 20 seconds.
Local tests do not establish production recovery or browser acceptance.

An outstanding operation retains its original account, game, payload and action
ID/key/revision. Failed retry preparation, including expired sessions, keeps the
operation and blocks fresh mutations. Recovery login accepts only the original
account ID, checks ownership and never submits the operation. Use **Retry saved
request** explicitly; it refreshes CSRF and checks account/ownership again.
An unconfirmed retry rejection keeps the lock for review. Do not reload or leave
while a saved request remains: it exists only in page memory. A new deployment
does not migrate the pending operation from an already-open production tab.

An uncertain NPC POST now pauses fast-forward and makes one bounded anonymous
receipt lookup, followed by an anonymous board read only if the receipt matches.
Confirmation checks the requested game route, successor revision, observed NPC,
original turn sequence, decision evaluation and canonical server action ID. An
advanced board revision alone is insufficient. Matching evidence and a usable
authoritative board clear pending without another POST; fast-forward stays paused.
Otherwise the same operation/account/payload remains locked. **Check committed
outcome (read only)** repeats those reads explicitly, including when the NPC POST
allowance is exhausted or the session has expired. It never sends authentication,
CSRF or gameplay POSTs. Read-check failure preserves pending and Retry-After.

Recovered transfers, dice/losses and explanations are merged into committed
history. A targeted receipt cannot skip unloaded history pages or rewind newer
state. A valid older action receipt whose follow-up state read fails also retains
the saved operation for confirmation. No missing result is treated as success.

The HTTP deadline remains 20 seconds. Errors expose only sanitized kind/status,
elapsed milliseconds, response/body/validation phase and observed header status.
Network failures while reading a body differ from malformed JSON/schema errors.
Observed headers alone do not prove complete response delivery. No raw exception,
request body, cookie, CSRF value or credential is logged. Successful reconciliation
reports the original response issue and confirmed committed move separately.

The development-only acceptance tools can set a maximum number of NPC POST
attempts for this page. This configuration is hidden in normal gameplay.
Zero blocks attempts; an unset limit
preserves normal fast-forward. Manual steps, fast-forward and retries share the
counter. CSRF/ownership preparation does not consume an attempt. Fast-forward
stops at the limit, a human turn, completion, Pause or an error. Pause lets an
already-submitted action settle and prevents further scheduling.

Changing the limit never resets attempts; reload does. This is a local acceptance
aid, not a server-enforced lifetime quota. Historical Stage F allowances do not
establish a current remaining count or authorize another test. There is no
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

Vercel Root Directory: `frontend`, Vite build, output `dist`.
`vercel.json` puts the `/api/:path*` rewrite before the SPA fallback and points to
the user-supplied existing Render base URL. It strips `/api`, excludes API paths
from SPA fallback, adds no-store and disables external rewrite caching.
The approved production origin is
`https://entrance-exam-game.vercel.app`.

The [Vercel rewrite documentation](https://vercel.com/docs/routing/rewrites)
supports external proxying with the original browser URL and documents cache
controls. Source configuration alone does not verify a deployed browser Origin
and session-cookie flow. The configuration adds no Origin transform;
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

New, unverified environments keep origins `[]` and both write gates false until
separately approved. The owner has already reported production authentication
and gameplay enabled; do not reconfigure that deployment based on historical
activation prose. Use [Stage E](../docs/STAGE_E_AUTH_ACTIVATION.md) as historical
procedure/evidence. Stage 9 uses human-operated connected gameplay; Codex does not
access production. The current release and submission package still need acceptance.

## Battle commentary

Committed dice-exchange receipts have a **Commentary** area alongside
the original dice, losses, ownership events and NPC explanation. Public reads
load saved narration. The game's authenticated owner can select **Generate
commentary**. **Commentary for new battles** defaults on for the authenticated
owner, during both human play and NPC fast-forward. The owner can turn it off.
Opening saved history or reloading starts at the current revision, so historical
exchanges do not generate new billable work. New receipts use an independent
cursor, separate from history pagination; there is no lifetime 16-exchange cutoff.
The scheduler reads at most 100 receipts and awaits one generation at a time.
It retains only 64 recent live displays; older narration stays retrievable from
saved history. Backend admission limits still apply to every new generation.
Turning it off cancels queued narration; a submitted request may finish. Account,
game and ownership checks prevent queued requests crossing access boundaries.

Narration has its own loading/error state and separate queues (two reads, one
generation request). It never sets gameplay busy, consumes an NPC attempt,
changes pending-operation identity, or resumes fast-forward. Requests share a
bounded per-page cache keyed by game and committed revision. Concurrent requests
for one receipt are deduplicated. After an uncertain response, **Check saved
commentary** performs only public GETs; the client never automatically retries
the billable request. The backend's persistent claim protects across reloads.
Counters persist across restarts: 100 global admissions per UTC day, 30 per game
per UTC day, 10 globally per minute, 60 globally per hour and 20 per account per
hour. A denied admission has a saved deterministic fallback and no Groq call.
Spectators can also use **Check saved commentary** after an initial not-generated
response, to retrieve narration completed later without a reload or billable POST.

Narration is generated by GroqCloud and appears as prose under Commentary; the
gameplay heading has no provider/model badge. Deterministic fallbacks remain
truthfully distinguished from provider narration. Spectators cannot
request generation. No provider key or provider environment variable belongs in
this frontend. Production provider availability and deployment acceptance remain
separate checks; local tests use deterministic mocks only.

### Audio Credits

Sound effects were generated using [ElevenLabs](https://elevenlabs.io).

These sound effects were created using the ElevenLabs Free plan for this non-commercial university entrance examination project.
