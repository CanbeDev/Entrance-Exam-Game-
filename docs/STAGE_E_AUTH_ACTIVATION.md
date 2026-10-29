# Stage D3 conclusion and controlled Stage E authentication

Prepared 2026-10-29. Procedure only; no external access or activation performed.

## Accepted baseline

The user confirms deployment `e5a3199`, successful Render build/startup, both
protected-write gates disabled, passed production Stage D2, and application role
`atlasAdmin@admin`. The old `indexes_not_ready` warning predates provisioning.
Reuse this evidence. D2 is closed; no repeat inspection, provisioning, recovery
work, diagnostic endpoint, code change or diagnostic restart is required.

## Stage D3 offline conclusion and selected hosting

**Stage D3 offline review is complete.** The user clarified the Phase 0/Phase 1
decision: React/Vite on Vercel, existing FastAPI on Render, with a same-origin
Vercel `/api/*` reverse proxy. The rewrite removes `/api` before forwarding to the
existing root FastAPI routes. For example, browser `/api/auth/login` becomes
Render `/auth/login`. The browser must use relative `/api/` URLs, not call Render
directly. `/app/` is no longer the assumed frontend deployment path.

The production Vercel hostname has not been assigned or approved. This is a
**Stage E configuration dependency**, not unfinished D3 infrastructure work or a
blocker to local frontend Phase 2. Phase 2 now implements the local Vite proxy
and Vercel rewrite; loopback forwarding tests pass. The production proxy remains
undeployed and unverified. Do not invent a hostname or claim browser acceptance.

The existing backend security contract is compatible with this architecture:

- Browser-facing HTTPS requests stay on the Vercel origin. Forward the backend's
  Set-Cookie unchanged; with no Domain attribute, the browser stores it for that
  browser-facing host. Preserve `__Host-geopolitics_session`, Secure, HttpOnly,
  SameSite=Lax and `Path=/`, including logout deletion. Do not rewrite Path to
  `/api` or add Domain: that would violate the existing cookie contract.
- Preserve the browser's Vercel Origin header, request Cookie, JSON content type
  and X-CSRF-Token when forwarding. The backend still checks Origin and CSRF;
  server-to-server forwarding does not bypass them. Preserve Idempotency-Key for
  later Stage F. Keep CSRF in memory and use `credentials: include`.
- Preserve auth status codes and `Cache-Control: no-store`; do not cache auth or
  personalized responses. Requests must remain proxy requests rather than
  browser redirects to Render. Browser cookie persistence, session restoration
  and logout through this exact proxy are part of the bounded Stage E acceptance.

No cookie, Origin, CSRF or CORS code change is indicated by the offline review.
Actual proxy behavior remains to be verified when it exists.

Future Stage E values (placeholder only; not executable until replaced and approved):

```text
PHASE4_TRUSTED_ORIGINS=["https://<production-vercel-hostname>"]
PHASE4_AUTH_WRITES_ENABLED=true
PHASE4_GAMEPLAY_WRITES_ENABLED=false
```

Trust only the exact approved browser-facing Vercel HTTPS origin, without `/api`,
another path or a trailing slash. Do not add Render, localhost, wildcard or
preview origins for this production flow. **Until separate approval, keep
PHASE4_TRUSTED_ORIGINS=[] and both protected-write gates false.**

## Smallest Stage E approval scope

After the exact origin is recorded, obtain one approval covering:

- Set `PHASE4_TRUSTED_ORIGINS` to the confirmed one-element JSON array and
  `PHASE4_AUTH_WRITES_ENABLED=true`; keep
  `PHASE4_GAMEPLAY_WRITES_ENABLED=false` throughout.
- Apply those settings in one controlled Render configuration rollout of the
  existing release. This process restart requires explicit approval; it is not a
  separate diagnostic restart. No source deployment or database setup is needed.
- Exercise one designated new test account through the Vercel `/api/` proxy from
  a browser at the approved origin. Scope includes users, sessions, rate-limit
  records and session/user authorization-fence updates, including authenticated
  GETs. No game creation or human/NPC gameplay writes are authorized.
- If a STOP condition occurs, restore both gates to `false` and origins to the
  baseline `[]` in an approved rollback configuration rollout. Preserve records.

Keep credentials, cookies and CSRF tokens private and out of captured evidence.

## Readiness and minimum acceptance

1. Confirm the actual approved Vercel origin, implemented prefix-stripping proxy
   and the three intended settings before the configuration rollout. A public
   `/api/countries` request can establish basic proxy routing without protected
   reads/writes. Verify the configured forwarding contract above; browser auth
   acceptance follows after approval. Use the existing backend release/database.
2. Wait for that rollout's successful application startup. Existing lifespan code
   checks topology, indexes and validators and refuses startup if readiness is
   not `ready` with auth enabled. No new ready log line is required. Confirm the
   new rollout, rather than an older worker, succeeded; `/health` alone is not
   evidence. Do not manually repeat D2 checks.
3. From the approved Vercel HTTPS browser context, run this bounded flow. The
   table names backend paths: prepend `/api` for every browser/client request,
   e.g. `/api/auth/me`. Use `credentials: include` for session requests and keep
   CSRF in memory only. Do not substitute direct Render calls for proxy acceptance.

| Check | Expected result |
| --- | --- |
| Anonymous `GET /auth/me` | `401 authentication_required` |
| One `POST /auth/register` with a new designated username and policy-compliant private password | `201`; registration does not log in |
| One login with an incorrect password | `401 invalid_credentials` |
| Correct `POST /auth/login` | `200`; browser accepts the Secure, HttpOnly, SameSite=Lax, Path=/, host-only session cookie |
| `GET /auth/me`, `GET /auth/csrf`, `GET /me/games` | `200`; correct account, in-memory CSRF, empty own-games list for the new account |
| Browser reload, then `GET /auth/me` and `GET /auth/csrf` | Session restored; fresh in-memory CSRF retrieval succeeds |
| `POST /auth/logout` with no CSRF, then an incorrect CSRF value | `403 csrf_rejected` for each; session remains usable |
| One POST to `/auth/register` without Origin, sent by an HTTP client with no credentials | `403 origin_rejected`; no account created |
| `POST /auth/logout` with the correct CSRF | `204`; browser cookie cleared |
| Subsequent `GET /auth/me` | `401 authentication_required` |

4. Reconfirm gameplay remains `false`. Do not issue game mutation requests or
   target historical games during Stage E. Record only settings, rollout identity,
   statuses/error codes and pass/fail results, with no sensitive headers/bodies.
5. Close Stage E after these checks pass. Account-to-account gameplay ownership,
   game creation, human/NPC actions and full-match acceptance belong to separately
   approved Stage F on new owned games.

Existing isolated tests cover expiry and rate limits. Do not shorten production
lifetimes, deliberately exhaust shared IP limits or wait through long expiry
periods for this minimal activation. Any unexpected `429` pauses the procedure;
honor Retry-After without retry loops.

## STOP and rollback

STOP activation on an unresolved/mismatched origin or absent/incorrect proxy,
enabled gameplay gate, failed readiness or startup, rejected/lost browser session,
unexpected auth/database `5xx`, an
unexpected `429`, accepted invalid Origin/CSRF, wrong-account data, or evidence of
an unauthorized gameplay write. Do not weaken cookie/CSRF controls, change roles,
repair database metadata or repeatedly retry failed writes.

Under the separately approved rollback scope, set both gates `false` and restore
origins `[]`, then confirm the rollback rollout succeeds. The closed auth gate
returns `503 authentication_disabled` on Phase 4 POSTs. Gate closure does not
delete accounts or revoke stored sessions; preserve all records and disclose that
limitation before any later reactivation. No database cleanup, restore or code
rollback is part of Stage E.

## Local references

- [Project requirements](../backend/docs/REQUIREMENTS.md).
- [API contract](api-contract.md), sections 8 and 9.
- [Startup enforcement](../backend/app/startup.py).
- [Configuration validation](../backend/app/security/environment.py).
- [Origin/CSRF checks](../backend/app/api/dependencies.py).
- [Authentication routes](../backend/app/api/auth.py).
