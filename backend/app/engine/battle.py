import random
from dataclasses import dataclass
from typing import Protocol

from app.engine.errors import GameRuleError


class DiceProvider(Protocol):
    def roll(self) -> int: ...


class RandomDice:
    def __init__(self):
        self._random = random.SystemRandom()

    def roll(self) -> int:
        return self._random.randint(1, 6)


@dataclass(frozen=True)
class Exchange:
    attacker_dice: tuple[int, ...]
    defender_dice: tuple[int, ...]
    attacker_losses: int
    defender_losses: int


def roll_exchange(attacker: int, defender: int, dice: DiceProvider) -> Exchange:
    if type(attacker) is not int or type(defender) is not int or attacker < 2 or defender < 1:
        raise GameRuleError("Insufficient soldiers for battle")
    count = min(attacker - 1, defender)
    attack_rolls = tuple(dice.roll() for _ in range(count))
    defend_rolls = tuple(dice.roll() for _ in range(count))
    if any(type(value) is not int or not 1 <= value <= 6 for value in attack_rolls + defend_rolls):
        raise GameRuleError("Invalid dice provider output")
    return Exchange(attack_rolls, defend_rolls,
                    sum(a < d for a, d in zip(attack_rolls, defend_rolls)),
                    sum(a > d for a, d in zip(attack_rolls, defend_rolls)))


def conquest_reward(base_soldier_value: int) -> int:
    if type(base_soldier_value) is not int or not 1 <= base_soldier_value <= 9:
        raise GameRuleError("Invalid base soldier value")
    return max(2, base_soldier_value // 2)
