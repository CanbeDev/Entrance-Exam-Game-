from functools import lru_cache

from fastapi import APIRouter

from app.engine.population_rules import soldiers_from_population
from app.services.country_catalog import CountryCatalog

router = APIRouter()


@lru_cache(maxsize=1)
def get_catalog() -> CountryCatalog:
    return CountryCatalog.load()


@router.get("/countries")
def list_countries():
    catalog = get_catalog()
    return {
        "population_snapshot": catalog.snapshot.model_dump(mode="json"),
        "countries": [
            {**country.model_dump(), "base_soldier_value": soldiers_from_population(country.population)}
            for country in catalog.countries
        ],
    }
