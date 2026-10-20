"""Mongo authorization/query/rollback contract doubles, not real transaction proof."""
import copy
import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from bson import BSON, ObjectId
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError

from app.engine.errors import GameplayWritesDisabled, PersistenceUnavailable, RevisionConflict
from app.models.actions import ActionCommand, Skip
from app.models.game_access import GameAccess
from app.repositories.phase4_indexes import phase4_indexes, provision_phase4_indexes, verify_required_indexes
from app.repositories.security_repository import MongoSecurityRepository
from app.security.errors import SecurityError
from app.services.game_action_service import GameActionService
from phase2_helpers import NOW, context, make_runtime


def field(document, path):
    value = document
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def matches(document, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(matches(document, choice) for choice in expected):
                return False
            continue
        value = field(document, key)
        if not isinstance(expected, dict):
            if value != expected:
                return False
            continue
        for operator, operand in expected.items():
            if operator == "$gt" and not (value is not None and value > operand):
                return False
            if operator == "$lt" and not (value is not None and value < operand):
                return False
            if operator == "$exists" and (value is not None) != operand:
                return False
            if operator == "$regex" and not re.search(operand, value or "", re.I if expected.get("$options") == "i" else 0):
                return False
    return True


class Cursor(list):
    def sort(self, key, direction):
        return Cursor(sorted(self, key=lambda item: field(item, key), reverse=direction == -1))

    def limit(self, count):
        return Cursor(self[:count])


class Collection:
    def __init__(self, name):
        self.name, self.docs, self.calls = name, {}, []
        self.fail_insert = False
        self.indexes = {}

    def find_one(self, query, **kwargs):
        self.calls.append(("find", copy.deepcopy(query), kwargs.get("session")))
        return next((copy.deepcopy(doc) for doc in self.docs.values() if matches(doc, query)), None)

    def find(self, query):
        self.calls.append(("find", copy.deepcopy(query), None))
        return Cursor(copy.deepcopy([doc for doc in self.docs.values() if matches(doc, query)]))

    def insert_one(self, document, **kwargs):
        self.calls.append(("insert", copy.deepcopy(document), kwargs.get("session")))
        if self.fail_insert:
            raise PyMongoError("Simulated write failure; never returned to client")
        document = copy.deepcopy(document)
        document.setdefault("_id", ObjectId())
        if document["_id"] in self.docs:
            raise DuplicateKeyError("duplicate")
        if self.name == "users" and any(doc["username_key"] == document["username_key"] for doc in self.docs.values()):
            raise DuplicateKeyError("duplicate")
        if self.name == "games" and any(doc.get("access", {}).get("owner_user_id") == document.get("access", {}).get("owner_user_id")
            and doc.get("creation", {}).get("key") == document.get("creation", {}).get("key") for doc in self.docs.values()):
            raise DuplicateKeyError("duplicate")
        BSON.encode(document)
        self.docs[document["_id"]] = document
        return SimpleNamespace(inserted_id=document["_id"])

    def update_one(self, query, update, **kwargs):
        self.calls.append(("update", copy.deepcopy(query), kwargs.get("session")))
        document = next((doc for doc in self.docs.values() if matches(doc, query)), None)
        if document is None:
            return SimpleNamespace(matched_count=0)
        document.update(copy.deepcopy(update.get("$set", {})))
        for key, amount in update.get("$inc", {}).items():
            document[key] = document.get(key, 0) + amount
        return SimpleNamespace(matched_count=1)

    def find_one_and_update(self, query, update, **kwargs):
        if query["_id"] not in self.docs:
            self.docs[query["_id"]] = {**query, **copy.deepcopy(update.get("$setOnInsert", {}))}
        self.update_one(query, update)
        return copy.deepcopy(self.docs[query["_id"]])

    def create_indexes(self, indexes):
        self.calls.append(("indexes", indexes))
        for index in indexes:
            specification = copy.deepcopy(dict(index.document))
            specification["key"] = list(specification["key"].items())
            self.indexes[specification["name"]] = specification
        return [index.document["name"] for index in indexes]

    def index_information(self):
        self.calls.append(("index_information", {}, None))
        return copy.deepcopy(self.indexes)


class Session:
    def __init__(self, client):
        self.client = client

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def with_transaction(self, callback, **kwargs):
        if self.client.before_transaction:
            self.client.before_transaction()
        snapshot = {key: copy.deepcopy(collection.docs) for key, collection in self.client.database.items()}
        self.client.options = kwargs
        try:
            if self.client.repeat:
                callback(self)
                for key, documents in snapshot.items():
                    self.client.database[key].docs = copy.deepcopy(documents)
            return callback(self)
        except Exception as error:
            for key, documents in snapshot.items():
                self.client.database[key].docs = documents
            if (self.client.retry_transient and isinstance(error, PyMongoError)
                    and error.has_error_label("TransientTransactionError")):
                self.client.retry_transient = False
                return callback(self)
            raise


class Client:
    def __init__(self, database):
        self.database = database
        self.before_transaction = None
        self.repeat = False
        self.retry_transient = False
        self.options = None

    def start_session(self):
        return Session(self)


def setup_store(catalog, *, enabled=True):
    database = {name: Collection(name) for name in phase4_indexes()}
    # Explicit fake metadata setup; no real indexes or database are accessed.
    for name, models in phase4_indexes().items():
        for index in models:
            specification = copy.deepcopy(dict(index.document))
            specification["key"] = list(specification["key"].items())
            database[name].indexes[specification["name"]] = specification
    client = Client(database)
    repository = MongoSecurityRepository(client, database, auth_writes_enabled=enabled, gameplay_writes_enabled=enabled)
    user_id, game_id = ObjectId(), ObjectId()
    user = {"_id": user_id, "username": "Alice", "username_key": "alice", "password_hash": "encoded-test-hash",
            "status": "active", "auth_version": 1, "authorization_revision": 0, "created_at": NOW}
    session = {"_id": "a" * 64, "user_id": str(user_id), "auth_version": 1, "csrf_token": "csrf-only-token",
               "created_at": NOW, "last_seen_at": NOW, "expires_at": NOW + timedelta(hours=12),
               "revoked_at": None, "revision": 0}
    state = make_runtime(catalog)
    access = GameAccess(owner_user_id=str(user_id), human_player_id=state.players[0].id, bound_at=NOW)
    game = {"_id": game_id, **state.model_dump(), "access": access.model_dump(), "creation": {"key": "old-key", "fingerprint": "old-fingerprint"}}
    database["users"].docs[user_id], database["auth_sessions"].docs[session["_id"]] = user, session
    database["games"].docs[game_id] = game
    principal = repository.authorize(session["_id"], NOW, 1800)
    return repository, principal, state, str(game_id), database, client


def service_for(repository, principal, game_id):
    return GameActionService(repository.action_store(principal, game_id, lambda: NOW, 1800, enabled=True), clock=lambda: NOW)


def test_owned_creation_first_and_replay_use_identical_bson_timestamps(catalog, monkeypatch):
    from app.services.public_game_service import public_game
    repository, principal, state, _, database, _ = setup_store(catalog)
    collection = database["games"]
    original_insert = collection.insert_one

    def bson_insert(document, **kwargs):
        # A faithful date/codec boundary without a database connection.
        return original_insert(BSON.encode(document).decode(), **kwargs)

    monkeypatch.setattr(collection, "insert_one", bson_insert)
    first = repository.create_owned_game(principal, state, "bson-creation", "same-request", NOW, 1800)
    replay = repository.create_owned_game(principal, state, "bson-creation", "same-request", NOW, 1800)
    assert first == replay
    assert first["created_at"].tzinfo is None
    assert first["access"]["bound_at"].tzinfo is None
    assert public_game(first) == public_game(replay)


def test_scoped_commit_preserves_envelope_and_fences_authorization(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    before = copy.deepcopy(database["games"].docs[ObjectId(game_id)]["access"])
    request = ActionCommand(action_id="skip", expected_revision=0, action=Skip())
    service = service_for(repository, principal, game_id)
    result = service.execute(game_id, context(state), request)
    assert result.state.revision == 1
    saved = database["games"].docs[ObjectId(game_id)]
    assert saved["access"] == before and saved["creation"]["key"] == "old-key"
    updates = [query for op, query, session in database["games"].calls if op == "update"]
    assert updates[-1]["access.owner_user_id"] == principal.user_id
    assert updates[-1]["access.version"] == 1
    assert database["users"].docs[ObjectId(principal.user_id)]["authorization_revision"] == 1
    assert database["auth_sessions"].docs[principal.session_hash]["revision"] == 1
    assert client.options["read_concern"].document == {"level": "snapshot"}
    assert service.execute(game_id, context(state), request) == result


@pytest.mark.parametrize("change", ["logout", "account_disabled", "version_changed", "owner_changed"])
def test_transaction_rechecks_authorization_before_receipt_or_mutation(catalog, change):
    repository, principal, state, game_id, database, client = setup_store(catalog)

    def revoke():
        if change == "logout":
            repository.revoke_session(principal.session_hash, NOW)
        elif change == "account_disabled":
            database["users"].docs[ObjectId(principal.user_id)]["status"] = "disabled"
        elif change == "version_changed":
            database["users"].docs[ObjectId(principal.user_id)]["auth_version"] = 2
        else:
            database["games"].docs[ObjectId(game_id)]["access"]["owner_user_id"] = str(ObjectId())
    client.before_transaction = revoke
    with pytest.raises(SecurityError):
        service_for(repository, principal, game_id).execute(game_id, context(state), ActionCommand(action_id="blocked", expected_revision=0, action=Skip()))
    assert not database["game_action_receipts"].docs
    assert database["games"].docs[ObjectId(game_id)]["revision"] == 0
    assert not any(op == "update" for op, *_ in database["games"].calls)


def test_revoked_session_cannot_lookup_committed_receipt(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    command = ActionCommand(action_id="skip", expected_revision=0, action=Skip())
    service_for(repository, principal, game_id).execute(game_id, context(state), command)
    database["game_action_receipts"].calls.clear()
    repository.revoke_session(principal.session_hash, NOW)
    with pytest.raises(SecurityError):
        service_for(repository, principal, game_id).execute(game_id, context(state), command)
    assert not any(operation == "find" for operation, *_ in database["game_action_receipts"].calls)


def test_concurrent_rate_bucket_upsert_duplicate_is_counted_not_bypassed(catalog, monkeypatch):
    repository, _, _, _, database, _ = setup_store(catalog)
    collection = database["auth_rate_limits"]
    original = collection.find_one_and_update
    raced = []

    def simultaneous_insert(query, update, **kwargs):
        if not raced:
            raced.append(True)
            # Another request wins creation of the same bucket.
            original(query, update, **kwargs)
            raise DuplicateKeyError("Simulated concurrent bucket creation")
        return original(query, update, **kwargs)

    monkeypatch.setattr(collection, "find_one_and_update", simultaneous_insert)
    assert repository.consume_limit("same-bucket", 2, 60, NOW)
    assert len(collection.docs) == 1
    assert next(iter(collection.docs.values()))["count"] == 2
    assert not repository.consume_limit("same-bucket", 2, 60, NOW)


def test_receipt_insert_failure_rolls_back_session_fences_game_and_receipt(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    before = {name: copy.deepcopy(collection.docs) for name, collection in database.items()}
    database["game_action_receipts"].fail_insert = True
    with pytest.raises(PersistenceUnavailable):
        service_for(repository, principal, game_id).execute(game_id, context(state), ActionCommand(action_id="skip", expected_revision=0, action=Skip()))
    assert {name: collection.docs for name, collection in database.items()} == before


def test_transaction_retry_does_not_duplicate_fences_or_receipt(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    client.repeat = True
    service_for(repository, principal, game_id).execute(game_id, context(state), ActionCommand(action_id="skip", expected_revision=0, action=Skip()))
    assert len(database["game_action_receipts"].docs) == 1
    assert database["auth_sessions"].docs[principal.session_hash]["revision"] == 1


@pytest.mark.parametrize("field_name,value", [("revoked_at", NOW), ("expires_at", NOW),
    ("last_seen_at", NOW - timedelta(seconds=1800)), ("auth_version", 2)])
def test_authorize_rejects_revoked_expired_idle_or_stale_session(catalog, field_name, value):
    repository, principal, *_ = setup_store(catalog)
    repository._sessions.docs[principal.session_hash][field_name] = value
    with pytest.raises(SecurityError) as failure:
        repository.authorize(principal.session_hash, NOW, 1800)
    assert failure.value.status == 401


def test_default_gates_prevent_auth_and_game_writes(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog, enabled=False)
    before = copy.deepcopy(database["games"].docs)
    with pytest.raises(SecurityError):
        repository.create_user({"username_key": "new"})
    with pytest.raises(SecurityError):
        repository.consume_limit("key", 1, 60, NOW)
    with pytest.raises(SecurityError):
        repository.create_owned_game(principal, state, "new", "hash", NOW, 1800)
    with pytest.raises(GameplayWritesDisabled):
        service_for(repository, principal, game_id).execute(game_id, context(state), ActionCommand(action_id="skip", expected_revision=0, action=Skip()))
    assert database["games"].docs == before and not database["game_action_receipts"].docs


def test_owned_creation_is_bson_safe_atomic_and_idempotent(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    first = repository.create_owned_game(principal, state, "new-key", "fp", NOW, 1800)
    second = repository.create_owned_game(principal, state, "new-key", "fp", NOW, 1800)
    assert first == second and first["_id"] != game_id
    assert len(database["games"].docs) == 2
    BSON.encode(database["games"].docs[ObjectId(first["_id"])])
    with pytest.raises(SecurityError) as failure:
        repository.create_owned_game(principal, state, "new-key", "different", NOW, 1800)
    assert failure.value.code == "creation_id_conflict"


def test_create_failure_rolls_back_authorization_guard(catalog):
    repository, principal, state, _, database, client = setup_store(catalog)
    before = {name: copy.deepcopy(collection.docs) for name, collection in database.items()}
    database["games"].fail_insert = True
    with pytest.raises(SecurityError) as failure:
        repository.create_owned_game(principal, state, "new", "fp", NOW, 1800)
    assert failure.value.code == "persistence_unavailable"
    assert {name: collection.docs for name, collection in database.items()} == before


def test_create_rechecks_session_inside_transaction(catalog):
    repository, principal, state, _, database, client = setup_store(catalog)
    client.before_transaction = lambda: repository.revoke_session(principal.session_hash, NOW)
    with pytest.raises(SecurityError):
        repository.create_owned_game(principal, state, "new", "fp", NOW, 1800)
    assert len(database["games"].docs) == 1


def test_user_unique_index_conflict_is_sanitized(catalog):
    repository, _, _, _, database, client = setup_store(catalog)
    with pytest.raises(SecurityError) as failure:
        repository.create_user({"username_key": "alice"})
    assert failure.value.code == "username_unavailable"


def test_login_session_rotation_checks_password_and_account(catalog):
    repository, principal, _, _, database, client = setup_store(catalog)
    new = {**database["auth_sessions"].docs[principal.session_hash], "_id": "b" * 64}
    repository.issue_session(new, "encoded-test-hash", principal.session_hash)
    assert database["auth_sessions"].docs[principal.session_hash]["revoked_at"] == NOW
    assert repository.authorize(new["_id"], NOW, 1800).user_id == principal.user_id
    with pytest.raises(SecurityError):
        repository.issue_session({**new, "_id": "c" * 64}, "changed-hash")
    assert "c" * 64 not in database["auth_sessions"].docs


def test_atomic_rate_counter_is_shared_and_expires(catalog):
    repository, _, _, _, database, client = setup_store(catalog)
    assert repository.consume_limit("login:test", 2, 60, NOW)
    assert repository.consume_limit("login:test", 2, 60, NOW)
    assert not repository.consume_limit("login:test", 2, 60, NOW)
    assert repository.consume_limit("login:test", 2, 60, NOW + timedelta(minutes=1))
    assert all(document["expires_at"] > NOW for document in database["auth_rate_limits"].docs.values())
    assert all("login:test" not in key for key in database["auth_rate_limits"].docs)


def test_owner_listing_escaped_search_and_pagination(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    for index in range(3):
        result = repository.create_owned_game(principal, state, f"key-{index}", "fp", NOW, 1800)
        database["games"].docs[ObjectId(result["_id"])]["game_name"] = "literal .* text"
    first = repository.list_owned_games(principal, status="active", query=".*", cursor=None, limit=2, now=NOW, idle_seconds=1800)
    second = repository.list_owned_games(principal, status="active", query=".*", cursor=first["next_cursor"], limit=2, now=NOW, idle_seconds=1800)
    assert len(first["games"]) == 2 and len(second["games"]) == 1
    assert not {game["_id"] for game in first["games"]} & {game["_id"] for game in second["games"]}
    assert second["next_cursor"] is None
    with pytest.raises(SecurityError):
        repository.list_owned_games(principal, status=None, query="", cursor="invalid", limit=2, now=NOW, idle_seconds=1800)


def test_legacy_owned_reads_rejected_before_receipts(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    database["games"].docs[ObjectId(game_id)].pop("access")
    with pytest.raises(SecurityError):
        service_for(repository, principal, game_id).execute(game_id, context(state), ActionCommand(action_id="skip", expected_revision=0, action=Skip()))
    assert not any(op == "find" for op, *_ in database["game_action_receipts"].calls)


def test_index_plan_is_explicit_and_legacy_creation_index_is_partial():
    indexes = phase4_indexes()
    database = {name: Collection(name) for name in indexes}
    assert not any(collection.calls for collection in database.values())
    names = provision_phase4_indexes(database)
    unique = next(index.document for index in indexes["games"] if index.document["name"] == "owned_game_creation_unique")
    assert unique["unique"] is True and "partialFilterExpression" in unique
    assert indexes["auth_sessions"][1].document["expireAfterSeconds"] == 0
    assert set(names) == {"users", "auth_sessions", "auth_rate_limits", "games", "game_action_receipts"}


def test_session_touch_is_transactional_and_fences_the_user(catalog):
    repository, principal, _, _, database, client = setup_store(catalog)
    repository.authorize(principal.session_hash, NOW + timedelta(seconds=5), 1800, touch=True)
    assert client.options["write_concern"].document == {"w": "majority"}
    assert database["users"].docs[ObjectId(principal.user_id)]["authorization_revision"] == 1
    session = database["auth_sessions"].docs[principal.session_hash]
    assert session["revision"] == 1 and session["last_seen_at"] == NOW + timedelta(seconds=5)


def test_owner_denied_before_receipt_and_npc_lookup(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    database["games"].docs[ObjectId(game_id)]["access"]["owner_user_id"] = str(ObjectId())
    with pytest.raises(SecurityError):
        service_for(repository, principal, game_id).execute(game_id, context(state), ActionCommand(action_id="skip", expected_revision=0, action=Skip()))
    with pytest.raises(SecurityError):
        repository.find_npc_result(principal, game_id, 0, NOW, 1800)
    assert not any(op == "find" for op, *_ in database["game_action_receipts"].calls)


def test_competing_request_cannot_commit_a_second_action(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    first = service_for(repository, principal, game_id)
    second = service_for(repository, principal, game_id)
    first.execute(game_id, context(state), ActionCommand(action_id="first", expected_revision=0, action=Skip()))
    with pytest.raises(RevisionConflict):
        second.execute(game_id, context(state), ActionCommand(action_id="second", expected_revision=0, action=Skip()))
    assert len(database["game_action_receipts"].docs) == 1
    assert database["games"].docs[ObjectId(game_id)]["revision"] == 1


def test_listing_rejects_revocation_before_query(catalog):
    repository, principal, _, _, database, client = setup_store(catalog)
    repository.revoke_session(principal.session_hash, NOW)
    database["games"].calls.clear()
    with pytest.raises(SecurityError):
        repository.list_owned_games(principal, status=None, query="", cursor=None, limit=10, now=NOW, idle_seconds=1800)
    assert database["games"].calls == []


def test_public_committed_events_are_sorted_and_bounded(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    for revision in (3, 1, 2):
        database["game_action_receipts"].docs[str(revision)] = {
            "_id": str(revision), "game_id": game_id, "result": {"state": {"revision": revision}}}
    documents = repository.public_events(game_id, after_revision=1, limit=1)
    assert [item["result"]["state"]["revision"] for item in documents] == [2, 3]


@pytest.mark.parametrize("collection,index_name,change", [
    ("users", "username_key_unique", "missing"),
    ("users", "username_key_unique", "not_unique"),
    ("games", "owned_game_creation_unique", "wrong_partial"),
    ("auth_sessions", "session_expiry", "wrong_ttl"),
])
def test_required_indexes_fail_closed_before_any_write(catalog, collection, index_name, change):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    index = database[collection].indexes[index_name]
    if change == "missing":
        del database[collection].indexes[index_name]
    elif change == "not_unique":
        index["unique"] = False
    elif change == "wrong_partial":
        index["partialFilterExpression"] = {"creation.key": {"$exists": True}}
    else:
        index["expireAfterSeconds"] = 3600
    with pytest.raises(SecurityError) as failure:
        repository.create_user({"username_key": "new"})
    assert failure.value.code == "security_indexes_not_ready"
    with pytest.raises(SecurityError):
        repository.create_owned_game(principal, state, "new", "fp", NOW, 1800)
    with pytest.raises(SecurityError):
        repository.action_store(principal, game_id, lambda: NOW, 1800, enabled=True)
    assert not any(op in {"insert", "update", "indexes"} for table in database.values() for op, *_ in table.calls)


def test_disabled_gates_do_not_inspect_database_indexes(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog, enabled=False)
    with pytest.raises(SecurityError):
        repository.create_user({"username_key": "new"})
    repository.action_store(principal, game_id, lambda: NOW, 1800, enabled=True)
    assert not any(op == "index_information" for table in database.values() for op, *_ in table.calls)


def test_index_verification_is_read_only_and_rechecked_for_new_writes(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    repository.consume_limit("test", 10, 60, NOW)
    repository.consume_limit("test", 10, 60, NOW)
    assert all(sum(op == "index_information" for op, *_ in table.calls) == 2 for table in database.values())
    assert not any(op == "indexes" for table in database.values() for op, *_ in table.calls)


def test_index_removed_after_successful_readiness_blocks_subsequent_write(catalog):
    repository, _, _, _, database, _ = setup_store(catalog)
    assert repository.consume_limit("ready", 10, 60, NOW)
    before = copy.deepcopy(database["auth_rate_limits"].docs)
    del database["users"].indexes["username_key_unique"]
    with pytest.raises(SecurityError) as failure:
        repository.consume_limit("after-removal", 10, 60, NOW)
    assert failure.value.code == "security_indexes_not_ready"
    assert database["auth_rate_limits"].docs == before


def test_index_driver_error_is_sanitized(catalog, monkeypatch):
    repository, principal, state, game_id, database, client = setup_store(catalog)

    def unavailable():
        raise PyMongoError("Sensitive driver details")
    monkeypatch.setattr(database["users"], "index_information", unavailable)
    with pytest.raises(SecurityError) as failure:
        repository.create_user({"username_key": "new"})
    assert failure.value.code == "security_index_verification_unavailable"
    assert "Sensitive" not in str(failure.value)


def test_transient_authorization_failure_preserves_driver_retry_label(catalog, monkeypatch):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    client.retry_transient = True
    original = database["users"].update_one
    failures = []

    def conflict_once(query, update, **kwargs):
        if kwargs.get("session") is not None and not failures:
            failures.append(True)
            raise OperationFailure("Simulated transient write conflict", code=112,
                                   details={"errorLabels": ["TransientTransactionError"]})
        return original(query, update, **kwargs)
    monkeypatch.setattr(database["users"], "update_one", conflict_once)
    result = service_for(repository, principal, game_id).execute(
        game_id, context(state), ActionCommand(action_id="retried", expected_revision=0, action=Skip()))
    assert result.state.revision == 1 and len(database["game_action_receipts"].docs) == 1
    assert database["auth_sessions"].docs[principal.session_hash]["revision"] == 1
    assert database["users"].docs[ObjectId(principal.user_id)]["authorization_revision"] == 1


def test_in_transaction_owned_read_preserves_raw_driver_error(catalog, monkeypatch):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    repository._auth_writes()
    failure = OperationFailure("Simulated conflict", code=112,
                               details={"errorLabels": ["TransientTransactionError"]})

    def unavailable(*args, **kwargs):
        raise failure
    monkeypatch.setattr(database["games"], "find_one", unavailable)
    with pytest.raises(OperationFailure) as caught:
        repository._owned(game_id, principal, NOW, 1800, session=object())
    assert caught.value is failure and caught.value.has_error_label("TransientTransactionError")
    with pytest.raises(SecurityError) as outside:
        repository.load_owned_game(game_id, principal, NOW, 1800)
    assert outside.value.code == "persistence_unavailable"


@pytest.mark.parametrize("after_revision,limit", [(-1, 1), (0, 0), (0, 101), (True, 10)])
def test_public_event_bounds_fail_before_database_queries(catalog, after_revision, limit):
    repository, _, _, game_id, database, _ = setup_store(catalog)
    database["games"].calls.clear()
    with pytest.raises(SecurityError) as failure:
        repository.public_events(game_id, after_revision, limit)
    assert failure.value.status == 422 and database["games"].calls == []


def test_public_event_missing_game_is_404_without_receipt_query(catalog):
    repository, _, _, game_id, database, _ = setup_store(catalog)
    with pytest.raises(SecurityError) as failure:
        repository.public_events(str(ObjectId()), 0, 10)
    assert failure.value.status == 404 and database["game_action_receipts"].calls == []


def test_access_change_after_facade_lookup_is_rejected_before_first_receipt(catalog):
    repository, principal, state, game_id, database, client = setup_store(catalog)
    original = GameAccess.model_validate(repository.load_owned_game(game_id, principal, NOW, 1800)["access"])
    database["games"].docs[ObjectId(game_id)]["access"]["version"] += 1
    scoped = repository.action_store(principal, game_id, lambda: NOW, 1800, enabled=True, expected_access=original)
    with pytest.raises(SecurityError) as failure:
        GameActionService(scoped).execute(game_id, context(state), ActionCommand(action_id="blocked", expected_revision=0, action=Skip()))
    assert failure.value.code == "game_access_changed"
    assert not any(op == "find" for op, *_ in database["game_action_receipts"].calls)
    assert database["games"].docs[ObjectId(game_id)]["revision"] == 0
