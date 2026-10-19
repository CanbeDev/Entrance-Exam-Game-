from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CountryDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1)
    population: int = Field(gt=0, strict=True)


class PopulationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://")
    population_year: int = Field(ge=1900, strict=True)
    retrieved_on: date
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GameCountry(CountryDefinition):
    owner_id: str = Field(min_length=1)
    base_soldier_value: int = Field(ge=1, le=9, strict=True)
    soldiers: int = Field(ge=1, strict=True)
