"""Isolated lifecycle/configuration verification; no production imports or clients."""
import importlib
import sys

from fastapi.testclient import TestClient
import pytest
from pymongo.errors import PyMongoError

from app.security.config import SecuritySettings
from app.security.environment import ApplicationSettings, ConfigurationError, load_application_settings
from app.startup import StartupError, create_client
from startup_helpers import StartupClient

BASE = {"MONGODB_URI": "mongodb://localhost:27017", "MONGODB_DB_NAME": "isolated"}
ORIGIN = "https://game.example"


def create_app(**kwargs):
    # Delay the entry-point import until network/legacy-import guards are active.
    from app.main import create_app as factory
    return factory(**kwargs)


@pytest.fixture(autouse=True)
def no_legacy_database_import(monkeypatch):
    monkeypatch.setitem(sys.modules, "app.database", None)


def config(**changes):
    return load_application_settings({**BASE, **changes})


def test_import_and_factory_never_load_dotenv_or_create_client(monkeypatch):
    import pymongo
    import dotenv
    def forbidden(*args, **kwargs):
        pytest.fail("Import touched external configuration/client")
    monkeypatch.setattr(pymongo, "MongoClient", forbidden)
    monkeypatch.setattr(dotenv, "load_dotenv", forbidden)
    monkeypatch.delitem(sys.modules, "app.main", raising=False)
    module = importlib.import_module("app.main")
    application = module.create_app(settings_loader=forbidden, client_factory=forbidden)
    assert module.app.state.phase4 is None and application.state.mongo_client is None


def test_default_configuration_and_all_existing_limits():
    settings = config()
    assert settings.security == SecuritySettings()
    assert settings.tls_required is False
    values = {"PHASE4_IDLE_SECONDS": "10", "PHASE4_ABSOLUTE_SECONDS": "20",
              "PHASE4_MAX_BODY_BYTES": "1024", "PHASE4_LOGIN_ACCOUNT_LIMIT": "3",
              "PHASE4_LOGIN_IP_LIMIT": "4", "PHASE4_REGISTER_IP_LIMIT": "2", "PHASE4_GAMEPLAY_LIMIT": "6"}
    loaded = config(**values).security
    assert (loaded.idle_seconds, loaded.absolute_seconds, loaded.max_body_bytes,
            loaded.login_account_limit, loaded.login_ip_limit, loaded.register_ip_limit, loaded.gameplay_limit) == (10, 20, 1024, 3, 4, 2, 6)


@pytest.mark.parametrize("missing", ["MONGODB_URI", "MONGODB_DB_NAME"])
def test_missing_database_settings_precede_client_creation(missing):
    values = {key: value for key, value in BASE.items() if key != missing}
    calls = []
    application = create_app(settings_loader=lambda: load_application_settings(values),
                             client_factory=lambda settings: calls.append(settings))
    with pytest.raises(ConfigurationError, match="missing_database_configuration"):
        with TestClient(application):
            pytest.fail("Startup unexpectedly succeeded")
    assert not calls and application.state.phase4 is None


@pytest.mark.parametrize("change", [
    {"PHASE4_AUTH_WRITES_ENABLED": "yes"}, {"PHASE4_AUTH_WRITES_ENABLED": "TRUE"},
    {"PHASE4_GAMEPLAY_WRITES_ENABLED": "true"}, {"PHASE4_AUTH_WRITES_ENABLED": "true"},
    {"PHASE4_IDLE_SECONDS": "0"}, {"PHASE4_IDLE_SECONDS": "-1"},
    {"PHASE4_IDLE_SECONDS": " 10"}, {"PHASE4_IDLE_SECONDS": "1.5"},
    {"PHASE4_IDLE_SECONDS": "50000"}, {"PHASE4_MAX_BODY_BYTES": "x"},
    {"PHASE4_TRUSTED_ORIGINS": "https://game.example"},
    {"PHASE4_TRUSTED_ORIGINS": "null"}, {"PHASE4_TRUSTED_ORIGINS": '[123]'},
    {"PHASE4_TRUSTED_ORIGINS": '["https://*.example"]'},
    {"PHASE4_TRUSTED_ORIGINS": '["http://game.example"]'},
    {"PHASE4_TRUSTED_ORIGINS": '["https://game.example/"]'},
    {"PHASE4_TRUSTED_ORIGINS": '["https://game.example", "https://game.example"]'},
    {"PHASE4_COOKIE_NAME": "insecure"}, {"PHASE4_AUTH_WRITE_ENABLED": "true"},
    {"MONGODB_DB_NAME": "admin/db"}, {"MONGODB_DB_NAME": ""},
    {"MONGODB_URI": "http://localhost"},
    {"MONGODB_URI": "mongodb+srv://test.example/?tls=false"},
    {"MONGODB_URI": "mongodb://test.example/?ssl=false"},
    {"MONGODB_URI": "mongodb://test.example/?tlsAllowInvalidCertificates=true"},
    {"MONGODB_URI": "mongodb://test.example/?tlsAllowInvalidHostnames=true"},
    {"MONGODB_URI": "mongodb://test.example/?w=0"},
    {"MONGODB_URI": "mongodb://test.example/?readPreference=secondary"},
    {"MONGODB_URI": "mongodb://test.example/?tls=true&ssl=true"},
    {"MONGODB_URI": "mongodb://test.example/?tls=true&tls=false"},
    {"MONGODB_URI": "mongodb+srv://test.example:27017"},
    {"MONGODB_URI": "mongodb+srv://test.example/?directConnection=true"},
    {"MONGODB_URI": "mongodb://test.example/?proxyHost=other"},
])
def test_invalid_configuration_is_rejected_without_values(change):
    with pytest.raises(ConfigurationError) as error:
        config(**change)
    assert str(error.value) in {"invalid_configuration", "missing_database_configuration"}


def test_remote_uri_validation_is_offline_and_secrets_are_redacted(monkeypatch):
    import socket
    import dns.resolver
    def forbidden(*args, **kwargs):
        pytest.fail("Configuration loading attempted DNS/network")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(dns.resolver, "resolve", forbidden)
    settings = config(MONGODB_URI="mongodb+srv://synthetic:secret-canary@cluster.example/?retryWrites=true&w=majority")
    assert settings.tls_required and "secret-canary" not in repr(settings)
    with pytest.raises(ConfigurationError) as error:
        config(MONGODB_URI="mongodb+srv://synthetic:secret-canary@cluster.example/?tls=false")
    assert "secret-canary" not in str(error.value)


def test_client_construction_enforces_tls_lazy_connect_and_timeouts(monkeypatch):
    import app.startup as startup
    calls = []
    monkeypatch.setattr(startup, "MongoClient", lambda *args, **kwargs: calls.append((args, kwargs)))
    create_client(config(MONGODB_URI="mongodb+srv://cluster.example"))
    assert calls[0][1] == {"tls": True, "connect": False, "serverSelectionTimeoutMS": 5000,
                           "connectTimeoutMS": 5000, "socketTimeoutMS": 10000}


def test_lifespan_wires_services_public_reads_and_closes_once():
    injected = StartupClient()
    application = create_app(settings_loader=config, client_factory=lambda settings: injected)
    with TestClient(application, base_url=ORIGIN) as http:
        context = application.state.phase4
        assert context.settings == SecuritySettings()
        assert context.auth.store is context.games.store
        assert context.auth.store._client is injected
        assert application.state.phase4_readiness == "ready"
        assert http.get("/").status_code == 200
        assert http.get("/countries").status_code == 200
        assert http.get("/health").json() == {"status": "healthy", "database": "connected"}
        for path in ("/auth/register", "/auth/login", "/auth/logout", "/games", "/games/0/actions", "/games/0/npc-steps"):
            response = http.post(path, json={})
            assert response.status_code == 503 and response.json()["detail"]["code"] == "authentication_disabled"
        for collection in injected.database.collections.values():
            assert not collection.documents and collection.insert_count == 0
    assert injected.closed == 1 and application.state.phase4 is None
    assert application.state.mongo_client is None and application.state.game_reader is None
    assert set(injected.commands) == {"ping", "hello"}


@pytest.mark.parametrize("issue,expected", [
    ("standalone", "transactions_unavailable"), ("secondary", "transactions_unavailable"),
    ("old_wire", "transactions_unavailable"), ("sessions", "transactions_unavailable"),
    ("index", "indexes_not_ready"), ("validator", "validators_not_ready"),
    ("warning", "validators_not_ready"), ("view", "validators_not_ready"),
    ("metadata_error", "validator_check_unavailable"), ("hello_error", "capability_check_unavailable"),
])
@pytest.mark.parametrize("enabled", [False, True])
def test_readiness_gates_enabled_startup_without_repairs(issue, expected, enabled):
    injected = StartupClient()
    if issue == "standalone":
        injected.hello.pop("setName")
    elif issue == "secondary":
        injected.hello["isWritablePrimary"] = False
    elif issue == "old_wire":
        injected.hello["maxWireVersion"] = 7
    elif issue == "sessions":
        injected.hello.pop("logicalSessionTimeoutMinutes")
    elif issue == "index":
        injected.database.collections["users"].indexes.clear()
    elif issue in {"validator", "warning", "view"}:
        item = injected.database.metadata[0]
        if issue == "view":
            item["type"] = "view"
        else:
            item["options"]["validator" if issue == "validator" else "validationAction"] = {} if issue == "validator" else "warn"
    else:
        def fail(*args):
            raise PyMongoError("secret-canary")
        if issue == "metadata_error":
            injected.database.list_collections = fail
        else:
            original = injected.admin.command
            injected.admin.command = lambda command: fail() if command == "hello" else original(command)
    settings = config(PHASE4_AUTH_WRITES_ENABLED=str(enabled).lower(), PHASE4_TRUSTED_ORIGINS='["https://game.example"]')
    application = create_app(settings_loader=lambda: settings, client_factory=lambda settings: injected)
    if enabled:
        with pytest.raises(StartupError, match=expected):
            with TestClient(application):
                pytest.fail("Enabled startup ignored readiness")
    else:
        with TestClient(application) as http:
            assert application.state.phase4_readiness == expected
            assert not application.state.phase4.settings.auth_writes_enabled
            assert http.get("/health").status_code == 200
    assert injected.closed == 1 and application.state.phase4 is None


@pytest.mark.parametrize("stage", ["factory", "ping", "composition", "close"])
def test_lifecycle_failures_close_owned_client_and_hide_details(stage, monkeypatch):
    import app.startup as startup
    injected = StartupClient()
    def fail(*args):
        raise PyMongoError("secret-canary")
    if stage == "ping":
        injected.admin.command = fail
    if stage == "composition":
        monkeypatch.setattr(startup, "build_phase4_context", fail)
    if stage == "close":
        injected.close = fail
    application = create_app(settings_loader=config,
                             client_factory=fail if stage == "factory" else lambda settings: injected)
    with pytest.raises(StartupError) as error:
        with TestClient(application):
            assert stage == "close"
    assert "secret-canary" not in str(error.value)
    if stage not in {"factory", "close"}:
        assert injected.closed == 1
    assert application.state.phase4 is None and application.state.mongo_client is None


def test_trusted_cors_does_not_weaken_origin_csrf_or_cookie_contract():
    injected = StartupClient()
    settings = config(PHASE4_TRUSTED_ORIGINS='["https://game.example"]')
    application = create_app(settings_loader=lambda: settings, client_factory=lambda settings: injected)
    with TestClient(application) as http:
        headers = {"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                   "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type,Idempotency-Key"}
        result = http.options("/games", headers=headers)
        assert result.status_code == 200
        assert result.headers["access-control-allow-origin"] == ORIGIN
        assert result.headers["access-control-allow-credentials"] == "true"
        assert "Origin" in result.headers["vary"]
        result = http.options("/games", headers={**headers, "Origin": "https://other.example"})
        assert result.status_code == 405 and "access-control-allow-origin" not in result.headers
        assert "access-control-allow-credentials" not in result.headers
        result = http.options("/games", headers={**headers, "Access-Control-Request-Headers": "Authorization"})
        assert result.status_code == 400
        assert settings.security.cookie_name == "__Host-geopolitics_session"


def test_multiple_applications_do_not_share_clients_or_context():
    first, second = StartupClient(), StartupClient()
    one = create_app(settings_loader=config, client_factory=lambda settings: first)
    two = create_app(settings_loader=config, client_factory=lambda settings: second)
    with TestClient(one), TestClient(two):
        assert one.state.phase4 is not two.state.phase4
        assert one.state.mongo_client is first and two.state.mongo_client is second
    assert first.closed == second.closed == 1


def test_explicit_test_settings_reach_both_repository_gates_without_writes():
    injected = StartupClient()
    settings = config(PHASE4_AUTH_WRITES_ENABLED="true", PHASE4_GAMEPLAY_WRITES_ENABLED="true",
                      PHASE4_TRUSTED_ORIGINS='["https://game.example"]')
    application = create_app(settings_loader=lambda: settings, client_factory=lambda settings: injected)
    with TestClient(application):
        context = application.state.phase4
        assert context.auth.settings is settings.security and context.games.settings is settings.security
        assert context.auth.store._auth_enabled is True and context.games.store._gameplay_enabled is True
        assert all(not collection.documents for collection in injected.database.collections.values())
    assert injected.closed == 1
