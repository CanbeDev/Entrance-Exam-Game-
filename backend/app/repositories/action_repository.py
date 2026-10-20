from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference
from pymongo.write_concern import WriteConcern

from app.engine.errors import GameplayWritesDisabled, PersistenceUnavailable, RevisionConflict
from app.models.events import ActionResult
from app.services.game_action_service import ActionReceipt, replay_receipt


def runtime_document(state) -> dict:
    document = state.model_dump(mode="json")
    document["created_at"] = state.created_at
    document["updated_at"] = state.updated_at
    return document


class MongoActionRepository:
    """Explicit client/database injection. No production connection import.

    gameplay_writes_enabled is a deliberate caller attestation AFTER disposable
    transaction verification. It defaults to False and is never set by the API.
    All transaction retries reuse the precomputed receipt, dice and events.
    """
    def __init__(self, client, database, *, gameplay_writes_enabled: bool = False):
        self._client = client
        self._games = database["games"]
        self._receipts = database["game_action_receipts"]
        self._enabled = gameplay_writes_enabled is True

    @staticmethod
    def object_id(game_id: str):
        if not isinstance(game_id, str):
            return None
        try:
            return ObjectId(game_id)
        except (InvalidId, TypeError):
            return None

    @staticmethod
    def receipt_id(game_id: str, action_id: str) -> str:
        # ObjectId has a fixed 24-character representation; command IDs forbid ':'.
        return f"{game_id}:{action_id}"

    def _authorize_access(self, game_id: str, *, session=None) -> None:
        """Trusted local repository has no account boundary; scoped adapters override."""

    def _scope_update(self, query: dict) -> dict:
        return query

    def find_receipt(self, game_id: str, action_id: str) -> ActionReceipt | None:
        self._authorize_access(game_id)
        object_id = self.object_id(game_id)
        if object_id is None:
            return None
        try:
            document = self._receipts.find_one({"_id": self.receipt_id(str(object_id), action_id)})
            if document is None:
                return None
            return ActionReceipt.model_validate({k: v for k, v in document.items() if k != "_id"})
        except PyMongoError:
            raise PersistenceUnavailable("Unable to read action receipt") from None

    def load_game(self, game_id: str) -> dict | None:
        self._authorize_access(game_id)
        object_id = self.object_id(game_id)
        if object_id is None:
            return None
        try:
            return self._games.find_one({"_id": object_id})
        except PyMongoError:
            raise PersistenceUnavailable("Unable to read game") from None

    def commit(self, receipt: ActionReceipt) -> ActionResult:
        self._authorize_access(receipt.game_id)
        if not self._enabled:
            raise GameplayWritesDisabled("Verify transactions on a disposable database before enabling writes")
        object_id = self.object_id(receipt.game_id)
        if object_id is None:
            raise RevisionConflict("Invalid game ID")
        key = self.receipt_id(str(object_id), receipt.command.action_id)
        existing = self.find_receipt(receipt.game_id, receipt.command.action_id)
        if existing is not None:
            return replay_receipt(existing, receipt.fingerprint)
        expected = receipt.command.expected_revision
        if receipt.result.state.revision != expected + 1:
            raise RevisionConflict("Invalid successor revision")
        state_document = runtime_document(receipt.result.state)
        receipt_document = {"_id": key, **receipt.model_dump(mode="json")}

        def commit_once(session):
            # This callback may run more than once. Do not generate randomness here.
            self._authorize_access(receipt.game_id, session=session)
            saved = self._receipts.find_one({"_id": key}, session=session)
            if saved is not None:
                parsed = ActionReceipt.model_validate({k: v for k, v in saved.items() if k != "_id"})
                return replay_receipt(parsed, receipt.fingerprint)
            query = {"_id": object_id}
            if expected == 0:
                query["$or"] = [{"revision": 0}, {"revision": {"$exists": False}, "schema_version": 2}]
            else:
                query["revision"] = expected
            update = self._games.update_one(self._scope_update(query), {"$set": state_document}, session=session)
            if update.matched_count != 1:
                raise RevisionConflict("Game revision changed; action was not committed")
            self._receipts.insert_one(receipt_document, session=session)
            return receipt.result

        try:
            with self._client.start_session() as session:
                return session.with_transaction(commit_once, read_concern=ReadConcern("snapshot"),
                                                write_concern=WriteConcern("majority"),
                                                read_preference=ReadPreference.PRIMARY)
        except (DuplicateKeyError, RevisionConflict):
            saved = self.find_receipt(receipt.game_id, receipt.command.action_id)
            if saved is not None:
                return replay_receipt(saved, receipt.fingerprint)
            raise RevisionConflict("Concurrent action conflict") from None
        except PyMongoError:
            # If acknowledgement was lost, retry by SAME action ID and payload.
            raise PersistenceUnavailable("Commit unavailable or uncertain; retry the identical action ID and payload") from None
