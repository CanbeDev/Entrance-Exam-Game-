"""No database: public allowlists, legacy compatibility and durable event views."""
import copy
import json
import random

import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.engine.game_setup import initialize_game
from app.models.actions import ActionCommand, ActorContext, Skip
from app.models.game import GameSetupRequest
from app.services.game_action_service import GameActionService
from app.services.public_game_service import public_event_page, public_game, public_result
from npc_helpers import controller_for, npc_state
from phase2_helpers import MemoryActionStore, NOW, context, make_runtime


def add_private_fields(value):
    if isinstance(value, dict):
        return {**{key: add_private_fields(item) for key, item in value.items()},
                "future_private": {"password_hash": "private-marker"}}
    if isinstance(value, (list, tuple)):
        return [add_private_fields(item) for item in value]
    return value


def committed_receipts(catalog, count=3):
    state = make_runtime(catalog)
    store = MemoryActionStore(state.model_dump())
    service = GameActionService(store, clock=lambda: NOW)
    receipts = []
    for index in range(count):
        command = ActionCommand(action_id=f"public-{index}", expected_revision=state.revision, action=Skip())
        result = service.execute(store.game_id, context(state), command)
        receipts.append(store.receipts[(store.game_id, command.action_id)])
        state = result.state
    return receipts


def test_legacy_minimal_document_is_readable_and_private_envelope_is_omitted():
    document = {"_id": ObjectId(), "game_name": "My First Game", "countries": [], "players": [],
                "status": "waiting", "access": {"owner_user_id": "secret"},
                "creation": {"fingerprint": "secret"}, "password_hash": "secret"}
    before = copy.deepcopy(document)
    public = public_game(document)
    assert public == {"_id": str(document["_id"]), "game_name": "My First Game", "countries": [],
                      "players": [], "status": "waiting"}
    assert document == before


def test_phase1_initialized_response_preserves_all_known_game_fields(catalog):
    game = initialize_game(GameSetupRequest(game_name="Phase 1", starting_country_id="south-africa"),
                           catalog, random.Random(8)).model_dump(mode="json")
    assert public_game(game) == game


def test_runtime_response_preserves_all_known_game_fields(catalog):
    state = make_runtime(catalog).model_dump(mode="json")
    assert public_game(state) == state


def test_game_allowlists_unknown_metadata_recursively(catalog):
    state = make_runtime(catalog).model_dump(mode="json")
    projected = public_game(add_private_fields(state))
    assert projected == state
    assert "private-marker" not in json.dumps(projected)


def test_battle_private_metadata_is_omitted(catalog):
    from app.models.actions import StartAttack
    from phase2_helpers import step
    state = make_runtime(catalog)
    source = state.countries[0]
    target = state.countries[1]
    result = step(state, StartAttack(source_id=source.id, target_id=target.id))
    raw = result.state.model_dump(mode="json")
    public = public_game(add_private_fields(raw))
    assert public["battle"] == {"source_id": source.id, "target_id": target.id}
    assert public == raw


def test_action_projection_has_only_state_events_and_public_explanation(catalog):
    state = npc_state(catalog)
    _, _, controller = controller_for(state)
    result = controller.submit(controller.prepare("0" * 24))
    public = public_result(result)
    assert set(public) == {"state", "events", "npc_decision"}
    assert public["state"] == result.state.model_dump(mode="json")
    decision = public["npc_decision"]
    assert decision["explanation"] == result.npc_decision.explanation
    assert len(decision["evaluation"]["countries"]) == 10
    assert len(decision["evaluation"]["participants"]) == 10
    assert "state_digest" not in decision and "tie_breaker" not in decision
    assert "fingerprint" not in json.dumps(public)


def test_committed_pages_order_paginate_and_preserve_events(catalog):
    receipts = committed_receipts(catalog)
    page = public_event_page(reversed(receipts), after_revision=0, limit=2)
    assert [entry["revision"] for entry in page["events"]] == [1, 2]
    assert page["next_after_revision"] == 2 and page["has_more"] is True
    assert page["events"][0]["events"] == receipts[0].result.model_dump(mode="json")["events"]
    assert page["events"][0]["actor"] == receipts[0].actor.model_dump()
    last = public_event_page(receipts, after_revision=2)
    assert [entry["revision"] for entry in last["events"]] == [3]
    assert last["has_more"] is False


def test_empty_page_keeps_cursor():
    assert public_event_page([], after_revision=9) == {
        "events": [], "after_revision": 9, "next_after_revision": 9, "has_more": False}


def test_historical_receipt_missing_npc_evidence_remains_readable(catalog):
    raw = committed_receipts(catalog, 1)[0].model_dump(mode="json")
    raw["result"].pop("npc_decision")
    page = public_event_page([raw])
    assert page["events"][0]["npc_decision"] is None


def test_receipts_allowlist_private_fields_recursively_before_validation(catalog):
    state = npc_state(catalog)
    store, _, controller = controller_for(state)
    controller.submit(controller.prepare(store.game_id))
    receipt = next(iter(store.receipts.values()))
    page = public_event_page([add_private_fields(receipt.model_dump(mode="json"))])
    assert page == public_event_page([receipt])
    text = json.dumps(page)
    for private in ("private-marker", "fingerprint", "state_digest", "tie_breaker", "future_private"):
        assert private not in text


def test_invalid_canonical_receipt_data_is_not_presented_as_committed(catalog):
    raw = committed_receipts(catalog, 1)[0].model_dump(mode="json")
    raw["result"]["state"]["countries"][0]["soldiers"] = 0
    with pytest.raises(ValidationError):
        public_event_page([raw])


def test_uncommitted_successor_revision_is_rejected(catalog):
    raw = committed_receipts(catalog, 1)[0].model_dump(mode="json")
    raw["command"]["expected_revision"] = 40
    with pytest.raises(ValueError, match="committed receipt revision"):
        public_event_page([raw])


def test_duplicate_or_cross_game_receipts_are_rejected(catalog):
    receipt = committed_receipts(catalog, 1)[0]
    with pytest.raises(ValueError, match="Duplicate committed revision"):
        public_event_page([receipt, receipt])
    raw = receipt.model_dump(mode="json")
    raw["game_id"] = "1" * 24
    with pytest.raises(ValueError, match="one game"):
        public_event_page([receipt, raw])


@pytest.mark.parametrize("cursor,limit", [(-1, 1), (True, 1), (0, 0), (0, 101), (0, True), (0, "1")])
def test_invalid_pagination_is_rejected(cursor, limit):
    with pytest.raises(ValueError):
        public_event_page([], after_revision=cursor, limit=limit)


def test_public_game_invalid_known_nested_shape_fails_closed(catalog):
    raw = make_runtime(catalog).model_dump(mode="json")
    raw["players"][0]["kind"] = "administrator"
    with pytest.raises(ValidationError):
        public_game(raw)
