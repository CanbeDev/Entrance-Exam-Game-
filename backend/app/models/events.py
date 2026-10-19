from typing import Literal

from pydantic import Field

from app.models.actions import Allocation, FrozenModel
from app.models.runtime_game import RuntimeGame
from app.models.npc import NpcDecision


class GameEvent(FrozenModel):
    type: Literal["attack_started", "dice_exchange", "conquered", "eliminated", "victory",
                  "transferred", "allocated", "attack_stopped", "attack_failed", "turn_ended", "turn_started"]
    actor_id: str
    round: int
    turn_sequence: int
    source_id: str | None = None
    target_id: str | None = None
    player_id: str | None = None
    amount: int | None = None
    attacker_dice: tuple[int, ...] = ()
    defender_dice: tuple[int, ...] = ()
    attacker_losses: int = 0
    defender_losses: int = 0
    allocations: tuple[Allocation, ...] = ()


class ActionResult(FrozenModel):
    state: RuntimeGame
    events: tuple[GameEvent, ...] = Field(min_length=1)
    # Missing on historical receipts; no change to the saved RuntimeGame schema.
    npc_decision: NpcDecision | None = None
