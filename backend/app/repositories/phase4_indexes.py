"""Explicit index manifest. Importing or reading this file never provisions indexes."""
from threading import Lock

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


def index_matches(found: dict, required: dict) -> bool:
    """Compare manifest semantics, ignoring only server bookkeeping/default false."""
    if list(found.get("key", ())) != list(required["key"].items()):
        return False
    for option in ("unique", "sparse", "hidden"):
        if bool(found.get(option, False)) != bool(required.get(option, False)):
            return False
    for option in ("expireAfterSeconds", "partialFilterExpression", "collation"):
        if found.get(option) != required.get(option):
            return False
    supported = {"key", "name", "v", "ns", "background", "unique", "sparse", "hidden",
                 "expireAfterSeconds", "partialFilterExpression", "collation"}
    return not set(found) - supported


def verify_required_indexes(database) -> None:
    """Read existing metadata only; never create collections/indexes or repair them.

    All manifest indexes must be present with their required keys and security
    options. Managed applications verify once per lifespan before enabling writes;
    unmanaged repositories retain per-write verification. Operators must not change
    indexes during writes, and must restart/reverify after administrative DDL.
    """
    try:
        for collection, indexes in phase4_indexes().items():
            actual = database[collection].index_information()
            for model in indexes:
                required = model.document
                found = actual.get(required["name"], {})
                if not index_matches(found, required):
                    raise SecurityError(503, "security_indexes_not_ready")
    except PyMongoError:
        raise SecurityError(503, "security_index_verification_unavailable") from None


class IndexReadiness:
    """One database/client lifespan, never a process-global cache or a DDL repair.

    Startup serializes verification. Failed attempts remain unready and can retry.
    Request gates only inspect the completed attestation; they cannot initialize it.
    Administrative index changes require paused writes and a new application lifespan.
    """
    def __init__(self, database):
        self._database = database
        self._lock = Lock()
        self._ready = False
        self._closed = False
        self.owned_lookup_compatible = False

    def ensure(self):
        with self._lock:
            if self._closed:
                raise SecurityError(503, "security_indexes_not_ready")
            if not self._ready:
                verify_required_indexes(self._database)
                self._ready = True

    def attest_read_collations(self, metadata):
        # $lookup uses the local collection's collation, unlike independent finds.
        # Only the existing simple/binary comparison semantics are consolidated.
        with self._lock:
            self.require_ready(self._database)
            self.owned_lookup_compatible = all(
                metadata.get(name, {}).get("options", {}).get("collation") in (None, {"locale": "simple"})
                for name in ("auth_sessions", "users", "games"))

    def require_ready(self, database):
        if database is not self._database or not self._ready or self._closed:
            raise SecurityError(503, "security_indexes_not_ready")

    def close(self):
        with self._lock:
            self._closed = True
            self._ready = False
            self.owned_lookup_compatible = False
