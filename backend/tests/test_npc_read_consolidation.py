"""Fresh joined authorization, feature guards and fail-closed behavior, offline only."""
import copy
from datetime import timedelta
from types import SimpleNamespace

from bson import ObjectId
import pytest
from pymongo.errors import OperationFailure, PyMongoError

from app import npc_diagnostics as diag
from app.models.auth import Principal
from app.repositories.security_repository import MongoSecurityRepository
from app.security.errors import SecurityError
from benchmark_npc import scenarios
from benchmark_npc_mongodb import run_case
from profile_npc_reads import profile
from phase2_helpers import NOW
from test_npc_mongodb_performance import prepared
from test_phase4_mongo import setup_store
from startup_helpers import StartupClient
from test_startup import create_app, config, ORIGIN
from fastapi.testclient import TestClient


@pytest.mark.parametrize("joined", [False, True])
@pytest.mark.parametrize("change,code", [
    ("logout", "authentication_required"), ("expired", "authentication_required"),
    ("idle", "authentication_required"), ("disabled", "authentication_required"),
    ("session_version", "authentication_required"), ("user_version", "authentication_required"),
    ("bad_user_id", "authentication_required"), ("missing_user", "authentication_required"),
    ("wrong_principal", "authentication_required"), ("missing_session", "authentication_required"),
    ("missing_csrf", "authentication_required"), ("missing_game", "game_not_found"),
    ("invalid_game", "game_not_found"), ("wrong_owner", "game_not_owned"),
])
def test_separate_and_joined_reads_reject_the_same_authority_changes(catalog, joined, change, code):
    store, principal, state, game_id, db, client = setup_store(catalog)
    store._consolidated_owned_reads = joined
    session, user = db["auth_sessions"].docs[principal.session_hash], db["users"].docs[ObjectId(principal.user_id)]
    if change == "logout": session["revoked_at"] = NOW
    elif change == "expired": session["expires_at"] = NOW
    elif change == "idle": session["last_seen_at"] = NOW - timedelta(seconds=1800)
    elif change == "disabled": user["status"] = "disabled"
    elif change == "session_version": session["auth_version"] += 1
    elif change == "user_version": user["auth_version"] += 1
    elif change == "bad_user_id": session["user_id"] = "invalid"
    elif change == "missing_user": db["users"].docs.clear()
    elif change == "wrong_principal": principal = principal.model_copy(update={"user_id": str(ObjectId())})
    elif change == "missing_session": db["auth_sessions"].docs.clear()
    elif change == "missing_csrf": del session["csrf_token"]
    elif change == "missing_game": db["games"].docs.clear()
    elif change == "invalid_game": game_id = "invalid"
    elif change == "wrong_owner": db["games"].docs[ObjectId(game_id)]["access"]["owner_user_id"] = str(ObjectId())
    with pytest.raises(SecurityError) as caught:
        store.load_owned_game(game_id, principal, NOW, 1800)
    assert caught.value.code == code
    assert not db["game_action_receipts"].docs


def test_all_remaining_reads_are_inventoried_without_private_values(catalog):
    measured = profile(catalog, scenarios(catalog)["allocation"], "allocation")
    assert len(measured["reads"]) == 15
    assert measured["groups"] == {
        "auth_sessions.find.authentication": 1, "users.find.authentication": 1,
        "auth_sessions.aggregate.none": 6, "game_action_receipts.find.none": 3,
        "auth_sessions.find.game": 1, "users.find.game": 1,
        "games.find.game": 1, "game_action_receipts.find.game": 1}
    assert all(row["session_supplied"] == (row["transaction"] != "none") for row in measured["reads"])
    import json
    text = json.dumps(measured)
    for forbidden in ("csrf-only-token", "encoded-test-hash", "Alice", "a"*64):
        assert forbidden not in text


@pytest.mark.parametrize("topology,expected", [("ReplicaSetWithPrimary", True), ("Unknown", False),
    ("Single", False), ("Sharded", False), ("ReplicaSetNoPrimary", False)])
def test_managed_lifespan_enables_join_only_for_known_replica_set(topology, expected):
    client = StartupClient()
    client.topology_description = SimpleNamespace(topology_type_name=topology)
    application = create_app(settings_loader=config, client_factory=lambda settings: client)
    with TestClient(application):
        assert application.state.phase4.games.store._consolidated_owned_reads is expected
    assert client.closed == 1


def test_unsupported_topology_keeps_first_pass_36_command_path(catalog, monkeypatch):
    import benchmark_npc as bench
    original = bench.setup_store
    def unverified(*args, **kwargs):
        bundle = original(*args, **kwargs)
        bundle[0]._consolidated_owned_reads = False
        return bundle
    monkeypatch.setattr(bench, "setup_store", unverified)
    result = run_case(catalog, scenarios(catalog)["allocation"], "allocation")
    assert (result["mongo_total"], result["find"], result["aggregate"]) == (36, 27, 0)


def test_join_is_fresh_never_used_by_transaction_and_cannot_write(catalog, monkeypatch):
    store, principal, state, game_id, db, client, service, _ = prepared(catalog)
    original = db["auth_sessions"].aggregate
    calls = []
    def observed(pipeline, **kwargs):
        assert kwargs == {"batchSize": 2}
        assert not any("$out" in s or "$merge" in s for s in pipeline)
        assert pipeline[0] == {"$match": {"_id": principal.session_hash}}
        calls.append(True)
        return original(pipeline, **kwargs)
    monkeypatch.setattr(db["auth_sessions"], "aggregate", observed)
    result = service.npc_step(principal, game_id, 0)
    assert len(calls) == 6 and result.state.revision == 1
    assert service.npc_step(principal, game_id, 0) == result
    assert len(calls) == 8
    db["users"].docs[ObjectId(principal.user_id)]["status"] = "disabled"
    with pytest.raises(SecurityError):
        service.npc_step(principal, game_id, 0)
    assert len(db["game_action_receipts"].docs) == 1


@pytest.mark.parametrize("code", [10334, 13, 11600])
def test_aggregate_size_fallback_is_read_only_and_other_failures_stay_closed(catalog, monkeypatch, code):
    store, principal, state, game_id, db, client = setup_store(catalog)
    before = copy.deepcopy({name:c.docs for name,c in db.items()})
    def failed(*args, **kwargs):
        raise OperationFailure("private-canary", code=code)
    monkeypatch.setattr(db["auth_sessions"], "aggregate", failed)
    if code == 10334:
        result = store.load_owned_game(game_id, principal, NOW, 1800)
        assert result["revision"] == 0
        db["auth_sessions"].docs[principal.session_hash]["revoked_at"] = NOW
        with pytest.raises(SecurityError) as caught:
            store.load_owned_game(game_id, principal, NOW, 1800)
        assert caught.value.code == "authentication_required"
        db["auth_sessions"].docs[principal.session_hash]["revoked_at"] = None
    else:
        with pytest.raises(SecurityError) as caught:
            store.load_owned_game(game_id, principal, NOW, 1800)
        assert caught.value.code == "persistence_unavailable" and "private-canary" not in str(caught.value)
    assert {name:c.docs for name,c in db.items()} == before


def test_aggregate_monitoring_is_allowlisted_read_without_command_or_reply_data():
    record = diag.RequestTimings()
    token = diag._current.set(record)
    try:
        listener = diag.NpcCommandListener()
        listener.succeeded(SimpleNamespace(command_name="aggregate", duration_micros=270000,
                                            reply={"secret": "private-canary"}))
        row = record.summary(200, "returned", True)
        assert row["mongo_commands"]["aggregate"]["count"] == 1
        assert row["mongo_by_category"]["read"]["total_ms"] == 270
        assert "private-canary" not in str(row)
    finally:
        diag._current.reset(token)



def test_same_database_concurrent_users_keep_joined_identity_and_games_separate(catalog, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock, local
    from app.services.authorized_game_service import AuthorizedGameService
    from test_phase4_mongo import Session
    first = prepared(catalog)
    store, alice, state, game_a, db, client, service_a, _ = first
    second = prepared(catalog)
    _, bob_seed, _, game_b, other_db, _, _, _ = second
    bob = bob_seed.model_copy(update={"session_hash": "b"*64, "username": "Bob"})
    user = copy.deepcopy(other_db["users"].docs[ObjectId(bob.user_id)])
    user.update(username="Bob", username_key="bob")
    db["users"].docs[user["_id"]] = user
    session = copy.deepcopy(other_db["auth_sessions"].docs[bob_seed.session_hash])
    session["_id"] = bob.session_hash
    db["auth_sessions"].docs[bob.session_hash] = session
    db["games"].docs[ObjectId(game_b)] = copy.deepcopy(other_db["games"].docs[ObjectId(game_b)])
    bob_store = MongoSecurityRepository(client, db, auth_writes_enabled=True, gameplay_writes_enabled=True,
                                         index_readiness=store._index_readiness, owned_lookup_compatible=True)
    service_b = AuthorizedGameService(bob_store, service_a.settings, lambda: NOW, catalog=catalog)
    barrier, seen = Barrier(2), local()
    aggregate = db["auth_sessions"].aggregate
    def synchronized(*args, **kwargs):
        if not getattr(seen, "entered", False):
            seen.entered = True
            barrier.wait(timeout=3)
        return aggregate(*args, **kwargs)
    monkeypatch.setattr(db["auth_sessions"], "aggregate", synchronized)
    transaction, lock = Session.with_transaction, Lock()
    def serialized(self, *args, **kwargs):
        with lock:
            return transaction(self, *args, **kwargs)
    monkeypatch.setattr(Session, "with_transaction", serialized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service_a.npc_step, alice, game_a, state.revision),
                   pool.submit(service_b.npc_step, bob, game_b, state.revision)]
        assert [f.result(timeout=5).state.revision for f in futures] == [state.revision+1]*2
    monkeypatch.setattr(db["auth_sessions"], "aggregate", aggregate)
    assert {doc["game_id"] for doc in db["game_action_receipts"].docs.values()} == {game_a, game_b}
    for service, principal, wrong in [(service_a, alice, game_b), (service_b, bob, game_a)]:
        with pytest.raises(SecurityError) as caught:
            service.npc_step(principal, wrong, state.revision)
        assert caught.value.code == "game_not_owned"
    assert len(db["game_action_receipts"].docs) == 2


def test_revision_change_after_preparation_reloads_and_blocks_stale_dice(catalog, monkeypatch):
    from app.engine.errors import RevisionConflict
    from app.services.npc_service import NpcController
    store, principal, state, game_id, db, client, service, dice = prepared(catalog, "dice_exchange")
    submit = NpcController.submit
    def raced(controller, submission):
        db["games"].docs[ObjectId(game_id)]["revision"] += 1
        return submit(controller, submission)
    monkeypatch.setattr(NpcController, "submit", raced)
    with pytest.raises(RevisionConflict):
        service.npc_step(principal, game_id, state.revision)
    assert dice.calls == 0
    assert not db["game_action_receipts"].docs
    assert db["games"].docs[ObjectId(game_id)]["revision"] == state.revision+1


@pytest.mark.parametrize("collection", ["auth_sessions", "users", "games"])
@pytest.mark.parametrize("collation,enabled", [(None, True), ({"locale": "simple"}, True), ({"locale": "en", "strength": 2}, False)])
def test_non_simple_collection_collation_preserves_separate_query_semantics(collection, collation, enabled):
    client = StartupClient()
    client.topology_description = SimpleNamespace(topology_type_name="ReplicaSetWithPrimary")
    item = next(item for item in client.database.metadata if item["name"] == collection)
    if collation is not None:
        item["options"]["collation"] = collation
    application = create_app(settings_loader=config, client_factory=lambda settings: client)
    with TestClient(application):
        store = application.state.phase4.games.store
        assert store._consolidated_owned_reads is enabled
    assert client.closed == 1
