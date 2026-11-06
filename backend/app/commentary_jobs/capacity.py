"""Shared conservative capacity. Slot ownership never expires automatically."""
from dataclasses import dataclass, field
import secrets

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.commentary_jobs.storage import collection, unavailable
from app.security.errors import SecurityError


class UnavailableCommentaryCapacity:
    def try_acquire(self):
        raise SecurityError(503, "commentary_jobs_configuration_unavailable")


@dataclass(frozen=True)
class ExecutionSlot:
    slot: int
    token: str = field(repr=False)


class MongoCommentaryCapacity:
    def __init__(self, database):
        self.database = database

    @property
    def rows(self):
        return collection(self.database, "commentary_execution_slots")

    def try_acquire(self):
        from app.commentary_jobs.readiness import verify_optional_storage
        verify_optional_storage(self.database)
        for number in (0, 1):
            token = secrets.token_urlsafe(24)
            try:
                row = self.rows.find_one_and_update({"_id": number, "token": None},
                    {"$set": {"token": token}}, return_document=ReturnDocument.AFTER)
                if row is not None:
                    if row != {"_id": number, "token": token}:
                        raise unavailable()
                    return ExecutionSlot(number, token)
            except PyMongoError:
                # Unknown acquisition is quarantined, never authorizes dispatch.
                raise unavailable() from None
        return None

    def release(self, slot, certain):
        if not certain:
            return  # Deliberately retain this non-expiring slot for human review.
        try:
            result = self.rows.update_one({"_id": slot.slot, "token": slot.token},
                {"$set": {"token": None}})
            if not result.acknowledged or result.matched_count != 1:
                raise unavailable()
        except PyMongoError:
            raise unavailable() from None
