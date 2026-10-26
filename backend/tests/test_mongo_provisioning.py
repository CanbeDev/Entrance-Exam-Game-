"""Offline schema contract checks and DDL safety doubles, never server proof."""
from datetime import datetime
import re
from types import SimpleNamespace

from bson import ObjectId, Int64
import pytest
from pymongo.errors import OperationFailure

from app.models.game import Game, GameSetupRequest
from app.engine.game_setup import initialize_game
from app.repositories.action_repository import runtime_document
from app.repositories.mongo_validators import mongo_validators
from app.repositories.mongo_provisioning import (
    ProvisioningError, inspect_database, preflight_database, provision_database, provisioning_plan,
    validate_target, verify_database,
)
from app.repositories.phase4_indexes import verify_required_indexes
from app.security.errors import SecurityError
from phase2_helpers import make_runtime


def matches(value, schema):
    """Small independent BSON oracle for this manifest, not a MongoDB emulator."""
    if "oneOf" in schema and sum(matches(value, part) for part in schema["oneOf"]) != 1:
        return False
    if "anyOf" in schema and not any(matches(value, part) for part in schema["anyOf"]):
        return False
    if "not" in schema and matches(value, schema["not"]):
        return False
    types = schema.get("bsonType", [])
    types = [types] if isinstance(types, str) else types
    kinds = {"object": isinstance(value, dict), "array": isinstance(value, (tuple, list)),
        "string": isinstance(value, str), "bool": type(value) is bool,
        "int": type(value) is int, "long": isinstance(value, Int64),
        "double": type(value) is float, "decimal": False,
        "date": isinstance(value, datetime), "objectId": isinstance(value, ObjectId), "null": value is None}
    if types and not any(kinds[kind] for kind in types):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", [])):
            return False
        if schema.get("additionalProperties") is False and set(value) - set(props):
            return False
        if any(not matches(child, props[key]) for key, child in value.items() if key in props):
            return False
    if isinstance(value, (list, tuple)):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", float("inf")):
            return False
        items = schema.get("items", {})
        if isinstance(items, list):
            if len(value) > len(items) and schema.get("additionalItems") is False:
                return False
            if any(not matches(child, spec) for child, spec in zip(value, items)):
                return False
        elif any(not matches(child, items) for child in value):
            return False
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", float("inf")):
            return False
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return False
    if type(value) in {int, float, Int64}:
        if "minimum" in schema and (value < schema["minimum"] or
                (schema.get("exclusiveMinimum") and value == schema["minimum"])):
            return False
        if "maximum" in schema and (value > schema["maximum"] or
                (schema.get("exclusiveMaximum") and value == schema["maximum"])):
            return False
    return True


def test_game_history_and_bson(catalog):
    schema = mongo_validators()["games"]["$jsonSchema"]
    initial = initialize_game(GameSetupRequest(game_name="History", starting_country_id="south-africa"), catalog)
    for document in (Game(game_name="Legacy").model_dump(), initial.model_dump(mode="json"),
                     runtime_document(make_runtime(catalog))):
        document["_id"] = ObjectId()
        assert matches(document, schema)
        document["round"] = Int64(document["round"])
        assert matches(document, schema)
    for version in (None, 1, 4, "3", True):
        document = Game(game_name="Legacy").model_dump()
        document["schema_version"] = version
        assert not matches(document, schema)
    document = runtime_document(make_runtime(catalog))
    for field, bad in (("revision", -1), ("revision", True), ("countries", []), ("phase", "unknown")):
        assert not matches({**document, field: bad}, schema)


def test_historical_receipts(catalog):
    from app.models.actions import ActionCommand, Skip
    from app.services.game_action_service import ActionReceipt, command_fingerprint
    from phase2_helpers import context, step
    state = make_runtime(catalog)
    actor = context(state)
    command = ActionCommand(action_id="old", expected_revision=0, action=Skip())
    result = step(state, Skip())
    receipt = ActionReceipt(game_id=str(ObjectId()), actor=actor, command=command,
                            fingerprint=command_fingerprint(actor, command), result=result)
    document = receipt.model_dump(mode="json")
    document["_id"] = document["game_id"] + ":old"
    document["result"].pop("npc_decision", None)
    schema = mongo_validators()["game_action_receipts"]["$jsonSchema"]
    assert matches(document, schema)
    document["result"]["state"]["created_at"] = datetime.now()
    assert matches(document, schema)
    document["command"]["expected_revision"] = True
    assert not matches(document, schema)


@pytest.mark.parametrize("collection,document", [
    ("users", {"username": "user", "username_key": "user", "password_hash": "encoded",
               "status": "active", "auth_version": 1, "created_at": datetime.now()}),
    ("auth_sessions", {"_id": "a" * 64, "user_id": str(ObjectId()), "auth_version": 1,
        "csrf_token": "csrf", "created_at": datetime.now(), "last_seen_at": datetime.now(),
        "expires_at": datetime.now(), "revoked_at": None, "revision": 0}),
    ("auth_rate_limits", {"_id": "a" * 64, "count": 1, "expires_at": datetime.now()}),
])
def test_security_documents(collection, document):
    schema = mongo_validators()[collection]["$jsonSchema"]
    assert matches(document, schema)
    field = "expires_at" if "expires_at" in document else "created_at"
    assert not matches({**document, field: "2026-01-01"}, schema)
    required = schema["required"][0]
    del document[required]
    assert not matches(document, schema)


class Database:
    name = "geo_prov_" + "a" * 24
    client = SimpleNamespace(nodes=frozenset({("127.0.0.1", 27017)}))

    def __init__(self):
        self.collections, self.writes = {}, []
        self.invalid, self.failure = 0, False
        self.duplicates, self.aggregate_calls = set(), []
        self.aggregate_failure = False

    def list_collections(self):
        return [{"name": name, "options": value["options"]} for name, value in self.collections.items()]

    def __getitem__(self, name):
        database = self
        class Collection:
            def index_information(self):
                return database.collections[name]["indexes"]

            def count_documents(self, query):
                assert query == {"$nor": [mongo_validators()[name]]}
                return database.invalid

            def aggregate(self, pipeline, **kwargs):
                database.aggregate_calls.append((name, pipeline, kwargs))
                if database.aggregate_failure:
                    raise OperationFailure("private data")
                return [{"count": 2}] if name in database.duplicates else []

            def create_indexes(self, indexes):
                database.writes.append(("indexes", name))
                if database.failure:
                    raise OperationFailure("private server details")
                database.collections[name]["indexes"] = {
                    model.document["name"]: {**dict(model.document), "key": list(model.document["key"].items())}
                    for model in indexes}
        return Collection()

    def create_collection(self, name, **options):
        self.writes.append(("create", name))
        self.collections[name] = {"options": options, "indexes": {}}

    def command(self, command, name, **options):
        assert command == "collMod"
        self.writes.append((command, name))
        self.collections[name]["options"] = options


def ready():
    database = Database()
    provision_database(database, apply=True, confirmation=database.name)
    return database


def test_dry_run_no_access():
    assert provision_database(object()) == provisioning_plan()
    assert sum(len(item["indexes"]) for item in provisioning_plan().values()) == 8
    first = mongo_validators()
    first.clear()
    assert len(mongo_validators()) == 5


@pytest.mark.parametrize("name", [None, "games", "production", "geo_prov_", "geo_prov_" + "A" * 24])
def test_bad_targets(name):
    with pytest.raises(ValueError):
        validate_target(name)


def test_apply_authorization_and_remote_guard():
    database = Database()
    with pytest.raises(ValueError):
        provision_database(database, apply=True)
    database.client = SimpleNamespace(nodes={("remote.example", 27017)})
    with pytest.raises(ValueError):
        provision_database(database, apply=True, confirmation=database.name)
    assert not database.writes


def test_roundtrip_inspection_and_preflight():
    database = ready()
    database.writes.clear()
    verify_database(database)
    assert all(item["exists"] for item in inspect_database(database).values())
    assert not database.writes
    provision_database(database, apply=True, confirmation=database.name)
    assert sum(kind == "collMod" for kind, _ in database.writes) == 5
    database.writes.clear()
    database.invalid = 1
    with pytest.raises(ValueError):
        provision_database(database, apply=True, confirmation=database.name)
    assert not database.writes


@pytest.mark.parametrize("option,bad", [("unique", True), ("sparse", True), ("hidden", True),
    ("expireAfterSeconds", 1), ("partialFilterExpression", {}), ("collation", {"locale": "en"}),
    ("key", [("wrong", 1)])])
def test_index_drift(option, bad):
    database = ready()
    database.collections["auth_sessions"]["indexes"]["session_user"][option] = bad
    with pytest.raises(SecurityError):
        verify_required_indexes(database)


@pytest.mark.parametrize("option,bad", [("validationLevel", "moderate"), ("validationAction", "warn"),
                                       ("validator", {})])
def test_validator_drift(option, bad):
    database = ready()
    database.collections["games"]["options"][option] = bad
    with pytest.raises(ValueError):
        verify_database(database)


def test_ddl_failure_stops_without_fallback():
    database = Database()
    database.failure = True
    with pytest.raises(ProvisioningError) as error:
        provision_database(database, apply=True, confirmation=database.name)
    assert error.value.category == "ddl_failed"
    assert error.value.collection == "games"
    assert error.value.may_have_changes and error.value.completed_operations == 1
    assert "private" not in str(error.value)
    assert database.writes == [("create", "games"), ("indexes", "games")]


def test_existing_custom_safeguard_is_not_replaced():
    database = ready()
    database.collections["games"]["options"]["validator"] = {"custom": "guard"}
    database.writes.clear()
    with pytest.raises(ValueError):
        provision_database(database, apply=True, confirmation=database.name)
    assert not database.writes


def test_metadata_failure_and_missing_collection():
    database = ready()
    del database.collections["users"]
    with pytest.raises(ValueError):
        verify_database(database)
    def unavailable():
        raise OperationFailure("private details")
    database.list_collections = unavailable
    with pytest.raises(ProvisioningError, match="metadata_unavailable"):
        inspect_database(database)
    assert len(database.writes) == 10


def test_cli_offline_and_preclient_refusal(monkeypatch, capsys):
    from tools.provision_phase4_indexes import main
    import pymongo
    def forbidden(*args, **kwargs):
        raise AssertionError("Client must not be constructed")
    monkeypatch.setattr(pymongo, "MongoClient", forbidden)
    main([])
    assert "owned_game_creation_unique" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["--apply", "--database", Database.name])


@pytest.mark.parametrize("collection", ["users", "games"])
def test_unique_preflight_no_mutation_or_key_disclosure(collection):
    database = ready()
    database.writes.clear()
    database.duplicates.add(collection)
    with pytest.raises(ProvisioningError) as error:
        provision_database(database, apply=True, confirmation=database.name)
    assert error.value.category == "unique_values_conflict"
    assert error.value.collection == collection
    assert not error.value.may_have_changes and not database.writes


def test_unique_preflight_exact_partial_filter_and_safe_projection():
    database = ready()
    database.aggregate_calls.clear()
    preflight_database(database)
    calls = {name: (pipeline, options) for name, pipeline, options in database.aggregate_calls}
    assert set(calls) == {"users", "games"}
    pipeline, options = calls["games"]
    assert pipeline[0] == {"$match": {"access.owner_user_id": {"$type": "string"},
                                      "creation.key": {"$type": "string"}}}
    assert pipeline[1]["$group"]["_id"] == {
        "k0": {"$ifNull": ["$access.owner_user_id", None]},
        "k1": {"$ifNull": ["$creation.key", None]}}
    assert pipeline[-2:] == [{"$limit": 1}, {"$project": {"_id": 0, "count": 1}}]
    assert options == {"allowDiskUse": False, "maxTimeMS": 10000}


@pytest.mark.parametrize("drift", ["named_keys", "unique", "other_name", "hidden", "unknown_option"])
def test_index_conflict_preflight_no_ddl(drift):
    database = ready()
    indexes = database.collections["users"]["indexes"]
    found = indexes["username_key_unique"]
    if drift == "named_keys":
        found["key"] = [("other", 1)]
    elif drift == "other_name":
        indexes["different_name"] = indexes.pop("username_key_unique")
    else:
        found[{"unique": "unique", "hidden": "hidden", "unknown_option": "prepareUnique"}[drift]] = drift != "unique"
    database.writes.clear()
    with pytest.raises(ProvisioningError, match="index_conflict"):
        provision_database(database, apply=True, confirmation=database.name)
    assert not database.writes


def test_preflight_failure_is_sanitized_and_stops_before_ddl():
    database = ready()
    database.aggregate_failure = True
    database.writes.clear()
    with pytest.raises(ProvisioningError) as error:
        provision_database(database, apply=True, confirmation=database.name)
    assert error.value.category == "preflight_unavailable"
    assert "private" not in str(error.value) and not database.writes


@pytest.mark.parametrize("timestamp", ["2026-10-25T12:34:56Z", "2026-10-25T12:34:56.123456+02:00",
    "2026-10-25T12:34:56", "2026-10-25 12:34:56.123-03:30", datetime(2026, 10, 25)])
def test_game_timestamp_compatibility(timestamp, catalog):
    document = runtime_document(make_runtime(catalog))
    document["created_at"] = timestamp
    assert matches(document, mongo_validators()["games"]["$jsonSchema"])


@pytest.mark.parametrize("timestamp", ["not-a-date", "2026-10-25", "2026-13-25T12:00:00Z",
    "2026-10-32T12:00:00Z", "2026-10-25T24:00:00Z", "2026-10-25T12:60:00Z",
    "2026-10-25T12:00:00Z\n", "2026-10-25T12:00:00Z junk"])
def test_invalid_game_timestamp_rejected(timestamp, catalog):
    document = runtime_document(make_runtime(catalog))
    document["updated_at"] = timestamp
    assert not matches(document, mongo_validators()["games"]["$jsonSchema"])


@pytest.mark.parametrize("value,valid", [("2026-10-25", True), (datetime(2026, 10, 25), True),
    ("2026-00-01", False), ("garbage", False), ("2026-10-25T12:00:00Z", False)])
def test_snapshot_date_format(value, valid, catalog):
    document = runtime_document(make_runtime(catalog))
    document["population_snapshot"]["retrieved_on"] = value
    assert matches(document, mongo_validators()["games"]["$jsonSchema"]) is valid


def test_eight_authoritative_indexes_frozen():
    from app.repositories.phase4_indexes import phase4_indexes
    actual = {collection: [dict(model.document) for model in indexes]
              for collection, indexes in phase4_indexes().items()}
    assert actual == {
        "users": [{"key": {"username_key": 1}, "unique": True, "name": "username_key_unique"}],
        "auth_sessions": [{"key": {"user_id": 1}, "name": "session_user"},
            {"key": {"expires_at": 1}, "expireAfterSeconds": 0, "name": "session_expiry"}],
        "auth_rate_limits": [{"key": {"expires_at": 1}, "expireAfterSeconds": 0, "name": "rate_limit_expiry"}],
        "games": [{"key": {"access.owner_user_id": 1, "_id": -1}, "name": "owned_game_listing"},
            {"key": {"access.owner_user_id": 1, "creation.key": 1}, "unique": True,
             "partialFilterExpression": {"access.owner_user_id": {"$type": "string"},
                                         "creation.key": {"$type": "string"}},
             "name": "owned_game_creation_unique"}],
        "game_action_receipts": [{"key": {"game_id": 1, "result.state.revision": 1}, "name": "game_event_revision"},
            {"key": {"game_id": 1, "command.expected_revision": 1, "actor.kind": 1}, "name": "npc_revision_replay"}]}
    # Dict equality alone cannot assert compound-key order.
    assert [list(index["key"].items()) for index in actual["games"]] == [
        [("access.owner_user_id", 1), ("_id", -1)], [("access.owner_user_id", 1), ("creation.key", 1)]]
    assert [list(index["key"].items()) for index in actual["game_action_receipts"]] == [
        [("game_id", 1), ("result.state.revision", 1)],
        [("game_id", 1), ("command.expected_revision", 1), ("actor.kind", 1)]]


def test_service_generated_npc_receipt_and_historical_variants(catalog):
    from copy import deepcopy
    from npc_helpers import controller_for, npc_state
    store, _, controller = controller_for(npc_state(catalog))
    submission = controller.prepare(store.game_id)
    result = controller.submit(submission)
    assert result.npc_decision == submission.decision
    document = next(iter(store.receipts.values())).model_dump(mode="json")
    document["_id"] = store.game_id + ":" + submission.command.action_id
    schema = mongo_validators()["game_action_receipts"]["$jsonSchema"]
    assert matches(document, schema)
    # Exercise the fixed positional array in current transfer evidence as well.
    document["result"]["npc_decision"]["projected_potential"] = [0, 1, -3, -4, 5]
    assert matches(document, schema)
    invalid = deepcopy(document)
    invalid["result"]["npc_decision"]["projected_potential"].append(6)
    assert not matches(invalid, schema)
    for historical in (None, "missing"):
        copy = deepcopy(document)
        if historical is None:
            copy["result"]["npc_decision"] = None
        else:
            del copy["result"]["npc_decision"]
        assert matches(copy, schema)


def test_actual_v2_storage_date_representation(catalog):
    initial = initialize_game(GameSetupRequest(game_name="v2", starting_country_id="south-africa"), catalog)
    document = initial.model_dump()
    document["population_snapshot"]["retrieved_on"] = initial.population_snapshot.retrieved_on.isoformat()
    document["_id"] = ObjectId()
    assert matches(document, mongo_validators()["games"]["$jsonSchema"])


def test_post_ddl_verification_failure_reports_partial_state(monkeypatch):
    import app.repositories.mongo_provisioning as module
    database = Database()
    def reject(database):
        raise ProvisioningError("validators_not_ready", "games")
    monkeypatch.setattr(module, "verify_database", reject)
    with pytest.raises(ProvisioningError) as error:
        provision_database(database, apply=True, confirmation=database.name)
    assert error.value.category == "verification_failed"
    assert error.value.may_have_changes and error.value.completed_operations == 10
    assert len(database.writes) == 10
