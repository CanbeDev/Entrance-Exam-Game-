import json

import pytest
from pydantic import ValidationError

from app.models.country import CountryDefinition
from app.services.country_catalog import CountryCatalog, CountryDataset, DEFAULT_DATASET


def test_snapshot_and_eligibility(catalog):
    assert len(catalog.countries) == 195
    assert len({c.id for c in catalog.countries}) == 195
    assert catalog.snapshot.population_year == 2026
    assert catalog.snapshot.retrieved_on.isoformat() == "2026-10-19"
    assert catalog.get("south-africa").population == 65_453_084
    assert catalog.get("holy-see").population == 506
    assert catalog.get("state-of-palestine")
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    assert len(raw["excluded_entries"]) == 39
    assert {c["id"] for c in raw["excluded_entries"]}.isdisjoint(c.id for c in catalog.countries)
    from app.engine.population_rules import soldiers_from_population
    assert {soldiers_from_population(c.population) for c in catalog.countries} == set(range(1, 10))


@pytest.mark.parametrize("country_id", ["unknown", "", "hong-kong", "taiwan", "greenland"])
def test_unknown_or_excluded_country(catalog, country_id):
    with pytest.raises(ValueError, match="Unknown or ineligible"):
        catalog.get(country_id)


@pytest.mark.parametrize("mutation", ["duplicate", "too_small", "overlap", "bad_population", "bad_metadata"])
def test_invalid_dataset_rejected(mutation):
    raw = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))
    if mutation == "duplicate":
        raw["countries"][1] = raw["countries"][0]
    elif mutation == "too_small":
        raw["countries"] = raw["countries"][:9]
    elif mutation == "overlap":
        raw["excluded_entries"].append(raw["countries"][0])
    elif mutation == "bad_population":
        raw["countries"][0]["population"] = "1000"
    else:
        raw["source_sha256"] = "invalid"
    with pytest.raises(ValidationError):
        CountryDataset.model_validate(raw)


@pytest.mark.parametrize("population", [0, -1, True, 1.5, "500"])
def test_invalid_country_population(population):
    with pytest.raises(ValidationError):
        CountryDefinition(id="test", name="Test", population=population)


def test_country_definitions_are_immutable(catalog):
    with pytest.raises(ValidationError):
        catalog.countries[0].population = 10


def test_load_errors_are_not_silently_replaced(tmp_path):
    with pytest.raises(FileNotFoundError):
        CountryCatalog.load(tmp_path / "missing.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        CountryCatalog.load(invalid)
