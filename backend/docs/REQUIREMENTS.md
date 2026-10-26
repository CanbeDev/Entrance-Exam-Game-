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
| G02 / 1 | Multiple independently resumable games. Owner-scoped services and persistence tests; session UI remains. |
| G05-G08 / 2-4 | Turns, rounds, skip, one target per turn, reserve one soldier, independent paired dice, ties and continued/stopped attacks. Engine rule tests. |
| G09-G10 / 2-3 | Conquest rewards and legal transfers between owned countries. Reward/transfer tests. |
| G11-G14 / 4 | Reinforcements from round two, elimination, ten-country victory and unrestricted geography. Turn/ownership/full-match tests. |
| G15 / 2, 4-5 | Show every country and soldier count, live battles, moves and NPC explanations during fast-forward. Events exist; display remains. |
| G16 / 5 | NPC board evaluation, attacks/stops, allocation, optional transfers and explanations. Strategy/controller tests; visible presentation remains. |
| G17 / 4 | LLM battle commentary. Not implemented. |
| G18 / 5 | Shared read access, signup and logged-in owner-only play. Backend security tests; production activation and UI remain. |
| T01-T03 / 5 | Web/mobile application, NoSQL and hosting. FastAPI/MongoDB/Render exist; playable frontend remains. |
| S01 / 6 | Amathuba submission: source ZIP, database access, deployed URL, application credentials and instructions. Packaging remains; share credentials privately. |

## Marksheet coverage

Database repositories and disposable tests support criteria 1-3. Models, services
and validation support 4-6. Engine, listing and viewing tests support 7-8, but the
playable interface and navigation for 9-10 remain. Account/ownership tests support
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

The remaining work is the frontend, visible battles and fast-forward, LLM
commentary, protected production activation and submission package. The optional
bonus feature does not replace any mandatory requirement. Passing backend tests
does not activate production writes or demonstrate the missing UI.
