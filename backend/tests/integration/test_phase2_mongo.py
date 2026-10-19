"""Real MongoDB proof; skipped unless explicitly requested. Never loads .env."""
import getpass
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.engine.errors import PersistenceUnavailable, RevisionConflict
from app.engine.game_setup import initialize_game
from app.engine.state_adapter import load_runtime
from app.models.actions import ActionCommand, Skip
from app.models.game import GameSetupRequest
from app.repositories.action_repository import MongoActionRepository
from app.services.game_action_service import GameActionService
from phase2_helpers import context

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
    print("Use a local replica set or separate NON-PRODUCTION Atlas project. No production URI.")
    if input("Type DISPOSABLE to authorize creation and cleanup of a fresh test database: ") != "DISPOSABLE":
        pytest.fail("Disposable database authorization was not provided", pytrace=False)
    uri = getpass.getpass("Dedicated test MongoDB URI (hidden; never read from .env): ")
    client = None
    database = None
    database_name = generate_disposable_database_name()
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        hello = client.admin.command("hello")
        if not hello.get("logicalSessionTimeoutMinutes") or not (hello.get("setName") or hello.get("msg") == "isdbgrid"):
            pytest.fail("Transactions require sessions and a replica set or sharded topology", pytrace=False)
        database = client[database_name]
        database.create_collection("games")
        database.create_collection("game_action_receipts")
    except PyMongoError as error:
        if client is not None:
            if database is not None and database.name == database_name and database_name.startswith(DISPOSABLE_DATABASE_PREFIX):
                try:
                    client.drop_database(database_name)
                except PyMongoError as cleanup_error:
                    print(f"Test setup cleanup failed for disposable database '{database_name}' "
                          f"({type(cleanup_error).__name__}); inspect only that database on the dedicated test target.")
            client.close()
        pytest.fail(f"Disposable target unavailable ({type(error).__name__}); no fallback", pytrace=False)
    try:
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
