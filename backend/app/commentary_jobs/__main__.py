"""Explicit background-worker entry point. Disabled invocation performs no I/O."""
import asyncio
import logging
import os
from datetime import datetime, timezone

from starlette.concurrency import run_in_threadpool

from app.commentary_jobs.settings import load_commentary_job_settings

logger = logging.getLogger("commentary_worker")


async def process(runtime, *, once=False, sleep=asyncio.sleep):
    while True:
        # Each operation preserves its own acknowledgement/CAS boundaries.
        # A failed iteration is never a replay of an in-memory provider request.
        for work in (runtime.discovery.run_once, runtime.worker.reconcile_expired):
            try:
                await run_in_threadpool(work)
            except Exception:
                logger.warning("commentary_worker_reconciliation_unavailable")
        try:
            await runtime.worker.run_once()
        except Exception:
            logger.warning("commentary_worker_processing_unavailable")
        if once:
            return
        await sleep(1)


def main(*, environ=None, once=False, client_factory=None, idle_when_disabled=False):
    values = os.environ if environ is None else environ
    settings = load_commentary_job_settings(values)
    if not settings.discovery_enabled and not settings.execution_enabled:
        print("Commentary worker disabled; no database or provider access.")
        if idle_when_disabled:
            async def idle():
                await asyncio.Event().wait()
            asyncio.run(idle())
        return 0
    # Deliberately below the disabled gate: no credentials or provider objects
    # are loaded merely to verify that the worker can start with both flags off.
    from app.commentary_jobs.runtime import build_commentary_jobs
    from app.security.environment import load_application_settings
    from app.services.phase4_context import build_phase4_context
    from app.services.groq_commentary import GroqNarrator, DEFAULT_MODEL
    from app.startup import create_client, storage_readiness
    from app.security.errors import SecurityError
    application = load_application_settings(values)
    client = (client_factory or create_client)(application)
    try:
        database = client[application.database_name]
        if storage_readiness(client, database) != "ready":
            raise SecurityError(503, "commentary_worker_storage_not_ready")
        clock = lambda: datetime.now(timezone.utc)
        games = build_phase4_context(client, database, application.security, clock=clock).games
        narrator = GroqNarrator(values.get("GROQ_API_KEY"), values.get("GROQ_MODEL", DEFAULT_MODEL))
        runtime = build_commentary_jobs(database, games, narrator, settings, clock)
        asyncio.run(process(runtime, once=once))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Optional Battlefield Dispatch worker")
    parser.add_argument("--idle-when-disabled", action="store_true",
        help="Keep a disabled Render worker idle without database/provider access")
    args = parser.parse_args()
    try:
        raise SystemExit(main(idle_when_disabled=args.idle_when_disabled))
    except KeyboardInterrupt:
        raise SystemExit(0)
    except Exception:
        # No config values, provider/driver exceptions or chained secrets.
        print("Commentary worker unavailable; configuration/readiness review required.")
        raise SystemExit(1) from None
