"""Validator-enabled service/transaction proofs, skipped without explicit opt-in.

Both target modes use the same cases. Atlas mode has additional pinned-target
authorization; imports never connect or read application configuration.
"""
import copy
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bson import Int64, ObjectId
from pymongo.errors import DuplicateKeyError, WriteError

from app.engine.errors import PersistenceUnavailable
from app.engine.game_setup import initialize_game
from app.engine.state_adapter import load_runtime
from app.models.actions import ActionCommand, Allocate, Allocation, EndTurn, Roll, Skip, StartAttack
from app.models.auth import Credentials
from app.models.game import Game, GameSetupRequest
from app.repositories.action_repository import MongoActionRepository, runtime_document
from app.repositories.mongo_provisioning import (
    ProvisioningError, preflight_database, provision_database, verify_database,
)
from app.repositories.security_repository import MongoSecurityRepository
from app.security.config import SecuritySettings
from app.services.auth_service import AuthService, token_hash
from app.services.authorized_game_service import AuthorizedGameService
from app.services.game_action_service import GameActionService
from integration.validator_harness import authorized_client, fresh_database
from npc_helpers import npc_state
from phase2_helpers import FixedDice, context, make_runtime, revise

pytestmark = pytest.mark.disposable_mongo
PASSWORD = "Disposable validator words 2027!"


@pytest.fixture(scope="module")
def validator_client(request):
    with authorized_client(request) as client:
        yield client


@pytest.fixture
def provisioned_database(validator_client):
    with fresh_database(validator_client) as database:
        yield database


@pytest.fixture
def unprovisioned_database(validator_client):
    with fresh_database(validator_client, provision=False) as database:
        yield database


@pytest.fixture
def real_security(provisioned_database, catalog):
    database = provisioned_database
    now = datetime.now(timezone.utc)
    now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    clock = lambda: now
    # Injected test objects only; no production settings or activation.
    settings = SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True,
                                trusted_origins=("https://testserver",))
    repository = MongoSecurityRepository(database.client, database, auth_writes_enabled=True,
                                         gameplay_writes_enabled=True)
    auth = AuthService(repository, settings, clock)
    credentials = Credentials(username=f"V_{ObjectId()}", password=PASSWORD)
    ip = f"validator-{ObjectId()}"
    user = auth.register(credentials, ip)
    login = auth.login(credentials, ip)
    principal = auth.authenticate(login.token)
    games = AuthorizedGameService(repository, settings, clock, FixedDice(), catalog, random.Random(7))
    return SimpleNamespace(database=database, repository=repository, settings=settings, clock=clock,
                           auth=auth, credentials=credentials, ip=ip, user=user, login=login,
                           principal=principal, games=games, catalog=catalog)


def _assert_rejected(collection, document):
    before = collection.count_documents({})
    with pytest.raises(WriteError) as error:
        collection.insert_one(document)
    assert error.value.code == 121
    assert collection.count_documents({}) == before


def test_real_service_auth_owned_game_and_logout(real_security):
    bundle = real_security
    document = bundle.games.create_game(bundle.principal, GameSetupRequest(
        game_name="Validator service-owned game", starting_country_id="south-africa"), "owned-service")
    user = bundle.database.users.find_one({"_id": ObjectId(bundle.user.id)})
    session = bundle.database.auth_sessions.find_one({"_id": token_hash(bundle.login.token)})
    owned = bundle.database.games.find_one({"_id": ObjectId(document["_id"])})
    assert isinstance(user["created_at"], datetime) and user["password_hash"].startswith("$argon2id$")
    assert session["user_id"] == bundle.user.id and session["revoked_at"] is None
    assert session["revision"] > 0 and isinstance(session["expires_at"], datetime)
    assert owned["access"]["owner_user_id"] == bundle.user.id
    assert owned["access"]["human_player_id"] == "human"
    assert isinstance(owned["access"]["bound_at"], datetime)
    assert owned["creation"]["key"] == "owned-service" and len(owned["creation"]["fingerprint"]) == 64
    assert bundle.database.auth_rate_limits.count_documents({}) > 0
    for bucket in bundle.database.auth_rate_limits.find({}):
        assert type(bucket["count"]) is int and isinstance(bucket["expires_at"], datetime)
    bundle.auth.logout(bundle.principal)
    assert isinstance(bundle.database.auth_sessions.find_one({"_id": session["_id"]})["revoked_at"], datetime)
    verify_database(bundle.database)


def test_real_schema_history_bson_and_iso_dates(provisioned_database, catalog, request):
    initial = initialize_game(GameSetupRequest(game_name="History", starting_country_id="south-africa"), catalog)
    bson_setup = initial.model_dump(mode="json")
    bson_setup["created_at"] = initial.created_at
    runtime = make_runtime(catalog)
    documents = [Game(game_name="Legacy").model_dump(), initial.model_dump(mode="json"),
                 bson_setup, runtime.model_dump(mode="json"), runtime_document(runtime)]
    for document in documents:
        assert isinstance(provisioned_database.games.insert_one(document).inserted_id, ObjectId)
    verify_database(provisioned_database)
    if request.config.getoption("--local-provisioning-mongodb"):
        # Retain real local reapplication coverage without adding remote apply.
        provision_database(provisioned_database, apply=True, confirmation=provisioned_database.name)
        verify_database(provisioned_database)


@pytest.mark.parametrize("version", [None, 4, "3", 3.0, True])
def test_real_malformed_version_cannot_use_legacy_branch(provisioned_database, catalog, version):
    document = runtime_document(make_runtime(catalog))
    document["schema_version"] = version
    _assert_rejected(provisioned_database.games, document)


@pytest.mark.parametrize("collection,invalid", [
    ("users", {"username": "missing security fields"}),
    ("auth_sessions", {"_id": "plaintext-token"}),
    ("auth_rate_limits", {"_id": "a" * 64, "count": True, "expires_at": "2027-01-01"}),
    ("game_action_receipts", {"game_id": "missing receipt"}),
])
def test_real_security_validation(provisioned_database, collection, invalid):
    _assert_rejected(provisioned_database[collection], invalid)


def test_real_supported_integer_and_rejected_dates(real_security):
    database = real_security.database
    database.auth_rate_limits.insert_one({"_id": "b" * 64, "count": Int64(2),
                                          "expires_at": real_security.clock() + timedelta(hours=1)})
    _assert_rejected(database.auth_rate_limits, {"_id": "c" * 64, "count": 2.5,
                                               "expires_at": real_security.clock()})
    game = runtime_document(make_runtime(real_security.catalog))
    game["updated_at"] = "not-a-date"
    _assert_rejected(database.games, game)
    session = database.auth_sessions.find_one({"_id": real_security.principal.session_hash})
    session["_id"] = "d" * 64
    session["expires_at"] = real_security.clock().isoformat()
    _assert_rejected(database.auth_sessions, session)


def _action_service(database, state, clock):
    game_id = str(database.games.insert_one(runtime_document(state)).inserted_id)
    repository = MongoActionRepository(database.client, database, gameplay_writes_enabled=True)
    return game_id, repository, GameActionService(repository, FixedDice(), clock)


def _execute(service, game_id, state, action, action_id):
    return service.execute(game_id, context(state), ActionCommand(
        action_id=action_id, expected_revision=state.revision, action=action)).state


def phase_scenario(catalog, *, final=False):
    """Labelled legal states/actions; also exercised offline before real tests."""
    if final:
        changes = {i: {"owner_id": "human"} for i in range(2, 10)}
        changes.update({0: {"soldiers": 2}, 1: {"soldiers": 1}})
        state = revise(make_runtime(catalog), country_changes=changes)
        return state, [StartAttack(source_id=state.countries[0].id, target_id=state.countries[1].id), Roll()]
    state = revise(make_runtime(catalog), round=2, phase="allocating", pending_reinforcements=2,
                   country_changes={0: {"soldiers": 3}, 1: {"soldiers": 1}})
    source, target = state.countries[:2]
    return state, [Allocate(allocations=(Allocation(country_id=source.id, amount=2),)),
                   StartAttack(source_id=source.id, target_id=target.id), Roll(), EndTurn()]


@pytest.mark.parametrize("final", [False, True], ids=["allocation-conquest-end-turn", "final-victory"])
def test_real_service_valid_gameplay_phase_transitions(provisioned_database, catalog, final):
    state, actions = phase_scenario(catalog, final=final)
    game_id, repository, service = _action_service(provisioned_database, state, lambda: state.updated_at)
    service._dice = FixedDice([6, 1])
    expected_phases = ["attacking", "finished"] if final else ["deciding", "attacking", "post_attack", "allocating"]
    for index, (action, phase) in enumerate(zip(actions, expected_phases)):
        state = _execute(service, game_id, state, action, f"phase-{index}")
        assert state.phase == phase and load_runtime(repository.load_game(game_id)) == state
    if final:
        assert state.status == "completed" and state.winner == "human"
    else:
        assert state.active_player_id == "npc-2"
    assert provisioned_database.game_action_receipts.count_documents({"game_id": game_id}) == len(actions)
    verify_database(provisioned_database)


@pytest.mark.parametrize("kind", ["human", "npc"])
def test_real_historical_receipt_fingerprint_and_replay(provisioned_database, catalog, kind):
    state = make_runtime(catalog) if kind == "human" else npc_state(catalog)
    game_id, repository, service = _action_service(provisioned_database, state, lambda: state.updated_at)
    actor = context(state)
    command = ActionCommand(action_id=f"historical-{kind}", expected_revision=state.revision, action=Skip())
    payload = {"actor": actor.model_dump(mode="json"), "command": command.model_dump(mode="json")}
    historical_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = service.execute(game_id, actor, command)
    match = {"_id": repository.receipt_id(game_id, command.action_id)}
    stored = provisioned_database.game_action_receipts.find_one(match)
    assert stored["fingerprint"] == historical_hash and stored["result"]["npc_decision"] is None
    provisioned_database.game_action_receipts.update_one(match, {"$unset": {"result.npc_decision": ""}})
    before = provisioned_database.game_action_receipts.find_one(match)
    fresh = GameActionService(MongoActionRepository(provisioned_database.client, provisioned_database,
                                                  gameplay_writes_enabled=True), FixedDice(),
                             lambda: pytest.fail("Replay called the clock"))
    assert fresh.execute(game_id, actor, command) == result
    assert provisioned_database.game_action_receipts.find_one(match) == before
    verify_database(provisioned_database)


def test_real_owned_npc_evidence_current_receipt_and_replay(real_security):
    bundle = real_security
    state = npc_state(bundle.catalog, source_soldiers=3, changes={0: {"soldiers": 2}})
    game_id = str(bundle.repository.create_owned_game(bundle.principal, state, "npc-evidence", "fixture",
                                                     bundle.clock(), bundle.settings.idle_seconds)["_id"])
    result = bundle.games.npc_step(bundle.principal, game_id, state.revision)
    assert result.npc_decision is not None
    receipt = bundle.database.game_action_receipts.find_one({"game_id": game_id})
    assert receipt["result"]["npc_decision"] == result.npc_decision.model_dump(mode="json")
    assert bundle.games.npc_step(bundle.principal, game_id, state.revision) == result
    assert bundle.database.game_action_receipts.count_documents({"game_id": game_id}) == 1
    malformed = copy.deepcopy(receipt)
    malformed["_id"] += "-invalid"
    malformed["result"]["npc_decision"]["strategy_version"] = "unknown-policy"
    _assert_rejected(bundle.database.game_action_receipts, malformed)
    verify_database(bundle.database)


def test_real_validator_rejection_rolls_back_game_session_and_user(real_security, monkeypatch):
    bundle = real_security
    state = make_runtime(bundle.catalog)
    game_id = str(bundle.repository.create_owned_game(bundle.principal, state, "rollback", "fixture",
                                                     bundle.clock(), bundle.settings.idle_seconds)["_id"])
    game_match = {"_id": ObjectId(game_id)}
    session_match = {"_id": bundle.principal.session_hash}
    user_match = {"_id": ObjectId(bundle.user.id)}
    before = {"game": bundle.database.games.find_one(game_match),
              "session": bundle.database.auth_sessions.find_one(session_match),
              "user": bundle.database.users.find_one(user_match)}
    original_store = bundle.repository.action_store
    original_insert = bundle.repository._receipts.insert_one
    observed = []

    def instrumented_store(*args, **kwargs):
        store = original_store(*args, **kwargs)
        store._receipts = bundle.repository._receipts
        return store

    def reject_invalid_receipt(document, *, session):
        assert session.in_transaction
        staged = bundle.database.games.find_one(game_match, session=session)
        staged_session = bundle.database.auth_sessions.find_one(session_match, session=session)
        staged_user = bundle.database.users.find_one(user_match, session=session)
        assert staged["revision"] == state.revision + 1
        assert staged_session["revision"] > before["session"]["revision"]
        assert staged_user["authorization_revision"] > before["user"]["authorization_revision"]
        invalid = copy.deepcopy(document)
        invalid["result"]["state"]["revision"] = -1
        try:
            original_insert(invalid, session=session)
        except WriteError as error:
            assert error.code == 121
            observed.append(error.code)
            raise
        pytest.fail("MongoDB accepted an invalid receipt")

    monkeypatch.setattr(bundle.repository, "action_store", instrumented_store)
    monkeypatch.setattr(bundle.repository._receipts, "insert_one", reject_invalid_receipt)
    command = ActionCommand(action_id="validator-rollback", expected_revision=state.revision, action=Skip())
    with pytest.raises(PersistenceUnavailable):
        bundle.games.human_action(bundle.principal, game_id, command)
    assert observed == [121]
    assert bundle.database.games.find_one(game_match) == before["game"]
    assert bundle.database.auth_sessions.find_one(session_match) == before["session"]
    assert bundle.database.users.find_one(user_match) == before["user"]
    assert bundle.database.game_action_receipts.count_documents({"game_id": game_id}) == 0
    monkeypatch.setattr(bundle.repository._receipts, "insert_one", original_insert)
    assert bundle.games.human_action(bundle.principal, game_id, command).state.revision == state.revision + 1
    verify_database(bundle.database)


@pytest.mark.parametrize("collection", ["users", "games"])
def test_real_duplicate_unique_values_preflight_before_ddl(real_security, unprovisioned_database, collection):
    bundle = real_security
    if collection == "users":
        document = bundle.database.users.find_one({"_id": ObjectId(bundle.user.id)})
    else:
        owned = bundle.games.create_game(bundle.principal, GameSetupRequest(
            game_name="Duplicate ownership fixture", starting_country_id="south-africa"), "duplicate-owner")
        document = bundle.database.games.find_one({"_id": ObjectId(owned["_id"])})
    document.pop("_id")
    unprovisioned_database[collection].insert_one(copy.deepcopy(document))
    unprovisioned_database[collection].insert_one(copy.deepcopy(document))
    before = list(unprovisioned_database.list_collections())
    with pytest.raises(ProvisioningError) as failure:
        preflight_database(unprovisioned_database)
    assert failure.value.category == "unique_values_conflict"
    assert failure.value.collection == collection and not failure.value.may_have_changes
    assert list(unprovisioned_database.list_collections()) == before


@pytest.mark.parametrize("index", ["same-name", "same-keys"])
def test_real_incompatible_indexes_preflight_without_repair(unprovisioned_database, index):
    users = unprovisioned_database.users
    if index == "same-name":
        users.create_index([("username", 1)], name="username_key_unique", unique=True)
    else:
        users.create_index([("username_key", 1)], name="wrong_semantics")
    before = users.index_information()
    with pytest.raises(ProvisioningError) as failure:
        preflight_database(unprovisioned_database)
    assert failure.value.category == "index_conflict"
    assert not failure.value.may_have_changes
    assert users.index_information() == before


def test_real_unique_indexes_reject_duplicate_service_documents(real_security):
    bundle = real_security
    user = bundle.database.users.find_one({"_id": ObjectId(bundle.user.id)})
    user.pop("_id")
    with pytest.raises(DuplicateKeyError):
        bundle.database.users.insert_one(user)
    owned = bundle.games.create_game(bundle.principal, GameSetupRequest(
        game_name="Unique ownership fixture", starting_country_id="south-africa"), "unique-owner")
    game = bundle.database.games.find_one({"_id": ObjectId(owned["_id"])})
    game.pop("_id")
    with pytest.raises(DuplicateKeyError):
        bundle.database.games.insert_one(game)
    verify_database(bundle.database)
