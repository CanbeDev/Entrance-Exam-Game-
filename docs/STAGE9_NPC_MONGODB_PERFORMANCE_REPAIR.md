# Stage 9 - MongoDB round-trip performance repair

Date: 2026-11-04, Africa/Johannesburg.

**PERFORMANCE REPAIR LOCALLY VERIFIED - READY FOR CONTROLLED RELEASE REVIEW**

The candidate halves measured steady-state command count. **The <=4-second / 80%
production target is NOT achieved or claimed.** At the observed command cost the
remaining 36 serial round trips still model roughly 9.9 seconds. Publication and
production acceptance need separate review; the original latency blocker is not
closed by these local results.

Branch: `npc-mongodb-performance-repair`.
Base/HEAD: `e57206c067a96a707dc7722eff3a43800e3d1bc7` (owner reports deployed).
This commit directly follows `9ddb09ea9121ffa6de328f7b0f4863bfa69ff98e`.
All changes remain unstaged and uncommitted in the separate optimization worktree.

## A. Root cause

**CONFIRMED from supplied production diagnostics and reproduced offline:**

- Baseline `backend/app/repositories/security_repository.py:35` verifies all eight
  required manifest indexes across five collections on every write-gate call.
  `authorize` (baseline line 123) checks before its authentication transaction and
  again inside it; rate consumption checks once; action-store construction checks
  once; game-commit authorization checks once. Five verifications therefore issue
  **25 listIndexes**. Startup already checked the same metadata but its result was
  not available to the repositories.
- Baseline `AuthorizedGameService._owned` (`services/authorized_game_service.py:37`)
  authorizes, then `MongoSecurityRepository._owned` (baseline line 187) authorizes
  again. Baseline `npc_step` (line 94) also discards a scoped game load before a
  separate owned-game/receipt lookup.
- Baseline `ScopedMongoActionRepository.load_game` (line 29) calls the base loader:
  its authorization already fetches the game, then the base loader fetches it
  again. This happens three times on the baseline normal NPC path.
- Baseline `MongoActionRepository.commit` (line 79) authorizes then calls the public
  `find_receipt`, which immediately repeats authorization and its owned-game read.
- Baseline totals: **11 authorization spans**, each reading session and user;
  **nine owned-game loads**, three additional game finds, and four receipt finds:
  `22 + 9 + 3 + 4 = 38 find` commands. Inclusive spans overlap and must not be added.

The owner's two successful traces show about 19.7 s application time, ~274 ms per
command, only 2.401 ms total pool checkout, and <2 ms NPC decision time. This
supports reducing sequential commands; it does not identify the cause of each
command's latency or explain separate browser Initial connection failures.

**UNVERIFIED:** current Render region, Atlas region/provider and cross-region
attribution. Tracked configuration and deployment notes contain no confirmed
region pair. Existing client creation remains once per lifespan with pooled reuse,
lazy TLS connection, and unchanged timeouts. No live database/DNS benchmark, URI,
credential file or production service was accessed. No Atlas change is proposed.

## B. Changes implemented - exact 12-path manifest

Eight modified runtime files, relative to `backend/app/`:

| Path | Purpose / current line |
| --- | --- |
| `repositories/phase4_indexes.py` | Database-bound `IndexReadiness`, line 67; serialized startup verification, retry after failure, shutdown invalidation; unchanged index definitions |
| `repositories/security_repository.py` | Request gates require lifespan readiness (35); unmanaged repositories retain per-write verification (42); exact original-access check in fresh NPC receipt lookup (298) |
| `startup.py` | Create/verify one guard before exposing services (78); invalidate on shutdown; no index provisioning or metadata writes |
| `services/phase4_context.py` | Pass the same guard to the same client/database repository |
| `services/authorized_game_service.py` | Let owned-game load perform current authorization (37); combine original-access fence with fresh receipt lookup instead of discarded state load (95) |
| `services/phase4_contracts.py` | Document reauthorization and the optional original-access argument in the internal store protocol |
| `repositories/scoped_action_repository.py` | Return game fetched by current authorization (30); no state cache |
| `repositories/action_repository.py` | Private receipt read after immediate caller authorization (59, 83); remove nested duplicate authorization; keep transaction checks |

One modified test adapter: `backend/tests/phase4_helpers.py` implements the same
original-access check for the existing in-memory service/API tests.

Three new files:

- `backend/tests/test_npc_mongodb_performance.py`: 28 focused regression cases.
- `backend/tests/benchmark_npc_mongodb.py`: bounded offline comparison harness that
  runs against an entire chosen source checkout, not just one substituted class.
- `docs/STAGE9_NPC_MONGODB_PERFORMANCE_REPAIR.md`: this report.

The earlier scoped read-reuse idea was reevaluated and implemented through a fresh
owned-game read on each call, with new fence tests. No unrelated dirty-worktree
files were copied. Engine, strategy, API routes/models, HTTP deadlines, validators,
frontend, dependency locks, diagnostic module and hosting settings are unchanged.

## C. Before/after performance

Actual classes run over existing in-memory collection/transaction doubles. Baseline
is a complete tracked-source export of e57206c, separate Python process/imports.
Managed candidate initialization verifies metadata before the timed requests.
Commit counts come from successful fake transaction boundaries, not wire events.

Counts below apply independently to allocate and start_attack, and also to roll,
conquest, transfer, end-turn and skip fixtures. The nine-action sequence scales to
648 -> 324 total commands, preserving nine receipts and output/dice equality.

| Metric per normal action | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: |
| Total MongoDB command model | 72 | 36 | -50% |
| listIndexes | 25 | 0 | -25 |
| find | 38 | 27 | -11 / -28.9% |
| Writes | 7 | 7 | unchanged |
| Commits | 2 | 2 | unchanged |
| Owned-game loads | 9 | 7 | -2 |
| Authorization spans | 11 | 8 | -3 |
| Request index-verification spans | 5 | 0 | -5 |
| Startup index inspections | 5 | 5 | moved readiness reused |
| Allocate local median (20 samples, no injected delay) | 22.147 ms | 16.697 ms | -24.6% |
| Start-attack local median (20 samples, no injected delay) | 10.906 ms | 5.887 ms | -46.0% |
| Allocate synthetic median (3 samples, 5 ms/command) | 422.642 ms | 213.438 ms | -49.5% |
| Start-attack synthetic median (3 samples, 5 ms/command) | 413.791 ms | 216.565 ms | -47.7% |
| Actual production application duration | ~19.7 s (owner evidence) | **NOT MEASURED** | pending |

All eight scenarios have identical public-result SHA-256, committed receipt count
and dice-call count between versions, in both modes. Local medians reflect machine
load and in-memory copying; the versions were sequential, not production paired
requests. Synthetic sleep and commit-boundary counts do not simulate MongoDB
transactions, retries, topology, getMore, network, proxy, TLS or pool contention.
No timing spans were summed as independent costs.

**LIKELY estimate, not a measurement:** `36 * 274 ms = 9,864 ms`, before other
processing. The code path is sequential. Four seconds would require <=14 such
round trips, or average command cost below ~111 ms for 36 commands (less with app
cost). Reducing another 22 commands would require a larger authorization/transaction
redesign; this patch deliberately keeps fresh security and commit boundaries.
Next evidence needed is reviewed Render/Atlas region information and authorized
post-release traces, before choosing another application or infrastructure change.

## D. Fresh verification

All commands ran on this optimization candidate, not the dirty development tree.
No real-database opt-in flags, production requests or provider calls were used.

- Backend: **997 passed, 0 failed, 44 skipped**, 48.71 s. The 44 skips are explicit
  real provisioning/persistence/startup cases; doubles do not prove live transactions.
  One existing Starlette/httpx deprecation warning remains.
- Focused coverage: concurrency-safe initialization, missing indexes/driver failure,
  failure retry, exact index definitions, repeated requests, three startup attempts,
  closed lifespans, separate client/databases, current ownership/session checks,
  invalid/missing CSRF/session, expiry, read-only spectator ownership denial,
  lost commit acknowledgement and exact receipt recovery, conflicting fingerprint,
  transaction retry, two prepared competing NPC submissions and one saved receipt.
- Existing engine/NPC/receipt/API/auth regressions and all 40 diagnostics tests pass,
  including nonblocking logging saturation, exceptions, lifecycle and concurrent traces.
- Frontend: **167 passed, 0 failed/skipped/cancelled**; TypeScript exit 0; production
  build exit 0. Dependencies were 541 independently copied/byte-verified locked files;
  no network installation. Baseline frontend has no map/country/audio drift commands.
- Runtime OpenAPI: baseline and candidate JSON exactly equal, **43 schemas / 15 paths**.
  Generated types, checked-in OpenAPI, routes and controller unchanged.
- Standard `npm.cmd run check:contracts`: **FAIL exit 1** on candidate AND untouched
  e57206c diagnostics worktree: `generate-contracts.mjs:43:57`, generated contracts
  stale. Exact in-memory generation equals the existing target after CRLF -> LF;
  1,821 CRLF lines; input SHA-256 is
  `8b0e95b04bcc2aba52888c08c21a6c5439b62b73ee4f4090f76219d2cb2b97aa`.
  This is the documented baseline exception, not an API regression; no contract
  file was rewritten. Full stdout/stderr and exit status are retained.
- One evidence wrapper hit a Windows cp1252 display error after npm test succeeded;
  raw test output was intact. Remaining commands used corrected console encoding.
  Initial focused failures identified setup authorization incorrectly included in
  benchmark span counts; the harness now excludes fixture setup consistently with
  its DB probes. The corrected counts and complete suite pass with assertions intact.
- Final tracked and untracked whitespace/inventory and workspace preservation
  verification are recorded in `final-verification.json` alongside these logs.

Reproduction from optimization `backend/`, using the existing development venv:

```powershell
& $python -B -m pytest -c pytest.ini tests/ --basetemp $uniqueTemp -p no:cacheprovider -q
& $python -B tests/benchmark_npc_mongodb.py --backend-root $baselineBackend --samples 20 --output $baselineJson
& $python -B tests/benchmark_npc_mongodb.py --backend-root . --samples 20 --managed-indexes --output $optimizedJson
# Repeat the two benchmark commands with --samples 3 --command-delay-ms 5.
```

From candidate `frontend/`: `npm.cmd test`, `npm.cmd run typecheck`,
`npm.cmd run check:contracts` (known exception), `npm.cmd run build`.
Evidence is local-only in sibling `Entrance-Exam-Game-npc-mongodb-evidence/`:
`backend-full.log`, complete frontend stdout/stderr/results, runtime OpenAPI and
EOL comparison JSON, baseline/optimized local/synthetic benchmark JSON and
`benchmark-comparison.json`. Do not include evidence, dependencies or build output
in a proposed release.

## E. Risks and remaining acceptance

**CONFIRMED lifecycle policy change:** managed apps attest stable index definitions
once at startup; they do NOT detect administrative index removal while serving.
Never change indexes during writes. Pause writes and restart/reverify every worker
after administrative DDL. Direct unmanaged repositories retain the old per-write
checks and their index-removal regressions still pass. No new periodic poll or DDL
permission was added. Each process/lifespan creates its own guard; there is no global
cache. Concurrency is tested with threads/doubles, not a real multi-worker deployment.

Transaction callbacks still reload session, account and ownership in their own
snapshot; guarded user/session writes fence revocation; revision/access CAS and
atomic game/receipt transaction are unchanged. No authorization or game document
is cached between method calls or transaction attempts. No dice is generated inside
the transaction callback. Replay still requires current authority and exact identity.
No migration, saved-document rewrite, NPC rule, receipt fingerprint or API change.

The e57206c diagnostic module remains byte-identical to its Git source: trace IDs,
allowlisting, listeners, spans, 128-record bounded worker, drop behavior, switch and
shutdown are retained. `false` disables request records/header/worker; absence still
defaults enabled. Listener dispatch/context checks remain when disabled. Managed
HTTP tests verify both modes and identical saved response projection.

Before any separately approved deployment, Pause all playback; wait for in-flight
operations and reconcile every uncertain action by its exact saved receipt. Preserve
pending tabs and page-memory identities; no reload or blind replay. If unresolved,
do not deploy. Capture the active e57206c Render deployment ID/rollback eligibility,
review only the 12 intended paths and verify the exact approved candidate commit.
Keep Vercel/frontend and Atlas/settings untouched. Observe startup readiness before
controlled gameplay, then compare correlated diagnostics. No such operation ran here.

Rollback, if later authorized, selects the known-good e57206c Render deployment,
after the same no-unresolved-action gate. No database restore, game reset, receipt
removal or frontend/controller rollback accompanies this schema-compatible patch.
Disabling diagnostics alone would not revert this performance change.

## F. Disposition

**PERFORMANCE REPAIR LOCALLY VERIFIED - READY FOR CONTROLLED RELEASE REVIEW**

Reviewable 50% command reduction, with preserved local safety evidence. Production
speed, real transaction behavior and the <=4-second target remain unverified/unmet.
No publication, deployment or configuration action is authorized by this report.
