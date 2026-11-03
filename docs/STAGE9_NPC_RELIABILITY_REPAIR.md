# Stage 9 - late NPC commit recovery repair

## Current revision - continuous player Fast-forward

Date: 2026-11-03, Africa/Johannesburg. Branch `ui-redesign`, unchanged HEAD
`a30247e1f02a45fb64bbb5e6ec787906804ea8ca`.

**The first repair below was insufficient for the player's one-click requirement:
it recovered a late receipt but always discarded Fast-forward intent. It must not
be released as the complete Fast-forward fix. This revised local patch preserves
the active intent through safe confirmation and passes isolated one-click tests.**

This section supersedes the first repair's always-paused policy, file inventory,
line references and test totals. The first report is retained below as history.
Production latency and connected acceptance remain unverified; Stage 9 is open.

### Implemented policy and safety

- One explicit Fast-forward click creates an in-memory intent bound to its
  generation, exact game and exact API session object. It is never persisted.
- Slow success continues normally. An uncertain response waits for the existing
  exact public receipt plus usable authoritative board, with one immediate and
  at most three additional checks on the existing five-second poll cycle.
- Confirmation can continue only the still-active original intent, after pending
  is cleared, owner/session context still matches and the next state is playable
  for an NPC. Each next POST is serial, uses the latest confirmed revision and
  still passes existing CSRF/ownership/backend authorization and attempt limits.
- No receipt means no next POST. Wrong actor/evaluation/sequence/action identity
  cannot establish commitment. A newer board alone remains insufficient.
- Pause revokes intent immediately, including during POST, receipt/board reads
  or the gap between checks. Submitted work can settle; no next action starts.
  A later explicit Resume creates a new intent only after settlement.
- Navigation, disposal, explicit refresh, session change, manual saved-request
  checking/retry, blocking errors and exhausted confirmation reads also cancel
  intent. Later confirmation never restores it. Reopening a page has no old intent.
- Transient confirmation network/timeout/503 failures may use the remaining
  bounded reads; authentication/permission/rate-limit/malformed read failures
  suspend continuation. Retry-After remains enforced. Exhaustion retains pending
  and its original ApiError/diagnostics for manual resolution.
- NPC Step and explicit saved-request retry never activate Fast-forward.
- Human turn, completed game, configured POST cap and genuine unresolved failure
  stop automatically. No five-second manual Pause deadline or timeout increase.
- Automatic confirmation displays ordinary progress and retains Pause. Technical
  saved-request controls appear only after suspension/Pause with unresolved work.
  Successful confirmation shows a short message, without transport diagnostics.

Current code references: `frontend/src/game/controller.ts:264` pending polling,
`:287` context validation, `:292` bounded waiting, `:298` background reconciliation,
`:408` submission, `:446` exact confirmation, `:504` Pause and `:508` the single
serial scheduler. `App.tsx:78` gates manual recovery presentation;
`components/Controls.tsx:163` supplies ordinary confirmation progress.
The HTTP client, receipt matching implementation and timeout remain unchanged.

### Demonstrated player journey

`frontend/tests/confirmation.test.mjs:24` drives the real controller/API with safe
scripted fetches. One click advances all nine NPCs to the human turn:

- An injected slow successful first response stays within the unchanged test
  deadline. The second response crosses that deadline and its worker commits late.
- Initial receipt lookup misses it; one transient 503 read also occurs. Existing
  polling then confirms the exact receipt and board automatically.
- The same intent continues without another Fast-forward click or mutation retry.
  POST expected revisions are exactly 7 through 15; final revision is 16.
- Maximum concurrent API mutation count is one; nine POSTs produce nine unique
  committed entries with saved explanations. A recovered synthetic dice receipt
  produces one dice cue and one mocked narration; refetch duplicates neither.

The test failed against the first repair because Fast-forward became false, then
passed after preserving intent. Injected deadlines are shortened for deterministic
tests; this is not a production speed benchmark or full-match engine simulation.
Actual backend attack-start/roll/replay tests are separate.

Additional isolated coverage verifies immediate confirmation followed by game-end
stopping, Pause while delayed confirmation is in flight, explicit Resume from the
next revision, bounded unresolved suspension, and no resurrection after refresh,
navigation, session change or disposal. Existing in-flight POST Pause, human-turn,
cap, exact-identity, stale-response, spectator/auth and receipt tests remain.
SSR confirms Pause/progress remain visible while technical recovery controls are
absent during automatic waiting and reappear on suspension. No browser visual or
production acceptance is claimed. Commentary failure is tested in both active
confirmation and explicitly paused states: it alters neither state nor identity.

### Final combined patch inventory

1. `frontend/src/game/controller.ts` - bounded reconciliation and context-bound
   continuous intent; cancellation, serial scheduling and unchanged security gates.
2. `frontend/src/App.tsx` - hide manual recovery while automatic confirmation runs.
3. `frontend/src/components/Controls.tsx` - contextual progress and Pause wording.
4. `frontend/tests/confirmation.test.mjs` - complete one-click, cancellation,
   recovery, completion and deduplicated-effect regressions.
5. `frontend/tests/recovery.test.mjs` - suspension after bounded uncertainty;
   preserve identity/cap/auth and explicit recovery assertions.
6. `frontend/tests/chronicle.test.mjs` - progress/Pause versus manual recovery SSR.
7. `frontend/tests/commentary.test.mjs` - provider failure preserves both active
   intent and explicit Pause without changing pending identity or cap.
8. `frontend/README.md` - current continuation/cancellation and progress contract.
9. `backend/tests/test_npc_controller.py` - retained first-repair test only;
   attack start, exact replay and next authoritative dice exchange. No backend
   application code change or backend deployment is needed.
10. This report. Logs and preservation evidence remain local under
    `output/stage9-npc-repair/`.

### Latest verification after the last code/test edit

| Check | Fresh result |
| --- | --- |
| Full frontend public suite | 377 passed, 0 failed/skipped/cancelled/todo |
| Focused controller/recovery/Chronicle run before final commentary-test update | 96 passed, 0 failed/skipped/cancelled/todo |
| Focused backend suite, same explicit selection shown below | 333 passed, 0 failed/skipped; one existing deprecation warning |
| TypeScript and API contracts | PASS; 43 components |
| Public audio integrity | PASS; 18 runtime clips/mappings/hashes |
| Map and country drift | PASS; 195 countries, 188 geometry/7 fallbacks; 181 capitals |
| Production build | PASS; 65 modules, JS 613.12 kB / 185.20 kB gzip, CSS 50.57 kB |
| Git whitespace | PASS; index remains empty |

The full-run commands are unchanged from the exact commands recorded below.
`results.json`, `frontend-tests.log`, `typecheck.log`, `contracts.log`, `sounds.log`,
`map.log`, `country.log`, `build.log` and `backend-continuous.log` record this run.
The >500 kB bundle warning is unchanged in severity. No package was installed.
Full backend, real MongoDB, real Groq and connected browser acceptance were not run.

### Latency, release decision and production procedure

The recurring 20-second cutoff is the unchanged frontend deadline, not a measured
NPC CPU duration. The actual backend/database/proxy delay remains unresolved.
Existing server access logs cannot attribute time to processing, transaction
retries, queueing, network or proxy delivery. No speculative timeout, auth-query,
index, database, provider or deployment change was made. The original source/
infrastructure budget review below still applies.

**One-click continuous Fast-forward works in the isolated scenarios above. This
does not close the production release blocker.** The first recovery-only patch
has now been revised; review the combined patch before any release. A separately
approved frontend build/promotion and real connected acceptance are still needed.
No Render release, environment change or migration is required. Use the recorded
eligible previous frontend deployment for rollback, preserving any uncertain tab;
rollback does not undo committed gameplay or restore lost page-memory identity.

For the existing Poland attack, revision 4 remains the last owner-supplied
confirmed attack-start evidence, not proof that the next dice exchange ran. Keep
an old pending tab untouched. Establish settlement using the existing approved
public confirmation flow before transitioning to the new build. Only with separate
manual gameplay approval, verify the current revision/actor/phase, then exercise
one-click Fast-forward and Pause/Resume under the approved attempt allowance.
Record ordered revisions, request durations, saved explanations/dice, effects and
the automatic stopping condition. Stop on unresolved identity/outcome, overlap,
duplicate effect, incorrect ownership/turn state or failure to honor Pause.

No production action, Git mutation, environment change or deployment occurred.
Pre-existing Stage E edits, local files, originals and the production tab remain
preserved. Final disposition: **LOCAL REPAIR VERIFIED - READY FOR HUMAN REVIEW**.

---

## Historical first repair - recovery only, superseded above

Date: 2026-11-03, Africa/Johannesburg.
Branch: `ui-redesign`. Baseline HEAD: `a30247e1f02a45fb64bbb5e6ec787906804ea8ca`.

**A local recovery defect is repaired and tested. The cause of production response
latency remains unconfirmed. This patch does not certify uninterrupted production
Fast-forward or complete Stage 9 acceptance.**

## Evidence and root cause

CONFIRMED from owner evidence, not new production observation:
- Campaign `6aea26725b34b509cb5e9456`, Stage 9 Final Acceptance.
- Human skip committed at revision 1. NPC Fiji skip committed at revision 2;
  browser duration approximately 20.04 seconds, HTTP 200.
- Marshall Islands skip timed out, then public receipt confirmation established
  revision 3. Poland timed out, then confirmation established revision 4.
- Revision 4 is an attack start against Seychelles. No supplied evidence proves
  a subsequent dice exchange. No new production request was issued here.

CONFIRMED in code and isolated reproduction:
- `frontend/src/api/http.ts:67` defaults to 20,000 ms. The timer aborts fetch at
  line 87; `Promise.race` at line 137 covers response/body parsing. The reported
  20,016/20,005 ms waiting-for-response timeouts are consistent with that explicit
  client deadline. Header status alone cannot establish complete response delivery.
- An abort does not prove server work stopped. A test holds a synthetic worker
  before commit, lets the client timeout and initial lookup finish, then releases
  exactly one commit. The old controller's ordinary poll did not recover it.
- `submitPending` previously made one immediate exact receipt check after an
  uncertain NPC response. `poll` returned whenever pending/error was set. A receipt
  appearing later could be confirmed only by the explicit public check.
- The new late-commit regression failed against the original controller (one test,
  one failure), then passed after the repair. This proves the recovery gap; it
  does not isolate production database, CPU, network or proxy latency.
- Fast-forward intentionally remains paused after uncertain outcomes, including
  successful confirmation. This is safe behavior, not a stuck server phase.

UNVERIFIED: why the first request nearly consumed 20 seconds, where subsequent
requests spent that time, transaction retries/contention, deployment load, network
latency or proxy-specific failure. Supplied Render access logs have no per-stage
durations. No live timings, settings or database operations were collected.

The server call graph has repeated authorization, index-metadata, rate and receipt
operations; these can accumulate round trips but their production cost is not
measured. No authorization/index check was removed or cached speculatively. NPC
decision code has no intentional 20-second sleep or Groq call. Commentary is a
separate flow. Pure unit-test success is not a measurement of live engine latency.

## End-to-end path and budgets

| Stage | Code / preserved behavior |
| --- | --- |
| UI Step / Fast-forward / Pause | Existing Controls/App callbacks; `App.tsx:27` owns the five-second poll interval |
| Controller | `controller.ts:340` Step, `:390` submission, `:427` exact confirmation, `:478` Pause, `:479` serial Fast-forward; no new operation while pending |
| HTTP/API | `client.ts:239` serial per-game mutation, `:284` npcStep; frozen game/expected revision; CSRF headers; unchanged 20-second HttpClient deadline |
| Vercel | Existing external rewrite `/api/:path*` to Render `/:path*`; no function, async job, bulk-NPC endpoint or configuration change added |
| FastAPI/access | `backend/app/api/games.py:44` NPC route; Origin/CSRF/session/ownership/write-gate protections unchanged |
| Authorized service | `authorized_game_service.py:94` revalidates ownership, checks original expected-revision replay, prepares one NPC action |
| Policy/action | `npc_service.py:37` prepare, `:50` submit; `game_action_service.py:51` validates receipt identity and applies authoritative rules |
| Persistence | `action_repository.py:76` commits board and receipt atomically with revision and access fences; transaction callback retains computed dice/events |
| Replay identity | game + expected revision + observed NPC/turn sequence; canonical `npc-<strategy>-<sequence>-<revision>`; unchanged |
| Reconciliation | Public events after the original revision, limit 1; exact successor actor/evaluation/action ID, then usable board at or beyond receipt revision; newer board alone is insufficient |
| Chronicle/effects | Existing event merge/cursor, sound ledger and independent commentary cursor; no duplicate receipt, audio queue or narration backfill |

The startup Mongo client uses selection/connect limits of 5 seconds and socket
limit of 10 seconds (`backend/app/startup.py:24`). These are not whole-request
deadlines. Successive operations and transaction retries can outlast the browser
deadline. PyMongo documents a transaction retry window up to 120 seconds; this
does not prove any production retry occurred.
[PyMongo transaction documentation](https://pymongo.readthedocs.io/en/stable/api/pymongo/client_session.html).

Vercel documents a maximum 120-second external-proxy timeout, rather than a
20-second Vite function limit. The repository uses an external rewrite. No live
project limit or Render request duration was established. Do not attribute these
20-second aborts to a serverless function without evidence.
[Vercel external target timeout](https://vercel.com/docs/errors/router_external_target_error).

## Minimal repair and exact files

1. `frontend/src/game/controller.ts`: arm three extra public confirmation attempts
   only after a submitted uncertain NPC operation. Reuse the existing poll cycle;
   no second timer, automatic POST retry, new identity or timeout increase.
   Serialize confirmation with recovery/auth/mutation workflows, retain identity
   and lock, respect Retry-After, stale-read guards and disposal. Background
   confirmation leaves foreground busy false. Manual confirmation remains after
   exhaustion and session expiry. Same-identity retries do not replenish reads.
2. `frontend/tests/confirmation.test.mjs`: nine new cases plus stricter anonymous
   read-only assertions in the eight existing mismatch cases.
3. `frontend/tests/recovery.test.mjs`: retain all seven preparation-failure identity
   and lock assertions; explicitly allow only the newly supported anonymous
   targeted read, never an additional POST. Rate-limited cases make no request.
4. `backend/tests/test_npc_controller.py`: one deterministic attack-start, identical
   replay, successor dice exchange and identical dice-replay regression.
5. `frontend/README.md`: document the bounded public confirmation behavior and
   distinguish read allowance from NPC POST allowance.
6. This report. Local verification logs/baseline are under
   `output/stage9-npc-repair/`, outside the proposed source patch.

Each automatic attempt is one receipt GET and, only when the receipt matches, one
board GET. Maximum three extra attempts/six extra GETs per pending identity. The
original immediate check and explicit human checks are separate. Slow reads keep
their existing per-request deadline; this is not a fifteen-second wall-clock
guarantee. The finite read count is a conservative recovery choice, not a measured
backend completion SLA. Exhaustion does not imply failure or permission to replay.

## Fresh checks after the last source edit

| Scope | Result |
| --- | --- |
| Full public frontend suite | 367 passed, 0 failed/skipped/cancelled/todo; includes nine new cases (baseline 358) |
| Focused frontend confirmation/recovery/polling, earlier targeted run | 95 passed, 0 failed/skipped/cancelled/todo |
| TypeScript | PASS |
| API contracts | PASS: 43 components; no schema changes |
| Public audio integrity | PASS: 18 exact runtime mappings/hashes |
| Map drift | PASS: 195 countries, 188 geometry + 7 fallbacks, 470 paths/221 groups |
| Country drift | PASS: 195 countries, 181 capitals |
| Frontend production build | PASS: 65 modules; JS 611.53 kB / 184.88 kB gzip; CSS 50.57 kB |
| Focused backend | 333 passed, 0 failed/skipped, one existing Starlette deprecation warning; includes one new case |
| Git whitespace | PASS: unstaged diff check; index empty |

The frontend runner logs each real command and exit in results.json; individual
logs retain counts. Existing >500 kB bundle warning remains non-blocking.

Commands from frontend:

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run check:contracts
npm.cmd run check:sounds
node scripts/build-map-data.mjs --check
node scripts/build-country-reference.mjs --check
npm.cmd run build
```

Commands from backend:

```powershell
$npcRepairTemp = Join-Path $env:TEMP ('geopolitics-npc-repair-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -B -m pytest -c pytest.ini `
    tests/test_npc_service.py tests/test_npc_controller.py tests/test_npc_persistence.py `
    tests/test_npc_strategy.py tests/test_npc_evaluation.py tests/test_phase2_service.py `
    tests/test_phase2_repository.py tests/test_phase2_rules.py tests/test_phase4_auth.py `
    tests/test_phase4_api.py tests/test_phase4_services.py tests/test_startup.py `
    --basetemp $npcRepairTemp -p no:cacheprovider
```

Coverage includes normal and slow success, cancellation before commit, late commit,
lost response, missing/mismatched receipts, original identity across retry, read
exhaustion/manual confirmation, foreground/background serialization, rate limits,
expired sessions, disposal/stale state, normal serial Fast-forward to human or
completion, in-flight Pause and explicit Resume from the successor revision.
Recovered dice keep original order/losses; one sound cue and one mocked narration
are observed and refetch/refresh does not duplicate them. Provider cost/claim and
sound policy source are unchanged. No real provider call occurred.

Not run: full backend suite, opt-in Mongo tests, production requests, connected
full-match acceptance, browser screenshots/listening or new live Groq tests.
Mock persistence tests do not prove Mongo transactions. Prior infrastructure and
Stage E acceptance were not reopened. All original audio remains local.

## Safety, requirements and limitations

The attachment explicitly authorizes this local controller repair and isolated
tests. Backend application, API client/contracts, authentication/session/CSRF/
Origin/ownership policy, NPC strategy, combat, reinforcement, database/indexes,
hosting configuration, timeouts, assets and presentation are unchanged.
Uncertain operations retain the same account/game/revision/observation and lock.
No automatic POST replay or Fast-forward restart is added. Exactly-once receipt
behavior remains server-enforced; this patch does not create a new guarantee for
arbitrary identities or prove live transaction behavior.

Official brief pages 2, 4 and 5 and the marksheet were checked through existing
rendered pages; current Downloads PDF hashes match the previously verified
official 2027 sources. Mandatory visible NPC Fast-forward, explanations, battle
visibility, authorization and dynamic commentary remain. Relevant rubric criteria
include functionality, validation/security, UI/navigation and battle/AI complexity.
The separate start/roll and immediate reward conventions remain those documented
in GAME_RULES.md; no rule or awarded mark is invented. Unmet connected full-game,
round-two, actual dice/commentary/audio and Pause acceptance stays outstanding.

Pre-existing Stage E edits in backend/docs/REQUIREMENTS.md and
docs/STAGE_E_AUTH_ACTIVATION.md, untracked validators, historical reports, design
references and originals were preserved. REQUIREMENTS.md was not edited because
it contains unrelated work; this report records the remaining acceptance gaps.

## Release implications and manual acceptance, only after separate approval

- Runtime change is frontend-only: a new reviewed frontend Preview/build and
  separately approved production promotion are needed to affect live users.
- No Render backend release, environment change, database migration or schema/
  index change is needed. The backend edit is test-only.
- Previous package hashes/manifests do not certify this new patch. A later release
  review must cover its exact diff. No Git mutation or deployment occurred here.
- Rollback is to the recorded eligible previous frontend deployment. It cannot
  undo moves, end a running backend request or restore page-memory pending state.
- Keep a production tab with any unresolved request open. A new build does not
  patch that tab's controller. Never reload it merely to obtain this repair.

After release review, deployment approval and a separate manual gameplay allowance:
1. Confirm exact frontend build, original account and game. Preserve any unresolved
   operation and its non-secret identity. If still pending, use only the existing
   authorized public confirmation flow; do not submit a new move or blind retry.
2. Confirm the last known Poland receipt at revision 4 is attack_started and the
   current authoritative board/actor/phase. If a later receipt/state exists, review
   it first. Do not assume revision 4 remains current or that a dice exchange ran.
3. Only after settlement and authorized transition to the new build, one approved
   Step may execute the next server-chosen battle operation. It may roll or stop
   according to the actual NPC evaluation; do not force a dice outcome.
4. If uncertain, observe the bounded public checks. Exact matching receipt plus
   usable board may release pending; otherwise STOP and retain the same operation.
   Confirmation must not automatically restart Fast-forward or duplicate effects.
5. Once settled, separately authorize a bounded Fast-forward/Pause/Resume trial.
   Pause may allow its in-flight request to finish but starts no next request.
   Resume must use the confirmed next revision and stop at human turn, completion,
   cap or uncertainty. No five-second manual Pause deadline applies.
6. Record request duration/status, before/after revision and saved explanation/
   dice events, audio and commentary without credentials/tokens. If repeated
   20-second cancellations persist, STOP sustained acceptance and provide the
   available sanitized request timing (especially wait/TTFB versus transfer).
   That evidence is needed before choosing a backend or deadline optimization.

This local patch fixes the demonstrated late-confirmation gap. It does not remove
the original 20-second cutoff, establish backend processing duration, resolve an
existing old-tab request or prove the live acceptance blocker fully eliminated.

Historical first-repair verdict: local late-confirmation recovery was verified;
continuous Fast-forward was not yet implemented. Superseded by the current revision.
