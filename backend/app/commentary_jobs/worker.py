"""Explicitly invoked worker steps. Import/startup never creates provider calls."""
import asyncio
from contextlib import suppress

from starlette.concurrency import run_in_threadpool

from app.commentary_jobs.models import ERRORS
from app.security.errors import SecurityError


class CommentaryWorker:
    def __init__(self, jobs, policies, commentary, settings, clock):
        self.jobs, self.policies, self.commentary = jobs, policies, commentary
        self.settings, self.clock = settings, clock

    def _result(self, job, result, *, expired=False):
        if result.action_id != job.action_id:
            return self.jobs.finish(job, self.clock(), reason="evidence_mismatch", expired=expired)
        if result.status == "ready" and result.source == "groq":
            return self.jobs.finish(job, self.clock(), expired=expired)
        if result.status == "fallback":
            reason = result.reason if result.reason in ERRORS else "legacy_fallback"
            return self.jobs.finish(job, self.clock(), reason=reason, expired=expired)
        if result.status == "pending":
            return self.jobs.retry(job, self.clock(), "interrupted", expired=expired)
        if result.status == "not_generated":
            return None
        return self.jobs.finish(job, self.clock(), reason="evidence_mismatch", expired=expired)

    def reconcile_expired(self):
        if not self.settings.execution_enabled:
            return 0
        recovered = 0
        for job in self.jobs.expired(self.clock(), self.settings.batch_size):
            result = self.commentary.read(job.game_id, job.revision)
            change = self._result(job, result, expired=True)
            if change is None:
                # No commentary claim exists; another coordination cycle is safe.
                change = self.jobs.retry(job, self.clock(), "interrupted", expired=True)
            recovered += bool(change)
        return recovered

    def reconcile_saved(self, game_id, revision):
        """Read-only provider reconciliation; repairs failed -> ready, never reruns."""
        if not self.settings.execution_enabled:
            return False
        job = self.jobs.get(game_id, revision)
        if job is None or job.status == "ready":
            return False
        result = self.commentary.read(game_id, revision)
        if job.status == "failed":
            return (self.jobs.finish(job, self.clock()) if result.status == "ready"
                and result.source == "groq" and result.action_id == job.action_id else False)
        return self._result(job, result)

    async def run_once(self):
        if not self.settings.execution_enabled:
            return False
        if self.commentary.capacity is None:
            raise SecurityError(503, "commentary_shared_capacity_required")
        job = self.jobs.claim(self.clock())
        if job is None:
            return False
        lost = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(job, lost))
        try:
            result = self.commentary.read(job.game_id, job.revision)
            change = self._result(job, result)
            if change is not None:
                return change
            result = await self.commentary.generate_internal(self.policies, job.game_id,
                job.revision, job.action_id, before_dispatch=lambda: self._live(job, lost))
            return self._result(job, result)
        except SecurityError as error:
            if error.code == "commentary_capacity_limited":
                return self.jobs.retry(job, self.clock(), "capacity_limited")
            if error.status in {401, 403}:
                return self.jobs.finish(job, self.clock(), reason="consent_required")
            # Storage/dispatch uncertainty closes processing. Never replay Groq.
            reason = "evidence_mismatch" if "evidence" in error.code else "storage_unavailable"
            return self.jobs.finish(job, self.clock(), reason=reason)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _heartbeat(self, job, lost):
        while True:
            await asyncio.sleep(10)
            try:
                if not await run_in_threadpool(self.jobs.renew, job, self.clock()):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    def _live(self, held, lost):
        current = self.jobs.get(held.game_id, held.revision)
        if (lost.is_set() or current is None or current.status != "claimed" or current.lease_token != held.lease_token
                or current.lease_expires_at <= self.clock()):
            raise SecurityError(409, "commentary_job_lease_lost")
