import random

import pytest
from bson import BSON, ObjectId
from pymongo.errors import PyMongoError

from app.models.game import Game, GameCreate, GameSetupRequest, InitializedGame
from app.repositories import game_repository
from app.repositories.game_repository import MongoGameRepository
from app.services.game_service import GameService


def test_service_persists_complete_bson_encodable_state(catalog, collection):
    repository = MongoGameRepository(collection)
    game_id = GameService(repository, catalog, random.Random(12)).create_game(
        GameSetupRequest(game_name="Saved", starting_country_id="south-africa"))
    assert collection.insert_count == 1
    saved = repository.get_game(game_id)
    assert saved["_id"] == game_id
    assert saved["turn_order"][saved["current_turn"]] in {p["id"] for p in saved["players"]}
    assert InitializedGame.model_validate(saved).population_snapshot == catalog.snapshot
    BSON.encode(collection.documents[ObjectId(game_id)])
    # Read through a fresh repository to simulate a later process/session.
    assert MongoGameRepository(collection).get_game(game_id) == saved


def test_invalid_selection_never_inserts(catalog, collection):
    with pytest.raises(ValueError):
        GameService(MongoGameRepository(collection), catalog).create_game(
            GameSetupRequest(game_name="Bad", starting_country_id="taiwan"))
    assert collection.insert_count == 0


def test_repository_failure_is_propagated(catalog):
    class FailingCollection:
        def insert_one(self, document):
            raise PyMongoError("Simulated write failure")
    with pytest.raises(PyMongoError, match="Simulated"):
        GameService(MongoGameRepository(FailingCollection()), catalog).create_game(
            GameSetupRequest(game_name="Game", starting_country_id="india"))


def test_legacy_my_first_game_unchanged(collection, monkeypatch):
    repository = MongoGameRepository(collection)
    monkeypatch.setattr(game_repository, "_repository", repository)
    game_id = game_repository.create_game(GameCreate(game_name="My First Game"))
    before = collection.find_one({"_id": ObjectId(game_id)})
    saved = game_repository.get_game(game_id)
    assert saved["game_name"] == "My First Game"
    assert saved["status"] == "waiting"
    assert saved["countries"] == saved["players"] == []
    assert "schema_version" not in saved
    assert Game.model_validate(saved).game_name == "My First Game"
    assert collection.find_one({"_id": ObjectId(game_id)}) == before
    assert collection.insert_count == 1


@pytest.mark.parametrize("game_id", ["not-an-id", "", None, "0" * 24])
def test_missing_or_invalid_id(collection, game_id):
    assert MongoGameRepository(collection).get_game(game_id) is None


def test_separate_games_do_not_share_state(catalog, collection):
    repository = MongoGameRepository(collection)
    service = GameService(repository, catalog, random.Random(5))
    request = GameSetupRequest(game_name="Game", starting_country_id="india")
    first, second = service.create_game(request), service.create_game(request)
    assert first != second
    saved = repository.get_game(first)
    saved["countries"][0]["soldiers"] = 99
    assert repository.get_game(first)["countries"][0]["soldiers"] == 9
    assert repository.get_game(second)["countries"][0]["soldiers"] == 9


def test_repository_revalidates_before_write(catalog, collection):
    from app.engine.game_setup import initialize_game
    from pydantic import ValidationError
    game = initialize_game(GameSetupRequest(game_name="Game", starting_country_id="india"), catalog)
    game.turn_order[1] = game.turn_order[0]
    with pytest.raises(ValidationError):
        MongoGameRepository(collection).save_initialized_game(game)
    assert collection.insert_count == 0
