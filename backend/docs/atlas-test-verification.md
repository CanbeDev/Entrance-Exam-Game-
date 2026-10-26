# Atlas TEST validator integration evidence

The separately authorized 2026-10-25 run on `UCT-INF4001N-2027-TEST` completed
**23 passed, 0 failed, 0 errors, 0 skipped in 101.80 seconds; process exit code 0**.
The log finished at 20:25 SAST (18:25 UTC). Only
`tests/integration/test_mongo_provisioning.py` ran, with both Atlas/disposable
opt-ins, exact pinned TEST seed allowlist, `DISPOSABLE`, hidden rotated TEST URI,
verified TLS and fail-fast. Three credential-free node handshakes passed TLS 1.3
before the suite. No credentials or connection strings are recorded here.

The real run covered server acceptance of five schemas, eight exact indexes,
service-produced authentication/owned games, version/date/numeric rejection,
gameplay phases/victory, historical human/NPC receipts and fingerprints, current
NPC evidence/replay, duplicate keys/preflight/index conflicts and code-121 receipt
rejection after staged game/session/user updates. The rollback assertions and
same-command retry passed.

Cleanup confirmation: every fixture-owned generated database reaches its
ownership-marker check and exact-name drop in `fresh_database` teardown. The run
completed with no teardown errors and exit 0, confirming those cleanup calls
succeeded. No independent post-run inventory was performed; this does not certify
older leftovers or databases not created by the fixture. The source transcript
was the local temporary `geo-atlas-verification-4c048c5c4c27400ba297f890b94f994b/results.txt`
and its `exit-code.txt`; their summary was re-read before recording this evidence.

Limits: this proves TEST repository/service behavior, not production permissions,
Render/Linux execution, browser cookies or new FastAPI startup wiring. Atlas
provisioning reapplication is not exercised (that branch remains local-only).
No failpoints or exhaustive crash/network-race testing was performed. This result
does not authorize production provisioning or activate either application gate.
