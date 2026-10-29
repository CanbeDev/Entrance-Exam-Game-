# Frontend Phase 3: functional frontend

Prepared 2026-10-29. Functional interface implemented locally. All 54 automated
tests, TypeScript checks and the build passed. The user subsequently reported
successful core manual browser acceptance against the offline fixture.
Automated Chrome testing remained blocked; no automated browser pass is claimed.
Phase 4 and production deployment/activation require separate authorization.

## Implemented flows

- Registration -> login -> memory-only CSRF initialization; existing-account
  login, reload/session restoration and logout. Password form fields reset on
  submission; no credentials/tokens are persisted or logged.
- My Games: server search, status filter, cursor pagination and resume links.
  Catalog-based country choice and creation use a frozen prepared request/key.
- Shared `/games/{id}` pages display the ten-country table, ownership, soldiers,
  round/turn/phase/status, locked battle and winner. Polling updates public reads
  without advancing gameplay. Unsupported historical states are read-only.
- Human controls send the existing allocate, start_attack, roll, stop_attack,
  transfer, skip and end_turn contracts. Controls match backend phases and use
  returned budgets/counts; no dice, casualties, ownership, reinforcement or NPC
  strategy is computed in React. Basic form bounds improve input validation.
- Owner-only NPC stepping and a serialized 650 ms fast-forward loop display
  returned moves/explanations and pause at a human turn/completion or on errors.
  Pause prevents another NPC request after the current in-flight action finishes.
- Latest server results and paginated committed history show attack/dice/loss
  events and plain-text NPC explanations. Receipts are deduplicated by revision.
- Controls require current authentication plus verified owner-list membership,
  independently of dashboard filters/pagination. Public human actor IDs never
  establish account ownership. Backend authorization remains authoritative.
- Uncertain writes retain the original prepared request and block new mutations;
  explicit retry preserves IDs, payloads and expected revision. 409 adopts the
  Phase 2 refetched state; 429 pauses requests; 401 clears access and 403 removes
  owner controls. Fast-forward stops on errors. No blind mutation replay.

## Files created/modified in Phase 3

Modified `frontend/src/App.tsx`. Added `frontend/src/base.css`,
`frontend/src/vite-env.d.ts`, `frontend/src/game/controller.ts`,
`frontend/src/game/view.ts`, and components `AuthForm.tsx`, `Dashboard.tsx`,
`GameBoard.tsx`, `Controls.tsx`, `History.tsx` under `frontend/src/components/`.
The stylesheet provides basic readability/layout only, not Phase 4 design.

Added `frontend/tests/controller.test.mjs`, `frontend/tests/mock-api.mjs` and
`frontend/tests/serve-smoke.mjs`. Updated `frontend/README.md`,
`docs/PROJECT_HANDOFF.md` and `backend/docs/REQUIREMENTS.md`; added this report.
The accepted Phase 2 API layer, package manifests/lockfile, proxy configuration,
backend runtime/tests and AGENTS.md were preserved. No dependencies were added
or installed. No commit/push was made.

## Final verification

| Check | Result |
| --- | --- |
| `npm.cmd test` | 54 passed, 0 failed, 0 skipped, 0 cancelled |
| Existing Phase 2 tests | All 42 retained and passing |
| New controller tests | 12 passed |
| `npm.cmd run build` | TypeScript `tsc --noEmit` and Vite build passed |
| `npm.cmd run check:contracts` | 40 OpenAPI components match the checked-in schema |
| Automated Chrome smoke journey | BLOCKED before interaction; not passed or counted as an automated skip |
| Core manual browser acceptance | PASSED against the offline fixture, user-reported on 2026-10-29 |
| Real backend/MongoDB/production tests | Not run; no backend import/startup or production call |

The scripted tests demonstrate registration, creation, attack/roll, transfer,
NPC action/explanation and fast-forward, reinforcement allocation, reload/resume,
logout, filtering/paging and public/non-owner restrictions. They also cover
uncertain retry identity, 409, 401/403/503, 429 cooldowns, pause and stable owner
forms during polling. They test controller/API integration with canned state;
they do not prove game rules, strategy, transactions or real browser behavior.

## Browser acceptance and remaining mandatory gaps

The local fixture server started successfully and was stopped after testing.
Computer Use ended with: it could not determine the current browser URL on
Windows with enough confidence to enforce policy. No alternate UI-control route
was attempted. The [manual smoke procedure](../frontend/README.md) is ready for
the same loopback fixture, with no dependency installation required. The user later
reported successful core manual acceptance against that fixture. This does not
change the historical automated Chrome blocker or establish production acceptance.

Both official PDFs were read before implementation (brief pages 1-6 and full
2027 marksheet). Mandatory visibility, fast-forward, public viewing and logged-in
play informed this UI. Approved A-H conventions in GAME_RULES.md continue to
control phase behavior. The PDFs are requirements, not authorization to operate
services or submit/share credentials.

Core manual Phase 3 acceptance passed against the offline fixture, as reported
by the user. Stage E/F still require
the approved frontend origin, separate deployment/activation approvals, actual
Vercel HTTPS cookie/Origin/CSRF checks and real owned-game acceptance. Dynamic
GroqCloud commentary (G17), final visual design and submission packaging remain.
Rubric UI/navigation/functionality/security now have source and local automated
evidence; no awarded marks or completed deployed/browser evidence is claimed.

No production service/database access, write, restart, deployment, environment
change, credential/role change or write-gate activation occurred. Origins stay
`[]`; auth/gameplay gates remain disabled. D2 is closed and D3 is not reopened.
