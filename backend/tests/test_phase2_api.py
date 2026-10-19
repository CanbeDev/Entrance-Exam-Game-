from app.repositories.action_repository import runtime_document
from phase2_helpers import make_runtime, step
from app.models.actions import Skip
from test_api import api  # Reuse the isolated fake-database fixture, never Atlas.


def test_existing_read_endpoint_accepts_runtime_game(api, catalog):
    client, _, _, repository = api
    runtime = step(make_runtime(catalog), Skip()).state
    game_id = repository.collection.insert_one(runtime_document(runtime)).inserted_id
    response = client.get(f"/games/{game_id}")
    assert response.status_code == 200
    assert response.json()["schema_version"] == 3
    assert response.json()["revision"] == 1
    assert response.json()["turn_order"] == list(runtime.turn_order)
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)(f"/games/{game_id}").status_code == 405
