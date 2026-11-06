"""Worker entry point: disabled mode must not acquire even a database client."""
import asyncio
from types import SimpleNamespace

import pytest

from app.commentary_jobs.__main__ import main, process
from app.security.environment import ConfigurationError


def test_disabled_entrypoint_does_not_load_database_credentials_or_provider(capsys):
    def forbidden(*args):
        raise AssertionError("Disabled worker contacted database")
    assert main(environ={}, client_factory=forbidden) == 0
    assert "no database or provider access" in capsys.readouterr().out


def test_invalid_entrypoint_flag_never_acquires_a_client():
    with pytest.raises(ConfigurationError):
        main(environ={"COMMENTARY_JOBS_EXECUTION_ENABLED": "typo"},
             client_factory=lambda _: pytest.fail("Unexpected database access"))


def test_render_disabled_idle_mode_does_not_load_credentials(monkeypatch):
    calls = []
    def stop_idle(coroutine):
        calls.append("idle")
        coroutine.close()
    monkeypatch.setattr(asyncio, "run", stop_idle)
    assert main(environ={}, idle_when_disabled=True,
        client_factory=lambda _: pytest.fail("Unexpected database access")) == 0
    assert calls == ["idle"]


def test_worker_iteration_runs_discovery_recovery_then_processing_without_hidden_replay():
    calls = []
    def broken():
        calls.append("discover")
        raise RuntimeError("PRIVATE_NOT_LOGGED")
    async def work():
        calls.append("work")
    runtime = SimpleNamespace(discovery=SimpleNamespace(run_once=broken),
        worker=SimpleNamespace(reconcile_expired=lambda: calls.append("recover"), run_once=work))
    asyncio.run(process(runtime, once=True))
    assert calls == ["discover", "recover", "work"]
