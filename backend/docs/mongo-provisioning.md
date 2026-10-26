# Local MongoDB validators and provisioning

The manifest covers `games`, `users`, `auth_sessions`, `auth_rate_limits` and
`game_action_receipts`. It uses the eight unchanged index definitions from
`phase4_indexes.py`. Importing the manifest/tool does not connect or load settings.
Runtime startup now composes these services with closed default gates; see
[startup wiring](phase4-startup.md). No deployment configuration was changed.

Game schemas distinguish absent `schema_version` (legacy), 2 (setup) and 3
(runtime); unknown versions fail. Structural constraints come from existing models,
translated to MongoDB JSON Schema with inline references. Defaults remain optional
for historical data. BSON int/long and game/receipt ISO date strings or BSON dates
are accepted; auth and TTL fields require BSON dates. String patterns distinguish
date-only snapshots from timestamps, bound month/day/time components and accept
historical naive timestamps, fractions up to six digits, `Z` and numeric offsets.
Calendar validity (such as February's day count) remains an application check.
Old receipts need no NPC evidence.
Ownership envelopes are optional for historical games. Additional security fields
remain allowed for forward compatibility. Cross-field gameplay invariants and
authentication decisions remain application responsibilities.

From `backend`, the default command is fully offline:

```powershell
.venv/Scripts/python.exe -B -m tools.provision_phase4_indexes
```

The CLI accepts only the fixed direct loopback endpoint `127.0.0.1:27017`, with no
URI/configuration/environment support. Database names must be
`geo_prov_<24 lowercase hexadecimal characters>`. Never tunnel this endpoint to a
remote or production deployment. The injected apply API also checks discovered
nodes are loopback and refuses an empty node set.

With separate authorization for a local disposable database, `--inspect --database
NAME` reads collection options/indexes and counts incompatible documents; `--verify
--database NAME` checks exact manifest validators, strict/error enforcement, stored
document compatibility and required index names, ordered keys and semantic options.
Unrelated indexes are permitted. Metadata/permission failures propagate; there is
no repair fallback. Fixed error categories suppress driver details, credentials,
document contents and duplicate key values.

Applying requires both `--apply --database NAME --confirm-database NAME`. All
collections are inspected before writes. Invalid documents, custom validators,
views and custom collection options refuse provisioning. Read-only preflight also
rejects duplicate unique-index values (using the exact partial filter), mismatched
required index definitions and equivalent key indexes under different names.
Duplicate grouping is bounded by a server time limit and returns no key values.
Existing manifest
validators can be reapplied; missing validators/collections can be installed.
This tooling does not migrate documents, drop data/indexes or enable writes.
DDL is not transactional: a later index/permission failure can leave partial
provisioning. Failure reports include a fixed category, manifest collection,
acknowledged operation count and whether changes may have occurred; even a failed
DDL acknowledgement can hide an applied change. Stop writers, inspect, resolve
the cause and explicitly retry. Preflight is not a concurrency lock. No automatic
rollback is attempted. Older installed validator versions need separate review;
they are not automatically replaced or weakened.

Isolated tests use BSON-aware structural checks, service-generated NPC receipts,
frozen index expectations and database/authorization doubles. They do not prove
server acceptance or transactions. Expanded opt-in cases in
`tests/integration/test_mongo_provisioning.py` exercise services under installed
validators, owned-game metadata, historical/current receipts, NPC evidence,
gameplay phases, invalid documents, actual validation-error transaction rollback,
duplicate keys and incompatible indexes. The 23 cases subsequently passed on the
dedicated Atlas TEST cluster; [verification evidence](atlas-test-verification.md)
records the cleanup confirmation and limits. They still skip in isolated runs;
local mode also retains the provisioning reapplication check.

The separate test-only harness uses generated `geo_prov_` databases, refuses an
existing name, creates an ownership marker and drops only the exact database with
its marker. Setup/cleanup failures are sanitized. The local mode requires
`--local-provisioning-mongodb`, a direct loopback server and a transaction-capable
replica set. Never tunnel loopback to a remote deployment.

Atlas mode requires both `--atlas-validator-mongodb` and `--disposable-mongodb`,
plus the exact `--disposable-mongodb-hosts` TEST seed. The harness pins
`geopoliticstestcluster.8kw5lci.mongodb.net`, reuses offline URI allowlisting,
requires SRV with verified TLS, prompts for `DISPOSABLE` and then a working hidden
credential prompt, and checks topology before fixture DDL. No settings, `.env`,
production URI, plaintext credential argument or production fallback is used.
The exact allowlist applies to the SRV seed, not every DNS-discovered member;
normal TLS verification and an additional discovered-cluster check remain active.
An identity/hostname change requires review, not widening the allowlist to bypass
failure. This harness does not add a remote provisioning API to application code.

Before separately authorizing a run, verify the TEST project identity, use test-only
credentials with no production privileges, confirm disposable DDL/cleanup rights
and keep other writers away. From `backend`, use `New-GameTestDirectory` from
[TESTING.md](TESTING.md) and run only the selected file:

```powershell
$validatorTemp = New-GameTestDirectory
.venv/Scripts/python.exe -B -m pytest -c pytest.ini tests/integration/test_mongo_provisioning.py -q -s --atlas-validator-mongodb --disposable-mongodb --disposable-mongodb-hosts geopoliticstestcluster.8kw5lci.mongodb.net --basetemp $validatorTemp -p no:cacheprovider
```

`-s` allows the confirmation/hidden prompts. Do not put the URI in commands or chat.
For a separately authorized local run, replace the three Atlas options with
`--local-provisioning-mongodb`. Do not combine target modes. On cleanup failure,
inspect only the reported generated database; never drop a configured/default DB.
Production provisioning and activation remain unsupported and disabled.
