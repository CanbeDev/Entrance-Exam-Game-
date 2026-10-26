"""Opt-in read-only lifespan smoke. Never creates, provisions or drops a database."""
import json

from bson import ObjectId
from fastapi.testclient import TestClient
import pytest
from pymongo.errors import InvalidOperation, PyMongoError

from app.security.environment import ConfigurationError, load_application_settings
from app.startup import StartupError, create_client
from integration.validator_harness import authorized_client

pytestmark = pytest.mark.disposable_mongo


class OwnedClient:
    """Observe lifespan ownership without exposing URI or client representation."""
    def __init__(self, client):
        self._client = client
        self.close_calls = 0

    @property
    def admin(self):
        return self._client.admin

    def __getitem__(self, name):
        return self._client[name]

    def close(self):
        self.close_calls += 1
        self._client.close()


def test_read_only_closed_gate_lifespan_on_atlas_test(request):
    if not request.config.getoption("--atlas-startup-smoke"):
        pytest.skip("Requires separately authorized --atlas-startup-smoke and existing Atlas TEST guards")
    if not request.config.getoption("--atlas-validator-mongodb"):
        pytest.fail("Startup smoke requires pinned Atlas TEST mode", pytrace=False)

    # A handle to an absent DB supports read-only startup checks. Do not invoke
    # fresh_database: its ownership marker/provisioning would be unauthorized DDL.
    name = "geo_smoke_" + str(ObjectId())
    private = {}

    def guarded_factory(uri):
        settings = load_application_settings({"MONGODB_URI": uri, "MONGODB_DB_NAME": name,
            "PHASE4_TRUSTED_ORIGINS": '["https://startup.example"]'})
        assert not settings.security.auth_writes_enabled and not settings.security.gameplay_writes_enabled
        private["settings"] = settings
        return create_client(settings)

    try:
        with authorized_client(request, read_only=True, client_factory=guarded_factory) as raw:
            assert name not in raw.list_database_names(), "Generated read-only target must not already exist"
            owned = OwnedClient(raw)
            # Import only after explicit guards; main itself remains import-safe.
            from app.main import create_app
            application = create_app(settings_loader=lambda: private["settings"],
                                     client_factory=lambda settings: owned)
            with TestClient(application, base_url="https://startup.example") as http:
                context = application.state.phase4
                assert context is not None and context.auth.store is context.games.store
                assert not context.settings.auth_writes_enabled and not context.settings.gameplay_writes_enabled
                assert application.state.phase4_readiness == "indexes_not_ready"
                checks = {}
                for path in ("/", "/health", "/countries", "/openapi.json"):
                    response = http.get(path)
                    assert response.status_code == 200
                    checks[path] = response.status_code
                assert http.get("/health").json() == {"status": "healthy", "database": "connected"}
                assert len(http.get("/countries").json()["countries"]) == 195
                missing = str(ObjectId())
                for path in ("/games/invalid", f"/games/{missing}", f"/games/{missing}/events"):
                    assert http.get(path).status_code == 404
                for path in ("/auth/register", "/auth/login", "/auth/logout", "/games",
                             f"/games/{missing}/actions", f"/games/{missing}/npc-steps"):
                    response = http.post(path, json={}, headers={"Origin": "https://startup.example"})
                    assert response.status_code == 503
                    assert response.json() == {"detail": {"code": "authentication_disabled"}}
                    assert "set-cookie" not in response.headers
                for path in ("/auth/me", "/auth/csrf", "/me/games"):
                    assert http.get(path).status_code == 401
                response = http.get("/auth/me", cookies={context.settings.cookie_name: "X" * 43})
                assert response.status_code == 503
                untrusted = http.options("/auth/me", headers={"Origin": "https://untrusted.example",
                    "Access-Control-Request-Method": "GET"})
                assert "access-control-allow-origin" not in untrusted.headers
                assert "access-control-allow-credentials" not in untrusted.headers
                assert name not in raw.list_database_names(), "Read-only smoke must not create a database"
                print(json.dumps({"startup": "passed", "gates": "both_disabled", "public": checks,
                    "protected_readiness": application.state.phase4_readiness,
                    "database_created": False, "database_setup": "not_performed"}), flush=True)
            assert owned.close_calls == 1
            assert application.state.phase4 is None and application.state.mongo_client is None
            assert application.state.game_reader is None
            with pytest.raises(InvalidOperation):
                raw.admin.command("ping")  # Driver refuses a closed client before sending.
            print('shutdown=passed client_closed=true', flush=True)
    except (ConfigurationError, StartupError, PyMongoError):
        pytest.fail("Read-only startup smoke failed [STARTUP_OR_DATABASE_UNAVAILABLE]; no fallback", pytrace=False)
