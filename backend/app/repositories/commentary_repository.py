"""Durable, single-document commentary claims. Importing never connects.

No lease is reclaimed: a process crash may leave a narration unavailable, but
cannot authorize another potentially billable provider attempt for that battle.
The collection's built-in unique _id is the only required index.
"""
from copy import deepcopy
import re

from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference
from pymongo.write_concern import WriteConcern

from app.security.errors import SecurityError


_PUBLIC_FIELDS = ("game_id", "revision", "action_id", "status", "source", "text", "reason", "facts")


class MongoCommentaryRepository:
    def __init__(self, database):
        # Collection acquisition stays lazy for managed startup and isolated apps.
        # Construction performs no provisioning, metadata reads or database I/O.
        self._database = database

    @property
    def _collection(self):
        return self._database.get_collection(
            "battle_commentary", write_concern=WriteConcern(w="majority", wtimeout=5000),
            read_concern=ReadConcern("majority"), read_preference=ReadPreference.PRIMARY)

    @staticmethod
    def _identity(game_id, revision):
        if not isinstance(game_id, str) or re.fullmatch(r"[0-9a-fA-F]{24}", game_id) is None:
            raise SecurityError(404, "game_not_found")
        if type(revision) is not int or revision < 1:
            raise SecurityError(422, "invalid_revision")
        return game_id.lower(), f"{game_id.lower()}:{revision}"

    @staticmethod
    def _token(token):
        if not isinstance(token, str) or re.fullmatch(r"[A-Za-z0-9_-]{16,128}", token) is None:
            raise ValueError("Invalid commentary claim")

    @staticmethod
    def _public(document, game_id, revision, statuses):
        if (document.get("game_id") != game_id or document.get("revision") != revision
                or document.get("status") not in statuses):
            raise ValueError("Invalid commentary document")
        return {key: deepcopy(document[key]) for key in _PUBLIC_FIELDS if key in document}

    def get(self, game_id, revision):
        _, identifier = self._identity(game_id, revision)
        try:
            document = self._collection.find_one({"_id": identifier}, {"_id": 0, "claim_token": 0})
            return deepcopy(document) if document is not None else None
        except PyMongoError:
            raise SecurityError(503, "commentary_storage_unavailable") from None

    def claim(self, game_id, revision, document, token):
        game_id, identifier = self._identity(game_id, revision)
        self._token(token)
        public = self._public(document, game_id, revision, {"pending"})
        claimed_at = document.get("claimed_at")
        if claimed_at is None:
            raise ValueError("Invalid commentary claim time")
        record = {**public, "_id": identifier, "claim_token": token, "claimed_at": claimed_at}
        try:
            result = self._collection.insert_one(record)
            if not result.acknowledged:
                raise SecurityError(503, "commentary_storage_unavailable")
            return True
        except DuplicateKeyError:
            return False
        except PyMongoError:
            # Even if insertion actually succeeded, never grant a provider call
            # after an uncertain acknowledgement. The durable claim stays closed.
            raise SecurityError(503, "commentary_storage_unavailable") from None

    def finish(self, game_id, revision, public_result, token):
        game_id, identifier = self._identity(game_id, revision)
        self._token(token)
        public = self._public(public_result, game_id, revision, {"ready", "fallback"})
        try:
            result = self._collection.update_one(
                {"_id": identifier, "status": "pending", "claim_token": token},
                {"$set": public, "$unset": {"claim_token": ""}})
            if not result.acknowledged or result.matched_count != 1:
                raise SecurityError(503, "commentary_storage_unavailable")
        except PyMongoError:
            raise SecurityError(503, "commentary_storage_unavailable") from None
