"""Offline index-lifespan and read-reuse safety; no production clients or data."""
import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo.errors import OperationFailure, PyMongoError

from app.engine.errors import ActionIdConflict, PersistenceUnavailable
from app.models.actions import ActionCommand, ActorContext, Skip
from app.models.game_access import access_from_document
from app.repositories.phase4_indexes import IndexReadiness
from app.security.config import SecuritySettings
from app.security.errors import SecurityError
from app.services.authorized_game_service import AuthorizedGameService
from app.services.game_action_service import GameActionService
from app.services.npc_service import NpcController
from benchmark_npc import scenarios
from benchmark_npc_mongodb import run_case
from phase2_helpers import FixedDice, NOW
from startup_helpers import StartupClient
from test_phase4_mongo import setup_store, Session
from test_startup import config, create_app, ORIGIN


def prepared(catalog, name="attack_start"):
    store, principal, _, game_id, db, client = setup_store(catalog)
    state = scenarios(catalog)[name]
    db["games"].docs[ObjectId(game_id)].update(state.model_dump())
    readiness = IndexReadiness(db)
    readiness.ensure()
    store._index_readiness = readiness
    settings = SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True)
    dice = FixedDice([6, 1] * 200)
    service = AuthorizedGameService(store, settings, lambda: NOW, dice=dice, catalog=catalog)
    return store, principal, state, game_id, db, client, service, dice


def metadata_count(db):
    return sum(op == "index_information" for c in db.values() for op, *_ in c.calls)


def test_guard_requires_success_same_database_and_open_lifespan(catalog):
    store, *_, db, client = setup_store(catalog)
    readiness = IndexReadiness(db)
    with pytest.raises(SecurityError):
        readiness.require_ready(db)
    readiness.ensure()
    assert metadata_count(db) == 5
    readiness.ensure()
    readiness.require_ready(db)
    assert metadata_count(db) == 5
    with pytest.raises(SecurityError):
        readiness.require_ready(dict(db))
    readiness.close()
    for call in (lambda: readiness.require_ready(db), readiness.ensure):
        with pytest.raises(SecurityError):
            call()


def test_simultaneous_initialization_is_serial_and_success_is_reused(catalog, monkeypatch):
    *_, db, client = setup_store(catalog)
    readiness = IndexReadiness(db)
    entered, release = Event(), Event()
    original = db["users"].index_information
    def slow():
        entered.set()
        assert release.wait(3)
        return original()
    monkeypatch.setattr(db["users"], "index_information", slow)
    with ThreadPoolExecutor(max_workers=8) as pool:
        first = pool.submit(readiness.ensure)
        try:
            assert entered.wait(3)
            others = [pool.submit(readiness.ensure) for _ in range(7)]
            with pytest.raises(SecurityError):
                readiness.require_ready(db)
        finally:
            release.set()
        for future in [first, *others]:
            future.result(timeout=3)
    assert metadata_count(db) == 5


@pytest.mark.parametrize("failure", ["missing", "driver"])
def test_failed_initialization_cannot_authorize_writes_and_can_retry(catalog, monkeypatch, failure):
    store, _, _, _, db, _ = setup_store(catalog)
    readiness = IndexReadiness(db)
    store._index_readiness = readiness
    original = db["users"].index_information
    if failure == "missing":
        indexes = db["users"].indexes
        db["users"].indexes = {}
    else:
        def fail():
            raise PyMongoError("private-canary")
        monkeypatch.setattr(db["users"], "index_information", fail)
    with pytest.raises(SecurityError) as caught:
        readiness.ensure()
    assert "private-canary" not in str(caught.value)
    with pytest.raises(SecurityError):
        store.consume_limit("blocked", 10, 60, NOW)
    assert not db["auth_rate_limits"].docs
    if failure == "missing":
        db["users"].indexes = indexes
    else:
        monkeypatch.setattr(db["users"], "index_information", original)
    readiness.ensure()
    assert store.consume_limit("allowed", 10, 60, NOW)
    count = metadata_count(db)
    for _ in range(3):
        assert store.consume_limit("allowed", 10, 60, NOW)
    assert metadata_count(db) == count


def test_each_real_application_lifespan_verifies_once_and_invalidates_after_stop(monkeypatch):
    from app.startup import StartupError
    clients = [StartupClient(), StartupClient(), StartupClient()]
    calls = []
    for client in clients:
        for collection in client.database.collections.values():
            original = collection.index_information
            def counted(original=original, client=client):
                calls.append(client)
                return original()
            monkeypatch.setattr(collection, "index_information", counted)
    clients[1].database.collections["users"].indexes.clear()
    settings = config(PHASE4_AUTH_WRITES_ENABLED="true", PHASE4_TRUSTED_ORIGINS='["https://game.example"]')
    queue = iter(clients)
    application = create_app(settings_loader=lambda: settings, client_factory=lambda settings: next(queue))
    with TestClient(application):
        store = application.state.phase4.auth.store
        for _ in range(4):
            store._auth_writes()
        assert calls.count(clients[0]) == 5
    with pytest.raises(SecurityError):
        store._auth_writes()
    with pytest.raises(StartupError, match="indexes_not_ready"):
        with TestClient(application):
            pytest.fail("Missing indexes passed startup")
    with TestClient(application):
        application.state.phase4.auth.store._auth_writes()
        assert calls.count(clients[2]) == 5
    assert [c.closed for c in clients] == [1, 1, 1]


@pytest.mark.parametrize("name", ["allocation", "attack_start", "dice_exchange", "conquest", "transfer", "end_turn", "skip"])
def test_steady_state_command_budget_and_exact_saved_replay(catalog, name):
    measured = run_case(catalog, scenarios(catalog)[name], name)
    assert (measured["mongo_total"], measured["listIndexes"], measured["find"], measured["writes"], measured["commits"]) == (24, 0, 9, 7, 2)
    assert measured["aggregate"] == 6
    assert (measured["owned_game_loads"], measured["authorizations"], measured["index_verifications"]) == (7, 8, 0)
    store, principal, state, game_id, db, _, service, dice = prepared(catalog, name)
    first = service.npc_step(principal, game_id, state.revision)
    before = copy.deepcopy((db["games"].docs, db["game_action_receipts"].docs))
    dice_calls = dice.calls
    assert service.npc_step(principal, game_id, state.revision) == first
    assert (db["games"].docs, db["game_action_receipts"].docs) == before
    assert dice.calls == dice_calls
    assert metadata_count(db) == 5


@pytest.mark.parametrize("change", ["logout", "owner", "access", "disabled", "version"])
def test_changes_after_facade_lookup_block_before_receipt_read(catalog, monkeypatch, change):
    store, principal, _, game_id, db, _, service, _ = prepared(catalog)
    def revoke(*args):
        if change == "logout": db["auth_sessions"].docs[principal.session_hash]["revoked_at"] = NOW
        elif change == "owner": db["games"].docs[ObjectId(game_id)]["access"]["owner_user_id"] = str(ObjectId())
        elif change == "access": db["games"].docs[ObjectId(game_id)]["access"]["version"] += 1
        elif change == "disabled": db["users"].docs[ObjectId(principal.user_id)]["status"] = "disabled"
        else: db["users"].docs[ObjectId(principal.user_id)]["auth_version"] += 1
    monkeypatch.setattr(service, "_rate", revoke)
    db["game_action_receipts"].calls.clear()
    with pytest.raises(SecurityError):
        service.npc_step(principal, game_id, 0)
    assert not db["game_action_receipts"].calls
    assert db["games"].docs[ObjectId(game_id)]["revision"] == 0


@pytest.mark.parametrize("change", ["logout", "owner", "access", "disabled", "version"])
def test_commit_transaction_still_rechecks_live_authority(catalog, change):
    store, principal, _, game_id, db, client, service, _ = prepared(catalog)
    def revoke():
        if change == "logout": db["auth_sessions"].docs[principal.session_hash]["revoked_at"] = NOW
        elif change == "owner": db["games"].docs[ObjectId(game_id)]["access"]["owner_user_id"] = str(ObjectId())
        elif change == "access": db["games"].docs[ObjectId(game_id)]["access"]["version"] += 1
        elif change == "disabled": db["users"].docs[ObjectId(principal.user_id)]["status"] = "disabled"
        else: db["users"].docs[ObjectId(principal.user_id)]["auth_version"] += 1
    client.before_transaction = revoke
    with pytest.raises(SecurityError):
        service.npc_step(principal, game_id, 0)
    assert not db["game_action_receipts"].docs
    assert db["games"].docs[ObjectId(game_id)]["revision"] == 0


def test_lost_acknowledgement_recovers_original_receipt_without_second_roll(catalog, monkeypatch):
    store, principal, state, game_id, db, _, service, dice = prepared(catalog, "dice_exchange")
    # The complete transaction succeeds before the connection is reported lost.
    from test_phase4_mongo import Session
    transaction = Session.with_transaction
    def uncertain(self, *args, **kwargs):
        transaction(self, *args, **kwargs)
        raise PyMongoError("lost acknowledgement")
    monkeypatch.setattr(Session, "with_transaction", uncertain)
    with pytest.raises(PersistenceUnavailable):
        service.npc_step(principal, game_id, state.revision)
    assert len(db["game_action_receipts"].docs) == 1
    count = dice.calls
    monkeypatch.setattr(Session, "with_transaction", transaction)
    saved = service.npc_step(principal, game_id, state.revision)
    assert saved.state.revision == state.revision + 1
    assert dice.calls == count and len(db["game_action_receipts"].docs) == 1
    db["auth_sessions"].docs[principal.session_hash]["revoked_at"] = NOW
    with pytest.raises(SecurityError):
        service.npc_step(principal, game_id, state.revision)


def test_two_prepared_npc_submissions_commit_only_one_receipt(catalog, monkeypatch):
    store, principal, _, game_id, db, _, service, _ = prepared(catalog, "allocation")
    first_store, first_actions = service._actions(principal, game_id, access_from_document(db["games"].docs[ObjectId(game_id)]))
    second_store, second_actions = service._actions(principal, game_id, access_from_document(db["games"].docs[ObjectId(game_id)]))
    first, second = NpcController(first_store, first_actions), NpcController(second_store, second_actions)
    a, b = first.prepare(game_id), second.prepare(game_id)
    assert a == b
    # Serialize only the fake transaction mechanism: it is not a MongoDB proof.
    original = Session.with_transaction
    lock = Lock()
    def serial(self, *args, **kwargs):
        with lock:
            return original(self, *args, **kwargs)
    monkeypatch.setattr(Session, "with_transaction", serial)
    barrier = Barrier(2)
    def submit(controller, submission):
        barrier.wait(timeout=3)
        return controller.submit(submission)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, first, a), pool.submit(submit, second, b)]
        outcomes = [f.result(timeout=5) for f in futures]
    assert outcomes[0] == outcomes[1]
    assert len(db["game_action_receipts"].docs) == 1
    assert db["games"].docs[ObjectId(game_id)]["revision"] == 1


def test_transaction_retry_and_conflicting_fingerprint_remain_safe(catalog, monkeypatch):
    store, principal, state, game_id, db, client, service, dice = prepared(catalog, "dice_exchange")
    client.retry_transient = True
    original = db["users"].update_one
    failures = []
    def conflict_once(*args, **kwargs):
        if kwargs.get("session") is not None and not failures:
            failures.append(True)
            raise OperationFailure("synthetic conflict", code=112, details={"errorLabels": ["TransientTransactionError"]})
        return original(*args, **kwargs)
    monkeypatch.setattr(db["users"], "update_one", conflict_once)
    result = service.npc_step(principal, game_id, state.revision)
    assert len(failures) == 1 and len(db["game_action_receipts"].docs) == 1
    assert db["auth_sessions"].docs[principal.session_hash]["revision"] == 1
    assert db["users"].docs[ObjectId(principal.user_id)]["authorization_revision"] == 1
    receipt = next(iter(db["game_action_receipts"].docs.values()))
    scoped, actions = service._actions(principal, game_id, access_from_document(db["games"].docs[ObjectId(game_id)]))
    command = ActionCommand.model_validate(receipt["command"])
    with pytest.raises(ActionIdConflict):
        actions.execute(game_id, ActorContext.model_validate(receipt["actor"]),
                        command.model_copy(update={"action": Skip()}))


@pytest.mark.parametrize("enabled", [False, True])
def test_managed_http_diagnostics_switch_headers_and_saved_body(catalog, monkeypatch, caplog, enabled):
    import json
    import logging
    from app import npc_diagnostics as diag
    from app.services.auth_service import AuthService, token_hash
    from app.services.phase4_context import Phase4Context
    from app.services.public_game_service import public_result

    store, principal, _, game_id, db, _, service, _ = prepared(catalog)
    raw = "t" * 43  # Synthetic fixture, never an external session.
    session = db["auth_sessions"].docs.pop(principal.session_hash)
    session["_id"] = token_hash(raw)
    db["auth_sessions"].docs[session["_id"]] = session
    settings = SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True,
                                trusted_origins=(ORIGIN,))
    auth = AuthService(store, settings, clock=lambda: NOW)
    service.settings = settings
    handoff = diag.DiagnosticLogHandoff()
    if enabled:
        assert handoff.start()
    monkeypatch.setattr(diag, "DiagnosticLogHandoff", lambda: handoff)
    monkeypatch.setenv("NPC_PERFORMANCE_DIAGNOSTICS", str(enabled).lower())
    caplog.set_level(logging.INFO, logger=diag.logger.name)
    application = create_app()
    application.state.phase4 = Phase4Context(settings, auth, service)
    try:
        http = TestClient(application, base_url=ORIGIN)
        http.cookies.set(settings.cookie_name, raw)
        headers = {"Origin": ORIGIN, "X-CSRF-Token": principal.csrf_token}
        url = f"/games/{game_id}/npc-steps"
        response = http.post(url, headers=headers, json={"expected_revision": 0})
        assert response.status_code == 200
        receipt = next(iter(db["game_action_receipts"].docs.values()))
        from app.services.game_action_service import ActionReceipt
        saved = ActionReceipt.model_validate({k: v for k, v in receipt.items() if k != "_id"})
        assert response.json() == public_result(saved.result)
        assert response.headers["cache-control"] == "no-store"
        assert ("x-npc-trace-id" in response.headers) == enabled
        if enabled:
            with handoff._queue.all_tasks_done:
                assert handoff._queue.all_tasks_done.wait_for(lambda: handoff._queue.unfinished_tasks == 0, timeout=3)
            row, = [json.loads(record.getMessage()) for record in caplog.records if record.name == diag.logger.name]
            assert row["trace_id"] == response.headers["x-npc-trace-id"]
            assert row["spans_inclusive"]["authorization"]["count"] == 8
            assert row["spans_inclusive"]["owned_game_load"]["count"] == 7
            assert "index_verification" not in row["spans_inclusive"]
            text = json.dumps(row)
            for private in (raw, principal.csrf_token, principal.user_id, game_id, "Alice"):
                assert private not in text
        else:
            assert handoff._thread is None
            assert not [r for r in caplog.records if r.name == diag.logger.name]
        # Real dependency checks: failed CSRF, missing session and spectator owner.
        before = copy.deepcopy((db["games"].docs, db["game_action_receipts"].docs))
        assert http.post(url, headers={"Origin": ORIGIN}, json={"expected_revision": 0}).status_code == 403
        assert http.post(url, headers={**headers, "X-CSRF-Token": "invalid"}, json={"expected_revision": 0}).status_code == 403
        db["games"].docs[ObjectId(game_id)]["access"]["owner_user_id"] = str(ObjectId())
        assert http.post(url, headers=headers, json={"expected_revision": 0}).status_code == 403
        db["games"].docs = before[0]
        session["expires_at"] = NOW
        assert http.post(url, headers=headers, json={"expected_revision": 0}).status_code == 401
        http.cookies.clear()
        assert http.post(url, headers=headers, json={"expected_revision": 0}).status_code == 401
        assert (db["games"].docs, db["game_action_receipts"].docs) == before
        assert metadata_count(db) == 5
    finally:
        handoff.stop()
        assert handoff.stopped.wait(3)


def test_independent_users_and_databases_do_not_share_readiness_or_state(catalog):
    first, second = prepared(catalog), prepared(catalog)
    assert first[1].user_id != second[1].user_id
    barrier = Barrier(2)
    def play(bundle):
        _, principal, _, game_id, _, _, service, _ = bundle
        barrier.wait(timeout=3)
        return service.npc_step(principal, game_id, 0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(play, bundle) for bundle in (first, second)]
        assert [f.result(timeout=5).state.revision for f in results] == [1, 1]
    for own, other in ((first, second), (second, first)):
        store, principal, _, game_id, db, _, service, _ = own
        assert len(db["game_action_receipts"].docs) == 1
        assert metadata_count(db) == 5
        with pytest.raises(SecurityError):
            store._index_readiness.require_ready(other[4])
        with pytest.raises(SecurityError):
            service.npc_step(other[1], game_id, 0)
