from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.engine.population_rules import soldiers_from_population
from app.models.actions import FrozenModel, Identifier
from app.models.country import GameCountry, PopulationSnapshot
from app.models.player import Player


class RuntimePlayer(Player):
    model_config = {"frozen": True, "extra": "forbid"}


class Battle(FrozenModel):
    source_id: Identifier
    target_id: Identifier


class RuntimeGame(FrozenModel):
    schema_version: Literal[3] = 3
    game_name: str = Field(min_length=1, max_length=100)
    status: Literal["active", "completed"] = "active"
    round: int = Field(ge=1, strict=True)
    current_turn: int = Field(ge=0, lt=10, strict=True)
    countries: tuple[GameCountry, ...] = Field(min_length=10, max_length=10)
    players: tuple[RuntimePlayer, ...] = Field(min_length=10, max_length=10)
    turn_order: tuple[str, ...] = Field(min_length=10, max_length=10)
    population_snapshot: PopulationSnapshot
    winner: str | None = None
    created_at: datetime
    updated_at: datetime
    revision: int = Field(default=0, ge=0, strict=True)
    turn_sequence: int = Field(default=0, ge=0, strict=True)
    phase: Literal["allocating", "deciding", "attacking", "post_attack", "finished"] = "deciding"
    pending_reinforcements: int = Field(default=0, ge=0, strict=True)
    attack_used: bool = Field(default=False, strict=True)
    battle: Battle | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc_timestamps(cls, value: datetime) -> datetime:
        # PyMongo defaults to naive UTC datetimes on BSON reads. Normalize at the
        # adapter boundary without changing the existing database client settings.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        # BSON dates have millisecond precision; receipts and state must agree.
        return value.replace(microsecond=(value.microsecond // 1000) * 1000)

    @property
    def active_player_id(self) -> str:
        return self.turn_order[self.current_turn]

    def country(self, country_id: str) -> GameCountry:
        from app.engine.errors import GameRuleError
        for country in self.countries:
            if country.id == country_id:
                return country
        raise GameRuleError("Unknown country")

    @model_validator(mode="after")
    def valid_runtime(self):
        ids = {p.id for p in self.players}
        countries = {c.id for c in self.countries}
        if len(ids) != 10 or len(countries) != 10:
            raise ValueError("Duplicate country or participant")
        if len(set(self.turn_order)) != 10 or set(self.turn_order) != ids:
            raise ValueError("Invalid participant order")
        if sum(p.kind == "human" for p in self.players) != 1:
            raise ValueError("One human and nine NPCs required")
        if {p.starting_country_id for p in self.players} != countries:
            raise ValueError("Invalid original country assignments")
        owners = {c.owner_id for c in self.countries}
        if not owners <= ids:
            raise ValueError("Unknown owner")
        if any(c.base_soldier_value != soldiers_from_population(c.population) for c in self.countries):
            raise ValueError("Invalid immutable base value")
        if self.status == "completed":
            if (self.phase != "finished" or owners != {self.winner} or self.battle is not None
                    or self.pending_reinforcements != 0):
                raise ValueError("Inconsistent completed state")
            return self
        if self.winner is not None or self.phase == "finished" or len(owners) < 2:
            raise ValueError("Inconsistent active state")
        if self.active_player_id not in owners:
            raise ValueError("Eliminated participant cannot be active")
        count = sum(c.owner_id == self.active_player_id for c in self.countries)
        if self.phase == "allocating":
            if self.round < 2 or self.pending_reinforcements != 2 * count:
                raise ValueError("Invalid turn-start reinforcement budget")
        elif self.pending_reinforcements:
            raise ValueError("Reinforcements require allocation phase")
        if self.phase == "attacking":
            if self.battle is None or not self.attack_used:
                raise ValueError("Missing locked battle")
            source, target = self.country(self.battle.source_id), self.country(self.battle.target_id)
            if source.owner_id != self.active_player_id or target.owner_id == self.active_player_id or source.soldiers < 2:
                raise ValueError("Invalid locked battle")
        elif self.battle is not None:
            raise ValueError("Battle outside attack phase")
        if self.attack_used != (self.phase in {"attacking", "post_attack"}):
            raise ValueError("Inconsistent per-turn attack flag")
        return self
