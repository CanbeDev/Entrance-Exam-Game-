# Project requirements

The official 2027 Geopolitics assignment brief and marksheet are the main sources.
The marksheet has 14 criteria worth 56 marks. The solo development plan is guidance.
[Game rules](GAME_RULES.md#project-conventions) separates approved conventions from
official rules. Security settings and NPC formulas are project design choices.

## Requirements and evidence

The existing IDs are kept for traceability. Test results are in [Testing](TESTING.md).

| IDs / brief pages | Requirement and evidence |
| --- | --- |
| G01, G03, G04 / 1-2 | Ten distinct countries, chosen human start, nine NPCs, Worldometer populations, full starting soldiers and random first participant. Setup/catalog/population tests. |
| G02 / 1 | Multiple independently resumable games. Owner-scoped services/persistence tests and Phase 3 dashboard/session/resume UI implemented. Automated tests and user-reported core manual offline-fixture acceptance passed; production acceptance remains. |
| G05-G08 / 2-4 | Turns, rounds, skip, one target per turn, reserve one soldier, independent paired dice, ties and continued/stopped attacks. Engine rule tests. |
| G09-G10 / 2-3 | Conquest rewards and legal transfers between owned countries. Reward/transfer tests. |
| G11-G14 / 4 | Reinforcements from round two, elimination, ten-country victory and unrestricted geography. Turn/ownership/full-match tests. |
| G15 / 2, 4-5 | Phase 3 board, battle events/dice/losses and NPC explanations with visible serialized fast-forward implemented. Automated tests and user-reported core manual fixture acceptance passed; real match acceptance remains. |
| G16 / 5 | Backend strategy/controller tests; Phase 3 stepping and plain-text decision/explanation history implemented. Core manual fixture acceptance passed as reported by the user; production presentation remains unverified. |
| G17 / 4 | LLM battle commentary. Not implemented. |
| G18 / 5 | Backend security tests and Phase 3 auth, public viewing and verified-owner-only control UI implemented. Automated tests and user-reported core manual fixture acceptance passed. Live authorization acceptance and production activation remain. |
| T01-T03 / 5 | FastAPI/MongoDB/Render exist; local React/Vite API/proxy and functional interface implemented with user-reported core manual fixture acceptance. Production frontend deployment/origin and browser acceptance remain. |
| S01 / 6 | Amathuba submission: source ZIP, database access, deployed URL, application credentials and instructions. Packaging remains; share credentials privately. |

## Marksheet coverage

Database repositories and disposable tests support criteria 1-3. Models, services
and validation support 4-6. Engine, listing and viewing tests support 7-8.
Phase 3 source and user-reported core manual fixture acceptance support 9-10;
automated Chrome testing was blocked. Account/ownership tests support
11; engine and NPC work support 12. Criterion 13 still needs the mandatory LLM
commentary. Code, tests and the final demonstration provide evidence for 14.
These are evidence links, not predicted marks.

Local database structure evidence: version-aware validators, exact metadata
verification, disposable provisioning safeguards and isolated historical/failure
tests are documented in [MongoDB provisioning](mongo-provisioning.md). Expanded
service/phase/NPC/rollback integration cases and a separately guarded Atlas TEST
harness passed 23 real TEST cases, including rollback; cleanup/evidence limits are
recorded in [Atlas TEST verification](atlas-test-verification.md). Local
[startup wiring](phase4-startup.md) composes services with validated settings and
closed default gates; isolated lifecycle/configuration tests support G18 and
database criteria 1-3. Live startup/Render/browser verification and production
prerequisites remain; these results do not activate production writes.

The remaining work is production browser/gameplay acceptance, LLM commentary,
deployment/protected production activation and submission package. The optional
bonus feature does not replace any mandatory requirement. Passing backend tests
does not activate production writes or establish deployed UI acceptance.

Stage D3 offline review is complete using the user-accepted deployment/role and
passed D2 evidence. The exact Vercel origin is a Stage E configuration dependency,
not a local frontend blocker. The [Stage E procedure](../../docs/STAGE_E_AUTH_ACTIVATION.md)
records cookie/Origin/CSRF proxy requirements, existing startup enforcement,
bounded authentication acceptance and rollback. No deployed proxy or browser
authentication acceptance is claimed; origins remain `[]` and both gates disabled
pending separate authorization. D2 is closed.

Frontend Phase 2 evidence: [API client/proxy notes](../../frontend/README.md),
42 passing local tests, no failures/skips, 40 OpenAPI components verified,
TypeScript checks and Vite build passed. Tests use offline mocks and loopback
servers; no backend/database import or production access occurred. This supplies
local evidence for G02/G15/G16/G18 and criteria 6-8/11, without claiming deployed
authentication, visible gameplay/UI/navigation or AI commentary. At Phase 2,
G17, the playable interface/fast-forward, Stage E/F acceptance and submission
remained unmet.

Frontend Phase 3 now supersedes the Phase 2 UI gap above: see
[implementation report](../../docs/FRONTEND_PHASE3_REPORT.md). Current evidence is
54 passing local tests, TypeScript/build and contract checks. On 2026-10-29, the
user reported successful core manual browser acceptance against the offline
fixture. Automated Chrome testing was blocked because Computer Use could not
confidently determine Chrome's URL to enforce policy; no automated browser pass
is claimed. No production or real backend/database testing occurred during this
frontend acceptance. G17 and Stage E/F/submission remain unmet.

Stage F recovery reliability, local-only evidence (2026-10-30): 105 frontend tests
passed (75 retained plus 30 recovery/UI regressions), TypeScript/Vite build and
40-component contract checks passed. Saved operations retain their original
account and immutable payload through failed retry preparation/reauthentication;
explicit retries verify account/ownership. Tests cover CSRF 401/503/timeout,
same-account recovery, replay identity, optional NPC attempt limits, Pause and
human/completion stopping. See [frontend recovery notes](../../frontend/README.md#saved-request-recovery-and-npc-acceptance-limit).
No production access, recovery or deployment occurred. The existing production
NPC request remains unresolved; its tab must be preserved. Production fast-forward
acceptance remains incomplete, and mandatory G17 LLM commentary remains missing.
