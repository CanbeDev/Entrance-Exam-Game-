# Phase 3: shared explainable NPC policy

## Authority, scope and evidence

The official INF4001N 2027 Geopolitics brief pp.2-5 and 56-mark marksheet p.1
were reread before implementation. The primary NPC requirements are on brief p.5:
evaluate the board, play to win rather than at random, choose attacks/targets/stops,
allocate reinforcements, optionally transfer, and explain every decision. One
shared strategy is explicitly permitted. The battle rules and no-geography rule
remain authoritative. See REQUIREMENTS.md for all mandatory features/rubric gaps.

The user approved this shared heuristic approach and Phase 2 conventions A-H.
Everything under "balanced-v1" below is an implementation convention, not an
official population threshold, combat rule, victory guarantee, or probability.
No authentication, frontend, LLM, public write route, live data operation, credential
change, or production write enablement is included. The human must never be acted
for by the NPC controller. Future authorized orchestration must still enforce the
real account boundary; ActorContext is trusted local input, not authentication.

## Architecture

- models/npc.py: frozen observations, attack evaluations, decisions and submissions.
- engine/npc/evaluation.py: full-board analysis and hypothetical soldier projections.
- engine/npc/strategy.py: one shared phase-aware policy with independent tie-breaking.
- engine/npc/explanations.py: canonical factual text and reproducibility validation.
- services/npc_service.py: prepare/submit and bounded orchestration via GameActionService.
- Existing action engine/dice: sole authority for legality and battle outcomes.
- Existing transaction repository: commits RuntimeGame and the receipt containing
  ActionResult.npc_decision together. No additional game fields/collections needed.

Each decision records all ten countries, all ten participant records (including
eliminated ones), all owned-source/enemy-target pairs, revision/turn context, a
state digest, action, strategy version, tie configuration/use, canonical explanation,
and projected potential when allocating/transferring. No future dice are observed.

## Exact balanced-v1 scoring and risk preferences

For every owned source and enemy target:

```
available = source.soldiers - 1
margin = available - target.soldiers
reward = max(2, target.base_soldier_value // 2)
eliminates = target owner controls exactly one country
wins = actor controls nine countries
income_gain = income_denial = 2   # future per-turn income from that territory
power_bonus = min(12, target owner's total soldiers // 4)
distance = (target owner's order index - current_turn) modulo 10
urgency_bonus = 10 - distance
risk_penalty = 8 * max(0, 1 - margin)

score = 4*margin + 3*reward + 12 + 4*(income_gain + income_denial)
        + 24*eliminates + 80*wins + power_bonus + urgency_bonus
        - risk_penalty - exposure_cost
```

The evaluator also records each opponent's full reinforcement income (twice its
country count), aggregate troops, and scheduled turn distance. Income is a future
opportunity measure, not an award of round-one reinforcements.

Exposure is deliberately conservative heuristic arithmetic:

```
strongest = maximum enemy (soldiers - 1)
projected_source = max(1, source.soldiers - target.soldiers)
source_cost = max(0, strongest - projected_source)
              - max(0, strongest - source.soldiers)
other_threat = maximum enemy (soldiers - 1), excluding this target
exposure_cost = source_cost + max(0, other_threat - reward)
defensive_exposure = sum(max(0, strongest - owned_country.soldiers))
```

The one-for-one attrition projection is NOT the paired-dice distribution, actual
casualties, a prediction, or a replacement for the engine. Empty maxima are zero.
All targets are reachable; geography is absent from evaluation.

A candidate needs available >= 1 and positive score. Ordinary preference is margin
>= 1. Explicit exceptions permit margin >= -1 for elimination, >= -2 for potential
world conquest, or >= 0 when reward >= 4. Thus margin one is not an absolute
restriction. Very poor attacks can still be rejected despite an elimination or
victory opportunity. Among acceptable candidates, rank lexicographically by:

1. potential world conquest;
2. opponent elimination;
3. score.

No capture probability or guaranteed outcome is claimed. Parameters are versioned
policy choices. Changes need documented evidence and a new policy version, while
historical receipt decoding/replay must remain supported.

## Allocation and transfers

Define board potential as the lexicographic tuple:

```
(best acceptable wins flag, best acceptable eliminates flag, its score,
 -defensive_exposure, sum(owned soldiers squared))
```

Use (0,0,0) for the first three entries when no attack is acceptable. The final term
consolidates otherwise equivalent forces; it cannot override earlier priorities.
This is a heuristic/local improvement policy, not globally optimal planning.

Allocation: for each soldier in the pending budget, hypothetically add one to each
owned country, choose maximal potential, and repeat. Submit the entire final
distribution as one Allocate. Budget/ownership validation remains in the engine.
All projected metrics in the explanation are explicitly labelled as projected.
During post_attack, attack potential refers to a future turn; it never permits
another attack in the current turn.

Transfer planning considers every distinct owned source/destination. Candidate
amounts are 1, all soldiers above one, half source soldiers, half the source-minus-
destination difference, and strongest enemy available minus destination soldiers.
It also considers amounts that would bring the destination's combat margin against
each enemy to 1, 0, -1 or -2. Duplicate/illegal amounts are removed. Only strictly
potential-improving candidates qualify; choose the maximal resulting potential.

Every transfer leaves one at source and executes through the existing engine.
For fixed ownership, enemy board and total soldiers, the possible distributions
are finite and potential strictly increases, preventing cycles/oscillation.
After real battle/ownership/reinforcement changes, the policy can legitimately
reposition again. Legal human transfer choices remain unrestricted by this policy.

## Phase behavior and randomness separation

- allocating: complete allocation first.
- deciding: beneficial transfer, otherwise best acceptable attack, otherwise skip.
- attacking: reevaluate full board and locked pair after each exchange; roll if the
  locked candidate remains acceptable, otherwise stop (which ends the turn).
- post_attack: beneficial transfer, otherwise EndTurn; never a second attack.
- human turn/completed game: no NPC decision or automated action.

Stable default tie-breaking sorts IDs, then transfer amount, and chooses first.
SeededTieBreaker accepts an integer and uses a fresh policy-only Random seeded by
its recorded seed identity plus state digest and decision context. Repeated workers
with the same configuration/state reproduce the same result. It selects only among
exactly equal best ranks. It never receives or consumes authoritative battle dice.
All nine NPCs use identical rules; there are no hidden difficulty bonuses.

## Receipts, explanations, retries and compatibility

ActionCommand and RuntimeGame schemas remain unchanged. ActionResult gains optional
npc_decision, absent/None for historical receipts and ordinary human actions.
The old actor/command-only fingerprint bytes remain identical when no evidence is
supplied. For NPC evidence, the fingerprint additionally includes npc_decision_v1.
Changing evidence while reusing a committed action ID causes ActionIdConflict.

Before consuming dice, GameActionService validates evidence against the actual
immutable board and reproduces the recorded supported policy/tie configuration.
This rejects fabricated values, prose, projections, and action claims. Computed
evidence is not published before commit; state, factual events, and decision are
saved in the same existing transaction. Transaction callback retries reuse the
precomputed result; duplicate submissions replay the original committed receipt.

Controller action IDs encode strategy version, turn sequence and expected revision.
Workers must use the same policy/tie configuration. Conflicts yield control; they
do not silently choose/reroll against new state. Reload and prepare anew after a
genuine revision conflict. On an uncertain commit, retain the returned pending
submission and retry controller.submit(pending) unchanged BEFORE starting a new
batch. A pending proposal is not a completed move. Historical schema-2 adaptation,
legacy waiting-record reads, and existing endpoints remain unchanged.

## Bounded orchestration and future presentation

run_until_human defaults to 32 submitted actions, with an explicit caller budget
of 1..256. It stops on human turn, completed game, budget exhaustion, conflict or
persistence error. Budget exhaustion yields processing_limit without changing the
game phase, ending a turn, or forcing a skip. Repeated tied dice therefore yield
safely and can resume. This is an action-count bound, not a wall-clock guarantee.
GameplayWritesDisabled still raises; no fallback repository or automatic enablement
is introduced. No controller is run during FastAPI startup or a public GET request.

NpcBatch.committed includes only successfully acknowledged/replayed action results,
in revision order, each with its explanation and factual events. Future display
and fast-forward must consume the same sequence and vary presentation delay only.
No frontend display, delivery queue, scheduler or commentary is claimed here.

## Safe verification

From backend, no database/network is used by:

```powershell
.\.venv\Scripts\python.exe -m tools.verify_npc
$npcTemp = Join-Path ([IO.Path]::GetTempPath()) ("geopolitics-npc-" + [guid]::NewGuid().ToString("N"))
.\.venv\Scripts\python.exe -m pytest -c pytest.ini tests --ignore=tests/integration -q --basetemp $npcTemp -p no:cacheprovider
```

The demo uses a labelled in-memory scenario and deterministic dice passed ONLY to
the authoritative engine. Its explicit demonstration store is not a production
fallback. It prints acknowledged decisions/events, then yields to the human.

Tests cover full-board metrics, score/risk preferences, all nine actors, seeded
ties, allocation, non-oscillating transfers, reassessment/stopping, human/NPC battle
equivalence, bounded tied battles, final victory, evidence validation, historical
fingerprints/receipts, stale submissions, uncertain acknowledgements, transaction
rollback and retry consistency. Phase 1/2 regression tests are retained.

Independent final-review verification (2026-10-20): 304 isolated cases passed,
zero failed in 2.32 seconds, including all 224 Phase 1/2 regressions and 80 NPC
cases. One existing Starlette/HTTPX TestClient deprecation warning remains. The
project virtual environment and a unique Windows pytest temporary directory were
used, with the integration directory explicitly excluded. Dependency and Git
whitespace checks passed. The user also independently confirmed the no-database
demo: strategic attack, conquest, legal transfer, factual explanations and return
to the human turn after four committed actions.

Real-server verification reported by the user (2026-10-20): all eight disposable
MongoDB cases passed in 38.58 seconds, with no failures and only the existing
deprecation warning. This includes four unchanged Phase 2 cases and four added
Phase 3 cases in tests/integration/test_phase2_mongo.py. The new coverage is:
(1) actual NPC casualties plus atomic
evidence/events persistence, duplicate replay and fresh-service recovery; (2) rollback
after observing the real in-transaction state update; (3-4) historical receipt/hash
compatibility parameterized for human and NPC actors. Replay guards reject strategy,
dice or clock work. No new collections or production schema changes were made.

The real run is user-reported evidence, not an independent rerun during this
review. No MongoDB connection was made. Exact server versions, production topology/
permissions and leftover databases were not independently inspected. A successful
run without teardown errors is consistent with cleanup, not an inventory of any
earlier failed runs. The earlier local preparation run passed 304 isolated tests
and skipped all eight real cases with one existing warning and no failures.
See phase2-verification.md for the exact case inventory and disposable safeguards.
Future real runs require separate execution approval and the dedicated disposable
environment. Production gameplay writes remain disabled; the disposable run does
not authorize production enablement or deployment.

Outstanding mandatory project work: authenticated account control, strategic NPC
decisions displayed in a frontend, battle visualization, visible fast-forward,
LLM battle commentary, navigation/session UI and final submission materials.
No claim is made that this policy is unbeatable, globally optimal, or sufficient
on its own for every marksheet criterion.
