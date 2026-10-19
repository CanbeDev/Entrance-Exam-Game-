from app.engine.errors import GameRuleError
from app.engine.npc.evaluation import evaluate_board, state_digest
from app.models.actions import Allocate, EndTurn, Roll, Skip, StartAttack, StopAttack, Transfer
from app.models.npc import BoardEvaluation, NpcDecision


def explain(action, board: BoardEvaluation, battle=None, projected_potential=None) -> tuple[str, str]:
    countries = {c.id: c for c in board.countries}
    projection = ""
    if projected_potential is not None:
        projection = (f" Projected best-attack score {board.potential[2]} to {projected_potential[2]}, "
                      f"defensive exposure {board.defensive_exposure} to {-projected_potential[3]}; "
                      "priority is victory, elimination, attack value, defense, then force concentration.")
    if isinstance(action, Allocate):
        total = sum(item.amount for item in action.allocations)
        parts = ", ".join(f"{countries[item.country_id].name}: +{item.amount} (currently {countries[item.country_id].soldiers})" for item in action.allocations)
        return "allocate", (f"Allocate the full {total}-soldier budget ({parts}), choosing marginal improvements "
                            "in attack opportunity, defensive exposure, then concentration; these are planning heuristics." + projection)
    if isinstance(action, Transfer):
        source, target = countries[action.source_id], countries[action.target_id]
        unit = "soldier" if action.amount == 1 else "soldiers"
        return "transfer", (f"Move {action.amount} {unit} from {source.name} ({source.soldiers}) to "
                            f"{target.name} ({target.soldiers}), leaving {source.soldiers - action.amount} behind. "
                            "The projected board potential strictly improves; no dice outcome is assumed." + projection)
    if isinstance(action, (StartAttack, Roll, StopAttack)):
        if not isinstance(action, StartAttack) and battle is None:
            raise GameRuleError("NPC battle explanation requires a locked battle")
        source_id = action.source_id if isinstance(action, StartAttack) else battle.source_id
        target_id = action.target_id if isinstance(action, StartAttack) else battle.target_id
        option = next(a for a in board.attacks if a.source_id == source_id and a.target_id == target_id)
        source, target = countries[source_id], countries[target_id]
        reason = "attack" if isinstance(action, StartAttack) else "continue" if isinstance(action, Roll) else "stop"
        defender_unit = "defender" if option.defenders == 1 else "defenders"
        text = (f"{reason.capitalize()} against {target.name} from {source.name}: {option.available} available "
                f"against {option.defenders} {defender_unit}, margin {option.margin}, conquest reward {option.reward}, "
                f"heuristic score {option.score}. ")
        if reason == "stop":
            text += "The locked battle no longer meets the risk/value preference; stopping ends this turn."
        else:
            if option.wins:
                text += "A capture would achieve world conquest. "
            elif option.eliminates:
                text += "A capture would eliminate this opponent. "
            if option.margin < 1:
                text += "Strategic value permits risk below the ordinary margin preference. "
            text += "The authoritative engine determines the dice; capture is not guaranteed."
        return reason, text
    if isinstance(action, Skip):
        return "skip", "Skip: no positive-scoring attack meets the risk preferences and no candidate transfer improves board potential."
    if isinstance(action, EndTurn):
        return "end_turn", "End this turn: the attack is resolved, a second attack is prohibited, and no candidate transfer improves board potential."
    raise GameRuleError("Unsupported NPC action")


def validate_decision(state, actor, action, decision: NpcDecision) -> None:
    if (actor.kind != "npc" or decision.action != action or decision.state_digest != state_digest(state)
            or decision.evaluation != evaluate_board(state) or decision.evaluation.actor_id != actor.player_id):
        raise GameRuleError("NPC evidence does not match the observed state and action")
    # Reproduce the supported policy, including tie context, before any dice are
    # consumed. This rejects fabricated metrics, prose and policy claims alike.
    from app.engine.npc.strategy import NpcStrategy, SeededTieBreaker, StableTieBreaker
    if decision.tie_breaker == "stable":
        ties = StableTieBreaker()
    elif decision.tie_breaker.startswith("seeded:"):
        try:
            ties = SeededTieBreaker(int(decision.tie_breaker.removeprefix("seeded:")))
        except ValueError:
            raise GameRuleError("Unknown NPC tie-break configuration") from None
    else:
        raise GameRuleError("Unknown NPC tie-break configuration")
    if decision != NpcStrategy(ties).decide(state):
        raise GameRuleError("NPC evidence is not reproducible from the observed state")
