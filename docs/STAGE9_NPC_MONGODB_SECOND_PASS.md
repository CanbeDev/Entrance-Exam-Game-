# Stage 9 - MongoDB performance optimization, second pass

Date: 2026-11-04, Africa/Johannesburg.

**PERFORMANCE REPAIR LOCALLY VERIFIED - READY FOR CONTROLLED RELEASE REVIEW**

**CONFIRMED offline:** normal eligible NPC operations use 24 modeled MongoDB
commands, down from first-pass 36 and deployed-diagnostics baseline 72. The
provisional 20-25 command target is met locally without removing authorization
checkpoints. **UNVERIFIED:** actual production query plans, activation/latency and
real MongoDB behavior. Four-second production acceptance remains open.

Worktree/branch: `Entrance-Exam-Game-npc-mongodb-performance-repair` /
`npc-mongodb-performance-repair`; HEAD/base remains
`e57206c067a96a707dc7722eff3a43800e3d1bc7`. Nothing staged or committed.
The first-pass report remains unchanged as historical evidence; this report and
`second-pass/final-verification.json` describe the current candidate.

## 1. Every remaining first-pass read

The profiler records collection, exact application stack/line, explicit driver
session presence and transaction phase. It never emits query values, session
hashes, principals or stored documents. The allocation and start_attack profiles
have the same shape; all 27 individual rows are retained in `first-pass-reads.json`.

| First-pass ordinals | Call/purpose | Context | Collections / find count | Second-pass commands |
| --- | --- | --- | --- | ---: |
| 1-2 | Authentication dependency -> authorize; current session/user before touch fences | Authentication transaction | auth_sessions, users / 2 | 2 find |
| 3-5 | AuthorizedGameService._owned -> load_owned_game; facade entry ownership | Outside explicit transaction | session, user, game / 3 | 1 aggregate |
| 6-9 | find_npc_result; current ownership/original access plus saved NPC result by expected revision | Outside | session, user, game, receipt / 4 | 1 aggregate + 1 find |
| 10-12 | NpcController.prepare -> _load; authoritative strategy input | Outside | session, user, game / 3 | 1 aggregate |
| 13-16 | GameActionService.execute -> find_receipt; exact action duplicate/fingerprint | Outside | session, user, game, receipt / 4 | 1 aggregate + 1 find |
| 17-19 | execute -> load_game; recheck revision and decision before dice | Outside | session, user, game / 3 | 1 aggregate |
| 20-23 | commit preflight; current authorization and exact-receipt fast path | Outside | session, user, game, receipt / 4 | 1 aggregate + 1 find |
| 24-27 | commit_once; fresh authority, game/access and exact receipt inside snapshot | Gameplay transaction | session, user, game, receipt / 4 | 4 find |

These are repeated data accesses at distinct checkpoints, rather than reusable
negative receipt results or authorization caches. Every checkpoint still runs.
Seven owned-game loads and eight authorization spans remain. Three outside
receipt reads and the transaction receipt read remain independently authoritative.

Current source entry points: `backend/app/repositories/security_repository.py:195`
(`_owned_joined`), line 262 (`_owned`), line 134 (`authorize`); existing services
and receipt protocol retain their first-pass call sequence. Exact stacks for both
versions are recorded in `first-pass-reads.json` and `second-pass-reads.json`.

## 2. Implementation and exact changed files

Six outside-transaction session/user/game triplets become one indexed read-only
aggregate each. The pipeline matches one session _id, looks up the bound user
with the existing active/auth-version predicates, and looks up one game _id.
Shared validation retains expiry/idle/revocation, identity/auth-version and owner
checks. Original access/version checks still run in the existing scoped adapter.
User projection returns only _id, username and auth_version; no password hash is
returned by that join. The complete game is retained for supported state parsing.
All data is local to this call; there is no user/game/receipt cache.

The request still performs the equivalent logical document accesses. This change
reduces network commands, not the number of security decisions or essential
server-side document lookups. No changes to strategy, engine, DTOs, HTTP deadlines,
controller, auth endpoints, recovery, writes, commits or index definitions.

**Nine modified paths relative to the frozen first pass:**

| Path | Role |
| --- | --- |
| `backend/app/repositories/security_repository.py` | Shared original session/principal validation; fresh joined reads outside transactions; topology/metadata guard; size-only read fallback |
| `backend/app/repositories/phase4_indexes.py` | Carry verified simple-collation eligibility for this database lifespan, clear it on shutdown |
| `backend/app/startup.py` | Attest collation compatibility from metadata already read for validator readiness; no extra command |
| `backend/app/services/phase4_context.py` | Pass verified eligibility when constructing the repository |
| `backend/app/npc_diagnostics.py` | Only diagnostic change: allowlist aggregate as read; worker, queue, trace and timing machinery otherwise exactly unchanged |
| `backend/tests/test_phase4_mongo.py` | Bounded aggregation evaluator for collection doubles, replica-set fixture capability; same failure assertions target aggregate outside transactions and find inside them |
| `backend/tests/benchmark_npc.py` | Count aggregate as one command, including synthetic latency |
| `backend/tests/benchmark_npc_mongodb.py` | Report aggregate separately, preserve total counting |
| `backend/tests/test_npc_mongodb_performance.py` | Assert the measured 24-command budget including six aggregates; all security/gameplay assertions preserved |

**Three added paths:**

- `backend/tests/profile_npc_reads.py`: reproducible privacy-safe call-site inventory.
- `backend/tests/test_npc_read_consolidation.py`: 51 focused cases, including both
  separate and consolidated denial paths, current authorization, compatibility,
  concurrency and stale-revision behavior.
- `docs/STAGE9_NPC_MONGODB_SECOND_PASS.md`: this report.

This pass changes exactly 12 paths relative to the first pass. The cumulative
candidate relative to e57206c is 18 paths: the original 12 plus diagnostics,
benchmark_npc.py, test_phase4_mongo.py and the three new paths above. The exact
hash manifests are `second-pass-changes.json` and `release-manifest.json`.
The pre-existing dirty development and diagnostics-release worktrees are preserved.

## 3. Counts and benchmarks

Counts are measured with actual services/engine and in-memory collection/transaction
doubles. Commit commands are counted at fake successful transaction boundaries.
They are **not production wire measurements**; actual retries/getMore can add commands.

| Per normal action | First pass | Second pass | Change |
| --- | ---: | ---: | ---: |
| find: auth_sessions | 8 | 2 | -6 |
| find: users | 8 | 2 | -6 |
| find: games | 7 | 1 | -6 |
| find: game_action_receipts | 4 | 4 | unchanged |
| find total | 27 | 9 | -18 |
| aggregate (each retains session/user/game checks) | 0 | 6 | +6 |
| All read commands | 27 | 15 | -12 |
| listIndexes during requests | 0 | 0 | unchanged |
| Writes | 7 | 7 | unchanged |
| Commits | 2 | 2 | unchanged |
| **All commands** | **36** | **24** | **-33.3%** |
| Owned-game loads / authorization spans | 7 / 8 | 7 / 8 | unchanged |
| Nine-action sequence total | 324 | 216 | -108 |

Before measurements use a complete 187-file hash-verified frozen first-pass source
copy; each version runs in a separate process/import environment. Identical fixture
states, fixed dice, clock, dependency graph and harness are used. Local mode uses
20 samples per case; synthetic mode uses three samples with 5 ms per command,
including commits. Medians below are milliseconds; versions run sequentially.

| Scenario | First, no delay | Second, no delay | First, synthetic | Second, synthetic |
| --- | ---: | ---: | ---: | ---: |
| allocation | 12.944 | 13.947 | 229.495 | 164.198 |
| attack_start | 7.709 | 7.203 | 219.983 | 152.976 |
| dice_exchange | 5.471 | 6.011 | 217.909 | 151.901 |
| conquest | 5.557 | 5.726 | 217.299 | 148.803 |
| transfer | 12.203 | 12.322 | 235.194 | 162.970 |
| end_turn | 5.136 | 5.661 | 219.115 | 152.988 |
| skip | 5.497 | 5.921 | 218.569 | 150.732 |
| nine_npc_sequence | 63.393 | 71.293 | 1981.913 | 1388.956 |

No-delay allocation and several other cases are slightly slower. Joined-query
collection doubles do more in-memory bookkeeping; no CPU speedup is claimed.
Synthetic command-delay reductions show the intended round-trip benefit; they
cannot establish real server query costs. Small n=3 synthetic tails are not a
production latency distribution. Inclusive authorization timing now includes the
combined query's game lookup; do not interpret it as isolated auth-document time
or add it to the overlapping owned-game span.

## 4. Verification and equivalent behavior

Fresh complete backend command, from candidate backend/, with the existing
Python executable and a unique local temporary directory:

```powershell
& $python -B -m pytest -c pytest.ini tests/ --basetemp $uniqueTemp -p no:cacheprovider -q
```

**1048 passed, 0 failed, 44 skipped**, 39.05 s. The 44 real-database cases remain
explicitly opt-in; no production/disposable Mongo was accessed. One existing
Starlette/httpx deprecation warning remains. An earlier second-pass full run passed
1037 before the last 11 focused compatibility/concurrency cases were added.

Coverage includes authorization/ownership, valid/missing/invalid CSRF, expiry,
revocation, session/account version changes, shared-database concurrent users,
separate databases, exact replay, conflicting action payload, lost commit response,
transaction retry/rollback, competing NPC submissions, stale revision after NPC
preparation with no dice consumption, reinforcement/combat/conquest/transfer/turn
progression, results, and all existing logging concurrency/lifecycle regressions.

All eight benchmark scenarios match full public-result SHA-256, dice-call count,
receipt count and revision progression across versions. Normal actions commit one
receipt; roll/conquest advance revision 1 -> 2. The nine-action sequence advances
exactly 1,2,3,4,5,6,7,8,9 with nine receipts. Concurrency tests separately assert one
receipt/effect for duplicate submissions and isolation for two accounts/games.

Frontend commands freshly run on this candidate: `npm.cmd test` -> **167 passed,
0 failed/skipped**; `npm.cmd run typecheck` -> exit 0; `npm.cmd run build` -> exit 0.
Runtime OpenAPI equals the first pass exactly: **43 schemas, 15 paths**. Source
contracts, frontend, validators, engine, strategy and dependency locks unchanged.

`npm.cmd run check:contracts` remains **FAIL exit 1**, `generate-contracts.mjs:43:57`,
with the established CRLF/LF baseline exception. Exact in-memory generation equals
the target after line-ending normalization; source SHA-256 remains
`8b0e95b04bcc2aba52888c08c21a6c5439b62b73ee4f4090f76219d2cb2b97aa`.
No contract regeneration or workaround was committed to source.

The only diagnostic source change is aggregate -> read classification. Trace IDs,
strict payload allowlisting, 128-record nonblocking worker, dropping, failures,
concurrent request isolation, lifecycle and absent/default-enabled / false-disabled
switch remain covered by passing tests. No raw query or joined values are logged.

## 5. Retained operations and safety guards

- Authentication transaction retains two finds, its guarded user/session writes
  and commit. Gameplay transaction retains four finds, user/session fences, game
  revision/access CAS, receipt insertion and commit. Each callback reloads within
  its current transaction; no pre-transaction state is reused by a retry.
- Three outside receipt reads plus the transaction read retain independent exact
  identities and conflict/acknowledgement handling. A negative read is never cached.
- Six independent joined checkpoints retain fresh session/user/game reads at their
  existing call sites. No checkpoint is reused after rate writes, strategy work,
  receipt reads or another transaction. The guard does not claim a new atomic
  cross-collection snapshot outside transactions; commit authorization stays inside
  the existing snapshot transaction.
- Startup enables this only for a known ReplicaSetWithPrimary topology and simple
  default collations across the three collections. Unknown/mongos/single/no-primary
  topology, non-simple collation, or absent attestation keeps the first-pass path.
  No per-request capability probe, new environment switch, setting or index is added.

These compatibility guards avoid assuming sharded $lookup support; MongoDB documents
version-dependent restrictions for sharded foreign collections.
[MongoDB $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/).
An aggregate uses one collation, so arbitrary per-collection comparison rules are
not consolidated. [MongoDB aggregate command](https://www.mongodb.com/docs/manual/reference/command/aggregate/).

All joins use unique constant _id matches. Root and foreign cardinalities are at
most one on the eligible replica-set path; batchSize=2 exhausts the ordinary
one-result cursor. Near-limit game wrapping can fail with BSONObjectTooLarge
(10334); only that read-only failure falls back once to original fresh reads.
Other database errors stay sanitized/fail-closed. No mutation is retried by this
fallback. [MongoDB error codes](https://www.mongodb.com/docs/manual/reference/error-codes/).

Normal eligible count is 24. Compatibility fallback is 36. A size error at all
six checkpoints can cost 42 commands (36 plus six failed aggregates); this is a
correctness fallback, not a guaranteed performance bound for oversized games.
No unbounded request cache, background poll or new mutation path was introduced.

These retained operations are the boundary of this narrow patch, not a proof of a
mathematical minimum. Further removal would need separate analysis of transaction
queries and receipt checkpoints. The provisional target is already met without
changing either transaction's query protocol or skipping any fresh check.

## 6. Latency projections and unresolved risks

**PROJECTION ONLY:** keeping the observed ~274 ms command cost gives
`36 * 274 = 9,864 ms` for the first pass and `24 * 274 = 6,576 ms` for the second,
a modeled saving of 3,288 ms / 33.3%. Relative to deployed 72 commands this is a
66.7% command reduction. The estimate assumes an aggregate costs about one prior
round trip; server-side join cost can raise it. Application/proxy/network/retry
costs are additional. This is not an optimized production measurement, and is
not evidence of <=4-second performance.

**UNVERIFIED:** production topology/collation eligibility, actual aggregation plan
and index use, CPU/payload/latency under live load, getMore/retry counts, Render and
Atlas regions, and browser Initial connection failures. No claims about production
speedup or the existing campaign were made from local doubles. Existing transaction
integration evidence is preserved, but the 44 skipped live tests are not fresh
transaction proof for this candidate.

Read-only startup metadata drives eligibility without configuration changes. An
existing non-simple deployment remains functional through the first-pass path.
Administrative index/collation/collection changes require quiescent writes and a
fresh verified lifespan, as in the first-pass lifecycle policy. Real observations
and any release operation require separate owner authorization. Before deployment,
Pause gameplay and reconcile all unresolved actions by exact receipt; preserve
pending tabs, never reload or blindly replay them. Rollback remains the recorded
e57206c deployment with no database restore or receipt removal.

## 7. Reproduction, evidence and verdict

The sibling `Entrance-Exam-Game-npc-mongodb-evidence/second-pass/` contains:

- `first-pass/`, `first-pass-manifest.json`: complete preserved source reference.
- `first-pass-reads.json`, `second-pass-reads.json`: every read and exact source stack.
- `first-pass-local.json`, `second-pass-local.json` and corresponding synthetic JSON.
- `benchmark-comparison.json`, `gameplay-equivalence.json`: all eight comparisons.
- `backend-final.log`, frontend stdout/stderr/results, API/diagnostic compatibility.
- Exact incremental/cumulative manifests and final whitespace/preservation evidence.

```powershell
# From backend/, run once for each complete source root; no network/database access.
& $python -B tests/profile_npc_reads.py --backend-root $firstPassBackend --output $firstProfile
& $python -B tests/profile_npc_reads.py --backend-root . --output $secondProfile
& $python -B tests/benchmark_npc_mongodb.py --backend-root $firstPassBackend --managed-indexes --samples 20 --output $firstJson
& $python -B tests/benchmark_npc_mongodb.py --backend-root . --managed-indexes --samples 20 --output $secondJson
# Repeat both benchmarks with --samples 3 --command-delay-ms 5.
```

Only Git source and declared first-pass changes were copied; no private audio or
actual environment/credential files were added. The exact release diff excludes
local evidence/dependencies/build output.
No commit, push, merge, deployment, production request or configuration change ran.

**PERFORMANCE REPAIR LOCALLY VERIFIED - READY FOR CONTROLLED RELEASE REVIEW**

The 24-command exploratory target is demonstrated locally on the guarded path.
Actual production performance and the four-second goal remain unverified/unmet.
