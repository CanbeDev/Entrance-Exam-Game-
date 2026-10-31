"""Narration is a projection, never an authoritative game command."""
from typing import Literal

from pydantic import Field

from app.models.actions import FrozenModel


class BattleFacts(FrozenModel):
    attacker: str = Field(min_length=1, max_length=128)
    defender: str = Field(min_length=1, max_length=128)
    attacker_dice: tuple[int, ...] = Field(min_length=1)
    defender_dice: tuple[int, ...] = Field(min_length=1)
    attacker_losses: int = Field(ge=0, strict=True)
    defender_losses: int = Field(ge=0, strict=True)
    conquered: bool
    eliminated: tuple[str, ...] = Field(max_length=10)
    round: int = Field(ge=1, strict=True)
    actor_kind: Literal["human", "npc"]


class BattleCommentary(FrozenModel):
    game_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    revision: int = Field(ge=1, strict=True)
    action_id: str = Field(min_length=1, max_length=128)
    status: Literal["not_generated", "pending", "ready", "fallback"]
    source: Literal["groq", "deterministic"]
    text: str = Field(min_length=1, max_length=1600)
    reason: str | None
    facts: BattleFacts


class CommentaryRequest(FrozenModel):
    """Identity comes exclusively from the path and persisted receipt."""
