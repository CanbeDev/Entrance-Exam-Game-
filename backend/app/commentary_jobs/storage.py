"""Optional MongoDB job coordination; no provisioning or claim-based billing."""
from datetime import timedelta
import secrets

from pymongo import ReturnDocument
from pymongo.collation import Collation
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference
from pymongo.write_concern import WriteConcern

from app.commentary_jobs.models import CommentaryJob, utc
from app.security.errors import SecurityError

SIMPLE = Collation("simple")


def collection(database, name):
    return database.get_collection(name, write_concern=WriteConcern(w="majority", wtimeout=5000),
        read_concern=ReadConcern("majority"), read_preference=ReadPreference.PRIMARY)


def unavailable():
    return SecurityError(503, "commentary_jobs_storage_unavailable")


class MongoCommentaryJobRepository:
    def __init__(self, database):
        self.database = database

    @property
    def rows(self):
        return collection(self.database, "commentary_jobs")

    def get(self, game_id, revision):
        try:
            row = self.rows.find_one({"game_id": game_id, "revision": revision}, collation=SIMPLE)
            return CommentaryJob.model_validate(row) if row is not None else None
        except (PyMongoError, ValueError):
            raise unavailable() from None

    def enqueue(self, game_id, revision, action_id, now):
        job = CommentaryJob.queued(game_id, revision, action_id, now)
        try:
            result = self.rows.update_one({"game_id": game_id, "revision": revision},
                {"$setOnInsert": job.document()}, upsert=True, collation=SIMPLE)
            if not result.acknowledged:
                raise unavailable()
        except DuplicateKeyError:
            pass
        except PyMongoError:
            raise unavailable() from None
        found = self.get(game_id, revision)
        if found is None or found.action_id != action_id:
            raise SecurityError(503, "commentary_evidence_mismatch")
        return found

    def claim(self, now):
        now = utc(now)
        try:
            row = self.rows.find_one_and_update(
                {"status": "queued", "available_at": {"$lte": now},
                 "$expr": {"$lt": ["$attempts", "$max_attempts"]}},
                {"$inc": {"attempts": 1}, "$set": {"status": "claimed",
                 "lease_token": secrets.token_urlsafe(24),
                 "lease_expires_at": now + timedelta(seconds=30), "updated_at": now}},
                sort=[("available_at", 1), ("_id", 1)],
                return_document=ReturnDocument.AFTER, collation=SIMPLE)
            return CommentaryJob.model_validate(row) if row is not None else None
        except (PyMongoError, ValueError):
            # An ambiguous atomic claim never grants a caller permission.
            raise unavailable() from None

    @staticmethod
    def _cas(job, now, expired=False):
        query = {"_id": job.id, "status": job.status, "attempts": job.attempts}
        if job.status == "claimed":
            query.update(lease_token=job.lease_token,
                lease_expires_at={"$lte" if expired else "$gt": utc(now)})
            if expired:
                query["$and"] = [{"lease_expires_at": job.lease_expires_at}]
        else:
            query["updated_at"] = job.updated_at
        return query

    def _change(self, job, fields, now, expired=False):
        candidate = CommentaryJob.model_validate({**job.document(), **fields, "updated_at": utc(now)})
        try:
            result = self.rows.update_one(self._cas(job, now, expired),
                {"$set": {**fields, "updated_at": candidate.updated_at}}, collation=SIMPLE)
            if not result.acknowledged:
                raise unavailable()
            return result.matched_count == 1
        except PyMongoError:
            raise unavailable() from None

    def renew(self, job, now):
        if job.status != "claimed":
            return False
        return self._change(job, {"lease_expires_at": utc(now) + timedelta(seconds=30)}, now)

    def finish(self, job, now, *, reason=None, expired=False):
        if job.status not in {"queued", "claimed", "failed"} or (job.status == "failed" and reason is not None):
            return False
        return self._change(job, {"status": "failed" if reason else "ready",
            "lease_token": None, "lease_expires_at": None, "last_error": reason,
            "failure_reason": reason, "completed_at": utc(now)}, now, expired)

    def retry(self, job, now, reason, *, expired=False):
        if job.status != "claimed" or job.attempts >= job.max_attempts:
            return self.finish(job, now, reason="attempts_exhausted", expired=expired)
        delay = 5 if job.attempts == 1 else 20
        return self._change(job, {"status": "queued", "available_at": utc(now) + timedelta(seconds=delay),
            "lease_token": None, "lease_expires_at": None, "last_error": reason,
            "failure_reason": None, "completed_at": None}, now, expired)

    def expired(self, now, limit=50):
        try:
            return [CommentaryJob.model_validate(row) for row in self.rows.find(
                {"status": "claimed", "lease_expires_at": {"$lte": utc(now)}},
                collation=SIMPLE).sort([("lease_expires_at", 1), ("_id", 1)]).limit(limit)]
        except (PyMongoError, ValueError):
            raise unavailable() from None
