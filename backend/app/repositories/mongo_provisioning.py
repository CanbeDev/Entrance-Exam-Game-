"""Explicit local disposable provisioning; no application settings or clients."""
import re

from pymongo.errors import PyMongoError

from app.repositories.mongo_validators import mongo_validators
from app.repositories.phase4_indexes import index_matches, phase4_indexes, verify_required_indexes
from app.security.errors import SecurityError


class ProvisioningError(ValueError):
    """Only fixed categories/manifest collection names; never driver messages/data."""
    CATEGORIES = frozenset({"invalid_target", "confirmation_required", "loopback_required",
        "metadata_unavailable", "unsupported_collection", "documents_incompatible",
        "validator_conflict", "collection_options_conflict", "index_conflict",
        "unique_values_conflict", "preflight_unavailable", "validators_not_ready",
        "indexes_not_ready", "ddl_failed", "verification_failed"})

    def __init__(self, category, collection=None, *, may_have_changes=False, completed_operations=0):
        if category not in self.CATEGORIES or collection not in {None, *phase4_indexes()}:
            raise ValueError("Invalid diagnostic category")
        self.category, self.collection = category, collection
        self.may_have_changes = may_have_changes
        self.completed_operations = completed_operations
        location = "" if collection is None else f" collection={collection}"
        super().__init__(f"{category}{location} may_have_changes={may_have_changes} "
                         f"completed_operations={completed_operations}")


def validate_target(name):
    if not isinstance(name, str) or re.fullmatch(r"geo_prov_[0-9a-f]{24}", name) is None:
        raise ProvisioningError("invalid_target")


def provisioning_plan():
    return {name: {"validator": validator, "validationLevel": "strict", "validationAction": "error",
                   "indexes": [dict(index.document) for index in phase4_indexes()[name]]}
            for name, validator in mongo_validators().items()}


def inspect_database(database):
    """Read metadata and counts only; never return document contents."""
    try:
        metadata = {item["name"]: item for item in database.list_collections()}
    except PyMongoError:
        raise ProvisioningError("metadata_unavailable") from None
    result = {}
    for name, validator in mongo_validators().items():
        item = metadata.get(name)
        if item is None:
            result[name] = {"exists": False}
            continue
        if item.get("type", "collection") != "collection":
            raise ProvisioningError("unsupported_collection", name)
        try:
            result[name] = {"exists": True, "options": item.get("options", {}),
                            "indexes": database[name].index_information(),
                            "invalid_documents": database[name].count_documents({"$nor": [validator]})}
        except PyMongoError:
            raise ProvisioningError("metadata_unavailable", name) from None
    return result


def verify_database(database):
    inspection = inspect_database(database)
    for name, validator in mongo_validators().items():
        item = inspection[name]
        options = item.get("options", {})
        if (not item["exists"] or options.get("validator") != validator
                or options.get("validationLevel", "strict") != "strict"
                or options.get("validationAction", "error") != "error"
                or item["invalid_documents"] != 0):
            raise ProvisioningError("validators_not_ready", name)
    try:
        verify_required_indexes(database)
    except SecurityError:
        raise ProvisioningError("indexes_not_ready") from None


def preflight_database(database):
    """Read-only checks for all collections before any DDL. Never return key values.

    Unique checks group only documents selected by the exact manifest partial
    filter. Missing/null nonpartial keys are grouped together as in a unique index.
    Schema validation runs first, so these indexed fields cannot be multikey arrays.
    This is a snapshot of observations, not a lock against concurrent writers.
    """
    before = inspect_database(database)
    plan = provisioning_plan()
    for name, item in before.items():
        if item.get("invalid_documents", 0):
            raise ProvisioningError("documents_incompatible", name)
        options = item.get("options", {})
        if options.get("validator") and options["validator"] != plan[name]["validator"]:
            raise ProvisioningError("validator_conflict", name)
        if any(key in options for key in ("timeseries", "capped", "collation", "encryptedFields")):
            raise ProvisioningError("collection_options_conflict", name)
        if not item["exists"]:
            continue
        for model in phase4_indexes()[name]:
            required = model.document
            for index_name, found in item["indexes"].items():
                same_keys = list(found.get("key", ())) == list(required["key"].items())
                if (index_name == required["name"] and not index_matches(found, required)
                        or same_keys and index_name != required["name"]):
                    raise ProvisioningError("index_conflict", name)
            if required.get("unique"):
                pipeline = []
                if "partialFilterExpression" in required:
                    pipeline.append({"$match": required["partialFilterExpression"]})
                group = {f"k{position}": {"$ifNull": ["$" + field, None]}
                         for position, field in enumerate(required["key"])}
                pipeline.extend([{"$group": {"_id": group, "count": {"$sum": 1}}},
                    {"$match": {"count": {"$gt": 1}}}, {"$limit": 1},
                    {"$project": {"_id": 0, "count": 1}}])
                try:
                    duplicates = list(database[name].aggregate(pipeline, allowDiskUse=False, maxTimeMS=10000))
                except PyMongoError:
                    raise ProvisioningError("preflight_unavailable", name) from None
                if duplicates:
                    raise ProvisioningError("unique_values_conflict", name)
    return before


def provision_database(database, *, apply=False, confirmation=None):
    """Dry-run has no database calls. Apply requires a local-only disposable handle.

    DDL is not transactional. Failures stop without rollback, drops or fallback.
    Inspect partial results before explicitly retrying.
    """
    plan = provisioning_plan()
    if apply is not True:
        return plan
    validate_target(database.name)
    if confirmation != database.name:
        raise ProvisioningError("confirmation_required")
    nodes = database.client.nodes
    if not nodes or any(host not in {"localhost", "127.0.0.1", "::1"} for host, _ in nodes):
        raise ProvisioningError("loopback_required")
    before = preflight_database(database)
    completed = 0
    try:
        for name, item in plan.items():
            options = {key: item[key] for key in ("validator", "validationLevel", "validationAction")}
            if before[name]["exists"]:
                database.command("collMod", name, **options)
            else:
                database.create_collection(name, **options)
            completed += 1
            database[name].create_indexes(list(phase4_indexes()[name]))
            completed += 1
    except PyMongoError:
        # Even the failing command may have succeeded before acknowledgement loss.
        raise ProvisioningError("ddl_failed", name, may_have_changes=True,
                                completed_operations=completed) from None
    try:
        verify_database(database)
    except (ProvisioningError, PyMongoError):
        raise ProvisioningError("verification_failed", may_have_changes=True,
                                completed_operations=completed) from None
    return plan
