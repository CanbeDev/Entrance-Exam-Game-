import random

import pytest
from pydantic import ValidationError

from app.engine.game_setup import initialize_game
from app.engine.population_rules import soldiers_from_population
from app.models.game import GameSetupRequest, InitializedGame


def request():
    return GameSetupRequest(game_name="Phase 1", starting_country_id="south-africa")


@pytest.mark.parametrize("seed", range(20))
def test_setup_invariants(catalog, seed):
    game = initialize_game(request(), catalog, random.Random(seed))
    assert len(game.countries) == len({c.id for c in game.countries}) == 10
    assert len(game.players) == 10
    assert sum(p.kind == "human" for p in game.players) == 1
    assert sum(p.kind == "npc" for p in game.players) == 9
    assert {c.owner_id for c in game.countries} == {p.id for p in game.players}
    assert {p.starting_country_id for p in game.players} == {c.id for c in game.countries}
    assert next(c for c in game.countries if c.id == "south-africa").owner_id == "human"
    for country in game.countries:
        assert country.soldiers == country.base_soldier_value == soldiers_from_population(country.population)
    assert len(set(game.turn_order)) == 10
    assert set(game.turn_order) == {p.id for p in game.players}
    assert game.current_turn == 0 and game.round == 1 and game.status == "active"
    assert game.winner is None
    assert game.population_snapshot == catalog.snapshot


def test_randomness_is_injected_and_reproducible(catalog):
    first = initialize_game(request(), catalog, random.Random(42))
    second = initialize_game(request(), catalog, random.Random(42))
    assert first.model_dump(exclude={"created_at"}) == second.model_dump(exclude={"created_at"})
    orders = {tuple(initialize_game(request(), catalog, random.Random(i)).turn_order) for i in range(10)}
    assert len(orders) > 1
    assert any(order[0] != "human" for order in orders)


def test_default_randomness(catalog):
    assert len(initialize_game(request(), catalog).countries) == 10


@pytest.mark.parametrize("data", [
    {"game_name": "", "starting_country_id": "south-africa"},
    {"game_name": "   ", "starting_country_id": "south-africa"},
    {"game_name": "x" * 101, "starting_country_id": "south-africa"},
    {"game_name": "Game"},
    {"game_name": "Game", "starting_country_id": ""},
    {"game_name": "Game", "starting_country_id": "south-africa", "soldiers": 99},
])
def test_invalid_setup_request(data):
    with pytest.raises(ValidationError):
        GameSetupRequest(**data)


def test_unknown_country(catalog):
    with pytest.raises(ValueError):
        initialize_game(GameSetupRequest(game_name="Game", starting_country_id="unknown"), catalog)


@pytest.mark.parametrize("mutation", ["countries", "owners", "human_count", "order", "soldiers", "base", "starting", "round", "turn", "winner"])
def test_invalid_initial_state_rejected(catalog, mutation):
    raw = initialize_game(request(), catalog, random.Random(1)).model_dump()
    if mutation == "countries":
        raw["countries"][1]["id"] = raw["countries"][0]["id"]
    elif mutation == "owners":
        raw["countries"][0]["owner_id"] = "missing"
    elif mutation == "human_count":
        raw["players"][1]["kind"] = "human"
    elif mutation == "order":
        raw["turn_order"][1] = raw["turn_order"][0]
    elif mutation in {"soldiers", "base"}:
        raw["countries"][0]["soldiers" if mutation == "soldiers" else "base_soldier_value"] = 1
    elif mutation == "starting":
        raw["players"][0]["starting_country_id"] = raw["players"][1]["starting_country_id"]
    elif mutation == "winner":
        raw["winner"] = "human"
    else:
        raw["round" if mutation == "round" else "current_turn"] = 2
    with pytest.raises(ValidationError):
        InitializedGame.model_validate(raw)
