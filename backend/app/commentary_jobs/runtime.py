"""Explicit optional composition. No CLI, auto-start, provider creation or DDL."""
from types import SimpleNamespace

from app.commentary_jobs.capacity import MongoCommentaryCapacity
from app.commentary_jobs.discovery import MongoCommentaryReceiptSource, ReceiptReconciler
from app.commentary_jobs.policy import MongoCommentaryPolicyStore, CommentaryConsentService
from app.commentary_jobs.readiness import verify_optional_storage
from app.commentary_jobs.storage import MongoCommentaryJobRepository
from app.commentary_jobs.worker import CommentaryWorker
from app.repositories.commentary_repository import MongoCommentaryRepository
from app.services.commentary_service import CommentaryService


def build_commentary_jobs(database, games, narrator, settings, clock):
    """The caller owns runtime invocation and explicit environment authorization."""
    if not settings.discovery_enabled and not settings.execution_enabled:
        return None
    verify_optional_storage(database)
    jobs, policies = MongoCommentaryJobRepository(database), MongoCommentaryPolicyStore(database)
    commentary = CommentaryService(games, MongoCommentaryRepository(database), narrator,
        clock=clock, capacity=MongoCommentaryCapacity(database))
    worker = CommentaryWorker(jobs, policies, commentary, settings, clock)
    discovery = ReceiptReconciler(policies, MongoCommentaryReceiptSource(database), jobs,
        commentary, settings, clock, saved_reconciler=worker.reconcile_saved)
    return SimpleNamespace(jobs=jobs, policies=policies, commentary=commentary, worker=worker,
        discovery=discovery, consent=CommentaryConsentService(games, policies, clock))
