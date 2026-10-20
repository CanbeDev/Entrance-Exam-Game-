"""Deterministic, injected security store. Not proof of MongoDB transactions.

This module never imports the production database or constructs a MongoDB client.
The RLock deliberately models the authorization/commit boundary for concurrency
tests; real snapshot/write-conflict behavior requires separate disposable tests.
"""
import copy
import threading
from datetime import timedelta

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.engine.errors import GameplayWritesDisabled, RevisionConflict
from app.models.auth import Principal
from app.models.game_access import access_from_document, runtime_payload
from app.security.errors import SecurityError
from app.services.game_action_service import ActionReceipt, replay_receipt
from phase2_helpers import NOW


class MemorySecurityStore:
    def __init__(self, *, clock=lambda: NOW):
        self.clock = clock
        self.lock = threading.RLock()
        self.users = {}
        self.sessions = {}
        self.limits = {}
        self.games = {}
        self.receipts = {}
        self.writes = 0
        self.receipt_reads = 0
        self.after_game_update = None

    @staticmethod
    def _id(value):
        try:
            return str(ObjectId(value))
        except (TypeError, ValueError, InvalidId):
            raise SecurityError(404, "game_not_found") from None

    @staticmethod
    def _now(value):
        return value() if callable(value) else value

    def consume_limit(self, key, limit, seconds, now):
        with self.lock:
            window = int(now.timestamp()) // seconds
            counter_key = (key, seconds, window)
            count = self.limits.get(counter_key, 0)
            self.limits[counter_key] = count + 1
            return count < limit

    def find_user(self, username_key):
        with self.lock:
            return copy.deepcopy(next((user for user in self.users.values()
                                       if user["username_key"] == username_key), None))

    def create_user(self, document):
        with self.lock:
            if any(user["username_key"] == document["username_key"] for user in self.users.values()):
                raise SecurityError(409, "username_unavailable")
            user_id = str(document.get("_id", ObjectId()))
            self.users[user_id] = {**copy.deepcopy(document), "_id": ObjectId(user_id)}
            return user_id

    def issue_session(self, document, password_hash, previous_hash=None):
        with self.lock:
            user = self.users.get(str(document["user_id"]))
            if (user is None or user.get("status") != "active"
                    or user.get("password_hash") != password_hash
                    or user.get("auth_version", 1) != document["auth_version"]):
                raise SecurityError(401, "invalid_credentials")
            if document["_id"] in self.sessions:
                raise DuplicateKeyError("Duplicate session verifier")
            if (previous_hash in self.sessions
                    and self.sessions[previous_hash]["user_id"] == str(document["user_id"])):
                self.sessions[previous_hash]["revoked_at"] = document["created_at"]
                self.sessions[previous_hash]["revision"] = self.sessions[previous_hash].get("revision", 0) + 1
            user["authorization_revision"] = user.get("authorization_revision", 0) + 1
            self.sessions[document["_id"]] = copy.deepcopy(document)

    def authorize(self, session_hash, now, idle_seconds, *, touch=False, session=None):
        with self.lock:
            record = self.sessions.get(session_hash)
            user = self.users.get(str(record["user_id"])) if record else None
            if (record is None or user is None or record.get("revoked_at") is not None
                    or record["expires_at"] <= now
                    or record["last_seen_at"] + timedelta(seconds=idle_seconds) <= now
                    or user.get("status") != "active"
                    or record["auth_version"] != user.get("auth_version", 1)):
                raise SecurityError(401, "authentication_required")
            if touch:
                record["last_seen_at"] = now
                record["revision"] = record.get("revision", 0) + 1
                user["authorization_revision"] = user.get("authorization_revision", 0) + 1
            return Principal(user_id=str(user["_id"]), username=user["username"],
                             session_hash=session_hash, csrf_token=record["csrf_token"],
                             auth_version=user.get("auth_version", 1))

    def _principal(self, principal, now, idle_seconds):
        current = self.authorize(principal.session_hash, now, idle_seconds)
        if (current.user_id != principal.user_id or current.auth_version != principal.auth_version
                or current.csrf_token != principal.csrf_token):
            raise SecurityError(401, "authentication_required")
        return current

    def revoke_session(self, session_hash, now):
        with self.lock:
            if session_hash in self.sessions:
                self.sessions[session_hash]["revoked_at"] = now
                self.sessions[session_hash]["revision"] = self.sessions[session_hash].get("revision", 0) + 1

    def _owned(self, game_id, principal, now, idle_seconds):
        self._principal(principal, now, idle_seconds)
        document = self.games.get(self._id(game_id))
        if document is None:
            raise SecurityError(404, "game_not_found")
        access = access_from_document(document)
        if access.owner_user_id != principal.user_id:
            raise SecurityError(403, "game_not_owned")
        return document

    def load_owned_game(self, game_id, principal, now, idle_seconds):
        with self.lock:
            return copy.deepcopy(self._owned(game_id, principal, now, idle_seconds))

    def create_owned_game(self, principal, state, key, fingerprint, now, idle_seconds):
        with self.lock:
            self._principal(principal, now, idle_seconds)
            for document in self.games.values():
                if (document.get("access", {}).get("owner_user_id") == principal.user_id
                        and document.get("creation", {}).get("key") == key):
                    if document["creation"]["fingerprint"] != fingerprint:
                        raise SecurityError(409, "creation_id_conflict")
                    return copy.deepcopy(document)
            document = state.model_dump(mode="json")
            human = next(player for player in state.players if player.kind == "human")
            game_id = str(ObjectId())
            document.update({"_id": ObjectId(game_id), "access": {
                "owner_user_id": principal.user_id, "human_player_id": human.id,
                "version": 1, "bound_at": now}, "creation": {"key": key, "fingerprint": fingerprint}})
            self.games[game_id] = document
            self.writes += 1
            return copy.deepcopy(document)

    def list_owned_games(self, principal, *, status, query, cursor, limit, now, idle_seconds):
        with self.lock:
            self._principal(principal, now, idle_seconds)
            if cursor is not None:
                cursor = self._id(cursor)
            candidates = [doc for key, doc in sorted(self.games.items(), reverse=True)
                          if doc.get("access", {}).get("owner_user_id") == principal.user_id
                          and (status is None or doc["status"] == status)
                          and query.casefold() in doc.get("game_name", "").casefold()
                          and (cursor is None or key < cursor)]
            selected = candidates[:limit]
            return {"games": copy.deepcopy(selected),
                    "next_cursor": str(selected[-1]["_id"]) if len(candidates) > limit else None}

    def action_store(self, principal, game_id, now, idle_seconds, *, enabled, expected_access=None):
        return MemoryScopedActionStore(self, principal, game_id, now, idle_seconds, enabled, expected_access)

    def find_npc_result(self, principal, game_id, revision, now, idle_seconds):
        with self.lock:
            self._owned(game_id, principal, self._now(now), idle_seconds)
            self.receipt_reads += 1
            return next((receipt.result for receipt in self.receipts.values()
                         if receipt.game_id == game_id and receipt.actor.kind == "npc"
                         and receipt.command.expected_revision == revision), None)

    def public_events(self, game_id, after_revision, limit):
        with self.lock:
            return [receipt.model_dump(mode="json") for receipt in sorted(
                self.receipts.values(), key=lambda item: item.result.state.revision)
                    if receipt.game_id == game_id and receipt.result.state.revision > after_revision][:limit + 1]


class MemoryScopedActionStore:
    def __init__(self, store, principal, game_id, now, idle_seconds, enabled, expected_access=None):
        self.store, self.principal, self.game_id = store, principal, game_id
        self.now, self.idle_seconds, self.enabled = now, idle_seconds, enabled
        self.access = expected_access
        with store.lock:
            document = self._authorize(game_id)
            self.access = access_from_document(document)

    def _authorize(self, game_id):
        if game_id != self.game_id:
            raise SecurityError(403, "game_not_owned")
        document = self.store._owned(game_id, self.principal, self.store._now(self.now), self.idle_seconds)
        if self.access is not None and access_from_document(document) != self.access:
            raise SecurityError(403, "game_access_changed")
        return document

    def find_receipt(self, game_id, action_id):
        with self.store.lock:
            self._authorize(game_id)
            self.store.receipt_reads += 1
            return self.store.receipts.get((game_id, action_id))

    def load_game(self, game_id):
        with self.store.lock:
            return copy.deepcopy(runtime_payload(self._authorize(game_id)))

    def commit(self, receipt: ActionReceipt):
        if not self.enabled:
            raise GameplayWritesDisabled("Gameplay writes are disabled")
        with self.store.lock:
            document = self._authorize(receipt.game_id)
            key = (receipt.game_id, receipt.command.action_id)
            existing = self.store.receipts.get(key)
            if existing is not None:
                return replay_receipt(existing, receipt.fingerprint)
            if (document.get("revision", 0) != receipt.command.expected_revision
                    or receipt.result.state.revision != receipt.command.expected_revision + 1):
                raise RevisionConflict("Game revision changed")
            old = copy.deepcopy(document)
            old_sessions = copy.deepcopy(self.store.sessions)
            old_users = copy.deepcopy(self.store.users)
            try:
                self.store.authorize(self.principal.session_hash, self.store._now(self.now),
                                     self.idle_seconds, touch=True)
                document.update(receipt.result.state.model_dump(mode="json"))
                if self.store.after_game_update:
                    self.store.after_game_update(receipt)
                self.store.receipts[key] = receipt
                self.store.writes += 1
            except Exception:
                self.store.games[receipt.game_id] = old
                self.store.sessions = old_sessions
                self.store.users = old_users
                self.store.receipts.pop(key, None)
                raise
            return receipt.result
