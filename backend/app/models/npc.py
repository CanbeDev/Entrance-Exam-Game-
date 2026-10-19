from typing import Literal

from pydantic import Field

from app.models.actions import Action, ActorContext, ActionCommand, FrozenModel


class CountryObservation(FrozenModel):
    id: str
    name: str
    owner_id: str
    soldiers: int
    base_soldier_value: int


class ParticipantObservation(FrozenModel):
    id: str
    kind: Literal["human", "npc"]
    countries: int
    soldiers: int
    reinforcement_income: int
    turn_distance: int


class AttackEvaluation(FrozenModel):
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


class BoardEvaluation(FrozenModel):
    actor_id: str
    revision: int
    turn_sequence: int
    round: int
    countries: tuple[CountryObservation, ...] = Field(min_length=10, max_length=10)
    participants: tuple[ParticipantObservation, ...] = Field(min_length=10, max_length=10)
    attacks: tuple[AttackEvaluation, ...]
    defensive_exposure: int
    concentration: int

    @property
    def potential(self) -> tuple[int, int, int, int, int]:
        best = max(((int(a.wins), int(a.eliminates), a.score) for a in self.attacks if a.acceptable),
                   default=(0, 0, 0))
        return (*best, -self.defensive_exposure, self.concentration)


class NpcDecision(FrozenModel):
    strategy_version: Literal["balanced-v1"] = "balanced-v1"
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Action
    evaluation: BoardEvaluation
    reason: Literal["allocate", "transfer", "attack", "continue", "stop", "skip", "end_turn"]
    explanation: str = Field(min_length=1)
    tie_breaker: str
    tie_break_used: bool
    projected_potential: tuple[int, int, int, int, int] | None = None


class NpcSubmission(FrozenModel):
    game_id: str
    actor: ActorContext
    command: ActionCommand
    decision: NpcDecision
