"""Transactional contract doubles. Real MongoDB proof is separately opt-in."""
import copy
from types import SimpleNamespace

import pytest
from bson import BSON, ObjectId
from pymongo.errors import PyMongoError

from app.engine.errors import GameplayWritesDisabled, PersistenceUnavailable, RevisionConflict
from app.models.actions import ActionCommand, Roll, Skip, StartAttack
from app.repositories.action_repository import MongoActionRepository
from app.services.game_action_service import ActionReceipt, GameActionService, command_fingerprint
from phase2_helpers import FixedDice, NOW, context, make_runtime, revise, step


class Collection:
    def __init__(self, documents=None):
        self.docs = copy.deepcopy(documents or {})
        self.fail_insert = False
        self.force_miss = False

    def find_one(self, query, **kwargs):
        return copy.deepcopy(self.docs.get(query["_id"]))

    def update_one(self, query, update, **kwargs):
        current = self.docs.get(query["_id"])
        expected = query.get("revision", 0)
        matched = current is not None and current.get("revision", 0) == expected and not self.force_miss
        if matched:
            current.update(copy.deepcopy(update["$set"]))
        return SimpleNamespace(matched_count=int(matched))

    def insert_one(self, document, **kwargs):
        if self.fail_insert:
            raise PyMongoError("Simulated receipt write failure")
        BSON.encode(document)
        self.docs[document["_id"]] = copy.deepcopy(document)


class Session:
    def __init__(self, database, repeat):
        self.database = database
        self.repeat = repeat

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def with_transaction(self, callback, **kwargs):
        snapshot = {name: copy.deepcopy(collection.docs) for name, collection in self.database.items()}
        try:
            if self.repeat:
                callback(self)
                for name, docs in snapshot.items():
                    self.database[name].docs = copy.deepcopy(docs)
            return callback(self)
        except Exception:
            for name, docs in snapshot.items():
                self.database[name].docs = docs
            raise


class Client:
    def __init__(self, database):
        self.database = database
        self.repeat = False
        self.sessions = 0

    def start_session(self):
        self.sessions += 1
        return Session(self.database, self.repeat)


def database_for(state):
    game_id = ObjectId()
    database = {"games": Collection({game_id: {"_id": game_id, **state.model_dump()}}),
                "game_action_receipts": Collection()}
    return str(game_id), database, Client(database)


def test_writes_disabled_by_default(catalog):
    state = make_runtime(catalog)
    game_id, database, client = database_for(state)
    service = GameActionService(MongoActionRepository(client, database))
    with pytest.raises(GameplayWritesDisabled):
        service.execute(game_id, context(state), ActionCommand(action_id="skip", expected_revision=0, action=Skip()))
    assert client.sessions == 0 and database["games"].docs[ObjectId(game_id)]["revision"] == 0


def test_transaction_commit_receipt_and_bson(catalog):
    state = make_runtime(catalog)
    game_id, database, client = database_for(state)
    repository = MongoActionRepository(client, database, gameplay_writes_enabled=True)
    service = GameActionService(repository, clock=lambda: NOW)
    request = ActionCommand(action_id="skip", expected_revision=0, action=Skip())
    result = service.execute(game_id, context(state), request)
    assert result.state.revision == 1 and client.sessions == 1
    assert repository.load_game(game_id)["revision"] == 1
    BSON.encode(repository.load_game(game_id))
    assert service.execute(game_id, context(state), request) == result
    assert client.sessions == 1


def test_transaction_rolls_back_game_when_receipt_fails(catalog):
    state = make_runtime(catalog)
    game_id, database, client = database_for(state)
    before = copy.deepcopy(database["games"].docs)
    database["game_action_receipts"].fail_insert = True
    service = GameActionService(MongoActionRepository(client, database, gameplay_writes_enabled=True))
    with pytest.raises(PersistenceUnavailable):
        service.execute(game_id, context(state), ActionCommand(action_id="skip", expected_revision=0, action=Skip()))
    assert database["games"].docs == before and database["game_action_receipts"].docs == {}


def test_transaction_retry_reuses_exact_dice_events(catalog):
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": 2}, 1: {"soldiers": 1}})
    state = step(state, StartAttack(source_id=state.countries[0].id, target_id=state.countries[1].id)).state
    game_id, database, client = database_for(state)
    client.repeat = True
    dice = FixedDice([3, 3])
    repository = MongoActionRepository(client, database, gameplay_writes_enabled=True)
    result = GameActionService(repository, dice, lambda: NOW).execute(
        game_id, context(state), ActionCommand(action_id="roll", expected_revision=1, action=Roll()))
    assert dice.calls == 2
    receipt = repository.find_receipt(game_id, "roll")
    assert receipt.result == result
    assert receipt.result.events[0].attacker_dice == (3,)
    assert len(database["game_action_receipts"].docs) == 1


def test_revision_conflict_never_inserts_receipt(catalog):
    state = make_runtime(catalog)
    game_id, database, client = database_for(state)
    database["games"].force_miss = True
    service = GameActionService(MongoActionRepository(client, database, gameplay_writes_enabled=True))
    with pytest.raises(RevisionConflict):
        service.execute(game_id, context(state), ActionCommand(action_id="skip", expected_revision=0, action=Skip()))
    assert not database["game_action_receipts"].docs
    assert database["games"].docs[ObjectId(game_id)]["revision"] == 0


@pytest.mark.parametrize("game_id", ["", "unknown", None])
def test_bad_repository_ids(catalog, game_id):
    _, database, client = database_for(make_runtime(catalog))
    repository = MongoActionRepository(client, database)
    assert repository.load_game(game_id) is None
    assert repository.find_receipt(game_id, "test") is None


def test_adapter_update_preserves_unknown_stored_metadata(catalog):
    state = make_runtime(catalog)
    game_id, database, client = database_for(state)
    # Storage updates use $set, never replacement; no existing metadata is dropped.
    result = step(state, Skip())
    database["games"].docs[ObjectId(game_id)]["future_metadata"] = "keep"
    request = ActionCommand(action_id="skip", expected_revision=0, action=Skip())
    actor = context(state)
    receipt = ActionReceipt(game_id=game_id, actor=actor, command=request,
                            fingerprint=command_fingerprint(actor, request), result=result)
    MongoActionRepository(client, database, gameplay_writes_enabled=True).commit(receipt)
    assert database["games"].docs[ObjectId(game_id)]["future_metadata"] == "keep"
