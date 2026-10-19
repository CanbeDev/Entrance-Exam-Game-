
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.country import GameCountry, PopulationSnapshot
from app.models.player import Player


class GameCreate(BaseModel):
    game_name: str = Field(min_length=1, max_length=100)


class GameSetupRequest(BaseModel):
    """Service input only; never accepts client-provided ownership or soldiers."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    game_name: str = Field(min_length=1, max_length=100)
    starting_country_id: str = Field(min_length=1)


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


class InitializedGame(Game):
    """Validated Phase 1 initial state, separate from legacy waiting documents.

    This model validates setup only, not future combat state transitions.
    current_turn is an index into turn_order, not into players.
    """
    schema_version: Literal[2] = 2
    status: Literal["active"] = "active"
    countries: list[GameCountry] = Field(min_length=10, max_length=10)
    players: list[Player] = Field(min_length=10, max_length=10)
    turn_order: list[str] = Field(min_length=10, max_length=10)
    population_snapshot: PopulationSnapshot

    @model_validator(mode="after")
    def validate_initial_state(self):
        from app.engine.population_rules import soldiers_from_population

        country_ids = {country.id for country in self.countries}
        player_ids = {player.id for player in self.players}
        if len(country_ids) != 10 or len(player_ids) != 10:
            raise ValueError("Country and player IDs must be unique")
        if sum(player.kind == "human" for player in self.players) != 1:
            raise ValueError("Setup requires one human and nine NPCs")
        if len(set(self.turn_order)) != 10 or set(self.turn_order) != player_ids:
            raise ValueError("Turn order must contain every player exactly once")
        owners = {country.owner_id for country in self.countries}
        if owners != player_ids:
            raise ValueError("Each player must initially own exactly one country")
        by_id = {country.id: country for country in self.countries}
        for player in self.players:
            country = by_id.get(player.starting_country_id)
            if country is None or country.owner_id != player.id:
                raise ValueError("Starting country must belong to its assigned player")
        for country in self.countries:
            expected = soldiers_from_population(country.population)
            if country.base_soldier_value != expected or country.soldiers != expected:
                raise ValueError("Initial soldiers must equal the population-derived value")
        if self.round != 1 or self.current_turn != 0 or self.winner is not None:
            raise ValueError("Initial state must start at round 1, turn index 0, without a winner")
        return self
