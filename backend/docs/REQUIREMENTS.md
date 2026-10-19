# Official requirements to implementation and evidence checklist

Primary sources: official INF4001N - Entrance Exam - Geopolitics.pdf (2027),
pp.1-6; official INF4001N MarksheetEntranceExam2027.pdf, p.1. Both were reread
for Phases 2 and 3. No detailed per-score descriptors are supplied by the marksheet.
Approved conventions are separately listed in phase1-rules.md, phase2-rules.md and
phase3-npc-rules.md (including the precise balanced-v1 scoring/risk rules).
The solo development plan is not an authoritative replacement for these documents.

Status: implemented means backend behavior covered by isolated tests, not proof of
an end-user demonstration or real transactional deployment. Phase 1 live deployment
and Atlas persistence were independently confirmed by the user. The user also
confirmed Phase 2 deployment before Phase 3 began. The earlier Phase 2 verification
record contains 224 isolated passes and the user's report of four real disposable
MongoDB cases passing in 23.20 seconds. Phase 3 remains undeployed. Existing public
endpoints and disabled-by-default gameplay writes are preserved.

Phase 3 final review (2026-10-20): independently reran 304 isolated tests, all
passing in 2.32 seconds (including all 224 prior regressions), with one existing
Starlette/HTTPX deprecation warning. The project virtual environment and a unique
Windows pytest temporary directory were used. The integration directory was
excluded; no MongoDB connection or operation occurred during this review. The user
independently confirmed the no-database NPC demo and return to the human after four
committed actions.

Real Phase 3 verification reported by the user (2026-10-20): all eight opt-in
MongoDB cases passed in 38.58 seconds, zero failures, with only the existing
deprecation warning. These are four unchanged Phase 2 cases, NPC commit/replay/
fresh-service, NPC rollback, and historical receipt compatibility parameterized
for human/NPC. This is user-reported disposable-target execution, not an
independently rerun database test. No new collections or production schema changes
were required. Earlier local test-addition verification passed 304 isolated tests
and skipped all eight real cases. Production transaction prerequisites and any
leftover-database inventory remain independently unverified; production write
enablement, future real tests and deployment require separate approval.

## Mandatory case-study requirements

| ID / brief | Mandatory behavior | Implementation | Test / demonstration | Status / gap |
|---|---|---|---|---|
| G01 p.1 | Single human against NPCs, ten countries | game_setup.py, player models, npc_service.py | test_game_setup.py; test_full_npc_sequence_yields_to_human_without_acting_for_them | Setup and bounded local NPC orchestration implemented; authorized UI integration pending |
| G02 p.1 | Multiple independent saved games | game_service.py, game_repository.py | test_separate_games_do_not_share_state | Persistence implemented; session list/resume UI pending |
| G03 pp.1-2 | Chosen country, nine random unique others; population table | country_catalog.py, population_rules.py | test_country_catalog.py, test_population_rules.py | Implemented; approved eligibility convention documented |
| G04 p.2 | Full starting soldiers, random first player | game_setup.py, saved turn_order | test_setup_invariants | Implemented; full-order shuffle is approved convention |
| G05 pp.2,4 | Turns, skip, rounds | turns.py, actions.py | test_round_boundary_and_allocation; test_eliminated_slots_skip_across_original_boundary | Implemented; eliminated-slot convention documented |
| G06 pp.2-3 | One attack per turn; attacker reserves one | battle.py, actions.py | test_official_dice_counts; test_conquest_keeps_survivors_rewards_capture_and_eliminates | Implemented |
| G07 pp.2-3 | Independent 1..6 dice, index pairing, casualties and ties | battle.py | test_official_pairing_example_and_ties; test_default_dice_range | Implemented; injected deterministic test dice |
| G08 pp.2-4 | Continue, stop, forced failure; no territory forfeit | actions.py | test_start_then_multiple_exchanges_then_stop; test_source_reduced_to_one_keeps_territory | Implemented |
| G09 p.3 | Conquest, floored bonus, optional movement, next-turn attacks | battle.py, actions.py | test_rewards; test_conquest_keeps_survivors_rewards_capture_and_eliminates | Implemented under approved A-D conventions |
| G10 pp.2-3 | Legal transfers outside battle, retain one | transfers.py, actions.py | test_transfer_conserves_and_does_not_advance; test_locked_battle_rejects_other_actions | Implemented |
| G11 p.4 | Round-2 onward 2 soldiers per controlled country; owner allocation | reinforcements.py, turns.py | test_reinforcement_formula; test_pending_reinforcement_validation | Implemented; complete allocation convention documented |
| G12 p.4 | Elimination, no future rewards/turns | runtime ownership, turns.py | test_eliminated_slots_skip_across_original_boundary; test_final_conquest_completes_immediately | Implemented |
| G13 p.4 | Control all ten wins | actions.py, RuntimeGame | test_final_conquest_completes_immediately; test_service_complete_match | Implemented, immediate finish convention |
| G14 p.4 | Attack irrespective of geography | actions.py has no adjacency restriction | combat target selection tests | Backend implemented |
| G15 pp.2,4-5 | Visible countries/soldiers, battles/dice/losses; fast-forward still shows moves | RuntimeGame, factual events and committed NPC decision evidence | verify_npc demo; test_npc_controller.py | Ordered evidence prepared; UI, animation and visible fast-forward pending |
| G16 p.5 | NPCs play to win, allocate/transfer/attack/stop; visible justifications | engine/npc evaluation/strategy/explanations; npc_service.py | test_npc_evaluation.py, test_npc_strategy.py, test_npc_service.py, test_npc_controller.py, test_npc_persistence.py; four added real cases in integration/test_phase2_mongo.py passed per user report | Shared strategic backend and factual explanations implemented; disposable evidence persistence verified per user report; frontend visibility pending |
| G17 p.4 | LLM-generated dynamic battle commentary | Factual events available as future input | No LLM integration yet | Unmet; mandatory future work |
| G18 p.5 | Shared public viewing, logged-in owner-only play, visitor signup | Existing GET games; no public writes | test_api.py; test_phase2_api.py | Authentication, signup, owner authorization, spectator UI pending |
| T01 p.5 | Web/mobile application | FastAPI deployed in Phase 1 | User verified Render endpoints | API implemented; playable frontend pending |
| T02 p.5 | NoSQL database | Existing Atlas MongoDB | User independently verified Phase 1 persistence and all eight Phase 2/3 real integration cases | Dedicated test target verified by user; production gameplay writes remain disabled |
| T03 p.5 | Server deployment | Existing Render deployment preserved | User confirmed Phase 2 deployment and functioning endpoints | Phase 3 not deployed, per instruction |
| S01 p.6 | Source ZIP, reviewer DB access, URL, app credentials, README, Amathuba submission | Final handoff work | Clean-room submission walkthrough required | Pending; never put secrets in Git |

One optional bonus feature is permitted by the brief; it is not a substitute for
any mandatory behavior. No bonus implementation or marks are claimed here.

## All 14 marksheet criteria (0-4 each; 56 total)

| Criterion | Evidence available | Remaining demonstration / rubric gap |
|---|---|---|
| 1 Database layer | Separate repositories and injected data access; existing configuration preserved; user-reported eight real integration cases pass | Production write enablement remains separately gated |
| 2 Connection to database | Existing Atlas/Render connection independently confirmed by user; disposable transaction run passed per user report | Production transaction prerequisites remain separately unverified |
| 3 Database design | Versioned state/revisions/receipts; atomic NPC evidence and historical receipt compatibility covered by the user-reported eight-case real run | Production topology/permissions remain separately unverified |
| 4 Coding structure | Models, pure rules, action dispatcher, service, repository separation | Continue standards in future API/UI work |
| 5 Object-oriented concepts | Encapsulated services/repositories, frozen NPC evaluations, shared strategy and independently injected tie/dice providers | Explain classes/dependencies in final demo/README |
| 6 Data validation, controls and security | Actor/phase validation, immutable input, CAS and duplicate IDs | Real account authorization and broader security tests pending |
| 7 Functionality | Setup, turn/combat/conquest loop and bounded strategic NPC orchestration | End-user playable loop and authorized UI integration pending |
| 8 Works correctly; lists/search/filter/view | 304 independently rerun isolated cases (including 224 prior regressions), eight user-reported real Phase 2/3 transaction cases, existing game/country reads | Session listing/search/filter/UI pending |
| 9 User interface | API state and factual events only | Game board/battle visualizations/responsive UI pending |
| 10 Ease of navigation | Existing API documentation | Create/resume/play/share navigation pending |
| 11 Security - authentication and authorization | Public writes remain absent | Signup/login, account ownership and visitor restrictions pending |
| 12 Sophistication and complexity | Turn state machine, paired combat, rewards, shared board-aware heuristic NPC policy and atomic decision evidence; eight real Phase 2/3 transaction cases passed per user report | Access control and complete frontend demonstration pending |
| 13 AI application | Explainable rule-based NPC decisions; structured factual battle events | Mandatory generated LLM commentary remains pending; strategic heuristics do not replace it |
| 14 Overall evidence of effort | Rules/contracts/checklist, regression suite and safe local demo | Complete demo, final docs, packaging and submission pending |

Do not infer full marks or completion of a criterion from backend-only coverage.
Update this checklist whenever implementation scope or verification status changes.
