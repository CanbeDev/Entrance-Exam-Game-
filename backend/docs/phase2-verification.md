# Safe Phase 2 verification

## Current status and gate

Final pre-deployment review (2026-10-20): the isolated suite was rerun in the
project Python 3.14 virtual environment with integration tests excluded:
224 passed, 0 failed, 1 existing Starlette/HTTPX TestClient deprecation warning
(1.15 seconds). All 106 Phase 1 regression cases remain passing.

The user independently reported 4 real MongoDB integration cases passed in
23.20 seconds, with no failures, against the dedicated disposable test environment.
This covers real commit/resume/duplicate replay, rollback, and competing distinct/
identical submissions. Those tests were NOT rerun during this review; no MongoDB
connection was made. The earlier 221-test report predates the naming regressions.
Passing doubles alone are not evidence of real transaction behavior.

The reported successful run provides disposable-target verification, not production
transaction approval. Exact server/topology versions and a leftover-database inventory
were not independently inspected during this review. A passing run without teardown
errors is consistent with successful cleanup, but is not an inventory of earlier runs.
Gameplay writes remain disabled by default and production enablement remains separate.

MongoActionRepository receives an explicit MongoClient and Database. It does not
read .env, use app.database, create indexes at import, or change Render settings.
`gameplay_writes_enabled=False` is the default. True is an explicit caller
attestation only after successful real verification; it is not an automatic
capability detection result. No existing API route constructs this repository.

## Atlas / MongoDB prerequisites

- A transaction-capable replica set or sharded cluster, with logical sessions.
  A standalone mongod is insufficient. Verify actual topology, not just a ping.
- A dedicated non-production Atlas project/cluster or disposable LOCAL replica
  set. Use a test-only database user with rights for the generated test database
  and network access configured by its owner. Never reuse the production URI.
- The same client must supply the database and transaction session. Use primary
  reads, snapshot transaction read concern, and majority write concern.
- Precreate test games and game_action_receipts collections before the transaction
  tests. The generated receipt _id encodes game/action IDs, so the built-in unique
  _id index enforces compound identity without an import-time index operation.
- Verify commit, abort-after-game-update, duplicate replay, and competing submissions
  against the actual server. A read-only hello topology check is necessary but is
  not sufficient proof. Server/driver/network permissions can still prevent commits.

Official references:

- https://www.mongodb.com/docs/manual/core/write-operations-atomicity/
- https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/transactions/
- https://www.mongodb.com/docs/manual/core/transactions-production-consideration/

No fallback exists: failed/unsupported transactions leave gameplay writes unavailable.

## Isolated Windows suite (safe; no Atlas connection)

From backend in PowerShell:

```powershell
$phase2Temp = Join-Path ([IO.Path]::GetTempPath()) ("geopolitics-phase2-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -c pytest.ini tests -q --basetemp $phase2Temp -p no:cacheprovider
```

The four real MongoDB cases are skipped by default. External connections are
blocked for isolated tests; Windows asyncio may use its internal loopback pipe.
Never run broad root-level pytest or import test_database.py: that legacy script
writes an Atlas game at module import. verify_persistence.py reads Atlas at import.

## Manual engine demonstration (safe; no writes)

```powershell
.\.venv\Scripts\python.exe -m tools.verify_phase2
```

This explicitly labelled test scenario adjusts a target to one defender, selects
the battle, rolls a deterministic 6 versus 1, captures it, transfers one additional
soldier, then ends the turn. Inspect the printed factual events: surviving attackers
stay at source, reward appears in the captured country, npc-1 is eliminated, and
the next surviving participant acts. It never imports the database connection.

## Real disposable integration suite (ONLY with explicit approval)

Do not run this against production or as part of Render startup/build. The following
command intentionally writes and cleans up a fresh test database. First obtain
explicit authorization for that disposable target and provision it separately.
No project credential/env/deployment changes are required by the tests.

```powershell
$mongoTemp = Join-Path ([IO.Path]::GetTempPath()) ("geopolitics-mongo-test-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -c pytest.ini tests/integration/test_phase2_mongo.py -q -s --disposable-mongodb --basetemp $mongoTemp -p no:cacheprovider
```

Type DISPOSABLE at the confirmation prompt, then enter the dedicated test URI at
the hidden prompt. Do not paste it into a shell command, source file, chat, or test
report. The fixture never loads production .env. It generates a unique database
named geo_p2_<random ObjectId>, checks topology, and precreates
collections. Only that generated database is cleaned up; production games and
database names are never selected by the harness. If cleanup fails, remove only
the generated test database after verifying its name in the dedicated test project.
The seven-byte prefix plus the complete 24-character ObjectId produces a 31-byte
ASCII name, below the 38-byte limit reported by Atlas. The generator checks UTF-8
byte length before any connection. Cleanup checks both the exact generated name
and the geo_p2_ prefix; failures identify only that name and exception type, never
the URI. Isolated regression tests cover length, identifier uniqueness and rejection
of an oversized prefix. The original longer prefix caused the user-reported fixture
setup failures; this local fix does not establish that real transaction tests pass.
The subsequent user-reported four-case success is recorded above separately.

Expected: all four real cases pass, including rollback and one-winner concurrent
updates. A new service must replay the same committed receipt, including dice,
events and original revision. Record date, target topology, driver/server versions,
test counts, and pass/fail evidence WITHOUT credentials before enabling writes.
The integration suite currently verifies commit/rollback/replay/concurrency; induced
server commit-ack loss and driver transaction retry are covered by isolated doubles,
not by privileged real-server failpoints.

## Retry semantics

Each successful action increases revision once. Stable action IDs and exact actor/
command content (including expected_revision) are required for retry. Receipts
return the original result even after later actions have changed the game.
Reusing an ID with different content fails. A stale new command fails without
rerolling against newer state. Concurrent identical submissions return the winner's
committed result. PyMongo transaction callback retries reuse the precomputed result,
not a new dice exchange. A commit acknowledgement failure is surfaced as uncertain;
retry the identical command to resolve it through the durable receipt.

Only committed outcomes are durable. If a transaction definitely aborts before
commit, no result/events were published or persisted. A new process cannot recover
uncommitted random numbers; it can only recover committed receipts. Do not display
or publish computed outcomes until commit succeeds. This is not a background
action queue or a promise to persist failed attempts.

## Manual service use after verification

Instantiate GameActionService with MongoActionRepository(client, test_database,
gameplay_writes_enabled=True) ONLY on the approved disposable target first. Load a
game through load_runtime, derive its current actor/kind, and submit an ActionCommand
with a unique action_id and the loaded expected_revision. ActorContext is trusted
local input, not authentication. Use allocate/start_attack/roll/stop_attack/transfer/
skip/end_turn as permitted by phase. Retrying must reuse the identical command.
No HTTP gameplay write endpoint is provided. Enabling production writes requires
separate explicit approval and verified production transaction prerequisites.
