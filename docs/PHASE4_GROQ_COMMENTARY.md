# GroqCloud battle commentary

Local implementation, 2026-10-31. No production access, provider calls, deployment,
Git mutation or database provisioning was performed. Frontend `74c712d` and
committed revision 8 are the user-confirmed production baseline. The transport
interruption remains unexplained; the old pending browser tab is untouched.

## Design and authoritative facts

The official 2027 brief p.4 requires dynamic LLM battle commentary alongside
visible battle results. Marksheet criteria 12–13 cover engine/AI sophistication
and AI application; criteria 6, 9–11 cover validation, UI and access control.
Existing rules and NPC strategy remain unchanged.

Generation is a separate request after a committed `dice_exchange`, for human
and NPC receipts. No game creation/action/NPC service calls the provider or waits
for narration. The existing 20-second gameplay deadline and receipt recovery,
idempotency, revisions, acceptance limit and Pause logic are unchanged.

Groq generates one varied atmospheric sentence using a constrained vocabulary.
The backend rejects factual vocabulary, numbers, country names, malformed JSON,
truncated or long output. It appends a deterministic sentence containing the
actual attacking/defending countries, dice, losses, conquest and eliminations.
This deliberate composition prevents model-created battle outcomes. The UI
labels LLM narration separately from authoritative results and NPC explanations.
Long dice lists are compacted in narration/provider context; full actual arrays
remain in returned facts and committed history. No dice are recalculated.

## API contract

| Method and path | Access and behavior |
| --- | --- |
| `GET /games/{game_id}/commentary/{revision}` | Public, read-only retrieval; no Groq call or commentary storage writes. |
| `POST /games/{game_id}/commentary/{revision}` | JSON `{}`; exact trusted Origin, authenticated current owner and CSRF required. Generates at most once for the committed receipt. |

Vercel browser paths add `/api`; the existing rewrite removes that prefix.
The POST obeys the existing authentication gate. It does not advance the game
and does not require enabling gameplay if gameplay has been paused operationally.

Both return `BattleCommentary`: game ID, committed revision, action ID, status,
source, text, sanitized reason and authoritative `BattleFacts`. Status is
`not_generated`, `pending`, `ready` or `fallback`; source is `groq` or
`deterministic`. Facts include countries, original ordered dice, actual losses,
conquest, eliminated participants, round and human/NPC actor kind.

Malformed requests are 422; absent/non-battle receipts are 404; authentication,
ownership/Origin/CSRF failures are 401/403; pre-claim capacity limits are 429 with
Retry-After; storage failures are sanitized 503. All routes use no-store.
Provider failures return a persisted, labeled fallback rather than failing play.
Generation-cap exhaustion returns a persisted `fallback` with reason
`admission_limited` (HTTP 200), without a provider call; capacity rejection before
claiming remains 429. API paths and response schemas are unchanged.

## Persistence and cost limits

`battle_commentary` is a separate collection; its built-in unique `_id` is
`game_id:committed_revision`. Existing games, receipts, fingerprints, validators
and indexes are not changed. Collection access is lazy; the first approved
generation creates its first record through normal application storage.
No MongoDB validator or custom index is installed on the new collection;
application Pydantic models validate its data. Its built-in unique `_id` is
sufficient for the one-record-per-receipt claim. Existing validator manifests
and startup readiness checks remain unchanged.

An acknowledged majority-write claim precedes any provider call. Only its private
claim token can finalize that record. Concurrent callers and later deployments
reuse its result. An uncertain insert acknowledgement never authorizes dispatch.
Claims are never reclaimed: after 30 seconds an interrupted pending claim returns
a deterministic fallback on reads, without rewriting data or calling Groq again.
This favors avoiding duplicate billing over automatic recovery of lost narration.
A provider response lost before final persistence may therefore remain unavailable.

Limits are two active generations per service process, plus durable shared
existing rate buckets: 10 generation admissions/minute globally, 60/hour globally,
20/hour/account, **100 globally per UTC calendar day** and **30 per game per UTC
calendar day**. Only the acknowledged unique receipt-claim winner reserves
admission. Duplicate callers, saved retrieval and spectators do not increment
generation counters. A failed provider attempt still consumes its admission.
Reservation across buckets is conservative: an earlier reservation is not
refunded when a later bucket denies, a counter write is uncertain or work stops.
No generation can pass a bucket's ceiling. Denied/failed claims are not reopened
automatically, including on the next day; new exchanges use the new day's budget.
The SDK has no automatic retries, a six-second HTTP timeout, an eight-second
overall provider deadline. GPT-OSS requests have a 512-token total completion
ceiling with low reasoning effort; other explicitly configured models retain
the legacy 120-token JSON-mode ceiling. Visible narration remains limited to
240 characters and 8–40 words. Provider context is bounded.
No worker queue or background task is started by gameplay.

Frontend retrieval/generation queues and caches are independent of gameplay.
Saved history and reloads only retrieve existing narration. Owners can generate
for a selected committed battle; spectators have no generation control. Live
narration defaults on for newly committed owner exchanges in human play and
fast-forward; the owner can disable it. A failed generation is checked with GET, never blindly
replayed. Spectators can explicitly check saved narration even if their initial
read arrived before generation; this only sends GET. React renders narration as
escaped text, never HTML.
The former 16-exchange lifetime cutoff is removed. An independent cursor starts
at the board revision when the game view mounts; it reads only subsequent
committed receipts, at most 100 per page, and awaits one generation at a time.
Ordinary polling may reveal new receipts but does not replay already processed
ones. Historical UI pagination cannot block current exchanges. The live display
retains 64 recent entries; older narration is retrieved from committed history.
No unbounded queue or per-exchange lifetime set is kept. The 256-entry recovery
guard applies only to unresolved commentary outcomes, not successful exchanges.
Disabling cancels unsent work; submitted requests can settle. Re-enabling uses
the current board revision, without backfilling the opted-out interval.
Account/game changes discard stale UI updates. Before every POST, the current
controller/account/game is checked; unresolved gameplay blocks new narration.

Daily counters reuse `auth_rate_limits` with its existing unique `_id` and TTL
index/validator. The key hashes the budget scope, interval and UTC epoch window;
86400-second windows align with UTC midnight. Atomic `find_one_and_update` uses
`$inc` and returns the updated count; no read/modify/write counter is added.
Expiry retains buckets past their window so TTL cleanup cannot reset an active
budget. A backend restart does not change these shared counters. No collection,
index, validator, migration or manual Atlas step is added for daily caps.

## Configuration and dependencies

`GROQ_API_KEY` and `GROQ_MODEL` are **already configured in Render by the owner**.
No replacement key, extra environment variable or Vercel secret is required.
The backend reads these process variables; it never loads them into the frontend.
The code default is now `openai/gpt-oss-20b`, matching the user's updated Render
model. `GROQ_MODEL` still takes precedence. The user confirmed that this model
was reached in production, but the corrected request has not been deployed or
verified live. No environment value was changed by this implementation.
Missing local configuration produces a deterministic fallback; tests inject a
mock provider and never need a real key.

The official Python SDK is pinned to `groq==1.7.0`. Runtime HTTP dependencies are
pinned in `backend/requirements.txt`, retaining its existing UTF-16 encoding.
No frontend package was added. Raw provider exceptions, credentials, cookies,
CSRF values and request bodies are not logged or returned by this integration.

## Deployment and acceptance: separate approval required

1. Review the local diff, tests and dependency checks; preserve unrelated Stage E
   edits and validator exports. Commit/push/deployment are not authorized here.
2. Deploy the backend with pinned dependencies, then the compatible frontend.
   Do not modify the two already-entered Groq variables. Existing startup guards
   remain unchanged; no storage metadata/provisioning investigation is needed.
3. Preserve the old tab and pending expected-revision-7 diagnostic evidence.
   Revision 8 is confirmed committed; do not retry that NPC operation.
4. Separately approve a commentary-only POST for an already committed dice
   receipt and verify real Groq narration, accurate facts, saved retrieval and
   public spectator display. Revision 8 was a transfer, not a dice receipt.
   A GET or deterministic fallback alone does not demonstrate a live LLM call.
5. Separately approve any new battle/fast-forward allowance before testing live
   narration during new gameplay. Check owner-default narration, opt-out, Pause/cap and no overlap
   or automatic resumption after uncertainty. No new NPC POST is authorized now.

STOP on identity mismatch, lost battle evidence, security failure, cap/Pause
regression or unresolved gameplay operation. Provider failure alone must leave
gameplay available. Turn off live commentary to stop scheduling generation;
let a submitted request settle. A separately approved frontend/backend rollback
may restore the prior release; retain commentary records and all game data.
Do not delete claims or retry generation to bypass cost safeguards.

Offline tests do not prove real MongoDB semantics or hosted/provider delivery.
Real Groq/browser acceptance, Stage F live fast-forward and submission packaging
remain outstanding. Optional illustrated styling/audio are outside this patch.

Provider references: [official SDK](https://github.com/groq/groq-python),
[GPT-OSS 20B model](https://console.groq.com/docs/model/openai/gpt-oss-20b),
[strict structured outputs](https://console.groq.com/docs/structured-outputs),
[API parameters](https://console.groq.com/docs/api-reference).

## Exact patch files

Modified existing files:

```text
README.md
backend/app/api/dependencies.py
backend/app/main.py
backend/app/startup.py
backend/docs/REQUIREMENTS.md
backend/requirements.txt
backend/tests/test_api.py
docs/api-contract.md
docs/openapi.json
frontend/README.md
frontend/src/App.tsx
frontend/src/api/client.ts
frontend/src/api/generated.ts
frontend/src/components/History.tsx
```

Created files:

```text
backend/app/api/commentary.py
backend/app/models/commentary.py
backend/app/repositories/commentary_repository.py
backend/app/services/commentary_service.py
backend/app/services/groq_commentary.py
backend/tests/test_commentary_api.py
backend/tests/test_commentary_repository.py
backend/tests/test_commentary_service.py
backend/tests/test_commentary_startup.py
backend/tests/test_groq_commentary.py
docs/PHASE4_GROQ_COMMENTARY.md
frontend/src/api/commentary.ts
frontend/src/api/live-commentary.ts
frontend/src/components/BattleCommentary.tsx
frontend/tests/commentary.test.mjs
```

Unrelated pre-existing edits remain excluded: `docs/STAGE_E_AUTH_ACTIVATION.md`,
the first Stage E hunk in `backend/docs/REQUIREMENTS.md`, `docs/PROJECT_HANDOFF.md`
and the four local `backend/*validator*.json` exports. No file was staged.
Do not stage the entire requirements document without reviewing its mixed hunks.

## Offline verification

Frontend: **167 passed, 0 failed, 0 skipped**, comprising 141 retained regressions
and 26 commentary/live-narration tests. TypeScript and the Vite production build
passed; all **43 OpenAPI components** passed the contract check.

Backend: **906 passed, 0 failed, 44 skipped** in the latest complete isolated run.
New coverage is 66 provider, 21 repository, 42 service, 17 API and 3 startup cases. The 44 real
MongoDB/provisioning/startup opt-in cases remain skipped without authorization.
All tests block external network access and use isolated memory/provider fixtures;
none imports `backend/test_database.py`. One existing Starlette/httpx deprecation
warning remains. Pinned dependency consistency (`pip check`) passes.
The offline OpenAPI export matches current route/model source exactly (15 paths,
16 operations, 43 components). Whitespace and targeted secret scans pass across
all 29 patch files. Git index remains empty; engine, NPC strategy, action service,
recovery controller, HTTP deadline and frontend dependency files have no changes.

Tests cover exact human/NPC rolls, losses/conquest/elimination, large dice lists,
missing configuration, provider timeout/rate/auth/outage/malformed/long output,
concurrent claims, restarts, uncertain persistence, cost limits, public retrieval,
owner/Origin/CSRF enforcement, UI escaping/loading/fallback, default-on/opt-out and queued
cancellation. Blocked-provider tests show human/NPC gameplay completes independently.
All prior pending recovery, idempotency, acceptance-cap and Pause tests pass.

AI assistance was used for implementation and test development. Runtime AI is
limited to narration; model output cannot determine rules or state. Existing
university documentation and disclosures were preserved. Real-provider/browser
acceptance is still required before claiming the mandatory feature demonstrated.

## Earlier security and release review, 2026-10-31

**PASS WITH RESERVATIONS — Clearly identified limitations**

The complete 29-file inventory above was reviewed against the working tree.
One confirmed functional defect was fixed: a spectator who fetched a battle
before generation had no check control and could remain on cached not-generated
output. The view now offers the same public GET-only saved check. A regression
failed before the fix and passed after it. No backend architecture, engine,
strategy, NPC deadline, authorization or recovery changes were needed.

Added review coverage: five-die all-tie exchanges with zero losses; exact old
receipt narration after the game advances; model unavailable, quota/HTTP errors;
service cancellation after the durable claim and browser cancellation after
submission; repeated spectator GETs; no provider replay and capacity release.
All tests and counts in the verification section were reproduced locally.

| Critical check | Result and evidence |
| --- | --- |
| Human/NPC mutation isolation | PASS — source paths unchanged; blocked-provider HTTP tests let both gameplay routes finish first. |
| Authoritative transactions and receipts | PASS — no provider dependency or commentary writes into games/receipts; exact receipt facts retained. |
| Owner/session/Origin/CSRF | PASS — anonymous, cross-account, expired-session and missing/invalid Origin/CSRF tests deny generation. |
| Public retrieval/cost safety | PASS — repeated anonymous GETs do not call Groq or write commentary/security/game data. |
| Durable deduplication | PASS locally — stable ID, majority claim, fenced completion, restart/concurrency/cancellation tests; no reclaim or automatic retry. |
| Narration accuracy | PASS locally — factual suffix comes from committed dice/losses/conquest/elimination, including ties and large exchanges. |
| Provider boundaries | PASS locally — installed pinned SDK request schema, no retries, bounded input/output/timeouts/concurrency and safe failure reasons. |
| Fast-forward/Pause/NPC cap/recovery | PASS locally — original 141 frontend regressions retained; commentary never calls NPC submission/counting or resumes automation. |
| Secrets/bundles/contracts/dependencies | PASS — targeted scans, all runtime pins, pip check, runtime OpenAPI equality, generated TypeScript and build verified. |
| Hosted Groq model/key access and output quality | NOT VERIFIED — no live provider request permitted; mocked SDK transport is not live provider proof. |
| Actual commentary collection writes/durability | NOT VERIFIED — no real MongoDB access permitted; 44 opt-in cases skipped, not passed. |
| Deployed browser/proxy and Stage F acceptance | NOT VERIFIED — original tab untouched, revision 8 committed; no new NPC attempts authorized. |

### Manual staging and deployment sequence

1. Stage exactly the 29 listed files. For `backend/docs/REQUIREMENTS.md`, use
   partial staging: include the G17 row, criterion-13 paragraph and appended
   Phase 4 implementation/review evidence; exclude the opening Stage E hunk
   (`@@ -1,5 +1,14 @@`). Keep the unrelated Stage E file, handoff, validator
   exports, virtual environments, caches and `dist` outside this commit.
2. Review the staged inventory/diff manually, then commit/push only after approval.
   Suggested message: `feat(commentary): add durable Groq battle narration`.
3. Deploy the Render backend first with its pinned `backend/requirements.txt`.
   The two Groq variables are already configured; verify they are available to
   the new process by successful startup and later functional results, never by
   printing their values. Keep all existing production settings unchanged.
4. Check that deployment's successful startup and existing `/health` response.
   No diagnostic route, DDL, extra index, validator change or manual Atlas action
   is required. The app lazily uses the new collection and its built-in `_id`
   index; the first approved generation normally creates its first record.
5. Deploy the matching Vercel frontend with the regenerated contracts. Preserve
   the exact existing origin, proxy, secure cookies and CSRF behavior. Reuse
   accepted Stage E evidence; check only that deployment did not regress it.
6. With separate read approval, use a public commentary GET for a known existing
   committed dice receipt. Confirm identity, facts and no-store. Do not select
   revision 8 as a battle: its committed action was a transfer. No read creates
   commentary or proves a provider call.
7. Separately authorize at most one commentary-generation attempt for one agreed
   existing battle. Use its owner session, ordinary Origin and CSRF through the
   frontend; record only non-secret statuses/identity. Confirm ready/groq output,
   factual accuracy, public saved retrieval and no change to game/receipt state.
   If interrupted, check with GET; do not submit another generation attempt.
8. New battle/live fast-forward testing needs a separate explicit NPC allowance.
   Gameplay Pause stops scheduling NPC actions; the commentary checkbox stops
   queued narration. Let already-submitted requests settle. Neither control
   creates an automatic gameplay or provider retry.
9. On provider failure, retain labeled fallback and normal gameplay. On security,
   receipt identity or gameplay regression, STOP and request rollback approval.
   Turn off live narration, then restore reviewed frontend/backend releases if
   authorized. Retain commentary claims and all game data; no deletion, metadata
   repair, environment change or replay is part of rollback.

Reservations: real Groq delivery/model availability and strict-lead acceptance
rate remain unmeasured; lexical validation can deliberately favor fallback.
Interrupted claims permanently sacrifice that narration rather than risk
duplicate billing. Concurrency is bounded per process; shared fixed-window spend
limits persist across workers/restarts. Public narration refresh is explicit,
not continuous provider polling. The completed local review permits deployment
approval; it does not certify production acceptance or close Stage F.

## Final compliance and daily-cost patch, 2026-10-31

**PASS WITH RESERVATIONS — Clearly identified limitations**

The current implementation supersedes the earlier opt-in and 16-exchange behavior.
Live narration defaults on for the verified owner and covers newly committed
human/NPC exchanges, subject to server admission limits. Saved-game entry,
reconnection and remount establish a current-revision baseline and do not bill
historical exchanges. Opt-out and pending gameplay stop new dispatch; an in-flight
request can settle. Reads/generation stay independent of authoritative mutations.

Per-exchange audit: `engine/actions.py` applies one `Roll` by calling
`roll_exchange` once and emitting exactly one `dice_exchange`. The action service
commits one receipt and increments the revision once. An attack can have multiple
rolls and therefore multiple commentary identities (`game_id:revision`), each with
its own dice/losses and any conquest/elimination from that exchange. Ties and
large dice lists retain their actual outcomes. The UI associates narration with
the corresponding receipt; no whole-attack aggregation or rule change is added.

Exact files changed in this targeted follow-up (all already in the 29-file
feature manifest; no additional files or dependencies):

- `backend/app/services/commentary_service.py`
- `backend/tests/test_commentary_service.py`
- `backend/tests/test_commentary_repository.py`
- `frontend/src/App.tsx`
- `frontend/src/api/commentary.ts`
- `frontend/src/api/live-commentary.ts`
- `frontend/src/components/History.tsx`
- `frontend/src/components/BattleCommentary.tsx`
- `frontend/tests/commentary.test.mjs`
- `frontend/README.md`
- `README.md`
- `backend/docs/REQUIREMENTS.md`
- `docs/PHASE4_GROQ_COMMENTARY.md`

Tests prove owner-default narration, opt-out, no reload/backfill generation,
processing of 125 new exchanges beyond the old display window, separate rolls
in one attack, no unconfirmed/pending dispatch, bounded reads and no lifetime
successful-request cutoff. Daily tests admit exactly 100 global and 30/game,
reset at UTC midnight with an offset-aware clock, retain counters after service
recreation, and admit only one caller competing for the final allowance.
Mongo command doubles verify the actual `$inc`/upsert/ReturnDocument.AFTER path;
they are not real-server durability proof. Duplicate claim races and cached GETs
do not consume allowance; provider failure after admission counts once.

The complete final suites pass **891 backend / 167 frontend**, with **0 failures**,
**44 backend real-database cases skipped** and **0 frontend skips**. The 43 API
contracts, TypeScript/build, dependency consistency, whitespace and secret checks
pass. The prior Starlette/httpx warning remains. Engine, NPC strategy, gameplay
transactions, request timeout, recovery controller, acceptance-cap and Pause
code are unchanged; their regressions pass.

No manual Atlas action is needed. Daily counters use existing storage and
metadata; the commentary collection still uses its built-in unique `_id`.
The two Render variables are already configured and require no changes.
The new caps are application controls, not a guarantee of provider pricing or
quota. Fixed windows permit boundary bursts within each window's limit.
Denied-admission fallback remains saved for that exchange; the next UTC day's
allowance applies to new exchanges, not an automatic retry of that record.
Live provider output/latency and real commentary persistence remain unverified.
Revision 8 remains committed, the transport interruption is unresolved, and
Stage F production fast-forward acceptance stays open. No Git mutation,
deployment, provider request, Atlas access or production gameplay was performed.

## Production JSON validation failure: local correction

User-provided evidence on frontend/backend release `2ffff1d`: Move 2 with
`llama-3.1-8b-instant` received Groq 404 `model_not_found`. The user changed
Render's model to `openai/gpt-oss-20b`. Move 6 then reached that model but received
HTTP 400 `json_validate_failed`, with 599 input and exactly 120 output tokens.
Both outcomes retained deterministic fallbacks and gameplay remained available.
The agent did not access those services or inspect/update those records.

Confirmed failure boundary: Groq rejected its generated JSON before returning a
usable completion. The old request used `response_format={"type":"json_object"}`,
no supplied JSON Schema, `max_completion_tokens=120` and no reasoning setting.
This was not an application schema rejection: `validate_lead` never received a
successful completion for that call. It was also separate from the earlier
model lookup failure and from the unresolved NPC transport interruption.

The exact malformed generation, finish reason and reasoning-token breakdown
were not supplied. Using exactly the 120-token ceiling strongly suggests output
exhaustion/truncation, but does not prove its byte-level cause. GPT-OSS defaults
to medium reasoning effort; extra reasoning is another plausible contributor.
No further provider request was made to reproduce the failure. Tests with a
synthetic provider 400 validate recovery, not the cause of the historical call.

For `openai/gpt-oss-20b` and the documented compatible GPT-OSS 120B model, the
adapter now sends:

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "battle_atmosphere",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {"lead": {"type": "string"}},
        "required": ["lead"],
        "additionalProperties": false
      }
    }
  },
  "reasoning_effort": "low",
  "include_reasoning": false,
  "max_completion_tokens": 512,
  "temperature": 0.8
}
```

This follows Groq's documented strict schema shape for GPT-OSS. It intentionally
does not send unsupported lexical/length schema keywords: existing local checks
still reject empty, long, factual, malformed or truncated narration. Strict JSON
controls structure, not factual accuracy. The server still appends the original
authoritative summary; no event facts come from model-generated fields.

The larger but bounded completion allowance provides headroom for the exhausted
120-token request; it is not a proven universal minimum. `include_reasoning=false`
hides returned reasoning, and does not claim to disable the model's reasoning.
Low effort is explicitly requested rather than relying on the provider default.
Other configured model IDs keep their old JSON-mode payload; there is no model
probe, second provider call, automatic format downgrade or retry on a 400.

Only the fixed `json_validate_failed` provider error code maps to `invalid_output`;
raw error messages and failed generations are never returned/logged by the
adapter. Other bad requests retain the sanitized unavailable fallback. The
pinned SDK `groq==1.7.0` supports and serializes the new fields, so no dependency
upgrade or API/frontend contract change is needed.

Unchanged protections: six-second HTTP/eight-second provider deadline, zero SDK
retries, gameplay's 20-second deadline, all five admission limits, durable unique
receipt claims, existing fallback records, owner/session/Origin/CSRF checks,
default-on live scheduling, pending recovery, Pause and NPC attempt counters.
Maximum completion spend per GPT-OSS call can be higher than before (512 versus
120 tokens); daily/request admission ceilings and the visible-text cap remain.

Exact files for this fix:

- `backend/app/services/groq_commentary.py`
- `backend/app/startup.py`
- `backend/tests/test_groq_commentary.py`
- `backend/tests/test_commentary_startup.py`
- `backend/docs/REQUIREMENTS.md` (new correction evidence only; leave the opening Stage E hunk unstaged)
- `docs/PHASE4_GROQ_COMMENTARY.md`

Verification adds strict GPT-OSS/legacy-model payload cases, real pinned-SDK
mock-HTTP success/400 behavior, valid narration, truncation/factual rejection,
safe provider errors and startup configuration. Committed-event tests verify
saved fallbacks are retained across a corrected-provider restart, counts do not
reset and game state/receipts are untouched. Latest totals: **906 backend passed,
0 failed, 44 skipped; 167 frontend passed, 0 failed/skipped; 43 contracts passed**.
TypeScript/build, dependency and security checks pass. The existing Starlette/
httpx warning remains. No real Groq/MongoDB or production acceptance is claimed.

Remaining risks: strict format plus extra headroom has not been verified against
the live provider and can still time out, be truncated or fail lexical validation.
Already saved fallbacks for Moves 2/6 remain unchanged and will not regenerate
after deployment. Any future live validation must separately approve one new
eligible receipt/provider attempt; never delete/reset/retry existing claims.
No key, environment, production game, browser tab, Git index/history or deployment
was changed. Release remains ready for separate approval with these limitations.
