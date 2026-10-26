# Testing the backend

The latest 2026-10-26 isolated regression run passed **757 tests, 0 failures/errors,
44 skipped, 1 existing Starlette/HTTPX warning in 13.78s; exit code 0**. The project
interpreter ran
`-B -m pytest -c pytest.ini tests -q` with a unique validated Windows temporary
`--basetemp` and `-p no:cacheprovider`. All 44 real cases skipped; no live database
connections were made during this isolated run.

The separate authorized Atlas TEST validator integration run passed **23 tests,
0 failures/errors/skips, exit 0 in 101.80s**. Fixture cleanup completed without
teardown errors; see [recorded evidence and limits](atlas-test-verification.md).

The separately authorized Atlas TEST read-only [Phase 4 startup](phase4-startup.md)
smoke passed **1 test, 0 failures/errors/skips, 2 deprecation warnings in 347.96s;
exit code 0**. Startup/shutdown passed, both write gates stayed disabled and
`/`, `/health`, `/countries` and `/openapi.json` returned 200. Readiness reported
`indexes_not_ready`; no database was created or provisioned. The elapsed time
includes interactive confirmation/hidden credential input and is not a measured
startup latency. This verifies TEST lifespan wiring, not deployment of the new
code to Render, production readiness or browser session behavior.

The 2026-10-25 validator/provisioning improvement isolated run passed **689 tests:
zero failed, 43 skipped, one existing Starlette/HTTPX warning**, in **16.79s**.
It used the project interpreter, `-B -m pytest -c pytest.ini tests -q`, a fresh
validated temporary `--basetemp` and `-p no:cacheprovider`. All real MongoDB
tests were skipped (23 validator cases and 20 earlier transaction cases); no
MongoDB connection or integration execution occurred. The previous local
validator implementation run was 620 passed, 25 skipped in 24.95s.
The earlier recorded isolated run passed **593 tests: zero failed, 20 skipped**. Another
**20 real MongoDB tests passed in separate runs**: 12 account/ownership cases and
eight engine/NPC cases, using a dedicated non-production Atlas cluster. These are
the previously verified results, not a new run during this documentation edit.
The existing Starlette/HTTPX deprecation warning remains.

## Running tests

From `backend`, install dependencies:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

Use explicit `tests` discovery and a fresh Windows temporary directory. Pytest can
remove its basetemp, so this helper rejects an existing path:

```powershell
function New-GameTestDirectory {
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $testPath = [IO.Path]::GetFullPath((Join-Path $tempRoot ('geo-tests-' + [guid]::NewGuid().ToString('N'))))
    if (-not $testPath.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $testPath)) {
        throw 'Temporary test directory failed validation'
    }
    return $testPath
}
$testTemp = New-GameTestDirectory
.venv/Scripts/python.exe -B -m pytest -c pytest.ini tests -q --basetemp $testTemp -p no:cacheprovider
```

Without the opt-in flag, real cases skip before prompting or connecting. Isolated
tests inject dependencies and block external connections; Windows asyncio may use
loopback internally. Never use broad root discovery: `backend/test_database.py`
writes to Atlas at import, and `backend/verify_persistence.py` reads Atlas at import.

Coverage includes population boundaries, setup, all game rules, invalid-state
protection, NPC scoring/explanations, dice equivalence, sessions, CSRF, ownership,
projections, idempotency, rollback, retry labels and missing-index protection.

## Offline demos

Run from `backend`:

```powershell
.venv/Scripts/python.exe -m tools.verify_game_setup --country south-africa
.venv/Scripts/python.exe -m tools.verify_phase2
.venv/Scripts/python.exe -m tools.verify_npc
.venv/Scripts/python.exe -m tools.verify_auth
.venv/Scripts/python.exe -m tools.provision_phase4_indexes
```

These show setup, battle/transfer, NPC turns, in-memory accounts/games and the
eight-index/validator plan. The index tool defaults to offline output; see
[local provisioning](mongo-provisioning.md) for explicitly gated local modes.
Do not add `--persist` to setup;
that writes to the application's configured database.

## Real MongoDB tests

The validator-enabled service/rollback suite has separate local and pinned Atlas
TEST opt-ins. Its prerequisites, guarded command and cleanup checks are in
[MongoDB provisioning](mongo-provisioning.md). The commands below are the earlier
transaction suites; those fixtures do not install validators.

These tests write, provision indexes and drop a generated database. Run only with
explicit approval for the dedicated test cluster, test-only credentials and
transaction-capable topology. Never use production or `GeopoliticsCluster`.

The fixture ignores application settings and `.env`. Supply
`--disposable-mongodb-hosts` exactly once: the exact SRV hostname, or all standard
URI seed hostnames comma-separated without ports. Missing, empty, malformed,
duplicate or mismatched allowlists fail before DNS/client creation. There is no
production fallback. Verify the hostname belongs to `UCT-INF4001N-2027-TEST`.

With approval, use the helper above and run the suites separately:

```powershell
$testHosts = 'geopoliticstestcluster.8kw5lci.mongodb.net'
$engineMongoTemp = New-GameTestDirectory
.venv/Scripts/python.exe -B -m pytest -c pytest.ini tests/integration/test_phase2_mongo.py -q -s --disposable-mongodb --disposable-mongodb-hosts $testHosts --basetemp $engineMongoTemp -p no:cacheprovider

$accountMongoTemp = New-GameTestDirectory
.venv/Scripts/python.exe -B -m pytest -c pytest.ini tests/integration/test_phase4_mongo.py -q -s --disposable-mongodb --disposable-mongodb-hosts $testHosts --basetemp $accountMongoTemp -p no:cacheprovider
```

Type exact `DISPOSABLE`, then enter the test URI at the hidden prompt. Never put
it in commands, Git or chat. Remove enclosing quotes/whitespace; percent-encode
credentials once. SRV requires one host without a port. The validator rejects
unsupported options, duplicate keys/TLS aliases, proxies, SRV overrides, file TLS
settings, IP/socket/trailing-dot hosts and malformed syntax. See
[mongo_safety.py](../tests/integration/mongo_safety.py) for supported options and
fixed diagnostic codes. Diagnose locally; never post the URI or widen the allowlist
just to bypass rejection.

After validation/topology checks, the fixture uses `geo_p2_<24-character ObjectId>`:
31 bytes, below Atlas's reported 38-byte limit. Cleanup drops only that exact name
and closes the client on failure paths. Account indexes are provisioned only there;
the missing-index case restores its test index. Cleanup errors identify the test
database without credentials. Inspect that target if cleanup fails. Passing cleanup
does not inventory older leftovers. The allowlist checks seed names, not every
DNS-discovered member; retain normal TLS verification and operator checks.

## Coverage limits

The eight engine/NPC cases cover commits, replay/recovery, conflicts, real soldier
changes, evidence, rollback and historical receipts. The twelve account cases cover
registration races, expiry/logout, idempotent creation, state/evidence/fence rollback,
owner denial, revocation, NPC replay, competing actions, shared limits and missing
indexes after a successful readiness check.

Some retry paths use doubles. Server failpoints, every crash/network race, browser
HTTPS cookies and the Render/Linux setup remain unverified. Test success does not
enable production writes.
