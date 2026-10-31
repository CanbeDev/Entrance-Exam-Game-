"""Single-document MongoDB call contracts, not live MongoDB verification."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from threading import RLock
from types import SimpleNamespace

import pytest
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_preferences import ReadPreference

from app.repositories.commentary_repository import MongoCommentaryRepository
from app.security.errors import SecurityError


GAME = "000000000000000000000001"
TOKEN = "synthetic_claim_000001"
NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)


class Collection:
    def __init__(self):
        self.documents, self.calls = {}, []
        self.lock = RLock()
        self.fail = None
        self.uncertain_insert = False
        self.acknowledged = True

    def find_one(self, query, projection):
        self.calls.append(("find_one", deepcopy(query), deepcopy(projection)))
        if self.fail == "find":
            raise PyMongoError("NEVER_EXPOSE_PROVIDER_OR_DRIVER_DETAIL")
        with self.lock:
            value = self.documents.get(query["_id"])
            return ({key: deepcopy(item) for key, item in value.items() if projection.get(key) != 0}
                    if value else None)

    def insert_one(self, document):
        self.calls.append(("insert_one", deepcopy(document)))
        with self.lock:
            if self.fail == "insert":
                raise PyMongoError("NEVER_EXPOSE_PROVIDER_OR_DRIVER_DETAIL")
            if document["_id"] in self.documents:
                raise DuplicateKeyError("Duplicate commentary identity")
            self.documents[document["_id"]] = deepcopy(document)
            if self.uncertain_insert:
                raise PyMongoError("NEVER_EXPOSE_PROVIDER_OR_DRIVER_DETAIL")
            return SimpleNamespace(acknowledged=self.acknowledged)

    def update_one(self, query, update):
        self.calls.append(("update_one", deepcopy(query), deepcopy(update)))
        if self.fail == "update":
            raise PyMongoError("NEVER_EXPOSE_PROVIDER_OR_DRIVER_DETAIL")
        with self.lock:
            value = self.documents.get(query["_id"])
            if value is None or any(value.get(key) != expected for key, expected in query.items()):
                return SimpleNamespace(acknowledged=True, matched_count=0)
            value.update(deepcopy(update["$set"]))
            for key in update["$unset"]:
                value.pop(key, None)
            return SimpleNamespace(acknowledged=self.acknowledged, matched_count=1)


class Database:
    def __init__(self):
        self.collection, self.accesses = Collection(), []

    def get_collection(self, name, **options):
        assert name == "battle_commentary", "No game, receipt or security collection may be changed"
        self.accesses.append((name, options))
        return self.collection


def pending(revision=8):
    return {"game_id": GAME, "revision": revision, "action_id": "npc-balanced-v1-1-7",
            "status": "pending", "source": "deterministic", "text": "Committed battle facts.",
            "reason": "in_progress", "facts": {"attacker_dice": [6], "defender_dice": [3]},
            "claimed_at": NOW}


def setup():
    database = Database()
    return database, MongoCommentaryRepository(database)


def test_constructor_is_lazy_and_does_not_provision_collections_or_indexes():
    database, _ = setup()
    assert database.accesses == []
    assert database.collection.calls == []


def test_claim_uses_durable_single_document_identity_and_does_not_mutate_input():
    database, repository = setup()
    document = pending()
    original = deepcopy(document)
    assert repository.claim(GAME, 8, document, TOKEN) is True
    assert document == original
    saved = database.collection.documents[f"{GAME}:8"]
    assert saved["claim_token"] == TOKEN
    assert saved["status"] == "pending"
    options = database.accesses[0][1]
    assert options["write_concern"].document == {"w": "majority", "wtimeout": 5000}
    assert options["read_concern"].document == {"level": "majority"}
    assert options["read_preference"] == ReadPreference.PRIMARY


def test_duplicate_and_restarted_service_cannot_reclaim_even_very_old_pending():
    database, repository = setup()
    document = pending()
    document["claimed_at"] = datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert repository.claim(GAME, 8, document, TOKEN)
    restarted = MongoCommentaryRepository(database)
    assert not restarted.claim(GAME, 8, pending(), "another_claim_00001")
    assert restarted.get(GAME, 8)["claimed_at"] == document["claimed_at"]
    assert len(database.collection.documents) == 1


def test_concurrent_claims_allow_exactly_one_dispatch_permission():
    database, repository = setup()
    with ThreadPoolExecutor(max_workers=8) as pool:
        grants = list(pool.map(lambda n: repository.claim(GAME, 8, pending(), f"claim_token_{n:016d}"), range(24)))
    assert sum(grants) == 1
    assert len(database.collection.documents) == 1


def test_uncertain_insert_never_grants_dispatch_and_persists_a_closed_claim():
    database, repository = setup()
    database.collection.uncertain_insert = True
    with pytest.raises(SecurityError, match="^commentary_storage_unavailable$") as error:
        repository.claim(GAME, 8, pending(), TOKEN)
    assert error.value.status == 503
    database.collection.uncertain_insert = False
    assert not repository.claim(GAME, 8, pending(), "another_claim_00001")


def test_unacknowledged_insert_never_grants_dispatch():
    database, repository = setup()
    database.collection.acknowledged = False
    with pytest.raises(SecurityError):
        repository.claim(GAME, 8, pending(), TOKEN)


@pytest.mark.parametrize("status", ["ready", "fallback"])
def test_terminal_results_are_saved_and_retrievable_without_private_claim_fields(status):
    database, repository = setup()
    assert repository.claim(GAME, 8, pending(), TOKEN)
    result = {**pending(), "status": status, "source": "groq" if status == "ready" else "deterministic",
              "text": "Narration and authoritative facts.", "reason": None}
    original = deepcopy(result)
    repository.finish(GAME, 8, result, TOKEN)
    assert result == original
    saved = repository.get(GAME, 8)
    assert saved["text"] == result["text"]
    assert saved["status"] == status
    assert saved["claimed_at"] == NOW
    assert "claim_token" not in saved and "_id" not in saved
    saved["facts"]["attacker_dice"].append(99)
    assert repository.get(GAME, 8)["facts"]["attacker_dice"] == [6]
    assert not repository.claim(GAME, 8, pending(), "another_claim_00001")


def test_wrong_claim_token_cannot_finish_or_override_another_operation():
    database, repository = setup()
    repository.claim(GAME, 8, pending(), TOKEN)
    with pytest.raises(SecurityError):
        repository.finish(GAME, 8, {**pending(), "status": "ready"}, "wrong_claim_000001")
    assert repository.get(GAME, 8)["status"] == "pending"
    call = database.collection.calls[-2]
    assert call[0] == "update_one"
    assert call[1] == {"_id": f"{GAME}:8", "status": "pending", "claim_token": "wrong_claim_000001"}


def test_completed_result_cannot_be_overwritten_even_with_original_token():
    database, repository = setup()
    repository.claim(GAME, 8, pending(), TOKEN)
    repository.finish(GAME, 8, {**pending(), "status": "ready", "text": "Original."}, TOKEN)
    with pytest.raises(SecurityError):
        repository.finish(GAME, 8, {**pending(), "status": "fallback", "text": "Replacement."}, TOKEN)
    assert repository.get(GAME, 8)["text"] == "Original."


@pytest.mark.parametrize("operation", ["find", "insert", "update"])
def test_storage_failure_sanitization(operation):
    database, repository = setup()
    database.collection.fail = operation
    with pytest.raises(SecurityError) as error:
        if operation == "find":
            repository.get(GAME, 8)
        elif operation == "insert":
            repository.claim(GAME, 8, pending(), TOKEN)
        else:
            repository.finish(GAME, 8, {**pending(), "status": "ready"}, TOKEN)
    assert error.value.code == "commentary_storage_unavailable"
    assert "NEVER_EXPOSE" not in str(error.value)


@pytest.mark.parametrize("game,revision", [("bad", 8), (GAME, 0), (GAME, True), (GAME, 1.5)])
def test_invalid_identity_never_reaches_database(game, revision):
    database, repository = setup()
    with pytest.raises(SecurityError):
        repository.get(game, revision)
    assert database.accesses == []


def test_get_without_a_record_is_read_only_and_does_not_create_one():
    database, repository = setup()
    assert repository.get(GAME, 8) is None
    assert [call[0] for call in database.collection.calls] == ["find_one"]
    assert database.collection.documents == {}


def test_claim_rejects_mismatched_identity_and_terminal_status_before_storage():
    database, repository = setup()
    for document in [{**pending(), "game_id": "000000000000000000000002"},
                     {**pending(), "revision": 9}, {**pending(), "status": "ready"}]:
        with pytest.raises(ValueError):
            repository.claim(GAME, 8, document, TOKEN)
    assert database.accesses == []


@pytest.mark.parametrize("scope,cap", [("global", 100), ("game", 30)])
def test_daily_caps_use_existing_atomic_mongo_counter_command_and_survive_restart(catalog, monkeypatch, scope, cap):
    from pymongo import ReturnDocument
    from app.repositories.security_repository import MongoSecurityRepository
    from app.services.commentary_service import CommentaryService
    from test_phase4_mongo import setup_store
    repository, principal, _, game_id, database, client = setup_store(catalog)
    limits = database["auth_rate_limits"]
    lock = RLock()
    original = limits.find_one_and_update
    commands = []
    def atomic_counter(query, update, **options):
        # Contract double models the atomic boundary; no live MongoDB claim.
        with lock:
            assert list(query) == ["_id"]
            assert update["$inc"] == {"count": 1}
            assert options["return_document"] == ReturnDocument.AFTER
            assert options.get("upsert") is True
            commands.append((deepcopy(query), deepcopy(update)))
            return original(query, update, **options)
    monkeypatch.setattr(limits, "find_one_and_update", atomic_counter)
    label = "global-day" if scope == "global" else "game-day:" + game_id
    key = hashlib.sha256(("commentary:" + label).encode()).hexdigest()
    window = int(NOW.timestamp()) // 86400
    identifier = hashlib.sha256(f"{key}:86400:{window}".encode()).hexdigest()
    limits.docs[identifier] = {"_id": identifier, "count": cap - 1,
        "expires_at": datetime.fromtimestamp((window + 2) * 86400, timezone.utc)}
    def attempt(index):
        restarted_store = MongoSecurityRepository(client, database, auth_writes_enabled=True)
        service = CommentaryService(SimpleNamespace(store=restarted_store), None, None, clock=lambda: NOW)
        try:
            service._rate(SimpleNamespace(user_id=f"parallel-{index}"), game_id)
            return True
        except SecurityError as error:
            assert error.status == 429
            return False
    with ThreadPoolExecutor(max_workers=8) as executor:
        granted = list(executor.map(attempt, range(8)))
    assert sum(granted) == 1 and limits.docs[identifier]["count"] == cap + 7
    assert any(query == {"_id": identifier} for query, _ in commands)
    assert limits.docs[identifier]["expires_at"].hour == 0
    assert limits.docs[identifier]["expires_at"] > NOW
    # Backend restart does not reset shared persisted counters. A new UTC day does.
    next_store = MongoSecurityRepository(client, database, auth_writes_enabled=True)
    service = CommentaryService(SimpleNamespace(store=next_store), None, None, clock=lambda: NOW + timedelta(days=1))
    service._rate(principal, game_id)
    next_identifier = hashlib.sha256(f"{key}:86400:{window + 1}".encode()).hexdigest()
    assert limits.docs[next_identifier]["count"] == 1
    assert set(database) == {"users", "auth_sessions", "auth_rate_limits", "games", "game_action_receipts"}
