"""Explicitly injected MongoDB security persistence. Importing never connects."""
from datetime import datetime, timedelta, timezone
import hashlib
import re

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference
from pymongo.write_concern import WriteConcern

from app.models.auth import Principal
from app.models.game_access import GameAccess, access_from_document
from app.security.errors import SecurityError


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class MongoSecurityRepository:
    def __init__(self, client, database, *, auth_writes_enabled: bool = False,
                 gameplay_writes_enabled: bool = False):
        self._client, self._database = client, database
        self._users, self._sessions = database["users"], database["auth_sessions"]
        self._limits, self._games = database["auth_rate_limits"], database["games"]
        self._receipts = database["game_action_receipts"]
        self._auth_enabled = auth_writes_enabled is True
        self._gameplay_enabled = gameplay_writes_enabled is True

    def _required_indexes(self):
        # Do not let an earlier positive check authorize later writes after a
        # required index was removed. This only inspects metadata; never repairs it.
        from app.repositories.phase4_indexes import verify_required_indexes
        verify_required_indexes(self._database)

    def _auth_writes(self):
        if not self._auth_enabled:
            raise SecurityError(503, "authentication_disabled")
        self._required_indexes()

    def _gameplay_writes(self):
        if not self._gameplay_enabled:
            raise SecurityError(503, "gameplay_writes_disabled")
        self._required_indexes()

    def _transaction(self, callback):
        try:
            with self._client.start_session() as session:
                return session.with_transaction(callback, read_concern=ReadConcern("snapshot"),
                                                write_concern=WriteConcern("majority"),
                                                read_preference=ReadPreference.PRIMARY)
        except PyMongoError:
            raise SecurityError(503, "persistence_unavailable") from None

    def consume_limit(self, key: str, limit: int, seconds: int, now: datetime) -> bool:
        self._auth_writes()
        if type(limit) is not int or limit < 1 or type(seconds) is not int or seconds < 1:
            raise ValueError("Invalid rate limit")
        window = int(utc(now).timestamp()) // seconds
        identifier = hashlib.sha256(f"{key}:{seconds}:{window}".encode()).hexdigest()
        try:
            try:
                document = self._limits.find_one_and_update(
                    {"_id": identifier}, {"$inc": {"count": 1}, "$setOnInsert": {
                        "expires_at": datetime.fromtimestamp((window + 2) * seconds, timezone.utc)}},
                    upsert=True, return_document=ReturnDocument.AFTER)
            except DuplicateKeyError:
                # A competing request may create this bucket first. Increment
                # that one existing bucket; never invent a second bucket or allow
                # an uncounted request. No non-atomic read/modify/write fallback.
                document = self._limits.find_one_and_update({"_id": identifier}, {"$inc": {"count": 1}},
                                                            return_document=ReturnDocument.AFTER)
            if document is None:
                raise SecurityError(503, "persistence_unavailable")
            return document["count"] <= limit
        except PyMongoError:
            raise SecurityError(503, "persistence_unavailable") from None

    def find_user(self, username_key: str) -> dict | None:
        try:
            return self._users.find_one({"username_key": username_key})
        except PyMongoError:
            raise SecurityError(503, "persistence_unavailable") from None

    def create_user(self, document: dict) -> str:
        self._auth_writes()
        try:
            return str(self._users.insert_one({**document, "authorization_revision": 0}).inserted_id)
        except DuplicateKeyError:
            raise SecurityError(409, "username_unavailable") from None
        except PyMongoError:
            raise SecurityError(503, "persistence_unavailable") from None

    def issue_session(self, document: dict, password_hash: str, previous_hash: str | None = None) -> None:
        self._auth_writes()
        try:
            if not isinstance(document["user_id"], str):
                raise ValueError("Invalid account identity")
            user_id = ObjectId(document["user_id"])
        except (InvalidId, KeyError, ValueError, TypeError):
            raise SecurityError(401, "invalid_credentials") from None

        def issue(session):
            result = self._users.update_one({"_id": user_id, "status": "active",
                "auth_version": document["auth_version"], "password_hash": password_hash},
                {"$inc": {"authorization_revision": 1}}, session=session)
            if result.matched_count != 1:
                raise SecurityError(401, "invalid_credentials")
            if previous_hash is not None:
                self._sessions.update_one({"_id": previous_hash, "user_id": str(user_id)},
                    {"$set": {"revoked_at": document["created_at"]}, "$inc": {"revision": 1}}, session=session)
            self._sessions.insert_one(document, session=session)
        self._transaction(issue)

    def authorize(self, session_hash: str, now: datetime, idle_seconds: int, *, touch: bool = False,
                  session=None) -> Principal:
        if touch and session is None:
            self._auth_writes()
            return self._transaction(lambda transaction: self.authorize(
                session_hash, now, idle_seconds, touch=True, session=transaction))
        if not isinstance(session_hash, str) or re.fullmatch(r"[0-9a-f]{64}", session_hash) is None:
            raise SecurityError(401, "authentication_required")
        now = utc(now)
        try:
            document = self._sessions.find_one({"_id": session_hash}, session=session)
            if document is None or document.get("revoked_at") is not None:
                raise SecurityError(401, "authentication_required")
            if (utc(document["expires_at"]) <= now
                    or utc(document["last_seen_at"]) <= now - timedelta(seconds=idle_seconds)):
                raise SecurityError(401, "authentication_required")
            if not isinstance(document["user_id"], str):
                raise ValueError("Invalid account identity")
            user_id = ObjectId(document["user_id"])
            user = self._users.find_one({"_id": user_id, "status": "active",
                                       "auth_version": document["auth_version"]}, session=session)
            if user is None:
                raise SecurityError(401, "authentication_required")
            if touch:
                self._auth_writes()
                guard = {"_id": session_hash, "user_id": str(user_id), "auth_version": user["auth_version"],
                         "revoked_at": None, "revision": document["revision"],
                         "expires_at": {"$gt": now}, "last_seen_at": {"$gt": now - timedelta(seconds=idle_seconds)}}
                result = self._sessions.update_one(guard, {"$set": {"last_seen_at": now},
                                                          "$inc": {"revision": 1}}, session=session)
                if result.matched_count != 1:
                    raise SecurityError(401, "authentication_required")
                if session is not None:
                    # Writes serialize against logout/session revocation and account
                    # disabling/version changes inside the same transaction.
                    result = self._users.update_one({"_id": user_id, "status": "active",
                        "auth_version": user["auth_version"]}, {"$inc": {"authorization_revision": 1}}, session=session)
                    if result.matched_count != 1:
                        raise SecurityError(401, "authentication_required")
            return Principal(user_id=str(user_id), username=user["username"], session_hash=session_hash,
                             csrf_token=document["csrf_token"], auth_version=user["auth_version"])
        except (InvalidId, KeyError, TypeError, ValueError, AttributeError):
            raise SecurityError(401, "authentication_required") from None
        except PyMongoError:
            if session is not None:
                # Preserve driver labels until with_transaction has retried.
                raise
            raise SecurityError(503, "persistence_unavailable") from None

    def _principal(self, principal: Principal, now: datetime, idle_seconds: int, *, session=None):
        actual = self.authorize(principal.session_hash, now, idle_seconds, touch=session is not None, session=session)
        if actual.user_id != principal.user_id or actual.auth_version != principal.auth_version:
            raise SecurityError(401, "authentication_required")
        return actual

    def revoke_session(self, session_hash: str, now: datetime) -> None:
        self._auth_writes()
        try:
            self._sessions.update_one({"_id": session_hash, "revoked_at": None},
                                     {"$set": {"revoked_at": now}, "$inc": {"revision": 1}})
        except PyMongoError:
            raise SecurityError(503, "persistence_unavailable") from None

    def _owned(self, game_id: str, principal: Principal, now: datetime, idle_seconds: int, *, session=None):
        self._principal(principal, now, idle_seconds, session=session)
        try:
            if not isinstance(game_id, str):
                raise ValueError("Invalid game identity")
            object_id = ObjectId(game_id)
        except (InvalidId, ValueError, TypeError):
            raise SecurityError(404, "game_not_found") from None
        try:
            document = self._games.find_one({"_id": object_id}, session=session)
            if document is None:
                raise SecurityError(404, "game_not_found")
            access = access_from_document(document)
            if access.owner_user_id != principal.user_id:
                raise SecurityError(403, "game_not_owned")
            return document, access
        except PyMongoError:
            if session is not None:
                raise
            raise SecurityError(503, "persistence_unavailable") from None

    def load_owned_game(self, game_id: str, principal: Principal, now: datetime, idle_seconds: int) -> dict:
        document, _ = self._owned(game_id, principal, now, idle_seconds)
        return {**document, "_id": str(document["_id"])}

    def create_owned_game(self, principal: Principal, state, key: str, fingerprint: str,
                          now: datetime, idle_seconds: int) -> dict:
        from app.repositories.action_repository import runtime_document
        self._gameplay_writes()
        self._principal(principal, now, idle_seconds)
        human = next(player.id for player in state.players if player.kind == "human")
        access = GameAccess(owner_user_id=principal.user_id, human_player_id=human, bound_at=now)
        document = {"_id": ObjectId(), **runtime_document(state), "access": access.model_dump(),
                    "creation": {"key": key, "fingerprint": fingerprint}}

        def create(session):
            self._principal(principal, now, idle_seconds, session=session)
            existing = self._games.find_one({"access.owner_user_id": principal.user_id,
                                             "creation.key": key}, session=session)
            if existing is not None:
                if existing.get("creation", {}).get("fingerprint") != fingerprint:
                    raise SecurityError(409, "creation_id_conflict")
                return {**existing, "_id": str(existing["_id"])}
            self._games.insert_one(document, session=session)
            # Return the database's codec/timestamp representation, just as the
            # duplicate path does. BSON dates use UTC milliseconds; returning the
            # pre-insert aware datetimes made first/replay JSON differ.
            saved = self._games.find_one({"_id": document["_id"]}, session=session)
            if saved is None:
                raise SecurityError(503, "persistence_unavailable")
            return {**saved, "_id": str(saved["_id"])}
        try:
            return self._transaction(create)
        except SecurityError as exc:
            # A competing same-key insertion is retriable by the exact request;
            # never fall back to a non-transactional insert.
            if exc.status != 503:
                raise
            self._principal(principal, now, idle_seconds)
            try:
                existing = self._games.find_one({"access.owner_user_id": principal.user_id, "creation.key": key})
            except PyMongoError:
                raise exc from None
            if existing is None:
                raise exc from None
            if existing.get("creation", {}).get("fingerprint") != fingerprint:
                raise SecurityError(409, "creation_id_conflict") from None
            return {**existing, "_id": str(existing["_id"])}

    def list_owned_games(self, principal: Principal, *, status: str | None, query: str,
                         cursor: str | None, limit: int, now: datetime, idle_seconds: int) -> dict:
        self._principal(principal, now, idle_seconds)
        if type(limit) is not int or not 1 <= limit <= 100 or not isinstance(query, str) or len(query) > 100:
            raise SecurityError(422, "invalid_game_filter")
        if status is not None and status not in {"waiting", "active", "completed"}:
            raise SecurityError(422, "invalid_game_filter")
        match = {"access.owner_user_id": principal.user_id}
        if status is not None:
            match["status"] = status
        if query:
            match["game_name"] = {"$regex": re.escape(query), "$options": "i"}
        if cursor is not None:
            try:
                match["_id"] = {"$lt": ObjectId(cursor)}
            except (InvalidId, ValueError, TypeError):
                raise SecurityError(422, "invalid_game_cursor") from None
        try:
            documents = list(self._games.find(match).sort("_id", -1).limit(limit + 1))
            more = len(documents) > limit
            documents = documents[:limit]
            return {"games": [{**doc, "_id": str(doc["_id"])} for doc in documents],
                    "next_cursor": str(documents[-1]["_id"]) if more else None}
        except PyMongoError:
            raise SecurityError(503, "persistence_unavailable") from None

    def action_store(self, principal: Principal, game_id: str, now, idle_seconds: int, *, enabled: bool,
                     expected_access: GameAccess | None = None):
        from app.repositories.scoped_action_repository import ScopedMongoActionRepository
        if enabled is True and self._gameplay_enabled:
            self._gameplay_writes()
        return ScopedMongoActionRepository(self, principal, game_id, now, idle_seconds,
                                           gameplay_writes_enabled=enabled is True and self._gameplay_enabled,
                                           expected_access=expected_access)

    def find_npc_result(self, principal: Principal, game_id: str, revision: int,
                        now: datetime, idle_seconds: int):
        from app.services.game_action_service import ActionReceipt
        self._owned(game_id, principal, now, idle_seconds)
        try:
            document = self._receipts.find_one({"game_id": str(ObjectId(game_id)), "command.expected_revision": revision,
                                               "actor.kind": "npc"})
            return None if document is None else ActionReceipt.model_validate(
                {key: value for key, value in document.items() if key != "_id"}).result
        except PyMongoError:
            raise SecurityError(503, "persistence_unavailable") from None

    def public_events(self, game_id: str, after_revision: int, limit: int) -> list[dict]:
        if type(after_revision) is not int or after_revision < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise SecurityError(422, "invalid_event_page")
        try:
            if not isinstance(game_id, str):
                raise ValueError("Invalid game identity")
            object_id = ObjectId(game_id)
        except (InvalidId, TypeError, ValueError):
            raise SecurityError(404, "game_not_found") from None
        try:
            if self._games.find_one({"_id": object_id}, projection={"_id": 1}) is None:
                raise SecurityError(404, "game_not_found")
            return list(self._receipts.find({"game_id": str(object_id),
                "result.state.revision": {"$gt": after_revision}}).sort("result.state.revision", 1).limit(limit + 1))
        except PyMongoError:
            raise SecurityError(503, "persistence_unavailable") from None
