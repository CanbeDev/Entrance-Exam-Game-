from app.engine.errors import GameRuleError
from app.models.actions import Allocate
from app.models.runtime_game import RuntimeGame


def validate_allocation(state: RuntimeGame, action: Allocate) -> None:
    if sum(item.amount for item in action.allocations) != state.pending_reinforcements:
        raise GameRuleError("Allocate the complete turn-start reinforcement budget")
    for item in action.allocations:
        if state.country(item.country_id).owner_id != state.active_player_id:
            raise GameRuleError("Reinforcements require owned countries")
