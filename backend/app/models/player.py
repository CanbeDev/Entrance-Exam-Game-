from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Player(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Literal["human", "npc"]
    starting_country_id: str = Field(min_length=1)
