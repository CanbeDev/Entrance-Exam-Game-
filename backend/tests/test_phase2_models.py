import copy

import pytest
from pydantic import ValidationError

from app.engine.errors import UnsupportedGame
from app.engine.state_adapter import load_runtime
from app.models.actions import ActionCommand
from app.models.runtime_game import RuntimeGame
from phase2_helpers import make_runtime


def test_phase1_adaptation_is_read_only(catalog):
    from app.engine.game_setup import initialize_game
    from app.models.game import GameSetupRequest
    initial = initialize_game(GameSetupRequest(game_name="Existing", starting_country_id="india"), catalog)
    document = initial.model_dump(mode="json")
    document["_id"] = "0" * 24
    before = copy.deepcopy(document)
    runtime = load_runtime(document)
    assert document == before
    assert runtime.revision == 0 and runtime.schema_version == 3
    assert runtime.turn_order == tuple(initial.turn_order)
    assert runtime.population_snapshot == initial.population_snapshot
    assert load_runtime(runtime.model_dump(mode="json")) == runtime


@pytest.mark.parametrize("document", [
    {"game_name": "My First Game", "status": "waiting", "countries": [], "players": []},
    {"schema_version": 2, "countries": []}, {"schema_version": 99}, {},
])
def test_unsupported_game_never_adapts(document):
    before = copy.deepcopy(document)
    with pytest.raises(UnsupportedGame):
        load_runtime(document)
    assert document == before


@pytest.mark.parametrize("mutation", ["owner", "base", "order", "active", "budget", "phase", "battle", "winner", "player"])
def test_runtime_invariants(catalog, mutation):
    data = make_runtime(catalog).model_dump(mode="json")
    if mutation == "owner":
        data["countries"][0]["owner_id"] = "missing"
    elif mutation == "base":
        data["countries"][0]["base_soldier_value"] = 1
    elif mutation == "order":
        data["turn_order"][1] = data["turn_order"][0]
    elif mutation == "active":
        data["countries"][0]["owner_id"] = "npc-1"
    elif mutation == "budget":
        data["pending_reinforcements"] = 2
    elif mutation == "phase":
        data["phase"] = "attacking"
    elif mutation == "battle":
        data["battle"] = {"source_id": data["countries"][0]["id"], "target_id": data["countries"][1]["id"]}
    elif mutation == "winner":
        data["winner"] = "human"
    else:
        data["players"][1]["kind"] = "human"
    with pytest.raises(ValidationError):
        RuntimeGame.model_validate(data)


def test_nested_state_is_immutable(catalog):
    state = make_runtime(catalog)
    with pytest.raises(ValidationError):
        state.revision = 2
    with pytest.raises(ValidationError):
        state.countries[0].soldiers = 9
    with pytest.raises(ValidationError):
        state.players[0].kind = "npc"
    with pytest.raises(TypeError):
        state.turn_order[0] = "npc-1"


@pytest.mark.parametrize("action", [
    {"type": "transfer", "source_id": "a", "target_id": "b", "amount": 0},
    {"type": "transfer", "source_id": "a", "target_id": "b", "amount": True},
    {"type": "transfer", "source_id": "a", "target_id": "b", "amount": 1.5},
    {"type": "roll", "dice": [6]}, {"type": "unknown"},
    {"type": "allocate", "allocations": [{"country_id": "a", "amount": 1}, {"country_id": "a", "amount": 1}]},
])
def test_invalid_commands(action):
    with pytest.raises(ValidationError):
        ActionCommand(action_id="test", expected_revision=0, action=action)


@pytest.mark.parametrize("fields", [{"action_id": ""}, {"action_id": "unsafe:id"},
                                      {"expected_revision": -1}, {"expected_revision": True}])
def test_invalid_envelope(fields):
    data = {"action_id": "valid", "expected_revision": 0, "action": {"type": "skip"}, **fields}
    with pytest.raises(ValidationError):
        ActionCommand.model_validate(data)


def test_bson_default_naive_utc_read_preserves_runtime(catalog):
    from bson import BSON
    from app.repositories.action_repository import runtime_document
    state = make_runtime(catalog)
    stored = BSON(BSON.encode(runtime_document(state))).decode()
    assert stored["created_at"].tzinfo is None
    assert load_runtime(stored) == state
