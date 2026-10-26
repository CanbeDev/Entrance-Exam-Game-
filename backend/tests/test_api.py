import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import PyMongoError

from app.repositories.game_repository import MongoGameRepository
from app.security.environment import ApplicationSettings
from startup_helpers import StartupClient


@pytest.fixture
def api(monkeypatch, collection):
    # Explicit factory dependencies: importing main does not load dotenv/Atlas.
    fake_database = ModuleType("app.database")
    fake_database.client = SimpleNamespace(admin=SimpleNamespace(command=lambda command: {"ok": 1}))
    fake_database.db = {"games": collection}
    monkeypatch.setitem(sys.modules, "app.database", fake_database)
    previous = sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    repository = MongoGameRepository(collection)
    injected = StartupClient()
    injected.database.collections["games"] = collection
    fake_database.client = injected
    module.app = module.create_app(settings_loader=lambda: ApplicationSettings("mongodb://localhost", "test"),
                                   client_factory=lambda settings: injected)
    with TestClient(module.app) as client:
        yield client, module, fake_database, repository
    sys.modules.pop("app.main", None)
    if previous is not None:
        sys.modules["app.main"] = previous


def test_country_listing_and_no_creation_route(api):
    client, module, _, _ = api
    response = client.get("/countries")
    assert response.status_code == 200
    data = response.json()
    assert len(data["countries"]) == 195
    assert data["population_snapshot"]["population_year"] == 2026
    south_africa = next(c for c in data["countries"] if c["id"] == "south-africa")
    assert south_africa["base_soldier_value"] == 5
    # Phase 4 adds explicitly authorized routes, with production dependencies
    # absent and write gates closed. Anonymous calls cannot create any game.
    assert client.post("/games", json={"game_name": "Blocked", "starting_country_id": "india"}).status_code == 503
    approved_posts = {"/auth/register", "/auth/login", "/auth/logout", "/games",
                      "/games/{game_id}/actions", "/games/{game_id}/npc-steps"}
    assert {path for path, operations in module.app.openapi()["paths"].items()
            if "post" in operations} == approved_posts


def test_existing_endpoints_and_legacy_read(api):
    client, _, _, repository = api
    legacy_id = repository.collection.insert_one({"game_name": "My First Game", "countries": [], "players": [], "status": "waiting"}).inserted_id
    assert client.get("/").json() == {"message": "Geopolitics Game API is running"}
    assert client.get("/health").json() == {"status": "healthy", "database": "connected"}
    result = client.get(f"/games/{legacy_id}")
    assert result.status_code == 200 and result.json()["game_name"] == "My First Game"
    assert client.get("/games/invalid").status_code == 404


def test_database_errors_still_return_503(api, monkeypatch):
    client, module, database, _ = api
    def fail(*args):
        raise PyMongoError("Simulated outage")
    monkeypatch.setattr(database.client.admin, "command", fail)
    monkeypatch.setattr(module.app.state, "game_reader", fail)
    assert client.get("/health").status_code == 503
    assert client.get("/games/" + "0" * 24).status_code == 503


def test_read_initialized_game(api, catalog):
    from app.models.game import GameSetupRequest
    from app.services.game_service import GameService
    client, _, _, repository = api
    game_id = GameService(repository, catalog).create_game(
        GameSetupRequest(game_name="Initialized", starting_country_id="south-africa"))
    response = client.get(f"/games/{game_id}")
    assert response.status_code == 200
    saved = response.json()
    assert saved["schema_version"] == 2
    assert len(saved["countries"]) == len(saved["turn_order"]) == 10
    assert saved["population_snapshot"]["retrieved_on"] == "2026-10-19"
