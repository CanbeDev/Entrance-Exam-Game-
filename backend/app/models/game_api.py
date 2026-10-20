"""Explicit public read contracts, independent of persistence-only metadata.

Unknown fields are discarded at every level. Never return saved documents or
receipt dictionaries directly: ownership and future private fields are not part
of these contracts.
"""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

class PublicModel(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class PublicCountry(PublicModel):
    id: str
    name: str
    population: int = Field(gt=0, strict=True)
    owner_id: str
    base_soldier_value: int = Field(ge=1, le=9, strict=True)
    soldiers: int = Field(ge=1, strict=True)


class PublicParticipant(PublicModel):
    id: str
    kind: Literal["human", "npc"]
    starting_country_id: str


class PublicPopulationSnapshot(PublicModel):
    dataset_id: str
    source_url: str
    population_year: int
    retrieved_on: date
    source_sha256: str


class PublicBattle(PublicModel):
    source_id: str
    target_id: str


class PublicGame(PublicModel):
    id: str | None = Field(default=None, alias="_id")
    game_name: str
    status: Literal["waiting", "active", "completed"] = "waiting"
    round: int | None = None
    current_turn: int | None = None
    countries: tuple[PublicCountry, ...] = ()
    players: tuple[PublicParticipant, ...] = ()
    winner: str | None = None
    created_at: datetime | None = None
    schema_version: Literal[2, 3] | None = None
    turn_order: tuple[str, ...] | None = None
    population_snapshot: PublicPopulationSnapshot | None = None
    updated_at: datetime | None = None
    revision: int | None = None
    turn_sequence: int | None = None
    phase: Literal["allocating", "deciding", "attacking", "post_attack", "finished"] | None = None
    pending_reinforcements: int | None = None
    attack_used: bool | None = None
    battle: PublicBattle | None = None


class PublicAllocation(PublicModel):
    country_id: str
    amount: int


class PublicAllocate(PublicModel):
    type: Literal["allocate"]
    allocations: tuple[PublicAllocation, ...]


class PublicTransfer(PublicModel):
    type: Literal["transfer"]
    source_id: str
    target_id: str
    amount: int


class PublicStartAttack(PublicModel):
    type: Literal["start_attack"]
    source_id: str
    target_id: str


class PublicRoll(PublicModel):
    type: Literal["roll"]


class PublicStopAttack(PublicModel):
    type: Literal["stop_attack"]


class PublicSkip(PublicModel):
    type: Literal["skip"]


class PublicEndTurn(PublicModel):
    type: Literal["end_turn"]


PublicAction = Annotated[PublicAllocate | PublicTransfer | PublicStartAttack | PublicRoll |
                         PublicStopAttack | PublicSkip | PublicEndTurn, Field(discriminator="type")]


class PublicGameEvent(PublicModel):
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
    allocations: tuple[PublicAllocation, ...] = ()


class PublicCountryObservation(PublicModel):
    id: str
    name: str
    owner_id: str
    soldiers: int
    base_soldier_value: int


class PublicParticipantObservation(PublicModel):
    id: str
    kind: Literal["human", "npc"]
    countries: int
    soldiers: int
    reinforcement_income: int
    turn_distance: int


class PublicAttackEvaluation(PublicModel):
    source_id: str
    target_id: str
    available: int
    defenders: int
    margin: int
    reward: int
    eliminates: bool
    wins: bool
    opponent_income: int
    income_gain: int
    income_denial: int
    exposure_cost: int
    opponent_power_bonus: int
    urgency_bonus: int
    score: int
    acceptable: bool


class PublicBoardEvaluation(PublicModel):
    actor_id: str
    revision: int
    turn_sequence: int
    round: int
    countries: tuple[PublicCountryObservation, ...]
    participants: tuple[PublicParticipantObservation, ...]
    attacks: tuple[PublicAttackEvaluation, ...]
    defensive_exposure: int
    concentration: int


class PublicNpcDecision(PublicModel):
    strategy_version: str
    action: PublicAction
    reason: Literal["allocate", "transfer", "attack", "continue", "stop", "skip", "end_turn"]
    explanation: str
    evaluation: PublicBoardEvaluation
    projected_potential: tuple[int, int, int, int, int] | None = None


class PublicActionResult(PublicModel):
    state: PublicGame
    events: tuple[PublicGameEvent, ...]
    npc_decision: PublicNpcDecision | None = None


class PublicActor(PublicModel):
    player_id: str
    kind: Literal["human", "npc"]


class PublicCommittedAction(PublicModel):
    revision: int
    action_id: str
    actor: PublicActor
    committed_at: datetime
    events: tuple[PublicGameEvent, ...]
    npc_decision: PublicNpcDecision | None = None


class PublicEventPage(PublicModel):
    events: tuple[PublicCommittedAction, ...]
    after_revision: int
    next_after_revision: int
    has_more: bool


class PublicGameSummary(PublicModel):
    id: str = Field(alias="_id")
    game_name: str
    status: Literal["waiting", "active", "completed"]
    round: int | None = None
    current_turn: int | None = None
    phase: Literal["allocating", "deciding", "attacking", "post_attack", "finished"] | None = None
    revision: int | None = None
    winner: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PublicGameList(PublicModel):
    games: tuple[PublicGameSummary, ...]
    next_cursor: str | None
