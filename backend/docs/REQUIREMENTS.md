# Official requirements to implementation and evidence checklist

Primary sources: official INF4001N - Entrance Exam - Geopolitics.pdf (2027),
pp.1-6; official INF4001N MarksheetEntranceExam2027.pdf, p.1. Both were reread
for Phase 2. No detailed per-score descriptors are supplied by the marksheet.
Approved conventions are separately listed in phase1-rules.md and phase2-rules.md.
The solo development plan is not an authoritative replacement for these documents.

Status: implemented means backend behavior covered by isolated tests, not proof of
an end-user demonstration or real transactional deployment. Phase 1 live deployment
and Atlas persistence were independently confirmed by the user. Phase 2 has not
been deployed. On 2026-10-20 the user reported all four real disposable-MongoDB
integration cases passed in 23.20 seconds, with no failures. The final review
reran only the isolated suite: 224 passed, 0 failed (1.15 seconds), with one existing
dependency deprecation warning. Production gameplay writes remain disabled.

## Mandatory case-study requirements

| ID / brief | Mandatory behavior | Implementation | Test / demonstration | Status / gap |
|---|---|---|---|---|
| G01 p.1 | Single human against NPCs, ten countries | game_setup.py, player models | test_game_setup.py | Setup implemented; automatic NPC behavior pending |
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
| G15 pp.2,4-5 | Visible countries/soldiers, battles/dice/losses; fast-forward still shows moves | RuntimeGame and factual events expose data | verify_phase2 demo; test_phase2_api.py | UI, animation and fast-forward pending |
| G16 p.5 | NPCs play to win, allocate/transfer/attack/stop; visible justifications | Shared legality engine available | NPC actor tests | Strategy, simulation and rationales pending; intentionally excluded from Phase 2 |
| G17 p.4 | LLM-generated dynamic battle commentary | Factual events available as future input | No LLM integration yet | Unmet; mandatory future work |
| G18 p.5 | Shared public viewing, logged-in owner-only play, visitor signup | Existing GET games; no public writes | test_api.py; test_phase2_api.py | Authentication, signup, owner authorization, spectator UI pending |
| T01 p.5 | Web/mobile application | FastAPI deployed in Phase 1 | User verified Render endpoints | API implemented; playable frontend pending |
| T02 p.5 | NoSQL database | Existing Atlas MongoDB | User independently verified Phase 1 persistence and four Phase 2 real integration cases | Dedicated test target verified by user; production gameplay writes remain disabled |
| T03 p.5 | Server deployment | Existing Render deployment preserved | User confirmed health/countries/games endpoints | Phase 2 not deployed, per instruction |
| S01 p.6 | Source ZIP, reviewer DB access, URL, app credentials, README, Amathuba submission | Final handoff work | Clean-room submission walkthrough required | Pending; never put secrets in Git |

One optional bonus feature is permitted by the brief; it is not a substitute for
any mandatory behavior. No bonus implementation or marks are claimed here.

## All 14 marksheet criteria (0-4 each; 56 total)

| Criterion | Evidence available | Remaining demonstration / rubric gap |
|---|---|---|
| 1 Database layer | Separate repositories and injected data access; existing configuration preserved; user-reported four real integration cases pass | Production write enablement remains separately gated |
| 2 Connection to database | Existing Atlas/Render connection independently confirmed by user | Verify Phase 2 target capabilities before enabling writes |
| 3 Database design | Versioned state/revisions/receipts; real commit, rollback and concurrency cases passed per user report | Production topology/permissions remain separately unverified |
| 4 Coding structure | Models, pure rules, action dispatcher, service, repository separation | Continue standards in future API/UI work |
| 5 Object-oriented concepts | Encapsulated services/repositories, immutable Pydantic models and injected providers | Explain classes/dependencies in final demo/README |
| 6 Data validation, controls and security | Actor/phase validation, immutable input, CAS and duplicate IDs | Real account authorization and broader security tests pending |
| 7 Functionality | Setup and backend turn/combat/conquest loop | End-user playable loop and NPC automation pending |
| 8 Works correctly; lists/search/filter/view | 224 isolated cases, four user-reported real transaction cases, existing game/country reads | Session listing/search/filter/UI pending |
| 9 User interface | API state and factual events only | Game board/battle visualizations/responsive UI pending |
| 10 Ease of navigation | Existing API documentation | Create/resume/play/share navigation pending |
| 11 Security - authentication and authorization | Public writes remain absent | Signup/login, account ownership and visitor restrictions pending |
| 12 Sophistication and complexity | Turn state machine, paired combat, rewards; real transactions verified on disposable target per user report | NPC intelligence and access control pending |
| 13 AI application | Structured factual battle events prepared | Actual generated LLM commentary pending |
| 14 Overall evidence of effort | Rules/contracts/checklist, regression suite and safe local demo | Complete demo, final docs, packaging and submission pending |

Do not infer full marks or completion of a criterion from backend-only coverage.
Update this checklist whenever implementation scope or verification status changes.
