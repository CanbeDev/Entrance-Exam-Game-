"""Real MongoDB proof; skipped unless explicitly requested. Never loads .env."""
import getpass
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.engine.errors import PersistenceUnavailable, RevisionConflict
from app.engine.game_setup import initialize_game
from app.engine.state_adapter import load_runtime
from app.models.actions import ActionCommand, Roll, Skip, StartAttack
from app.models.game import GameSetupRequest
from app.repositories.action_repository import MongoActionRepository, runtime_document
from app.services.game_action_service import GameActionService, command_fingerprint
from app.services.npc_service import NpcController
from integration.mongo_safety import parse_test_cluster_hosts, validate_disposable_uri
from npc_helpers import npc_state
from phase2_helpers import FixedDice, NOW, context, make_runtime, step

pytestmark = pytest.mark.disposable_mongo

DISPOSABLE_DATABASE_PREFIX = "geo_p2_"
MAX_DATABASE_NAME_BYTES = 38


def generate_disposable_database_name():
    name = DISPOSABLE_DATABASE_PREFIX + str(ObjectId())
    if len(name.encode("utf-8")) > MAX_DATABASE_NAME_BYTES:
        raise ValueError("Disposable database name exceeds the 38-byte limit")
    return name


@pytest.fixture(scope="module")
def disposable_database(request):
    if not request.config.getoption("--disposable-mongodb"):
        pytest.skip("Real MongoDB verification requires --disposable-mongodb and a dedicated disposable target")
    configured_hosts = request.config.getoption("--disposable-mongodb-hosts")
    if not configured_hosts or len(configured_hosts) != 1:
        pytest.fail("Specify --disposable-mongodb-hosts exactly once with the dedicated test hostnames", pytrace=False)
    try:
        allowed_hosts = parse_test_cluster_hosts(configured_hosts[0])
    except ValueError as error:
        pytest.fail(str(error), pytrace=False)
    print("Use a local replica set or separate NON-PRODUCTION Atlas project. No production URI.")
    if input("Type DISPOSABLE to authorize creation and cleanup of a fresh test database: ") != "DISPOSABLE":
        pytest.fail("Disposable database authorization was not provided", pytrace=False)
    uri = getpass.getpass("Dedicated test MongoDB URI (hidden; never read from .env): ")
    try:
        validate_disposable_uri(uri, allowed_hosts)
    except ValueError as error:
        pytest.fail(str(error), pytrace=False)
    client = None
    database = None
    database_name = generate_disposable_database_name()
    try:
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            hello = client.admin.command("hello")
            if not hello.get("logicalSessionTimeoutMinutes") or not (hello.get("setName") or hello.get("msg") == "isdbgrid"):
                pytest.fail("Transactions require sessions and a replica set or sharded topology", pytrace=False)
            database = client[database_name]
            database.create_collection("games")
            database.create_collection("game_action_receipts")
        except PyMongoError as error:
            pytest.fail(f"Disposable target unavailable ({type(error).__name__}); no fallback", pytrace=False)
        yield client, database
    finally:
        # Never drop a configured/default database or a caller-provided database name.
        try:
            if database is not None and database.name == database_name and database_name.startswith(DISPOSABLE_DATABASE_PREFIX):
                try:
                    client.drop_database(database_name)
                except PyMongoError as cleanup_error:
                    pytest.fail(f"Disposable database cleanup failed for '{database_name}' "
                                f"({type(cleanup_error).__name__}); remove only that database on the dedicated test target manually",
                                pytrace=False)
        finally:
            if client is not None:
                client.close()


@pytest.fixture
def real_repository(disposable_database, catalog):
    client, database = disposable_database
    initial = initialize_game(GameSetupRequest(game_name="Disposable transaction verification",
                                              starting_country_id="south-africa"), catalog)
    game_id = str(database["games"].insert_one(initial.model_dump(mode="json")).inserted_id)
    repository = MongoActionRepository(client, database, gameplay_writes_enabled=True)
    return repository, game_id, load_runtime(initial.model_dump())


def test_real_commit_duplicate_and_resume(real_repository):
    repository, game_id, state = real_repository
    request = ActionCommand(action_id="real-skip", expected_revision=0, action=Skip())
    result = GameActionService(repository).execute(game_id, context(state), request)
    assert result.state.revision == 1
    assert GameActionService(repository).execute(game_id, context(state), request) == result
    assert repository.find_receipt(game_id, request.action_id).result == result
    assert load_runtime(repository.load_game(game_id)) == result.state


def test_real_rollback_after_game_update(real_repository, monkeypatch):
    repository, game_id, state = real_repository
    before = repository.load_game(game_id)
    def reject_receipt(*args, **kwargs):
        raise PyMongoError("Deliberate disposable rollback test")
    monkeypatch.setattr(repository._receipts, "insert_one", reject_receipt)
    with pytest.raises(PersistenceUnavailable):
        GameActionService(repository).execute(game_id, context(state),
            ActionCommand(action_id="rollback", expected_revision=0, action=Skip()))
    assert repository.load_game(game_id) == before
    assert repository.find_receipt(game_id, "rollback") is None


@pytest.mark.parametrize("same_action_id", [False, True])
def test_real_competing_submissions(real_repository, monkeypatch, same_action_id):
    repository, game_id, state = real_repository
    barrier = Barrier(2, timeout=15)
    original_load = repository.load_game
    def synchronized_load(identifier):
        document = original_load(identifier)
        barrier.wait()
        return document
    monkeypatch.setattr(repository, "load_game", synchronized_load)
    def submit(index):
        action_id = "same" if same_action_id else f"competing-{index}"
        try:
            return GameActionService(repository).execute(game_id, context(state),
                ActionCommand(action_id=action_id, expected_revision=0, action=Skip()))
        except RevisionConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(submit, [0, 1]))
    if same_action_id:
        assert results[0] == results[1] and results[0] is not None
    else:
        assert sum(result is not None for result in results) == 1
    assert original_load(game_id)["revision"] == 1


@pytest.fixture
def real_npc_battle(disposable_database, catalog):
    """Labelled state, seeded ONLY in the existing generated disposable database.

    Select the battle locally without dice; the real transaction under test must
    persist the exchange's actual casualties and decision evidence together.
    """
    client, database = disposable_database
    state = npc_state(catalog, source_soldiers=3, changes={0: {"soldiers": 2}})
    state = step(state, StartAttack(source_id=state.countries[1].id,
                                  target_id=state.countries[0].id)).state
    game_id = str(database["games"].insert_one(runtime_document(state)).inserted_id)
    repository = MongoActionRepository(client, database, gameplay_writes_enabled=True)
    return client, database, repository, game_id, state


def _unexpected_replay_work(*args, **kwargs):
    pytest.fail("Duplicate replay must not rerun strategy, dice, or the clock", pytrace=False)


def test_real_npc_commit_replay_and_fresh_service(real_npc_battle, monkeypatch):
    from app.engine.npc.strategy import NpcStrategy

    client, database, repository, game_id, state = real_npc_battle
    dice = FixedDice([1, 4, 2, 3])
    service = GameActionService(repository, dice, lambda: NOW)
    controller = NpcController(repository, service)
    submission = controller.prepare(game_id)
    assert isinstance(submission.command.action, Roll) and dice.calls == 0
    before = repository.load_game(game_id)
    result = controller.submit(submission)

    # Index-paired dice produce one casualty on each side: source 3->2, target 2->1.
    assert dice.calls == 4
    assert result.state.country(state.battle.source_id).soldiers == 2
    assert result.state.country(state.battle.target_id).soldiers == 1
    assert result.state.revision == state.revision + 1
    assert result.npc_decision == submission.decision
    exchange = result.events[0]
    assert exchange.type == "dice_exchange"
    assert exchange.attacker_dice == (1, 4) and exchange.defender_dice == (2, 3)
    assert exchange.attacker_losses == exchange.defender_losses == 1
    stored_game = repository.load_game(game_id)
    assert stored_game != before and load_runtime(stored_game) == result.state
    assert "npc_decision" not in stored_game
    key = {"_id": repository.receipt_id(game_id, submission.command.action_id)}
    stored_receipt = database["game_action_receipts"].find_one(key)
    assert stored_receipt["result"]["npc_decision"] == submission.decision.model_dump(mode="json")
    assert stored_receipt["result"]["events"] == [event.model_dump(mode="json") for event in result.events]
    assert stored_receipt["result"]["state"] == result.state.model_dump(mode="json")
    assert database["game_action_receipts"].count_documents({"game_id": game_id}) == 1

    # These guards also catch evidence validation accidentally recomputing policy.
    monkeypatch.setattr(NpcStrategy, "decide", _unexpected_replay_work)
    monkeypatch.setattr(dice, "roll", _unexpected_replay_work)
    monkeypatch.setattr(service, "_clock", _unexpected_replay_work)
    assert controller.submit(submission) == result
    fresh_repository = MongoActionRepository(client, database, gameplay_writes_enabled=True)
    fresh_dice = FixedDice()
    monkeypatch.setattr(fresh_dice, "roll", _unexpected_replay_work)
    fresh_service = GameActionService(fresh_repository, fresh_dice, _unexpected_replay_work)
    fresh_controller = NpcController(fresh_repository, fresh_service)
    assert fresh_controller.submit(submission) == result
    assert fresh_repository.find_receipt(game_id, submission.command.action_id).result == result
    assert repository.load_game(game_id) == stored_game
    assert database["game_action_receipts"].find_one(key) == stored_receipt
    assert database["game_action_receipts"].count_documents({"game_id": game_id}) == 1


def test_real_npc_rollback_after_observed_game_update(real_npc_battle, monkeypatch):
    _, database, repository, game_id, state = real_npc_battle
    dice = FixedDice([1, 4, 2, 3])
    controller = NpcController(repository, GameActionService(repository, dice, lambda: NOW))
    submission = controller.prepare(game_id)
    before = repository.load_game(game_id)
    before_receipts = list(database["game_action_receipts"].find({"game_id": game_id}))
    observed_updates = []

    def reject_after_observed_update(document, *, session):
        assert session.in_transaction
        staged = database["games"].find_one({"_id": ObjectId(game_id)}, session=session)
        assert staged["revision"] == state.revision + 1
        staged_state = load_runtime(staged)
        assert staged_state.country(state.battle.source_id).soldiers == 2
        assert staged_state.country(state.battle.target_id).soldiers == 1
        assert document["result"]["npc_decision"] == submission.decision.model_dump(mode="json")
        assert document["result"]["events"][0]["attacker_losses"] == 1
        observed_updates.append(staged["revision"])
        raise PyMongoError("Deliberate disposable NPC rollback test after observed update")

    monkeypatch.setattr(repository._receipts, "insert_one", reject_after_observed_update)
    with pytest.raises(PersistenceUnavailable):
        controller.submit(submission)
    assert observed_updates and dice.calls == 4
    assert repository.load_game(game_id) == before
    assert repository.find_receipt(game_id, submission.command.action_id) is None
    assert list(database["game_action_receipts"].find({"game_id": game_id})) == before_receipts


@pytest.mark.parametrize("actor_kind", ["human", "npc"], ids=["historical-human", "historical-npc"])
def test_real_historical_receipt_and_fingerprint(disposable_database, catalog, actor_kind):
    client, database = disposable_database
    state = make_runtime(catalog) if actor_kind == "human" else npc_state(catalog)
    actor = context(state)
    assert actor.kind == actor_kind
    game_id = str(database["games"].insert_one(runtime_document(state)).inserted_id)
    repository = MongoActionRepository(client, database, gameplay_writes_enabled=True)
    command = ActionCommand(action_id=f"historical-{actor_kind}", expected_revision=state.revision, action=Skip())
    # Independent pre-Phase-3 algorithm: no optional evidence key, including null.
    old_payload = {"actor": actor.model_dump(mode="json"), "command": command.model_dump(mode="json")}
    old_fingerprint = hashlib.sha256(json.dumps(old_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert command_fingerprint(actor, command) == command_fingerprint(actor, command, None) == old_fingerprint
    result = GameActionService(repository, FixedDice(), lambda: NOW).execute(game_id, actor, command)
    assert result.npc_decision is None
    key = {"_id": repository.receipt_id(game_id, command.action_id)}
    assert database["game_action_receipts"].find_one(key)["fingerprint"] == old_fingerprint

    # Deliberate fixture-only edit recreates the old on-disk format in THIS test DB.
    unset = database["game_action_receipts"].update_one(key, {"$unset": {"result.npc_decision": ""}})
    assert unset.matched_count == 1
    historical_receipt = database["game_action_receipts"].find_one(key)
    stored_game = repository.load_game(game_id)
    assert "npc_decision" not in historical_receipt["result"]
    fresh_repository = MongoActionRepository(client, database, gameplay_writes_enabled=True)
    replay_dice = FixedDice()
    # Empty dice would also fail if replay attempted any random exchange.
    replay = GameActionService(fresh_repository, replay_dice, _unexpected_replay_work).execute(game_id, actor, command)
    assert replay == result and replay.npc_decision is None and replay_dice.calls == 0
    assert repository.load_game(game_id) == stored_game
    assert database["game_action_receipts"].find_one(key) == historical_receipt
    assert database["game_action_receipts"].count_documents({"game_id": game_id}) == 1
