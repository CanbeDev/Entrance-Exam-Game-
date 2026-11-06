"""Actual repository operations against offline atomic BSON/validator doubles."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from copy import deepcopy

from bson import BSON, Int64
import pytest
from pydantic import ValidationError

from app.commentary_jobs.capacity import MongoCommentaryCapacity
from app.commentary_jobs.models import CommentaryJob
from app.commentary_jobs.readiness import verify_optional_storage
from app.commentary_jobs.schema import job_indexes, job_validator
from app.commentary_jobs.storage import MongoCommentaryJobRepository
from app.security.errors import SecurityError
from commentary_jobs_helpers import Database
from phase2_helpers import NOW
from test_mongo_provisioning import matches

GAME = "000000000000000000000001"


def setup():
    db = Database()
    return db, MongoCommentaryJobRepository(db)


def test_lazy_construction_performs_no_metadata_or_provisioning():
    db, jobs = setup()
    MongoCommentaryCapacity(db)
    assert db.accesses == []


def test_duplicate_scheduling_race_preserves_one_complete_document():
    db, jobs = setup()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: jobs.enqueue(GAME, 1, "roll", NOW), range(30)))
    assert len({job.id for job in results}) == 1
    row = results[0].document()
    assert len(row) == 16 and row["attempts"] == 0
    assert BSON.encode(row) and matches(row, job_validator()["$jsonSchema"])
    assert len(db.get_collection("commentary_jobs").docs) == 1
    with pytest.raises(SecurityError, match="evidence_mismatch"):
        jobs.enqueue(GAME, 1, "different-action", NOW)
    assert jobs.get(GAME, 1).action_id == "roll"


def test_atomic_claim_races_grant_one_coordination_lease():
    db, jobs = setup()
    jobs.enqueue(GAME, 1, "roll", NOW)
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: MongoCommentaryJobRepository(db).claim(NOW), range(20)))
    assert sum(job is not None for job in claims) == 1
    winner = next(job for job in claims if job)
    assert winner.attempts == 1 and winner.status == "claimed"


@pytest.mark.parametrize("operation", ["update_one", "find_one_and_update"])
def test_unknown_ack_never_returns_a_claim_or_success(operation):
    db, jobs = setup()
    if operation == "find_one_and_update":
        jobs.enqueue(GAME, 1, "roll", NOW)
    db.get_collection("commentary_jobs").fail_after = operation
    with pytest.raises(SecurityError) as error:
        jobs.enqueue(GAME, 1, "roll", NOW) if operation == "update_one" else jobs.claim(NOW)
    assert "PRIVATE" not in str(error.value)
    assert jobs.get(GAME, 1) is not None


def test_renewal_fences_expiry_scan_and_stale_token():
    _, jobs = setup()
    jobs.enqueue(GAME, 1, "roll", NOW)
    original = jobs.claim(NOW)
    assert jobs.renew(original, NOW + timedelta(seconds=20))
    assert jobs.expired(NOW + timedelta(seconds=31)) == []
    assert not jobs.retry(original, NOW + timedelta(seconds=31), "interrupted", expired=True)
    current = jobs.get(GAME, 1)
    wrong = CommentaryJob.model_validate({**current.document(), "lease_token": "wrong_token_00000001"})
    assert not jobs.finish(wrong, NOW + timedelta(seconds=31))
    assert jobs.finish(original, NOW + timedelta(seconds=31))
    assert jobs.get(GAME, 1).status == "ready"


def test_bounded_processing_retry_and_attempt_exhaustion():
    _, jobs = setup()
    jobs.enqueue(GAME, 1, "roll", NOW)
    now = NOW
    for expected in (1, 2, 3):
        job = jobs.claim(now)
        assert job.attempts == expected
        assert jobs.retry(job, now, "capacity_limited")
        if expected < 3:
            assert jobs.claim(now) is None
            now += timedelta(seconds=25)
    terminal = jobs.get(GAME, 1)
    assert terminal.status == "failed" and terminal.failure_reason == "attempts_exhausted"
    assert not jobs.retry(terminal, now, "capacity_limited")
    assert jobs.finish(terminal, now)  # Saved-result truth repair only at service boundary.
    assert jobs.get(GAME, 1).status == "ready"


@pytest.mark.parametrize("field,value", [
    ("attempts", -1), ("attempts", True), ("revision", False),
    ("created_at", "2026-11-06T00:00:00Z"), ("lease_token", "short"),
    ("status", "generating"), ("max_attempts", 4),
])
def test_invalid_job_images_rejected(field, value):
    row = CommentaryJob.queued(GAME, 1, "roll", NOW).document()
    row[field] = value
    with pytest.raises(ValidationError):
        CommentaryJob.model_validate(row)


def test_bson_long_nullable_fields_and_no_schema_drift():
    row = CommentaryJob.queued(GAME, 1, "roll", NOW).document()
    row["revision"], row["attempts"] = Int64(1), Int64(0)
    assert CommentaryJob.model_validate(row).revision == 1
    assert matches(row, job_validator()["$jsonSchema"])
    assert len(job_indexes()) == 3
    assert all("expireAfterSeconds" not in idx for idx in job_indexes())
    assert job_indexes()[0]["unique"] is True


def test_capacity_is_shared_nonexpiring_and_token_fenced():
    db = Database()
    for i in (0, 1):
        db.get_collection("commentary_execution_slots").insert_one({"_id": i, "token": None})
    with ThreadPoolExecutor(max_workers=8) as pool:
        slots = list(pool.map(lambda _: MongoCommentaryCapacity(db).try_acquire(), range(20)))
    winners = [slot for slot in slots if slot]
    assert len(winners) == 2
    restarted = MongoCommentaryCapacity(db)
    assert restarted.try_acquire() is None
    restarted.release(winners[0], False)
    assert restarted.try_acquire() is None
    restarted.release(winners[0], True)
    fresh = restarted.try_acquire()
    assert fresh and fresh.token != winners[0].token
    with pytest.raises(SecurityError):
        restarted.release(winners[0], True)


def test_unknown_capacity_claim_is_quarantined_without_permission():
    db = Database()
    for i in (0, 1):
        db.get_collection("commentary_execution_slots").insert_one({"_id": i, "token": None})
    db.get_collection("commentary_execution_slots").fail_after = "find_one_and_update"
    with pytest.raises(SecurityError):
        MongoCommentaryCapacity(db).try_acquire()
    assert db.get_collection("commentary_execution_slots").docs[0]["token"] is not None


def test_optional_readiness_is_readonly_and_checks_shapes():
    db = Database()
    for i in (0, 1):
        db.get_collection("commentary_execution_slots").insert_one({"_id": i, "token": None})
    verify_optional_storage(db)
    before = {name: deepcopy(rows.docs) for name, rows in db.collections.items()}
    db.metadata = []
    with pytest.raises(SecurityError):
        verify_optional_storage(db)
    assert {name: rows.docs for name, rows in db.collections.items()} == before
    assert all(not rows.images for name, rows in db.collections.items() if name == "commentary_jobs")
