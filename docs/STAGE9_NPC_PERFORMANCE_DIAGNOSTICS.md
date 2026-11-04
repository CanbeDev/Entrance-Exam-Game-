# Stage 9 - request-scoped NPC performance diagnostics

Date: 2026-11-04, Africa/Johannesburg.
Branch: `ui-redesign`. HEAD: `f990946660ce6de4055643829bc95753bc0c2a82`.

**READY FOR CONTROLLED DIAGNOSTIC RELEASE**

Current correction: Section J supersedes the initial synchronous logging design,
test totals and release assessment below. Earlier sections retain the original
implementation evidence. The pre-deployment audit correctly blocked release for
event-loop logging; this continuation fixes only that verified issue.

This is a diagnostic release candidate for human review, not a performance fix,
production measurement, deployment authorization or completed Stage 9 acceptance.
No production host, dashboard, database, account, campaign or provider was accessed.
The 80% improvement / <=4-second target and 1-3-second stretch remain unverified.

## A. Implemented instrumentation and exact scope

Twelve source/test/report paths changed in this task:

| Path | Functions / change |
| --- | --- |
| New `backend/app/npc_diagnostics.py` | `RequestTimings`, `span`, `timed`, `mark`, `operation`; `NpcPerformanceMiddleware.__call__`; `NpcTimingRoute.get_route_handler`; command/pool listeners and `mongo_listeners` |
| `backend/app/main.py` | `create_app`: install outer user ASGI middleware and read optional, non-secret diagnostics switch |
| `backend/app/startup.py` | `create_client`: attach two per-client PyMongo listeners, preserving every existing client option |
| `backend/app/api/dependencies.py` | `authenticated`, `authenticated_mutation`: timing decorators only; security decisions unchanged |
| `backend/app/api/games.py` | Use the timing route class; `npc_step`: time route body/public projection and extract an allowlisted committed action category |
| `backend/app/services/npc_service.py` | `NpcController._load` and `prepare`: time existing state loading and strategy call |
| `backend/app/services/game_action_service.py` | `execute`: time existing evidence validation and engine application separately |
| `backend/app/repositories/security_repository.py` | `_required_indexes`, `authorize`, `_owned`, `find_npc_result`: timing decorators; `_transaction`: time unchanged driver transaction and each callback invocation |
| `backend/app/repositories/action_repository.py` | `find_receipt`, `commit`, nested `commit_once`: timing only, including receipt insertion and existing driver transaction |
| New `backend/tests/test_npc_diagnostics.py` | 29 isolated diagnostic cases, including parameterized cases |
| `backend/tests/test_startup.py` | Retain exact TLS/connect/timeout assertions; additionally assert the two listener types |
| This new report | Evidence, boundaries and human-operated measurement/release plan |

The preceding four-file performance patch is preserved byte-for-byte:
`scoped_action_repository.py`, `benchmark_npc.py`, `test_npc_performance.py` and
`STAGE9_NPC_PERFORMANCE_REPAIR.md`. Its 70-to-67 method-call reduction is still
not a demonstrated explanation or fix for the recurring 20-second delay.
Unrelated Stage E edits, validators, local reports, design references and all
original audio remain in place. AGENTS.md was not edited. Index remains empty;
no stage/commit/push/branch switch/reset/stash/merge/deploy occurred.
Final preservation comparison checked 532 pre-existing source/resource paths:
only the nine listed existing files changed; the other 523 are byte-identical.
The three additions are exactly the new module, test file and this report.

### Actual measurement boundaries

All elapsed values use `perf_counter_ns`, except driver-supplied monotonic
durations, converted to milliseconds. Wall-clock UTC is used only for correlation.

| Field / span | What it actually includes |
| --- | --- |
| `app_total_ms` | Outer user middleware entry through inner ASGI return/failure, before summary formatting/log emission. Includes security/body buffering, routing, dependencies, worker waits, response construction and final ASGI send await |
| `started_utc`, `completed_utc` | ISO-8601 UTC timestamps at measurement entry/end; not browser start/end |
| `response_start_ms` | Entry to response-start send, relative to middleware entry |
| `response_body_sent_ms` | Final body send await returned; handoff to ASGI server, not proof of browser receipt |
| `route_handler` | FastAPI handler, including body parsing, dependency resolution/thread handoffs, endpoint, framework response validation/serialization |
| `route_function` | Synchronous NPC endpoint function, after dependencies and worker dispatch |
| `authentication` / `csrf_check` | Existing authentication dependency/session touch, and existing CSRF comparison respectively |
| `authorization` | Repository session/account checks and any nested touch transaction; recursive same-label spans suppressed to avoid double-counting a recursive authorization as two outer calls |
| `owned_game_load` | Existing `_owned`: fresh authorization plus game fetch and ownership/access parsing; deliberately combined |
| `npc_state_load` | Controller `_load`: scoped authorized load plus runtime-state validation |
| `index_verification` | Existing required-index metadata check; not a new query |
| `npc_decision` | Initial `strategy.decide` call |
| `npc_evidence_validation` | Existing evidence validation, including reproduced policy decision; not just the initial strategy call |
| `engine_action` | Existing `apply_action`, including dice, rules, event construction and state validation |
| `npc_receipt_lookup`, `action_receipt_lookup` | Existing receipt lookup/validation methods, including their authorization calls |
| `receipt_commit` | Existing repository commit method including authorization, replay checks, document construction, transaction and conflict handling |
| `receipt_insert` | Receipt insert call inside the existing transaction; driver/network waiting included |
| `auth_transaction`, `game_transaction` | `with_transaction` wall time including callbacks, driver retry/backoff and commit/abort work; session creation/close sit outside these spans |
| Corresponding `*_transaction_body` | Each actual callback invocation, including failed/repeated callbacks. More than one indicates repeated callback execution; the timer does not cause a retry |
| `response_projection` | Existing public model validation/projection and JSON-mode dump inside endpoint |
| `post_route_framework_ms` | Successful endpoint return to FastAPI handler return: worker handoff plus framework validation/serialization/response creation. Not pure serializer CPU; omitted if those endpoints are not reached |

`spans_inclusive` rows contain count, total_ms, max_ms and failed count. Spans
nest/overlap. **Never sum them or subtract all of them from app_total_ms.** No
invented exclusive `other_ms` or server-selection measurement is emitted.
Absent spans mean the boundary was not observed, not a fabricated zero duration.

### Driver observations

Installed and pinned driver: PyMongo 4.19.0. Its supported `CommandListener` and
`ConnectionPoolListener` interfaces are attached to the existing lifespan client;
no global listener, second client, query, pool setting or retry policy was added.
Public event constructors and the real lazy client factory are exercised locally.
Installed synchronous command-runner/pool sources confirm inline event delivery.
See [PyMongo monitoring](https://pymongo.readthedocs.io/en/stable/api/pymongo/monitoring.html).

- `mongo_commands`: count, aggregate/max duration and failed count for completed
  command attempts. Known command names are allowlisted; unknown names become
  `other`. No command/reply/failure document, namespace, address or driver ID is read.
- `mongo_by_category`: the same command observations grouped into read, write,
  metadata, transaction and other. This is a second view of the SAME durations.
  `findAndModify` is a write; `listIndexes` is metadata. Max is the slowest one
  observed command, not a separately measured category wall interval.
- Command duration includes the driver's monitored network round trip, server
  work and reply processing. It is **not Atlas CPU time** and excludes preceding
  server selection/checkout and some client-side work. Failed attempts count too.
- `mongo_pool.checkout`: successful/failed checkout durations supplied by the
  driver, including waiting and possibly new connection setup. This is not an
  exclusive wait-queue measurement. `connection_setup` is an overlapping subset
  when a connection-ready event occurs on the request thread.
- `mongo_transaction_commands`: commit/abort command observations split by the
  active auth/game transaction span, also subsets of mongo_commands. Additional
  commit attempts with one callback support commit-retry investigation. Failed
  command counts alone do not establish a specific transient-error label.
- Background heartbeat/topology events have no request context and are ignored.
  Server-selection time has no supported public per-operation duration listener
  in this integration. Internal driver hooks/broad DEBUG logs were deliberately
  avoided. Selection/retry-sleep/client-overhead gaps remain unseparated.

The old benchmark's 67 method calls are **not** a measured wire-command count.
`find_one` normally sends `find`, index_information sends listIndexes (and may
fetch more batches), and updates/inserts/findOneAndUpdate normally send their
corresponding wire commands. Two routine with_transaction scopes also issue
commitTransaction, absent from that fake-method count. Retries/getMore/cleanup
can change counts further. The new listeners report actual completed driver
command attempts when deployed; this task has not measured a production count.

## B. Actual local diagnostic sample

Captured by `output/stage9-npc-diagnostics/sample-local.py` through the real ASGI,
security repository, service and engine path with injected in-memory storage.
No application lifespan/settings loader or real database was started. One POST,
one committed local receipt, one 1,966-byte summary. Selected fields from the
actual log (the full row is in sample-http.log):

```json
{
  "event": "npc_request_performance",
  "trace_id": "f8f013d5ce68447292bb66af1a6f7973",
  "started_utc": "2026-11-04T17:47:32.150Z",
  "completed_utc": "2026-11-04T17:47:32.167Z",
  "status": 200,
  "response_complete": true,
  "app_total_ms": 16.901,
  "operation": "start_attack",
  "post_route_framework_ms": 0.594,
  "mongo_commands": {},
  "mongo_pool": {}
}
```

Measured inclusive totals in that row: authentication 0.658 ms, repository
authorization 1.602 ms across 11 calls, index verification 0.552 ms across five
calls, initial decision 0.510 ms, evidence validation 0.593 ms, engine 0.132 ms,
game transaction 0.855 ms, public projection 0.234 ms. These overlap.
Storage doubles do not emit driver events: empty objects are NOT evidence of
zero real database latency. Listener aggregation is separately verified using
the installed driver's real event classes with explicitly synthetic durations.

Local callback microbenchmark: 20 samples of 5,000 synthetic completed-command
callbacks; median 124.3 ns without a request recorder and 1,019.5 ns with one.
This excludes driver APM construction, sockets, full request instrumentation and
Render's log sink. It is not a production overhead guarantee or speedup claim.
Evidence: listener-overhead.json. One bounded summary is logged after response
handling; no per-command output, queue, telemetry service or external call.

## C. Measurement limitations and supplied production evidence

CONFIRMED LOCAL: middleware surrounds CORS/security and catches ordinary early
rejections, errors and cancellation. It resets request context in finally.
Cancellation logs partial observations with response_complete=false; no HTTP
status is invented if response-start was never observed. A worker finishing
after cancellation cannot append to a closed summary. A hard process kill may
produce no summary. Diagnostics never establish whether an uncertain action
committed; exact-receipt recovery is still required.

OWNER-REPORTED: response dated 2026-11-04T17:13:34Z, approximately 19.92 seconds
waiting and 3.63 ms downloading, total approximately 19.93 seconds, HTTP 200.
Sanitized Render identifier e4698929-4fff-4c8c is not our new trace ID. A separate
request spent about 20.03 seconds in Initial connection. No new evidence was
collected from either live host; they must not be assumed to share a cause.

Atlas correlation for the November 3 slow requests remains **INCONCLUSIVE**:
absolute request timestamps are missing. The newly supplied November 4 response
timestamp is roughly twenty hours after the reported November 3 election window;
it does not demonstrate direct overlap with that window. Neither a persistent
failover cause nor irrelevance of all database behavior is established.

Unobserved: browser queue/DNS/TCP/TLS, Vercel-to-Render forwarding, Render cold
start/queue before ASGI entry, Uvicorn receive scheduling, and delivery after ASGI
send. Body delivery waits after middleware entry are included but not separately
timed. Pure CPU, AnyIO worker wait, server selection, transaction backoff and
client processing are not all individually separable. Do not label a residual
interval as proxy latency without additional evidence.

Read-only Vercel inspection confirms external `/api/:path*` rewrite to the Render
host with `/api` stripped, ahead of SPA fallback and with no-store. No frontend
serverless handler or routing change was introduced. `X-NPC-Trace-ID` is an
opaque locally generated UUID hex, never a reflected client header. Same-origin
Chrome DevTools can inspect it without CORS changes. Existing CORS allow/expose
rules stay unchanged; cross-origin JavaScript may not read this unexposed header.
Actual Vercel forwarding of the header remains UNVERIFIED until human inspection.

## D. Safety verification

Only fixed labels, numeric aggregates, generated trace IDs and UTC timestamps
enter the JSON logger `uvicorn.error.npc_performance` at INFO. No path/game ID,
user/account/session identity, IP, token, cookie, header value, payload, MongoDB
query/URI/address/namespace, state, driver error text or exception repr is logged.
The logger uses existing Uvicorn Python logging; no logging configuration was
changed and broad PyMongo DEBUG logging is not enabled.

ContextVar propagation carries the same request recorder into AnyIO's synchronous
workers; locks protect small aggregates. Concurrent requests have separate
recorders, verified through interleaved ASGI calls and thread offload. Metric
keys have bounded cardinality. Recursive same-name spans are suppressed.

Observers catch ordinary timing/listener/formatting/log-handler exceptions;
injected failures preserve successful HTTP bodies and the one existing receipt.
They do not retry actions, generate dice, schedule a next operation or change
transaction ordering. Existing with_transaction options, revision/access fences,
fresh authorization, idempotency, rate limits and atomic board+receipt commits
remain intact. Engine/policy code, schemas, API bodies and frontend recovery,
Fast-forward/Pause/Resume/commentary/sound code were not changed. Tests compare
instrumented versus disabled outcomes/dice counts across seven action scenarios,
and repeated callbacks still compute the engine once and leave one receipt.
Mocked transaction evidence does not replace real-database verification.

## E. Fresh automated verification

| Check | Fresh result |
| --- | --- |
| Full isolated backend tests/ | 971 passed, 0 failed, 44 opt-in real-DB cases skipped; one existing Starlette warning, 27.97 s |
| Targeted diagnostics/performance/security/persistence/API/startup run | 182 passed, 0 failed/skipped; before the final additional lazy-client test, which passed in the full suite |
| New diagnostic cases | 29, all included in the full passing suite |
| Frontend public regression | 377 passed, 0 failed/skipped/cancelled/todo |
| TypeScript | PASS |
| API contracts | PASS, 43 components |
| Public sounds | PASS, 18 runtime mappings/files/hashes |
| Map drift | PASS, 195 countries, 188 geometry/7 fallback, 470 paths/221 groups |
| Country drift | PASS, 195 countries/181 capitals |
| Vite build | PASS, 65 modules; unchanged 613.12 kB JS / 185.20 kB gzip, 50.57 kB CSS; existing large-chunk warning |
| Git whitespace / scope | PASS; no staged paths, unrelated work preserved |

From backend, safe commands (no opt-in flags):

```powershell
$diagTemp = Join-Path $env:TEMP ('geo-diag-full-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $diagTemp) { throw 'Test temp path already exists' }
.venv/Scripts/python.exe -B -m pytest -c pytest.ini tests/ --basetemp $diagTemp -p no:cacheprovider -q
```

This explicit tests/ selection excludes backend/test_database.py. Existing test
network guards block external connections. No disposable/Atlas flags were passed.
All frontend verification commands were run from frontend:

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run check:contracts
npm.cmd run check:sounds
node scripts/build-map-data.mjs --check
node scripts/build-country-reference.mjs --check
npm.cmd run build
```

Root: `git diff --check` and read-only status/index inspection.
Evidence: output/stage9-npc-diagnostics/{backend-full.log,targeted-tests.log,
frontend-tests.log,typecheck.log,contracts.log,sounds.log,map.log,country.log,
build.log,results.json,sample-http.log,sample-evidence.json,listener-overhead.json,
baseline.json,preservation.json}. These local artifacts are not a release package.
Initial test-construction errors (event constructor arguments and iterator
comparison) were corrected in new tests, without weakening production assertions.
The startup test now verifies added listeners and every previous client option.

## F. Human-reviewed release, disabling and rollback

Suitable for a **human-reviewed backend diagnostic release**, subject to review
of the exact diff and the existing separate Git/deployment permissions. No
publication action was taken. Runtime requires the eight modified existing
backend application files plus new app/npc_diagnostics.py. Tests/report support
verification; no new dependency, migration, schema, index or secret is needed.
The earlier scoped read optimization is separate, preserved local work: review
it explicitly if included in the same future release; do not describe it as
part of diagnostics or as an established latency fix.

No frontend deployment or coordinated API release is required. Saved games,
sessions and old receipts remain compatible. Source-controlled configuration,
driver timeouts, retry policy, write gates and trusted origins are unchanged.
Default logging is enabled when the INFO logger is enabled. No additional Render
configuration is required for default operation. Optional
`NPC_PERFORMANCE_DIAGNOSTICS=false` disables recording, summaries and trace
headers at app construction; listeners then do no request aggregation. Only
literal `true` enables when the variable is supplied. A future approved setting
change/restart is required to apply a different value; none was performed here.
INFO logger suppression also bypasses request recording. Do not disable security
or loosen logging/Origin/CSRF to collect this evidence.

Owner reports Render main/9ddb09e, Free, Auto-Deploy disabled; live dashboard state
was not accessed. Inspect the exact current backend release/branch/commit and
approved manual-release mechanism before publishing. A ui-redesign push does
not prove Render updated; earlier Vercel production triggers also make it unsafe
to assume such a push is preview-only. Publishing is outside this task.

Before an approved Render release: Pause NPC scheduling; settle/reconcile any
in-flight operation with the existing exact-receipt flow. Preserve uncertain
tabs/identity; do not blindly reload/resubmit. Deploy only after review, keep
existing data/settings untouched, retain a known-good eligible backend release,
and verify readiness by the already approved procedure. A deployment can sever
a response after commit; instrumentation does not eliminate that risk.

Rollback: after separate approval, restore the recorded previous backend release
and unchanged settings. Do not revert database state, rewrite receipts, restart
a match or reset a campaign. Exact-receipt recovery still governs uncertain work.
After investigation, remove just the diagnostic middleware/listeners/decorators/
span wrappers in a separately reviewed change, restoring original call statements
and retaining the earlier optimization and regression coverage. Do not blanket
revert the dirty working tree. No database cleanup is needed.

## G. Production evidence checklist - human action only, after approval

1. Review/release the backend separately; verify the actual deployed commit and
   that INFO application logs are available. Do not start competing clients.
2. Keep the existing campaign and settled tab. Open Chrome Network and enable
   Preserve log. Continue ordinary authorized play, observing one naturally
   occurring NPC request. Do not use Replay/Edit and Resend/Copy as fetch, create
   another campaign, reset state or submit simultaneous operations.
3. Capture only: UTC observation/response Date, HTTP status, total duration and
   Chrome phases (Initial connection, Waiting/TTFB, download), plus response
   X-NPC-Trace-ID and available non-secret Vercel/Render response identifiers.
   Do not copy cookies, CSRF/authorization/request headers, payloads or raw HAR.
   Omit the private game/account identifiers and full URL from shared evidence.
4. Filter Render Application logs for npc_request_performance and the exact trace
   ID. Copy that one sanitized JSON row. Match its UTC window and operation/status.
   The trace is newly generated for each HTTP request; replayed saved outcomes
   have a different diagnostic trace but retain their gameplay receipt identity.
5. Compare app_total_ms/response_start_ms with that request's browser phases.
   Treat spans as inclusive; inspect database categories/commands and checkout
   independently. Record callback/commit attempt counts and completion flag.
6. If the header is stripped upstream, do not pretend timestamps uniquely prove
   identity: use an unambiguous isolated observation window and operation/status
   as supporting evidence, mark correlation provisional, and review proxy header
   forwarding separately. A browser-cancelled response may provide no trace;
   preserve pending identity and use the existing recovery flow, not a new POST.
7. Repeat across several naturally occurring operations, recording warm/cold and
   operation categories. Do not generate extra moves to fill a sample quota.
   Historical actions cannot acquire retroactive timing records.

Collect an evidence table with: trace, started/completed UTC, operation, HTTP
status, response_complete, browser initial-connection/wait/download/total ms,
app_total_ms, route_handler/route_function/authentication ms, decision/evidence/
engine/projection/tail ms, command category counts/totals/max/failures, checkout/
setup observations, auth/game callback and commit/abort counts. Missing means
NOT MEASURED, not zero. Use it to select a bottleneck before approving a fix.

## H. Next optimization decision tree - no optimization implemented

| Observed evidence | Next bounded investigation |
| --- | --- |
| Mongo read/metadata/write command totals dominate | Separate many round trips from one slow command; inspect approved existing storage/region/plan evidence. Consider only demonstrated redundant work, preserving fresh authorization and index checks. No speculative caching/index/config change |
| Initial decision/evidence-validation dominates | Profile those exact pure functions offline with comparable state size; retain strategy/tie/dice equivalence and receipt evidence. Do not change policy for speed |
| Engine dominates | Profile the measured action locally; preserve deterministic dice/events/rules. Do not skip validation or shorten combat |
| Handler is large but route function/DB are small | Compare authentication, body buffering and framework tail; investigate AnyIO worker contention/CPU with separately approved numeric diagnostics. Residual is not automatically server selection or proxy time |
| Checkout dominates | Distinguish setup/reconnect from possible queue pressure; use existing safe driver/pool configuration evidence. Do not raise pool limits/timeouts without proving the cause |
| Repeated transaction callbacks/commit attempts | Correlate command failures and timing with approved existing topology/Atlas events. Callback count >1 proves repeated execution, not a specific failure label. Keep retry labels/fences/precomputed dice and exactly-once protocol |
| Backend is fast but browser Waiting is slow | Unmeasured time is before entry and/or after send. Review approved Vercel/Render forwarding/cold-start/network evidence; do not attribute the residual to one provider without proof |
| Browser Initial connection is slow | Investigate that browser/network connection separately; FastAPI timings cannot measure DNS/TLS/client connection setup |

No timeout increase, connection/pool tuning, retry removal, infrastructure upgrade,
batch mutation, new UI or game-rule change was made. Production measurement and
any resulting correction require the next human decision.

## I. Historical initial status - superseded by Section J

**DIAGNOSTICS IMPLEMENTED AND VERIFIED LOCALLY**

The tooling is ready for human code review and a separately approved backend-only
diagnostic release. The real recurring bottleneck remains unmeasured. No commit,
push, deploy, production request, saved-campaign change or Atlas change occurred.

## J. Bounded logging handoff - release-blocker correction

Date: 2026-11-04, Africa/Johannesburg. Same branch/HEAD as above; index empty.

### Confirmed cause and correction

The previous middleware called logger.info directly on the ASGI event loop.
Catching an exception did not isolate a slow handler. The audit's artificial
80 ms handler delayed an unrelated coroutine until 89.326 ms. This demonstrated
an instrumentation defect, not an observed Render logging delay.

`DiagnosticLogHandoff` now owns one standard-library Queue and daemon Thread.
Only the worker invokes the existing Python logger. Middleware serializes the
already allowlisted summary to an immutable JSON string, submits it without
waiting for space, and resets request context normally. No handler/formatter or
logging I/O runs in the request handoff. Existing command/pool listeners and
all timing boundaries remain unchanged. Summary UTC timestamps and elapsed times
are captured before queuing; delayed emission does not change those values.

Exact continuation changes (three existing files, no new source/dependency):

| File / reference | Change |
| --- | --- |
| `backend/app/npc_diagnostics.py:39` | New `DiagnosticLogHandoff` with start/submit/stop/worker methods |
| `backend/app/npc_diagnostics.py:283` | Middleware owns dispatcher; ASGI lifespan starts/stops it; finally hands off serialized summary instead of logging |
| `backend/tests/test_npc_diagnostics.py:26` | Explicit worker fixture and bounded synchronization for existing asynchronous log assertions |
| `backend/tests/test_npc_diagnostics.py:431` | Held-handler responsiveness, full-queue gameplay replay, drop/size bounds, lock contention, worker failure, detached context, lifespan and start/stop tests |
| This report, Section J | Current evidence and corrected release assessment |

Other files in the original 12-file instrumentation inventory are unchanged by
this continuation. The prior scoped-document optimization, its benchmark/tests/
report, unrelated Stage E work, AGENTS.md, original audio, generated data and all
frontend/controller/API/engine/security configuration files are preserved.
New files only under output/stage9-npc-log-handoff/ are local verification evidence.

### Capacity, dropping and lifecycle behavior

- Default capacity: **128 waiting records plus at most one in-flight record** per
  middleware instance. Maximum submitted string: **16,384 characters**. No new
  dependency, production setting or external telemetry service.
- Producer uses non-waiting lifecycle-lock acquisition and Queue.put_nowait.
  Full/contended/stopped/unstarted queues, invalid/oversized messages and ordinary
  submission failures lose diagnostics instead of delaying or failing gameplay.
- Internal dropped counts track ordinary rejected/discarded records; contention
  drops are deliberately not counted because acquiring that lock would wait.
  Counters are not new endpoints, public metrics or additional log traffic.
- Worker catches ordinary logging exceptions, increments a failure counter and
  continues. It never logs exception text or retries gameplay. No recursive
  logging is used to report logger failures.
- Worker starts with ASGI lifespan, before serving requests. A worker-start
  failure leaves diagnostics unavailable and does not fail application startup.
  The inner application's own startup errors still propagate unchanged.
- Stop rejects new records, discards at most the bounded queue backlog and sets
  a stop event. It never inserts a sentinel into a full queue, joins/flushes a
  handler, waits for the worker or blocks application teardown on handler I/O.
  An idle worker observes stop within its 50 ms polling interval plus scheduling.
- A handler already running cannot be forcibly interrupted. At most that one
  diagnostic can finish after stop; it may be lost on process termination. The
  worker is daemonized and is not joined by this ASGI teardown. This is bounded
  dispatcher shutdown, not a guarantee about arbitrary third-party handler or
  process-wide Python logging finalization behavior.
- Start is idempotent while running; a stopped dispatcher is one-shot and cannot
  spawn replacement threads behind a stuck handler. A fresh application/middleware
  instance owns the next dispatcher. Direct ASGI harnesses without lifespan must
  explicitly start/inject a dispatcher; otherwise summaries are dropped safely.

The unchanged NPC_PERFORMANCE_DIAGNOSTICS switch defaults to enabled when absent
and the INFO logger accepts records. Literal false disables request recording,
summaries and trace headers and does not start the production logging worker.
It is read at app construction, not hot-reloaded. The existing PyMongo listeners
remain attached, so driver event creation/callback dispatch still has small
monitoring overhead when request recording is off. No environment was changed.

Trace headers remain compatible even if a summary is dropped. A trace header
therefore does not guarantee a corresponding log record. Queue wait/handler time
is not included in app_total_ms; use the JSON's UTC fields for request correlation
rather than assuming Render's emission timestamp is the request end time.

### Deterministic tests and actual offline evidence

The new tests hold a real logging.Handler behind an Event with a finite watchdog.
They prove ordering: the original response and an unrelated event-loop response
complete while the handler is still held. No tight scheduler timing threshold is
required. A full-capacity test performs one local committed NPC move and twelve
identical local replays: all return the same successful body, thirteen distinct
diagnostic traces, one durable fake-store receipt, no extra game writes/dice.
Eleven queued summaries drop; shutdown discards the one waiting summary without
waiting for the held handler, and a subsequent replay still succeeds.

Other tests prove worker exception isolation/continuation, bounded payloads,
lock-contention dropping, explicit empty worker context, immutable snapshots,
idempotent start/stop, disabled lifespan, cleanup after application startup failure
and graceful handling of worker-start failure. Existing concurrent-request tests
still verify independent traces and measurements; existing transaction tests retain
authorization, rollback, repeat-callback, exactly-once and receipt replay coverage.

Standalone offline probe, after correcting the test helper's accidental shadowing
of logging.Handler.release (test/support code only), produced:

| Observation | Actual local result |
| --- | --- |
| Original synthetic ASGI request returned | 0.166 ms |
| Coroutine scheduled after 5 ms woke | 14.045 ms, while handler remained held |
| Unrelated ASGI response completed while handler held | Yes |
| Capacity-two queue while handler held | Two waiting; five dropped |
| Stop returned while handler held | Yes; 0.033 ms |
| Request after stop | Successful; diagnostic dropped |
| Total dropped after stop/backlog and final request | Eight; one summary emitted |

These numbers are observations, not timing assertions or production predictions.
Windows scheduling and concurrent test load affect wake time. Synchronization
proves independence from handler release. There was no socket/HTTP connection,
database, credential read or production operation. Evidence:
output/stage9-npc-log-handoff/{probe-handoff.py,probe-results.json,sample-http.log}.

### Fresh final verification

| Check | Result |
| --- | --- |
| Full isolated backend after final test-helper correction | **982 passed, 0 failed, 44 opt-in real-DB cases skipped**, one existing Starlette warning; 22.59 s |
| Diagnostic cases included in that suite | **40**, including 11 new handoff cases |
| Frontend public tests | **377 passed, 0 failed/skipped/cancelled/todo** |
| TypeScript / contracts | PASS / **43 components** |
| Public sound / map / country drift | PASS; 18 sounds, 195 countries, 188 geometry/7 fallbacks, 181 capitals |
| Production Vite build | PASS; unchanged 65 modules, 613.12 kB JS / 185.20 kB gzip, 50.57 kB CSS; existing chunk warning |
| Whitespace and preservation | PASS; final hashes/scope recorded in preservation.json; no staged paths |

Commands from backend (new unique temporary path; no real-DB flags):

```powershell
$queueTemp = Join-Path $env:TEMP ('geo-log-release-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $queueTemp) { throw 'Test temp path already exists' }
.venv/Scripts/python.exe -B -m pytest -c pytest.ini tests/ --basetemp $queueTemp -p no:cacheprovider -q
```

Frontend commands are the seven commands in Section E, freshly run for this
correction. Runtime source did not change after them; the later correction fixed
only the backend test/support helper and was covered by the final full backend
run. Root: git diff --check and read-only status/index inspections. Existing test
network guards remained active; backend/test_database.py was never imported/run.
Logs/results remain under output/stage9-npc-log-handoff/, including backend-full.log,
frontend-tests.log, typecheck.log, contracts.log, sounds.log, map.log, country.log,
build.log, results.json, baseline.json and preservation.json. Earlier diagnostic
evidence and the original local sample script remain unchanged as history.

### Compatibility and current release decision

Only diagnostic delivery changed: no gameplay, authorization, revision, transaction,
receipt, API-body, schema, timeout, NPC strategy, Fast-forward/Pause/Resume, sound
or narration behavior was modified. No database migration/configuration change
is required; this is a backend-only candidate with no frontend release requirement.
The audit's concurrency blocker is closed by local synchronized evidence.

Render log delivery/overhead, actual proxy forwarding of X-NPC-Trace-ID and the
live Mongo timings remain unverified. This task did not investigate or optimize
the original 20-second latency. These need the first separately approved natural
production observation, using the existing Section G plan and best-effort drop
limitations above. No production host/data/provider was accessed.

The owner must still review the complete candidate, explicitly decide whether to
include the previous scoped-document optimization, retain a rollback artifact and
Pause/resolve any outstanding operation before any approved backend release.
An uncertain action must be reconciled by exact receipt, never by blind replay or
board revision alone. No stage, commit, push, merge, deployment or production
configuration change occurred in this continuation.

**READY FOR CONTROLLED DIAGNOSTIC RELEASE**
