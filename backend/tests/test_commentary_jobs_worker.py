"""Real receipt evidence and provider-call counts; all storage/provider I/O mocked."""
import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import pytest

from app.commentary_jobs.discovery import ReceiptReconciler
from app.commentary_jobs.worker import CommentaryWorker
from app.security.errors import SecurityError
from app.services.groq_commentary import NarrationUnavailable
from commentary_jobs_helpers import system, discover_all


@pytest.mark.parametrize("npc", [False, True])
def test_receipt_discovery_covers_committed_human_and_npc_battles_after_restart(catalog, npc):
    s = system(catalog, npc=npc, rolls=4)
    before = deepcopy((s.store.games, s.store.receipts))
    discover_all(s)
    expected = {r.result.state.revision for r in s.store.receipts.values()
        if any(e.type == "dice_exchange" for e in r.result.events)}
    assert expected and {job["revision"] for job in s.db.get_collection("commentary_jobs").docs.values()} == expected
    s.discovery = ReceiptReconciler(s.policies, s.source, s.jobs, s.commentary, s.settings, lambda:s.now[0])
    discover_all(s)
    assert len(s.db.get_collection("commentary_jobs").docs) == len(expected)
    assert s.narrator.calls == [] and (s.store.games, s.store.receipts) == before


def test_discovery_enqueue_failure_rescans_receipt_without_losing_battle(catalog):
    s = system(catalog, rolls=3)
    s.db.get_collection("commentary_jobs").fail_after = "update_one"
    with pytest.raises(SecurityError):
        s.discovery.run_once()
    discover_all(s)
    assert len(s.db.get_collection("commentary_jobs").docs) == 3
    assert not s.narrator.calls


def test_reenable_discovery_never_silently_backfills_older_receipts(catalog):
    s = system(catalog, rolls=3)
    s.consent.set_enabled(s.principal, s.game_id, False, 1)
    s.consent.set_enabled(s.principal, s.game_id, True, 2)
    discover_all(s)
    assert not s.db.get_collection("commentary_jobs").docs
    assert not s.narrator.calls


def test_disabled_discovery_and_execution_do_not_read_or_call_anything(catalog):
    s = system(catalog)
    disabled = replace(s.settings, discovery_enabled=False, execution_enabled=False)
    s.discovery.settings = disabled
    s.worker.settings = disabled
    before = len(s.db.accesses)
    assert s.discovery.run_once() == 0
    assert asyncio.run(s.worker.run_once()) is False
    assert s.worker.reconcile_expired() == 0
    assert len(s.db.accesses) == before and not s.narrator.calls


def test_worker_success_uses_saved_narration_and_never_changes_receipts(catalog):
    s = system(catalog)
    discover_all(s)
    before = deepcopy((s.store.games, s.store.receipts))
    assert asyncio.run(s.worker.run_once())
    assert s.jobs.get(s.game_id, 2).status == "ready"
    assert s.commentary.read(s.game_id, 2).source == "groq"
    assert len(s.narrator.calls) == 1
    assert asyncio.run(s.worker.run_once()) is False
    assert (s.store.games, s.store.receipts) == before


def test_concurrent_web_and_worker_share_permanent_claim_and_capacity(catalog):
    s = system(catalog)
    discover_all(s)
    async def run():
        return await asyncio.gather(s.worker.run_once(), s.commentary.generate(s.principal, s.game_id, 2))
    asyncio.run(run())
    s.worker.reconcile_saved(s.game_id, 2)
    assert len(s.narrator.calls) == 1
    assert s.jobs.get(s.game_id, 2).status == "ready"
    assert all(row["token"] is None for row in s.db.get_collection("commentary_execution_slots").docs.values())


@pytest.mark.parametrize("reason", ["provider_timeout", "provider_unavailable", "invalid_output", "not_configured"])
def test_provider_failures_are_terminal_and_never_rebilled(catalog, reason):
    s = system(catalog, reason=reason)
    discover_all(s)
    assert asyncio.run(s.worker.run_once())
    assert s.jobs.get(s.game_id, 2).failure_reason == reason
    s.now[0] += timedelta(days=1)
    restarted = CommentaryWorker(s.jobs, s.policies, s.commentary, s.settings, lambda:s.now[0])
    discover_all(s)
    assert asyncio.run(restarted.run_once()) is False
    assert len(s.narrator.calls) == 1
    occupied = sum(row["token"] is not None for row in s.db.get_collection("commentary_execution_slots").docs.values())
    assert occupied == int(reason in {"provider_timeout", "provider_unavailable"})


def test_admission_denial_is_saved_terminal_and_no_provider_call(catalog):
    s = system(catalog)
    discover_all(s)
    s.store.consume_limit = lambda *args: False
    asyncio.run(s.worker.run_once())
    assert s.jobs.get(s.game_id, 2).failure_reason == "admission_limited"
    assert not s.narrator.calls
    s.now[0] += timedelta(days=1)
    discover_all(s)
    assert asyncio.run(s.worker.run_once()) is False
    assert not s.narrator.calls


def test_restart_recovers_expired_job_only_without_reclaiming_commentary(catalog):
    s = system(catalog)
    discover_all(s)
    first = s.jobs.claim(s.now[0])
    s.now[0] += timedelta(seconds=31)
    worker = CommentaryWorker(s.jobs, s.policies, s.commentary, s.settings, lambda:s.now[0])
    assert worker.reconcile_expired() == 1
    s.now[0] += timedelta(seconds=6)
    assert asyncio.run(worker.run_once())
    assert s.jobs.get(s.game_id, 2).attempts == 2 and len(s.narrator.calls) == 1


def test_existing_stale_permanent_claim_never_reopens_after_job_lease_expiry(catalog):
    s = system(catalog)
    discover_all(s)
    s.jobs.claim(s.now[0])
    base = s.commentary._battle(s.game_id, 2).model_copy(update={"status":"pending","reason":"in_progress"})
    s.commentary.repository.claim(s.game_id, 2,
        {**base.model_dump(mode="json"), "claimed_at":s.now[0]}, "permanent_claim_token_001")
    s.now[0] += timedelta(seconds=31)
    assert s.worker.reconcile_expired() == 1
    assert s.jobs.get(s.game_id, 2).failure_reason == "interrupted"
    discover_all(s)
    assert not s.narrator.calls and asyncio.run(s.worker.run_once()) is False


def test_uncertain_permanent_claim_insert_never_dispatches(catalog):
    s = system(catalog)
    discover_all(s)
    s.db.get_collection("battle_commentary").fail_after = "insert_one"
    assert asyncio.run(s.worker.run_once())
    assert s.jobs.get(s.game_id, 2).status == "failed" and not s.narrator.calls
    s.now[0] += timedelta(seconds=31)
    discover_all(s)
    assert not s.narrator.calls


def test_ready_save_with_uncertain_ack_is_reconciled_without_second_provider_call(catalog):
    s = system(catalog)
    discover_all(s)
    s.db.get_collection("battle_commentary").fail_after = "update_one"
    asyncio.run(s.worker.run_once())
    assert s.jobs.get(s.game_id, 2).status == "failed"
    assert s.commentary.read(s.game_id, 2).status == "ready"
    assert s.worker.reconcile_saved(s.game_id, 2)
    assert s.jobs.get(s.game_id, 2).status == "ready" and len(s.narrator.calls) == 1


def test_existing_saved_prose_is_reused_without_new_admission(catalog):
    s = system(catalog)
    asyncio.run(s.commentary.generate(s.principal, s.game_id, 2))
    limits = deepcopy(s.store.limits)
    discover_all(s)
    asyncio.run(s.worker.run_once())
    assert s.jobs.get(s.game_id, 2).status == "ready"
    assert len(s.narrator.calls) == 1 and s.store.limits == limits


def test_optout_before_worker_dispatch_closes_job_without_provider_or_claim(catalog):
    s = system(catalog)
    discover_all(s)
    s.consent.set_enabled(s.principal, s.game_id, False, 1)
    asyncio.run(s.worker.run_once())
    assert s.jobs.get(s.game_id, 2).failure_reason == "consent_required"
    assert not s.narrator.calls
    assert not s.db.get_collection("battle_commentary").docs


def test_optout_at_final_guard_preserves_closed_claim_without_dispatch(catalog, monkeypatch):
    s = system(catalog)
    discover_all(s)
    original, calls = s.policies.recheck, [0]
    def recheck(context):
        calls[0] += 1
        if calls[0] == 3:
            s.consent.set_enabled(s.principal, s.game_id, False, 1)
        return original(context)
    monkeypatch.setattr(s.policies, "recheck", recheck)
    asyncio.run(s.worker.run_once())
    assert not s.narrator.calls and s.commentary.read(s.game_id, 2).status == "pending"
    assert s.jobs.get(s.game_id, 2).failure_reason == "consent_required"


def test_capacity_denial_is_processing_retry_without_permanent_claim(catalog):
    s = system(catalog)
    discover_all(s)
    s.commentary.capacity.try_acquire()
    s.commentary.capacity.try_acquire()
    asyncio.run(s.worker.run_once())
    job = s.jobs.get(s.game_id, 2)
    assert job.status == "queued" and job.last_error == "capacity_limited"
    assert not s.narrator.calls and not s.db.get_collection("battle_commentary").docs


def test_expired_job_cannot_duplicate_inflight_call_and_late_ready_is_repaired(catalog):
    s = system(catalog)
    discover_all(s)
    async def run():
        started, finish = asyncio.Event(), asyncio.Event()
        async def blocked(facts):
            s.narrator.calls.append(deepcopy(facts))
            started.set()
            await finish.wait()
            return "A fierce clash changes the mood across the battlefield."
        s.narrator.generate = blocked
        original = asyncio.create_task(s.worker.run_once())
        await asyncio.wait_for(started.wait(), 2)
        s.now[0] += timedelta(seconds=31)
        replacement = CommentaryWorker(s.jobs, s.policies, s.commentary, s.settings, lambda:s.now[0])
        assert replacement.reconcile_expired() == 1
        assert s.jobs.get(s.game_id, 2).failure_reason == "interrupted"
        assert await replacement.run_once() is False
        finish.set()
        assert await original is False  # Old job CAS is fenced, saved prose still finishes.
        assert s.commentary.read(s.game_id, 2).status == "ready"
        assert replacement.reconcile_saved(s.game_id, 2)
        assert len(s.narrator.calls) == 1 and s.jobs.get(s.game_id, 2).status == "ready"
    asyncio.run(run())


def test_cancellation_after_dispatch_keeps_capacity_and_permanent_claim_closed(catalog):
    s = system(catalog)
    discover_all(s)
    async def run():
        started = asyncio.Event()
        async def blocked(facts):
            s.narrator.calls.append(deepcopy(facts))
            started.set()
            await asyncio.Event().wait()
        s.narrator.generate = blocked
        task = asyncio.create_task(s.worker.run_once())
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert s.commentary.read(s.game_id, 2).status == "pending"
        s.now[0] += timedelta(seconds=31)
        assert s.worker.reconcile_expired() == 1
        assert await s.worker.run_once() is False
    asyncio.run(run())
    assert len(s.narrator.calls) == 1
    assert sum(row["token"] is not None for row in s.db.get_collection("commentary_execution_slots").docs.values()) == 1


def test_multiple_worker_instances_share_two_global_slots_for_different_battles(catalog):
    s = system(catalog, rolls=4)
    discover_all(s)
    async def run():
        occupied, finish = asyncio.Event(), asyncio.Event()
        async def blocked(facts):
            s.narrator.calls.append(deepcopy(facts))
            if len(s.narrator.calls) == 2:
                occupied.set()
            await finish.wait()
            return "The field falls silent after a fierce clash."
        s.narrator.generate = blocked
        workers = [CommentaryWorker(s.jobs, s.policies, s.commentary, s.settings, lambda:s.now[0]) for _ in range(4)]
        tasks = [asyncio.create_task(worker.run_once()) for worker in workers]
        await asyncio.wait_for(occupied.wait(), 2)
        # All tasks get a chance to observe capacity while the first two remain occupied.
        for _ in range(20):
            await asyncio.sleep(0.005)
        assert len(s.narrator.calls) == 2
        finish.set()
        await asyncio.gather(*tasks)
    asyncio.run(run())
    rows = list(s.db.get_collection("commentary_jobs").docs.values())
    assert sum(row["status"] == "ready" for row in rows) == 2
    assert sum(row["status"] == "queued" for row in rows) == 2
