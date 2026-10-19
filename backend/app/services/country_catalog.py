import json
from pathlib import Path

from pydantic import Field, model_validator

from app.models.country import CountryDefinition, PopulationSnapshot

DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "data/countries.json"


class CountryDataset(PopulationSnapshot):
    eligibility_source_url: str = Field(pattern=r"^https://")
    eligibility_policy: str = Field(min_length=1)
    eligibility_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    countries: tuple[CountryDefinition, ...] = Field(min_length=10)
    excluded_entries: tuple[CountryDefinition, ...]

    @model_validator(mode="after")
    def unique_entries(self):
        entries = self.countries + self.excluded_entries
        if len({entry.id for entry in entries}) != len(entries):
            raise ValueError("Dataset IDs must be unique, including excluded entries")
        if len({entry.name for entry in self.countries}) != len(self.countries):
            raise ValueError("Eligible country names must be unique")
        return self


class CountryCatalog:
    """Immutable country definitions; no network or database dependency."""

    def __init__(self, dataset: CountryDataset):
        self._dataset = dataset
        self._by_id = {country.id: country for country in dataset.countries}

    @classmethod
    def load(cls, path: Path = DEFAULT_DATASET):
        return cls(CountryDataset.model_validate(json.loads(path.read_text(encoding="utf-8"))))

    @property
    def countries(self) -> tuple[CountryDefinition, ...]:
        return self._dataset.countries

    @property
    def snapshot(self) -> PopulationSnapshot:
        return PopulationSnapshot.model_validate(
            self._dataset.model_dump(include=set(PopulationSnapshot.model_fields))
        )

    def get(self, country_id: str) -> CountryDefinition:
        try:
            return self._by_id[country_id]
        except KeyError:
            raise ValueError("Unknown or ineligible starting country") from None
