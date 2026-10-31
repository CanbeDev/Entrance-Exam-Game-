"""Optional Groq process configuration; startup never contacts the provider."""
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security.environment import ApplicationSettings
from startup_helpers import StartupClient


@pytest.mark.parametrize("model", [None, "fixture-model", "openai/gpt-oss-20b"])
def test_optional_commentary_configuration_and_lifecycle(monkeypatch, model):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    if model is not None:
        monkeypatch.setenv("GROQ_API_KEY", "synthetic-local-test-value")
        monkeypatch.setenv("GROQ_MODEL", model)
    client = StartupClient()
    app = create_app(settings_loader=lambda: ApplicationSettings("mongodb://localhost", "test"),
                     client_factory=lambda _settings: client)
    assert app.state.commentary is None
    with TestClient(app):
        narrator = app.state.commentary.narrator
        assert narrator.model == (model if model is not None else "openai/gpt-oss-20b")
        assert narrator.api_key == ("synthetic-local-test-value" if model is not None else None)
        assert narrator.client is None
        assert "synthetic-local-test-value" not in repr(narrator)
        assert "battle_commentary" not in client.database.collections
        assert client.commands == ["ping", "hello"]
    assert app.state.commentary is None
    assert client.closed == 1
