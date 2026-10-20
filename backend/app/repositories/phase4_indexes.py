"""Explicit index manifest. Importing or reading this file never provisions indexes."""
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import PyMongoError

from app.security.errors import SecurityError


def phase4_indexes() -> dict[str, tuple[IndexModel, ...]]:
    return {
        "users": (IndexModel([("username_key", ASCENDING)], unique=True, name="username_key_unique"),),
        "auth_sessions": (IndexModel([("user_id", ASCENDING)], name="session_user"),
                          IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="session_expiry")),
        "auth_rate_limits": (IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="rate_limit_expiry"),),
        "games": (IndexModel([("access.owner_user_id", ASCENDING), ("_id", DESCENDING)], name="owned_game_listing"),
                  IndexModel([("access.owner_user_id", ASCENDING), ("creation.key", ASCENDING)],
                    unique=True, partialFilterExpression={"access.owner_user_id": {"$type": "string"},
                        "creation.key": {"$type": "string"}}, name="owned_game_creation_unique")),
        "game_action_receipts": (IndexModel([("game_id", ASCENDING), ("result.state.revision", ASCENDING)],
                                            name="game_event_revision"),
                                 IndexModel([("game_id", ASCENDING), ("command.expected_revision", ASCENDING),
                                             ("actor.kind", ASCENDING)], name="npc_revision_replay")),
    }


def provision_phase4_indexes(database) -> dict[str, list[str]]:
    """Caller must explicitly authorize the supplied database before calling."""
    return {name: database[name].create_indexes(list(indexes)) for name, indexes in phase4_indexes().items()}


def verify_required_indexes(database) -> None:
    """Read existing metadata only; never create collections/indexes or repair them.

    All manifest indexes must be present with their required keys and security
    options. Write gates recheck this metadata rather than caching a positive
    result indefinitely. Operators must still avoid index changes during writes.
    """
    try:
        for collection, indexes in phase4_indexes().items():
            actual = database[collection].index_information()
            for model in indexes:
                required = model.document
                found = actual.get(required["name"], {})
                if list(found.get("key", ())) != list(required["key"].items()):
                    raise SecurityError(503, "security_indexes_not_ready")
                if bool(found.get("unique", False)) != bool(required.get("unique", False)):
                    raise SecurityError(503, "security_indexes_not_ready")
                for option in ("expireAfterSeconds", "partialFilterExpression"):
                    if found.get(option) != required.get(option):
                        raise SecurityError(503, "security_indexes_not_ready")
    except PyMongoError:
        raise SecurityError(503, "security_index_verification_unavailable") from None
