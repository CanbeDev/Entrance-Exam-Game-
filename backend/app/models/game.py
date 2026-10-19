
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class GameCreate(BaseModel):
    game_name: str = Field(min_length=1, max_length=100)


class Game(BaseModel):
    game_name: str = Field(min_length=1, max_length=100)
    status: Literal["waiting", "active", "completed"] = "waiting"
    round: int = Field(default=1, ge=1)
    current_turn: int = Field(default=0, ge=0)
    countries: list = Field(default_factory=list)
    players: list = Field(default_factory=list)
    winner: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
