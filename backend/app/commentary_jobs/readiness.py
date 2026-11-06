"""Optional metadata checks only. Never provisions or enters gameplay readiness."""
from app.commentary_jobs.schema import job_indexes, job_validator
from app.commentary_jobs.storage import collection, unavailable
from app.security.errors import SecurityError


def auxiliary_validators():
    integer = {"bsonType": ["int", "long"], "minimum": 1}
    identifier = {"bsonType": "string", "pattern": "^[0-9a-f]{24}$"}
    policy = {
        "_id": identifier, "owner_user_id": identifier, "owner_auth_version": integer,
        "access_fingerprint": {"bsonType": "string", "pattern": "^[0-9a-f]{64}$"},
        "enabled": {"bsonType": "bool"}, "version": integer,
        "activation_revision": integer, "updated_at": {"bsonType": "date"},
    }
    slots = {
        "_id": {"bsonType": ["int", "long"], "enum": [0, 1]},
        "token": {"bsonType": ["string", "null"], "pattern": "^[A-Za-z0-9_-]{16,128}$"},
    }
    return {name: {"$jsonSchema": {"bsonType": "object", "additionalProperties": False,
        "required": list(props), "properties": props}} for name, props in {
        "commentary_policies": policy, "commentary_execution_slots": slots}.items()}


def verify_optional_storage(database):
    """Separate activation gate. No collection creation, repair or job inserts."""
    try:
        expected = {"commentary_jobs": job_validator(), **auxiliary_validators()}
        infos = {row["name"]: row for row in database.list_collections(
            filter={"name": {"$in": list(expected)}})}
        for name, validator in expected.items():
            info = infos.get(name, {})
            opts = info.get("options", {})
            if (info.get("type") != "collection" or opts.get("validator") != validator
                    or opts.get("validationLevel", "strict") != "strict"
                    or opts.get("validationAction", "error") != "error"
                    or opts.get("capped") or opts.get("timeseries")
                    or opts.get("collation", {"locale": "simple"}) != {"locale": "simple"}):
                raise SecurityError(503, "commentary_jobs_not_ready")
            if any("expireAfterSeconds" in index for index in collection(database, name).index_information().values()):
                raise SecurityError(503, "commentary_jobs_not_ready")
        indexes = collection(database, "commentary_jobs").index_information()
        for required in job_indexes():
            found = indexes.get(required["name"], {})
            if (list(found.get("key", [])) != list(required["key"].items())
                    or bool(found.get("unique")) != required["unique"]
                    or found.get("partialFilterExpression") != required.get("partialFilterExpression")
                    or found.get("collation", {"locale": "simple"}) != {"locale": "simple"}
                    or found.get("sparse") or found.get("hidden") or "expireAfterSeconds" in found):
                raise SecurityError(503, "commentary_jobs_not_ready")
        slots = list(collection(database, "commentary_execution_slots").find({}))
        if len(slots) != 2 or {row["_id"] for row in slots} != {0, 1}:
            raise SecurityError(503, "commentary_capacity_not_ready")
        for row in slots:
            if set(row) != {"_id", "token"} or (row["token"] is not None
                    and (not isinstance(row["token"], str) or not 16 <= len(row["token"]) <= 128)):
                raise SecurityError(503, "commentary_capacity_not_ready")
    except SecurityError:
        raise
    except Exception:
        raise unavailable() from None
