"""Managed read-only readiness and client lifecycle; never provisions storage."""
from contextlib import asynccontextmanager
import logging

from pymongo import MongoClient
from starlette.concurrency import run_in_threadpool

from app.repositories.game_repository import MongoGameRepository
from app.repositories.mongo_validators import mongo_validators
from app.repositories.phase4_indexes import verify_required_indexes
from app.security.environment import ConfigurationError, load_application_settings
from app.services.phase4_context import build_phase4_context

logger = logging.getLogger(__name__)


class StartupError(RuntimeError):
    """Fixed diagnostic only. No driver messages/URIs or config values."""


def create_client(settings):
    return MongoClient(settings.mongodb_uri, connect=False, tls=settings.tls_required,
                       serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=10000)


def storage_readiness(client, database):
    """Read metadata only. Does not prove transaction privileges or scan old data."""
    try:
        hello = client.admin.command("hello")
    except Exception:
        return "capability_check_unavailable"
    if (not hello.get("logicalSessionTimeoutMinutes") or
            not (hello.get("setName") or hello.get("msg") == "isdbgrid") or
            not hello.get("isWritablePrimary") or hello.get("maxWireVersion", 0) < 8):
        return "transactions_unavailable"
    try:
        verify_required_indexes(database)
    except Exception:
        return "indexes_not_ready"
    try:
        metadata = {item["name"]: item for item in database.list_collections()}
        for name, validator in mongo_validators().items():
            item = metadata.get(name, {})
            options = item.get("options", {})
            if (item.get("type") != "collection" or options.get("validator") != validator or
                    options.get("validationLevel", "strict") != "strict" or
                    options.get("validationAction", "error") != "error"):
                return "validators_not_ready"
    except Exception:
        return "validator_check_unavailable"
    return "ready"


def application_lifespan(settings_loader=load_application_settings, client_factory=create_client):
    @asynccontextmanager
    async def lifespan(app):
        client = None
        app.state.phase4 = None
        app.state.mongo_client = None
        app.state.game_reader = None
        app.state.phase4_readiness = "starting"
        try:
            try:
                settings = settings_loader()
            except ConfigurationError:
                raise
            except Exception:
                raise ConfigurationError() from None

            def initialize():
                nonlocal client
                try:
                    client = client_factory(settings)
                    client.admin.command("ping")
                    database = client[settings.database_name]
                    readiness = storage_readiness(client, database)
                    if (settings.security.auth_writes_enabled or settings.security.gameplay_writes_enabled) and readiness != "ready":
                        raise StartupError(readiness)
                    context = build_phase4_context(client, database, settings.security)
                    reader = MongoGameRepository(database["games"]).get_game
                    return context, reader, readiness
                except StartupError:
                    raise
                except Exception:
                    raise StartupError("database_initialization_failed") from None

            context, reader, readiness = await run_in_threadpool(initialize)
            app.state.mongo_client, app.state.game_reader = client, reader
            app.state.phase4, app.state.phase4_readiness = context, readiness
            if readiness != "ready":
                logger.warning("phase4_readiness=%s; writes remain disabled", readiness)
            yield
        finally:
            app.state.phase4 = None
            app.state.mongo_client = None
            app.state.game_reader = None
            app.state.phase4_readiness = "stopped"
            if client is not None:
                try:
                    await run_in_threadpool(client.close)
                except Exception:
                    raise StartupError("database_close_failed") from None
    return lifespan
