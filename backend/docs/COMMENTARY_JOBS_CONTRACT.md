# Automatic Battlefield Dispatch — local implementation contract

6 November 2026. This authorizes no database installation or activation. Discovery
and execution default off; no process is started by importing these modules.

## Authorization and consent

The public POST retains its existing session, owner, CSRF and Origin guards.
An internal worker uses a separate typed authorization context, never a Principal,
cookie or actor ID. It resolves current game ownership, active account/auth_version
and an explicit durable campaign policy before work and again before dispatch.
Authorization is a fresh pre-dispatch snapshot, not an atomic lock against a
concurrent account/ownership change. A change observed at that check denies the
call; a call already admitted at that check may finish. No stronger revocation
ordering is claimed.

`commentary_policies` stores one record per game (_id is canonical game-id string),
owner account, account auth_version, the hash of its complete canonical saved
GameAccess tuple, enabled, version, activation_revision and updated_at. Only the
existing fresh authenticated owner service may set consent.
Initial enable/re-enable/ownership adoption uses current saved revision + 1; no
backfill. Repeated enable of the same grant preserves its activation boundary.
Opt-out disables it using version CAS. Ownership/auth-version mismatch invalidates
the old grant even if enabled. Re-enabling requires fresh owner consent. No policy
means no worker generation. Owner-only commentary-preference GET/POST routes use
existing HTTP session, ownership, CSRF and Origin guards. They never schedule work
or call Groq. The Chronicle reads server mode and exposes the durable checkbox in
worker mode, where local automatic POST generation is disabled. Uncertain
preference reads fail closed until an explicit saved check.

## Discovery

An independent reconciler scans enabled policies and immutable per-game receipts,
including completed games and every human/NPC exchange during Fast-forward. It
uses receipt revision/action identity and the existing battle evidence parser.
Each eligible receipt produces an idempotent natural-key job upsert. No queue write,
provider operation or new dependency enters gameplay transactions. Bounded, fair
pages freeze a saved head revision per campaign and repeat from each policy boundary;
cursors are volatile, so restart rescans
instead of skipping receipts. Existing jobs are never reset. Retention of receipts
is necessary for eventual coverage. A malformed receipt aborts that game's page
for review and is retried from its boundary on a later full sweep. It cannot pin
enumeration or prevent other games from progressing.

## Provider authority, leases and capacity

The 16-field jobs schema and three indexes in the specification remain the job
contract. A job lease owns coordination only. Only the existing acknowledged
permanent battle_commentary insert winner can reserve admission and call Groq.
Existing ready/fallback/pending records never authorize another provider request.

Both new execution paths share `commentary_execution_slots`: two fixed records
(_id integer 0 and 1), with nullable token. Atomic null-to-token acquisition uses
majority acknowledgement. There is no TTL or time-based reclaim. Unknown acquire
outcomes grant no permission. A slot is released by exact token only when no
provider call began or the outcome proves the call settled. Timeout, cancellation
or unknown provider failure quarantines it indefinitely for read-only diagnosis
and separate human recovery review. No automatic reset/reclaim is supplied.
This sacrifices availability to preserve conservative capacity across restarts.
All HTTP/worker instances must run the shared-capacity configuration before worker
activation. An older/local-semaphore instance cannot be covered by this protocol.

Existing global/account/game admission buckets, output validation, permanent claims
and no SDK retries remain authoritative. Admission-limited and other saved
fallbacks are terminal. Processing attempts (max three) are not provider attempts.
Retry only pre-claim local capacity/read failures or saved-state reconciliation.

## Uncertainty and finalization

An expired job lease never reclaims a permanent narration claim. A pending claim
is reconciled read-only, then closed interrupted when stale; never regenerated.
Any ambiguous storage acknowledgement is handled conservatively. A caller already
holding a permanent claim may finish its saved narration after losing a job lease,
but stale job updates fail CAS. Save narration first, then job metadata. Metadata
failure is repaired from exact saved evidence without another provider call.
Failed-to-ready repair is allowed only after saved ready/groq is verified.

Four states: queued -> claimed -> ready/failed; claimed -> queued only for bounded
safe processing retries; queued -> ready/failed for reconciliation; expired claimed
is recovered with token+expiry CAS. Failed never reopens execution; it may only be
repaired to ready from saved truth. Explicit nulls clear job leases/errors; do not
unset required fields. BSON datetimes remain datetimes, counters are integers.

## Runtime and installation gates

Settings: COMMENTARY_JOBS_DISCOVERY_ENABLED and COMMENTARY_JOBS_EXECUTION_ENABLED,
strict true/false, both false by default. Execution requires shared-capacity
readiness; optional jobs failures must not affect gameplay readiness/transactions.
No automatic worker is attached to FastAPI startup. The separate entry point is
`python -m app.commentary_jobs --idle-when-disabled`; both flags off keeps it idle
without even loading database credentials or creating a provider client. Plain
`python -m app.commentary_jobs` exits successfully in disabled mode for local
verification. Runtime components require explicit invocation; offline tests use
fake narrators only. No Render service was created or configured.

No production collections are created or changed by this work. The existing empty
jobs collection is insufficient: policies and two initialized capacity records,
their reviewed validators, optional readiness, verified consent UI/API integration and real
disposable MongoDB compatibility tests are separate activation gates. No disposable
MongoDB environment is authorized by this contract. No Groq calls are authorized.
