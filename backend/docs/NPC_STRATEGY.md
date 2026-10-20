# NPC strategy

All nine NPCs use `balanced-v1`, evaluating the full board before each decision.
Strategic decisions and explanations are required by the brief; these formulas
are approved project choices. They estimate value, not guaranteed battle results.

## Scoring attacks

Every owned source is compared with every enemy target:

```text
available = source.soldiers - 1
margin = available - target.soldiers
reward = max(2, target.base_soldier_value // 2)
eliminates = target owner has one country
wins = acting participant owns nine countries
power_bonus = min(12, target owner's total soldiers // 4)
distance = (target owner's order index - current_turn) modulo 10
risk_penalty = 8 * max(0, 1 - margin)
score = 4*margin + 3*reward + 12 + 4*(2 + 2)
        + 24*eliminates + 80*wins + power_bonus + (10 - distance)
        - risk_penalty - exposure_cost
```

Flags are 0/1. The two income terms represent future reinforcement gain and denial;
they do not award soldiers in round one. Empty maxima below are zero:

```text
strongest = maximum enemy (soldiers - 1)
projected_source = max(1, source.soldiers - target.soldiers)
source_cost = max(0, strongest - projected_source)
              - max(0, strongest - source.soldiers)
other_threat = maximum enemy (soldiers - 1), excluding target
exposure_cost = source_cost + max(0, other_threat - reward)
defensive_exposure = sum(max(0, strongest - c.soldiers)) over owned countries
```

An attack needs available soldiers and a positive score. The normal margin is
at least 1; exceptions allow -1 for elimination, -2 for victory, or 0 for rewards
of at least 4. Rank acceptable attacks by victory, elimination, then score.

## Allocation and transfers

Projected boards are ranked by this tuple, compared left to right:

```text
(best_attack.wins, best_attack.eliminates, best_attack.score,
 -defensive_exposure, sum(owned soldiers squared))
```

The first three values are zero without an acceptable attack. Allocate one soldier
to the best projected country repeatedly, then submit the complete allocation.

Transfers consider every owned source/destination pair. Candidate amounts are 1,
source minus 1, half the source, half the source/destination difference, strongest
enemy availability minus destination soldiers, and amounts giving the destination
margins of 1, 0, -1 or -2 against each enemy. Halves use floor division; discard
illegal and duplicate amounts. Only a strictly better tuple qualifies, preventing
cycles on an unchanged board.

## Decisions and explanations

Allocate first. Before battle, prefer an improving transfer, then an acceptable
attack, otherwise skip. Reevaluate the locked pair after each exchange to continue
or stop. After conquest/failure, transfer if useful, otherwise end the turn.

Default ties use country IDs and transfer amount. Injected seeded ties are
reproducible from the seed identity, board digest and context. Policy randomness
is separate from authoritative dice; NPCs cannot choose or predict rolls.

Evidence saves observations, evaluations, revision/turn, strategy version, action,
explanation, digest, tie settings and projected potential. The action service
validates it before dice and commits it with state/events. Only committed results
are shown. Human fingerprints are unchanged; NPC fingerprints add `npc_decision_v1`.
Historical receipts remain readable; changed evidence under the same ID conflicts.
Formula changes need a new strategy version.

## Running NPC turns

The controller uses the human action service. IDs include strategy version, turn
sequence and revision. Batches default to 32 actions, accept 1-256, and stop at the
human turn, victory, limit, conflict or persistence error. Disabled writes raise
an error. Limits pause processing without forcing a gameplay action.

Retry an uncertain pending submission unchanged. Fresh processes recover committed
receipts, not aborted random results; workers need matching policy/tie settings.
The protected endpoint performs one action per request and replays duplicates
before strategy or dice. Display fast-forward and LLM commentary are still separate
work; see [Requirements](REQUIREMENTS.md).
