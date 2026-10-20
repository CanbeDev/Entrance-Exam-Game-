# Backend architecture

Models validate data; the engine handles rules without FastAPI or MongoDB.
Services coordinate actions, repositories handle storage, and `app/api` handles
HTTP. `GameActionService` supplies revisions, dice and commits;
`AuthorizedGameService` adds ownership; `NpcController` uses the same engine.
Tests inject memory stores or an approved disposable database.

## Population data

[countries.json](../app/data/countries.json) uses Worldometer's
[population table](https://www.worldometers.info/world-population/population-by-country/)
and [country list](https://www.worldometers.info/geography/alphabetical-list-of-countries/):
reference year **2026**, retrieved **2026-10-19**. The dataset ID is
`worldometer-2026-2026-10-19`.

The approved eligibility convention uses 195 countries, including Holy See and
Palestine. The other 39 of 234 entries are recorded as excluded, including Taiwan,
Western Sahara and dependent territories. Holy See covers the Vatican City example.
The JSON keeps URLs, source hashes and stable local slugs. Setup is offline; games
save their population/base values and provenance.

To deliberately download and replace the snapshot from `backend`:

```powershell
.venv/Scripts/python.exe tools/build_country_dataset.py --retrieved-on YYYY-MM-DD --population-year YYYY
```

Review counts, matching, reference year and snapshot tests before accepting it.

## Database

| Collection | Contents |
| --- | --- |
| `users` | Canonical/display username, Argon2id hash, status, account/auth revisions and creation time. |
| `auth_sessions` | Hashed credential `_id`, user ID, CSRF token, account version, expiry/activity/revocation and revision. |
| `auth_rate_limits` | Hashed scope/window ID, count and expiry. |
| `games` | Gameplay plus separate `access` owner/human/version binding and `creation` key/fingerprint. |
| `game_action_receipts` | Actor, command, fingerprint and committed result/events/NPC evidence. |

Sessions require an active user and matching account version. Ownership binds that
user to the game's human participant. Validation is in code; MongoDB foreign keys
and JSON Schema validators are not provisioned. There is no ownership-transfer,
legacy-claim or account-deletion API.

### Indexes

The [manifest](../app/repositories/phase4_indexes.py) defines these eight indexes,
in addition to built-in unique `_id` indexes:

| Collection / name | Keys and options |
| --- | --- |
| `users` / `username_key_unique` | `username_key: 1`; unique |
| `auth_sessions` / `session_user` | `user_id: 1` |
| `auth_sessions` / `session_expiry` | `expires_at: 1`; TTL 0 seconds |
| `auth_rate_limits` / `rate_limit_expiry` | `expires_at: 1`; TTL 0 seconds |
| `games` / `owned_game_listing` | `access.owner_user_id: 1`, `_id: -1` |
| `games` / `owned_game_creation_unique` | `access.owner_user_id: 1`, `creation.key: 1`; unique; partial filter: both fields `$type: "string"` |
| `game_action_receipts` / `game_event_revision` | `game_id: 1`, `result.state.revision: 1` |
| `game_action_receipts` / `npc_revision_replay` | `game_id: 1`, `command.expected_revision: 1`, `actor.kind: 1` |

Writes recheck required definitions and fail closed if indexes are missing or
incompatible. Startup does not create them. Provision explicitly; do not change
indexes during writes. TTL cleanup does not replace application expiry checks.

### Transactions and compatibility

State and receipt/events/evidence commit together using snapshot reads, majority
writes and primary preference. MongoDB needs logical sessions and a replica set or
sharded topology. There is no non-atomic fallback.

Actions carry `action_id`, `expected_revision` and typed `action`. Matching retries
return the original result; changed content or stale new actions conflict.
Transaction callback retries reuse computed dice/events and preserve driver error
labels. Retry uncertain commits with identical submissions. Fresh processes cannot
recover aborted random results.

Authorization is checked before receipts, strategy or dice, and rechecked within
the transaction using user/session fences and owner/human/access-version predicates.
Logout/revocation can conflict with a commit. Creation keys are unique per owner:
matching requests return the same game, changed payloads conflict, and late retries
do not reset play. Listings remain owner-scoped.

Schema-2 initialized games adapt to runtime schema 3 in memory; reads do not
migrate documents. Ownerless records, including "My First Game", stay readable but
unplayable. Historical receipts and human fingerprints remain compatible. Runtime
dates use UTC milliseconds.

## Authentication

Usernames are 3-32 ASCII letters/digits/underscores, unique ignoring case.
Registration passwords are 15-128 Unicode characters; registration/login normalize
NFC without trimming. Registration rejects NUL, repeated-character and local
common-list passwords. Argon2id uses 19 MiB, two iterations, parallelism one and
random salts; each password provider permits two concurrent hashes. Unknown-user
login does dummy verification and returns the normal invalid-login error.

A login issues a fresh 256-bit opaque credential; only its SHA-256 verifier is
stored. The `__Host-geopolitics_session` cookie is Secure, HttpOnly, SameSite=Lax,
Path=/, without Domain. Login revokes a presented same-account session; logout
revokes and clears the current one. Idle expiry is 30 minutes, absolute expiry
12 hours. Protected requests recheck expiry, revocation, status and account version.
Authenticated reads may refresh activity; public reads do not write.

POSTs require an exact trusted Origin and JSON, except empty logout bodies.
Authenticated POSTs also require `X-CSRF-Token`. Bodies are limited to 16 KiB.
Clients cannot supply actors, owners, dice, evidence or state. New session/game
routes use no-store; errors omit passwords and driver details. Allowlisted public
schemas omit ownership, credentials, fingerprints, digests, tie seeds and unknown
private fields.

Shared fixed-window limits count all attempts: registration 5/IP/hour; login
30/IP/5 minutes and 10/account/15 minutes; gameplay 120/account/game/minute.
429 includes `Retry-After`. Boundary bursts remain possible. Client IP comes from
the connection, not untrusted forwarded headers.

## API contracts

Existing root/health/catalog/saved-game reads remain public. The additional routes
below require a supplied application context; by default they return disabled.

| Route | Contract when configured |
| --- | --- |
| `POST /auth/register` | Anonymous, Origin; credentials; public user, 201. |
| `POST /auth/login` | Anonymous, Origin; credentials; cookie, user and expiry. |
| `POST /auth/logout` | Session, Origin, CSRF; revoke; 204. |
| `GET /auth/me` | Session; public account ID/username. |
| `GET /auth/csrf` | Session; CSRF token. |
| `POST /games` | Account, Origin, CSRF, gameplay gate; `game_name`, `starting_country_id`, `Idempotency-Key`; public game, 201. |
| `GET /me/games` | Account; `status`, literal `query` (up to 100 characters), ObjectId `cursor`, `limit`; `games`, `next_cursor`. |
| `POST /games/{game_id}/actions` | Owner, Origin, CSRF, gate; action ID/revision/action; server-derived human actor. |
| `POST /games/{game_id}/npc-steps` | Same owner protections; nonnegative `expected_revision`; one server NPC action. |
| `GET /games/{game_id}/events` | Anonymous; committed public events, `after_revision` (default 0), `limit`. |

Page limits are 1-100, default 20. Event responses include `events`,
`after_revision`, `next_after_revision`, `has_more`; entries include revision,
action ID, actor, time, factual events and optional decision. Action responses use
`state`, `events`, optional `npc_decision`. Creation keys are 1-128 ASCII
letters/digits/underscores/hyphens. New human commands reserve `npc-`; matching
historical receipts remain replayable.

New errors use `detail.code`: 401 authentication, 403 access/CSRF/origin, 404 missing,
409 conflict, 413 body size, 415 content type, 422 validation, 429 limit, 503 disabled
or unavailable. Existing reads keep their contracts; `/docs` shows request schemas.

## Deployment requirements

Authentication/gameplay settings and repository write gates default false.
`app.state.phase4` is `None`; normal startup supplies no protected context and no
environment switch activates it. Production credentials and Render settings remain
unchanged. Index provisioning and protected activation require separate approval.

Prefer same-origin HTTPS for the future frontend. Keep CSRF in memory and session
credentials out of localStorage. Local browser work needs trusted HTTPS/proxy;
loopback HTTP test tooling does not prove browser cookie behaviour. Separate
origins require reviewed CORS/cookie settings; wildcard credentialed CORS is absent.
Review Render proxy trust, Linux build, transaction permissions, index checks and
Argon2 resource use before activation. Password recovery, email verification, MFA
and account administration are not implemented.
