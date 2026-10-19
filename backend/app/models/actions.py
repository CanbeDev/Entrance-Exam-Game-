from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ActorContext(FrozenModel):
    player_id: Identifier
    kind: Literal["human", "npc"]


class Allocation(FrozenModel):
    country_id: Identifier
    amount: PositiveInt


class Allocate(FrozenModel):
    type: Literal["allocate"] = "allocate"
    allocations: tuple[Allocation, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_countries(self):
        if len({item.country_id for item in self.allocations}) != len(self.allocations):
            raise ValueError("Allocation countries must be unique")
        return self


class Transfer(FrozenModel):
    type: Literal["transfer"] = "transfer"
    source_id: Identifier
    target_id: Identifier
    amount: PositiveInt


class StartAttack(FrozenModel):
    type: Literal["start_attack"] = "start_attack"
    source_id: Identifier
    target_id: Identifier


class Roll(FrozenModel):
    type: Literal["roll"] = "roll"


class StopAttack(FrozenModel):
    type: Literal["stop_attack"] = "stop_attack"


class Skip(FrozenModel):
    type: Literal["skip"] = "skip"


class EndTurn(FrozenModel):
    type: Literal["end_turn"] = "end_turn"


Action = Annotated[Allocate | Transfer | StartAttack | Roll | StopAttack | Skip | EndTurn,
                   Field(discriminator="type")]


class ActionCommand(FrozenModel):
    action_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    expected_revision: int = Field(ge=0, strict=True)
    action: Action
