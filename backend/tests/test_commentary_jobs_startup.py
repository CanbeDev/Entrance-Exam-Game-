"""Optional settings never start a worker or compromise core startup."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.commentary_jobs.capacity import MongoCommentaryCapacity, UnavailableCommentaryCapacity
from app.security.environment import ApplicationSettings
from app.security.errors import SecurityError
from startup_helpers import StartupClient


@pytest.mark.parametrize("value,kind", [(None, type(None)), ("true", MongoCommentaryCapacity),
    ("false", type(None)), ("typo", UnavailableCommentaryCapacity)])
def test_optional_execution_flag_constructs_no_worker_or_database_writes(monkeypatch, value, kind):
    monkeypatch.delenv("COMMENTARY_JOBS_DISCOVERY_ENABLED", raising=False)
    monkeypatch.delenv("COMMENTARY_JOBS_EXECUTION_ENABLED", raising=False)
    if value is not None:
        monkeypatch.setenv("COMMENTARY_JOBS_EXECUTION_ENABLED", value)
    client = StartupClient()
    app = create_app(settings_loader=lambda: ApplicationSettings("mongodb://localhost", "test"),
        client_factory=lambda _settings: client)
    with TestClient(app):
        assert isinstance(app.state.commentary.capacity, kind)
        assert app.state.commentary.narrator.client is None
        assert not any(name.startswith("commentary_") for name in client.database.collections)
        if value == "typo":
            with pytest.raises(SecurityError):
                app.state.commentary.capacity.try_acquire()
