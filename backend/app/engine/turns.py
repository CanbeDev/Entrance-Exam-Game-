from dataclasses import dataclass

from app.engine.errors import GameRuleError
from app.models.runtime_game import RuntimeGame


@dataclass(frozen=True)
class NextTurn:
    index: int
    round: int
    player_id: str
    reinforcements: int


def calculate_reinforcements(round_number: int, country_count: int) -> int:
    if type(round_number) is not int or type(country_count) is not int or round_number < 1 or country_count < 0:
        raise GameRuleError("Invalid reinforcement inputs")
    return 0 if round_number == 1 else 2 * country_count


def advance_turn(state: RuntimeGame, countries: list[dict]) -> NextTurn:
    counts = {player: sum(c["owner_id"] == player for c in countries) for player in state.turn_order}
    if sum(count > 0 for count in counts.values()) < 2:
        raise GameRuleError("A won game cannot advance turns")
    index, round_number = state.current_turn, state.round
    for _ in range(10):
        index = (index + 1) % 10
        if index == 0:
            round_number += 1
        player = state.turn_order[index]
        if counts[player]:
            return NextTurn(index, round_number, player, calculate_reinforcements(round_number, counts[player]))
    raise GameRuleError("No surviving participant")
