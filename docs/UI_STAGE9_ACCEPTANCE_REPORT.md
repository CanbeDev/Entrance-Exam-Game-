# Stage 9 - acceptance report

Date: 2026-11-03, Africa/Johannesburg.
Verdict: **READY FOR HUMAN GAMEPLAY ACCEPTANCE**. This is not release approval.

## Scope, baseline and authority

The reviewer authorized hybrid acceptance: Codex runs isolated checks and prepares
evidence; the human plays the actual connected campaigns. This replaces the prior
proposal to provision a new disposable browser-test database. No new database is
needed for Codex's work, and no historical database approval is reused.

Branch: `ui-redesign`; HEAD: `9ddb09ea9121ffa6de328f7b0f4863bfa69ff98e`.
The initial working tree already contained the uncommitted UI redesign, Super QA
work, assets/reports, local validators/handoff and unrelated Stage E document edits.
The index was empty. A 521-file SHA-256 baseline, excluding `output/` and `tmp/`,
was saved before Stage 9 edits in `output/stage9/baseline.json`.

**PASS - official references inspected.** Exact-name Downloads PDFs were rendered
with Windows PDF APIs because Poppler/Python PDF packages were unavailable. All six
brief pages and the single 2027 marksheet page were opened and read. The marksheet
has 14 criteria scored 0-4, total 56; no marks are claimed. Gameplay is mandatory;
Graphics and Animations is the selected bonus, not a replacement for commentary.
Official page renders are local evidence in `output/stage9/brief-1.png` through
`brief-6.png` and `marksheet-1.png`.

The current types/OpenAPI/controller, backend rule conventions, Stage 8/8.5 reports,
Super QA sound/browser reports, human audio checklist, NPC/recovery/commentary
tests and deployment documentation were inspected. No separate existing Stage 9
manual guide was found in the repository; the new checklist follows the reviewer's
22 required steps and actual UI labels. Historical results remain historical.

## A. Automated gameplay verification

**PASS - isolated coverage.** The complete backend suite passes 929 cases, with
44 real-database cases deliberately skipped. No mandatory logic rule in the
reviewer's enumerated list was found without automated coverage. That statement
does not establish connected browser/persistence acceptance or statistical
randomness quality.

| Official requirement | Automated evidence | Boundary / approved convention |
| --- | --- | --- |
| Ten countries, one human/nine NPCs, random rivals/first player | `test_game_setup.py` setup invariants across seeds, injected reproducibility and default randomness | Saved shuffled full turn order and 195-country eligibility are approved project conventions |
| Population-based initial soldiers 1-9 | `test_population_rules.py` all boundaries/extremes/invalid inputs; setup checks | Actual country snapshot, not the mock catalog, supplies production populations |
| Any enemy may be attacked regardless of distance | `test_phase2_rules.py` start/lock/transfer/action validation; shared engine | No adjacency restriction or invented phase |
| Attacker leaves one; min(source minus one, defender) dice per side | `test_official_dice_counts`, including eight dice each; invalid battle/dice cases | No conventional Risk cap, sorting or policy-controlled dice |
| Pair by original index; casualties/ties | `test_official_pairing_example_and_ties`, loss application and dice validation | Ties lose no soldiers; bad actions leave input unchanged |
| One attack/skip; continued rolls or stop | Locked-battle/invalid-action/forced-failure/turn tests in `test_phase2_rules.py` | Start and roll are separate actions; voluntary stop ends turn |
| Conquest, ownership and reward | Reward boundaries, conquest/endgame, recapture tests | Approved immutable base formula max(2, base // 2), placed immediately in captured country |
| Optional transfer outside battle | Transfer conservation/leave-one/invalid-action tests | Positive explicit transfer, then existing End turn; no conquest confirmation |
| Round-two onward reinforcement | Formula, full/split allocation and round boundary tests | Submit full pool; original saved-order boundary retained when eliminated actors are skipped |
| Elimination and all-ten victory | Eliminated-slot, final-conquest, NPC-after-human-elimination tests | Human elimination can precede whole-game completion |
| Complete progression and conservation | `test_phase2_match.py` reaches human victory with nine conquests, reinforcement and receipt/write/revision checks | Scripted in-memory scenario with fixed dice, not a live stochastic match |
| Explainable strategic NPCs | Strategy/evaluation/service/controller/persistence tests | Balanced-v1 is a project policy; tests do not prove globally optimal play |
| Invalid actions never mutate | Rules/service/repository validation and rollback doubles | Mock rollback is not proof of MongoDB transactions |

Mandatory visible battles, live narration, full connected match, public watching,
NoSQL deployment and submission evidence still require the relevant human/live
evidence. No production/database validation was reopened.

## B. NPC Fast-forward/Pause and recovery

**PASS - isolated tests and source inspection.** One controller and per-game API
serialization preserve pending identity, expected revision and account ownership.
Fast-forward awaits each Step, then schedules the next after 650 ms. Pause clears
the schedule and invalidates its generation; it does not undo an in-flight commit.
Human turn, completion, error, unresolved operation and configured cap stop playback.

Existing regression suites cover CSRF preparation failure, same-account login,
wrong-account denial, exact retry payload/identity, attempt accounting, lost response
confirmation, receipt matching, stale reads and history ordering. Relevant sources:
`frontend/tests/controller.test.mjs`, `recovery.test.mjs`, `confirmation.test.mjs`,
`polling.test.mjs` and `api.test.mjs`; backend `test_npc_controller.py`,
`test_npc_service.py`, `test_npc_persistence.py` and phase-two/four suites.

Two new cases in `frontend/tests/recovery.test.mjs` verify:

1. Rapid repeated Step clicks plus Fast-forward cannot dispatch another mutation
   while the original Step response is held. The same pending object remains;
   exactly one attempt/receipt commits.
2. Repeated Pause while Fast-forward's POST is held preserves pending state,
   accepts settlement and schedules no next request. Explicit resume submits
   expected revision 5 after the original revision 4 operation, exactly once;
   the shared two-attempt cap stops it with committed revisions 5 and 6.

The targeted recovery suite passes **31 cases**. The complete frontend suite
passes **351**, including those two new cases. No assertions were removed or weakened.

**PASS - refresh safety.** Ordinary Check game status/navigation/logout are locked
while an operation is unresolved. Read-only exact confirmation remains available
for saved NPC requests; newer board revision alone is insufficient. Pending lives
in page memory, so browser reload is not a recovery method. Same-account login
and receipt checks never auto-replay. Successful confirmation leaves Fast-forward
paused. Explicit identical retry remains separately controlled.

**PASS - NPC elimination coverage.** Backend tests skip eliminated slots across
the saved round boundary and permit NPC victory after human elimination. The UI
retains owner NPC continuation. **NOT TESTED - current connected run:** actual
Step/fast/Pause/resume, eliminated-player continuation and transport recovery await
human results. Earlier transport interruption is not claimed resolved by local tests.

## C. Manual connected-game results

**NOT TESTED - Stage 9 human campaign.** No new connected-game evidence has been
supplied for this release. The reviewer will operate the existing authorized
account/environment; Codex will not create campaigns or mutate real games.

| Evidence item | Current result |
| --- | --- |
| Tested frontend build/environment and game ID | NOT TESTED - awaiting human record |
| Full match through round two to completed victory/defeat | NOT TESTED |
| Current release NPC Step/Fast-forward/in-flight Pause/resume | NOT TESTED |
| Reopen/persistence and anonymous spectator | NOT TESTED |
| Current release Flag Poster and result perspective | NOT TESTED |
| Naturally encountered interruption/reconciliation | NOT TESTED; do not induce a production failure |

Prior accepted Stage E/F auth/gameplay observations and reported production Groq
success at baseline `9ddb09e` remain evidence for those earlier builds. They do
not certify the uncommitted UI/audio release or close current full-match acceptance.

Use [STAGE9_HUMAN_GAMEPLAY_ACCEPTANCE.md](STAGE9_HUMAN_GAMEPLAY_ACCEPTANCE.md).
All 22 manual rows and individual audio event rows start NOT TESTED. Update this
report from sanitized observations/receipts rather than restarting passed tests.

## D. Real-game sound and commentary

**PASS - human-reported panel playback only.** The reviewer reports every configured
clip audible through the developer panel. **PASS - offline wiring:** SoundLedger
requires eligible new committed receipts and settled ownership/session state;
baseline/duplicate/historical/uncertain evidence cannot produce success cues.
The sound suites cover volume/mute, persistence/activation, cooldown, stale playback,
new victory versus defeat and no old-result replay. Country selection and accepted
Fast-forward/Pause have separate local cues. Ordinary fixture action callbacks are
intentionally inert; no fixtures were changed to manufacture action sounds.

**NOT TESTED - real gameplay audio.** Selection, attack, dice/loss, conquest,
transfer, NPC, fast/Pause, both result perspectives and their mute/refresh/recovery
behavior await per-event human observations. Optional aftermath and cooldown can
omit some cues; audio never holds gameplay or determines authoritative results.

**PASS - mocked commentary integration.** Full backend testing includes provider,
service, durable-claim repository, API and startup suites. Frontend tests cover
owner-default automatic generation for new human/NPC exchanges, independent cursor
through Fast-forward, no duplicate generation, opt-out/no backfill, exact receipt
identity, saved display, spectator read-only checks, uncertainty and fallbacks.
Hanging narration cannot serialize gameplay/Pause or change dice/ownership.

**NOT TESTED - current real-provider integration.** No Groq call/credit was used.
A deterministic fallback is successful resilience, not proof of provider narration.
Automatic generation and display are distinct: expand the corresponding Chronicle
entry; pending/uncertain narration may need the existing safe saved-status check.
Do not reset existing receipts/rate counters or regenerate historical fallbacks.

**HUMAN REVIEW REQUIRED:** audio distribution rights and any remaining perceived
balance/timing concerns. Panel audibility does not resolve licensing.

## E. Security and persistence

**PASS - isolated tests.** Authentication/session restoration/expiry/logout,
CSRF/Origin, ownership, wrong-account denial, anonymous/spectator restrictions,
invalid requests, idempotency/receipt replay, serialization and saved-state recovery
are covered by phase-four API/auth/service/repository/startup tests and frontend
API/controller/recovery tests. Provider access is backend-only.

**NOT TESTED - new real persistence/transactions.** All 44 real integration cases
skipped with no opt-in. No `backend/test_database.py` or legacy persistence import
was executed. In-memory tests do not establish live transaction safety. Stage D2
remains closed; no index/validator/provisioning, backup or activation investigation.
The human checks persistence by settled refresh/reopening in the authorized game.

## F. UI and release-readiness checks

**PASS - offline output inspection.** Production `index.html` enters main/App.
No development preview import exists there. The current production JS hash matches
the reviewed Super QA bundle; the prior 55-file import-graph exclusion remains
applicable because application source is unchanged. Dist has one HTML entry and
none of the distinctive fixture, sound-test, acceptance-limit or fixture-account
strings. All 19 originals and 18 prepared audio files appear byte-identically in
dist. Contract/data tests cover canonical atlas, flags and country reference.

**PASS - bounded secret review.** No Groq/OpenAI-like key, credential-bearing Mongo
URI or private-key block was found in built HTML/JS/CSS. No credential file was
opened; no secrets were printed. Pattern checks cannot prove absence of every
possible secret format. Evidence: `output/stage9/release-output-review.json`.

**PASS - visual evidence reused.** Super QA's completed direct-Chrome CDP run has
726 assertions, 198 fixture/viewport cases and 15 actually inspected screenshots
at 1440 x 900, 768 x 1024 and 375 x 812. No new browser run was necessary for test/
documentation-only changes. These are offline layouts, not connected-game proof
or a new exact-font/physical-device certification. See
[Super QA report](UI_AUDIO_AUTOMATED_QA_REPORT.md).

**PASS - documentation corrections.** Root and frontend README prose now reflects
the implemented UI/audio/commentary, current test counts, hidden acceptance tools,
approved Vercel origin and already-reported production activation. Historical Phase
3 browser limitation is retained. No disclosure, required document or local-only
file was removed. AI narration is disclosed in documentation while gameplay uses
the approved Commentary presentation.

**PASS - deployment source review only.** Vercel root `frontend`, Vite `dist` output,
same-origin `/api` rewrite to Render with prefix removed, exact-origin/session/CSRF
contracts and loopback-only development proxy remain unchanged. No setting or live
host was checked or changed. Current live build/configuration remains a human
record, not an inference from local files.

### Release checklist - no deployment authorized

- [ ] HUMAN REVIEW REQUIRED: connect the tested build/environment to the filled
  manual checklist; close critical gameplay/recovery/persistence failures first.
- [ ] HUMAN REVIEW REQUIRED: complete one actual match, round-two allocation,
  NPC fast/Pause and current audio/commentary evidence. Unencountered opposite
  outcome/rare branches must remain explicitly NOT TESTED.
- [ ] HUMAN REVIEW REQUIRED: confirm audio distribution rights and asset notices.
- [ ] HUMAN REVIEW REQUIRED: supply a source ZIP excluding secrets, dependencies,
  private/local credentials and disposable evidence not intended for submission.
  No archive was built or Git operation performed here.
- [ ] HUMAN REVIEW REQUIRED: confirm deployed URL, examiner application/database
  access by the official private method, current README and required AI-use
  disclosures. Never place passwords in public source/docs.
- [ ] HUMAN REVIEW REQUIRED: final human acceptance, separate Git/release/deployment
  authorization, and submission to the official Amathuba assignment folder.

Graphics & Animations evidence exists in `docs/UCT_BONUS_GRAPHICS_ANIMATIONS.md`.
Official marksheet areas include database/connection/design, structure/OOP,
validation/security, functionality, lists/search/filter/viewing, UI/navigation,
auth/access control, battle/AI complexity, AI application and effort. Local tests
support assessment; no row or bonus is declared earned. Deadline supplied by the
human: Friday, 6 November 2026, 23:00 South African time.

## G. Outstanding defects and risks

No demonstrated critical application defect or failing automated check was found.
No application/engine/controller/API repair was required.

Release remains gated by human connected-match evidence, correct tested build,
current real audio/provider observations, rights/access/submission preparation and
explicit approval. The old underlying transport interruption is not explained by
test success. Any recurrence requires sanitized request duration/status and exact
receipt evidence before proposing protected-code changes.

Nonblocking limitations: existing >500 kB JavaScript warning, existing Starlette/
httpx deprecation warning, preview favicon 404s in reused Super QA evidence and
intentional sound priority/cooldown. No speculative timeout changes, normalization,
bundle redesign, analytics, military facts or new gameplay feature was introduced.

## H. Exact commands and results

From `frontend/`, after the last test edit:

```powershell
npm.cmd test
npm.cmd run typecheck
npm.cmd run check:contracts
npm.cmd run build
node scripts/build-map-data.mjs --check
node scripts/build-country-reference.mjs --check
node scripts/prepare-sound-assets.mjs --check
```

| Result | Check | Actual count/result |
| --- | --- | --- |
| PASS | Full frontend | 351 passed; 0 failed/skipped/cancelled/todo |
| PASS | Targeted recovery | 31 passed; 0 failed/skipped/cancelled |
| PASS | TypeScript | Exit 0 |
| PASS | OpenAPI drift | 43 components |
| PASS | Production build | 65 modules; JS 610.92 kB / 184.75 kB gzip, CSS 50.57 kB |
| PASS | Map drift | 195 countries, 188 geometry/seven fallbacks, 470 paths/221 groups |
| PASS | Country reference drift | 195 countries, 181 available capitals |
| PASS | Sound drift | 18 portable copies/hashes, originals preserved |
| PASS | Full isolated backend | 929 passed, 44 skipped, 0 failed; one existing warning |
| PASS | Whitespace/source preservation | `git diff --check`; final baseline comparison |

Backend command from `backend/` used the fresh validated unique path generated
with this exact pattern (no real-integration flags):

```powershell
$stage9TempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$stage9Temp = [IO.Path]::GetFullPath((Join-Path $stage9TempRoot ('geo-stage9-' + [guid]::NewGuid().ToString('N'))))
if (-not $stage9Temp.StartsWith($stage9TempRoot, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $stage9Temp)) { throw 'Unsafe test temporary path' }
.venv/Scripts/python.exe -B -m pytest -c pytest.ini tests/ --basetemp $stage9Temp -p no:cacheprovider -q
```

Logs and machine checks: `output/stage9/`. All 44 integration skips explicitly
require dedicated disposable/provisioning/startup opt-ins; none was supplied.
The full backend includes the 172 mocked commentary cases previously run alone;
929 and 172 are not additive totals. Initial 349 frontend results preceded the
two new tests and were superseded by the final 351 run.

## I. Final readiness verdict

Exact Stage 9 changes:

- `frontend/tests/recovery.test.mjs`: two bounded NPC click/Pause/resume regressions.
- `README.md` and `frontend/README.md`: current release-facing documentation only.
- New `docs/STAGE9_HUMAN_GAMEPLAY_ACCEPTANCE.md` and this report.
- Local verification artifacts under `output/stage9/`.

No existing application code, protected backend/API/controller, sound service,
assets, hosting/env configuration, pending browser tab or unrelated work changed.
Final baseline comparison confirms 518 of 521 existing files unchanged, exactly
the three intended existing-file edits above, two new reports and zero removals.
Evidence: `output/stage9/final-verification.json`; the index remains empty.
No staging, commit, push, merge, branch switch, deployment, production API call,
database connection/write or real Groq request occurred. No dependency installed.

The [human checklist](STAGE9_HUMAN_GAMEPLAY_ACCEPTANCE.md) is ready. Preserve this
report and append reviewed connected evidence as it arrives. Do not declare
release-ready or deploy until the human results and separate approval are received.

**READY FOR HUMAN GAMEPLAY ACCEPTANCE**

## Final technical release verification - 2026-11-03

The preceding Stage 9 counts are preserved historical evidence. The final public
suite now contains **358 passing tests** (zero failed/skipped/cancelled), including
seven bounded checksum/manifest regressions. Original-versus-prepared assertions
remain in the explicit private profile, which passes one inventory/byte-equality
test plus preparation consistency when all 19 sources are supplied. Missing private
sources fail that profile's prerequisite; public verification does not pretend
to prove original equality.

An isolated LF Git-content candidate, with a separate byte-verified dependency
copy and no originals, passes the public suite, TypeScript, 43 contracts,
map/reference drift, 18 runtime hashes and production build. Canonical CRLF text
checksums preserve existing generated identifiers without modifying API types,
country facts or map geometry. Original/prepared MP3s and gameplay/security code
are unchanged. The frontend README's extra final blank line was removed while
retaining its ElevenLabs credit.

The owner explicitly accepts the non-commercial ElevenLabs Free-plan packaging
decision (18 prepared public clips, 19 originals local). This is human risk
acceptance, not independently verified redistribution permission. No repeated
licensing decision or new provider/account action is required for technical work.

Current exact package, commands, hashes, timeout investigation and remaining
hosting confirmations are in the local-only release audit. No backend test rerun
or live acceptance is implied: 929 backend passes/44 skips remain the earlier
isolated result. Connected full-match, current game audio/commentary/persistence,
Vercel/Render dashboard values, rollback target and separate Git/deployment
authorization still require human evidence/action. The technical package is
prepared for that controlled rollout; this report does not authorize it.
