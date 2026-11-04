"""Local HTTP/service doubles and supported driver events; never Atlas."""
import asyncio
import copy
from datetime import datetime, timedelta
import json
import logging
import re
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pymongo import monitoring

from app import npc_diagnostics as diag
from app.security.config import SecuritySettings
from app.services.authorized_game_service import AuthorizedGameService
from app.services.phase4_context import Phase4Context
from app.services.public_game_service import public_result
from benchmark_npc import scenarios
from phase2_helpers import FixedDice, NOW
from test_phase4_api import ORIGIN, owned_game, secured_api, sign_in
from test_phase4_mongo import setup_store

LogHandoff = diag.DiagnosticLogHandoff


def drained(handoff):
    # Bounded test synchronization, never a production flush/join operation.
    with handoff._queue.all_tasks_done:
        assert handoff._queue.all_tasks_done.wait_for(lambda: handoff._queue.unfinished_tasks == 0, timeout=2)


def summaries(caplog):
    drained(caplog.npc_handoff)
    return [json.loads(record.getMessage()) for record in caplog.records if record.name == diag.logger.name]


@pytest.fixture(autouse=True)
def diagnostic_logging(caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger=diag.logger.name)
    handoff = LogHandoff()
    assert handoff.start()
    caplog.npc_handoff = handoff
    # Standalone ASGI / TestClient-without-lifespan cases explicitly inject a
    # started dispatcher. Production starts it only through ASGI lifespan.
    monkeypatch.setattr(diag, "DiagnosticLogHandoff", lambda: handoff)
    yield handoff
    handoff.stop()
    assert handoff.stopped.wait(2)


def npc_request(secured_api, catalog):
    client, module, store, _, _ = secured_api
    headers, _ = sign_in(client)
    game = owned_game(client, headers)
    saved = store.games[game["_id"]]
    from npc_helpers import npc_state
    store.games[game["_id"]] = {**npc_state(catalog).model_dump(mode="json"), "_id": saved["_id"],
                                "access": saved["access"], "creation": saved["creation"]}
    return client, module, store, headers, f"/games/{game['_id']}/npc-steps"


def test_http_success_has_one_correlated_safe_summary_and_unchanged_replay(secured_api, catalog, caplog):
    client, _, store, headers, path = npc_request(secured_api, catalog)
    caplog.clear()
    response = client.post(path, headers={**headers, "X-NPC-Trace-ID": "untrusted-client-value"},
                           json={"expected_revision": 0})
    assert response.status_code == 200
    row, = summaries(caplog)
    assert re.fullmatch(r"[0-9a-f]{32}", row["trace_id"])
    assert response.headers["x-npc-trace-id"] == row["trace_id"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert row["status"] == 200 and row["outcome"] == "returned" and row["response_complete"]
    assert row["operation"] == "start_attack"
    assert row["app_total_ms"] >= row["response_body_sent_ms"] >= row["response_start_ms"] >= 0
    assert row["post_route_framework_ms"] >= 0
    assert datetime.fromisoformat(row["completed_utc"].replace("Z", "+00:00")) >= datetime.fromisoformat(
        row["started_utc"].replace("Z", "+00:00"))
    assert {"route_handler", "route_function", "authentication", "csrf_check", "npc_state_load",
            "npc_decision", "npc_evidence_validation", "engine_action", "response_projection"} <= row["spans_inclusive"].keys()
    # This API fixture uses an in-memory store: absence of driver events is not
    # misrepresented as a measurement of zero production database latency.
    assert row["mongo_commands"] == row["mongo_pool"] == {}
    snapshot = copy.deepcopy((store.games, store.receipts))
    caplog.clear()
    replay = client.post(path, headers=headers, json={"expected_revision": 0})
    assert replay.content == response.content
    assert (store.games, store.receipts) == snapshot
    row2, = summaries(caplog)
    assert row2["trace_id"] != row["trace_id"]
    assert "engine_action" not in row2["spans_inclusive"]


@pytest.mark.parametrize("failure,status", [("origin", 403), ("csrf", 403), ("validation", 422), ("revision", 409)])
def test_rejections_are_timed_without_mutation_or_sensitive_data(secured_api, catalog, caplog, failure, status):
    client, _, store, headers, path = npc_request(secured_api, catalog)
    snapshot = copy.deepcopy((store.games, store.receipts))
    body = {"expected_revision": 0}
    if failure == "origin": headers["Origin"] = "https://untrusted.invalid"
    if failure == "csrf": headers["X-CSRF-Token"] = "synthetic-csrf-canary"
    if failure == "validation": body["private_payload_canary"] = "synthetic-password-canary"
    if failure == "revision": body["expected_revision"] = 999
    caplog.clear()
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == status
    row, = summaries(caplog)
    assert row["status"] == status and row["response_complete"]
    assert response.headers["x-npc-trace-id"] == row["trace_id"]
    assert (store.games, store.receipts) == snapshot
    text = json.dumps(row)
    assert path.split("/")[2] not in text
    for canary in ("synthetic-csrf-canary", "private_payload_canary", "synthetic-password-canary", "untrusted.invalid"):
        assert canary not in text


def test_sanitized_service_failure_still_has_summary(secured_api, catalog, caplog, monkeypatch):
    client, _, _, headers, path = npc_request(secured_api, catalog)
    def unavailable(*args):
        raise RuntimeError("synthetic-private-error-canary")
    monkeypatch.setattr(secured_api[4], "npc_step", unavailable)
    caplog.clear()
    response = client.post(path, headers=headers, json={"expected_revision": 0})
    assert response.status_code == 503
    row, = summaries(caplog)
    assert row["status"] == 503 and row["response_complete"]
    assert row["spans_inclusive"]["route_function"]["failed"] == 1
    assert "synthetic-private-error-canary" not in json.dumps(row)


def test_logging_sink_failure_cannot_invalidate_or_replay_commit(secured_api, catalog, monkeypatch, diagnostic_logging):
    client, _, store, headers, path = npc_request(secured_api, catalog)
    def broken(*args, **kwargs):
        raise RuntimeError("broken diagnostic sink")
    monkeypatch.setattr(diag.logger, "info", broken)
    response = client.post(path, headers=headers, json={"expected_revision": 0})
    assert response.status_code == 200 and response.json()["state"]["revision"] == 1
    snapshot = copy.deepcopy((store.games, store.receipts))
    assert client.post(path, headers=headers, json={"expected_revision": 0}).content == response.content
    assert snapshot == (store.games, store.receipts)
    assert len(store.receipts) == 1
    drained(diagnostic_logging)
    assert diagnostic_logging.failures == 2


@pytest.mark.parametrize("fault", ["span", "summary", "construction"])
def test_observer_failures_are_fail_open(secured_api, catalog, monkeypatch, fault):
    client, _, store, headers, path = npc_request(secured_api, catalog)
    def broken(*args, **kwargs):
        raise RuntimeError("observer unavailable")
    if fault == "span": monkeypatch.setattr(diag.RequestTimings, "add", broken)
    elif fault == "summary": monkeypatch.setattr(diag.RequestTimings, "summary", broken)
    else: monkeypatch.setattr(diag, "RequestTimings", broken)
    response = client.post(path, headers=headers, json={"expected_revision": 0})
    assert response.status_code == 200 and len(store.receipts) == 1


def test_disabled_switch_preserves_http_contract_and_has_no_diagnostics(secured_api, catalog, monkeypatch, caplog):
    client, module, _, headers, path = npc_request(secured_api, catalog)
    response = client.post(path, headers=headers, json={"expected_revision": 0})
    context = module.app.state.phase4
    # No lifespan started, no settings/credentials/database loaded.
    monkeypatch.setenv("NPC_PERFORMANCE_DIAGNOSTICS", "false")
    disabled = module.create_app()
    disabled.state.phase4 = context
    caplog.clear()
    replay_client = TestClient(disabled, base_url=ORIGIN, cookies=dict(client.cookies))
    replay = replay_client.post(path, headers=headers, json={"expected_revision": 0})
    assert replay.content == response.content
    assert "x-npc-trace-id" not in replay.headers and summaries(caplog) == []


def test_non_npc_request_is_not_instrumented(secured_api, caplog):
    caplog.clear()
    response = secured_api[0].get("/auth/me")
    assert response.status_code == 401
    assert "x-npc-trace-id" not in response.headers and summaries(caplog) == []


def test_monotonic_span_ignores_wall_clock_and_suppresses_recursive_double_count(monkeypatch):
    record = diag.RequestTimings()
    token = diag._current.set(record)
    ticks = iter((100_000_000, 125_000_000))
    monkeypatch.setattr(diag, "perf_counter_ns", lambda: next(ticks))
    try:
        with diag.span("authorization"):
            with diag.span("authorization"):
                pass
        assert record.spans["authorization"] == {"count": 1, "total_ns": 25_000_000,
                                                 "max_ns": 25_000_000, "failed": 0}
    finally:
        diag._current.reset(token)


def test_supported_driver_events_are_aggregated_without_inspecting_payloads():
    record = diag.RequestTimings()
    token = diag._current.set(record)
    command, pool = diag.mongo_listeners()
    try:
        command.started(monitoring.CommandStartedEvent({"find": "private-table", "secret": "synthetic-query-canary"},
                                                       "private-database", 1, ("private-server", 27017), 1))
        command.succeeded(monitoring.CommandSucceededEvent(timedelta(milliseconds=5), {"secret": "synthetic-reply-canary"},
                                                          "find", 1, ("private-server", 27017), 1))
        with diag.span("game_transaction"):
            for _ in range(2):
                command.failed(monitoring.CommandFailedEvent(timedelta(milliseconds=7), {"secret": "synthetic-error-canary"},
                                                            "commitTransaction", 2, ("private-server", 27017), 2))
        command.succeeded(SimpleNamespace(command_name="synthetic-untrusted-command", duration_micros=2000))
        pool.connection_checked_out(monitoring.ConnectionCheckedOutEvent(("private-server", 27017), 1, .011))
        pool.connection_check_out_failed(monitoring.ConnectionCheckOutFailedEvent(("private-server", 27017), "timeout", .020))
        pool.connection_ready(monitoring.ConnectionReadyEvent(("private-server", 27017), 1, .003))
        row = record.summary(200, "returned", True)
        assert row["mongo_commands"]["find"]["total_ms"] == 5
        assert row["mongo_by_category"]["read"]["total_ms"] == 5
        assert row["mongo_commands"]["commitTransaction"] == {"count": 2, "total_ms": 14, "max_ms": 7, "failed": 2}
        assert row["mongo_transaction_commands"]["game.commitTransaction"]["count"] == 2
        assert row["mongo_commands"]["other"]["total_ms"] == 2
        assert row["mongo_pool"]["checkout"] == {"count": 2, "total_ms": 31, "max_ms": 20, "failed": 1}
        assert row["mongo_pool"]["connection_setup"]["total_ms"] == 3
        for text in ("private-server", "private-database", "private-table", "synthetic-", "secret"):
            assert text not in json.dumps(row)
    finally:
        diag._current.reset(token)


def test_driver_callbacks_outside_request_or_with_missing_duration_are_safe():
    command, pool = diag.mongo_listeners()
    command.failed(object())
    pool.connection_checked_out(object())
    record = diag.RequestTimings()
    token = diag._current.set(record)
    try:
        command.failed(object())
        pool.connection_checked_out(SimpleNamespace(duration=None))
        assert record.commands == record.pool == {}
    finally:
        diag._current.reset(token)


def test_actual_installed_client_accepts_listeners_without_connecting():
    from app.startup import create_client
    client = create_client(SimpleNamespace(mongodb_uri="mongodb://127.0.0.1:1", tls_required=False))
    try:
        assert not client.options.connect
        assert client.options.server_selection_timeout == 5
        assert client.options.pool_options.connect_timeout == 5
        assert client.options.pool_options.socket_timeout == 10
    finally:
        client.close()


def test_real_repository_http_path_has_auth_transaction_and_receipt_spans(catalog, caplog):
    from app.main import create_app
    repo, principal, _, game_id, database, _ = setup_store(catalog)
    database["games"].docs[ObjectId(game_id)].update(scenarios(catalog)["attack_start"].model_dump())
    settings = SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True, trusted_origins=(ORIGIN,))
    service = AuthorizedGameService(repo, settings, lambda: NOW, dice=FixedDice([6, 1] * 100), catalog=catalog)
    auth = SimpleNamespace(authenticate=lambda ignored: repo.authorize(principal.session_hash, NOW, 1800, touch=True))
    application = create_app(npc_diagnostics_enabled=True)
    application.state.phase4 = Phase4Context(settings, auth, service)
    response = TestClient(application, base_url=ORIGIN).post(f"/games/{game_id}/npc-steps",
        headers={"Origin": ORIGIN, "X-CSRF-Token": principal.csrf_token, "Authorization": "synthetic-private-auth-canary"},
        json={"expected_revision": 0})
    assert response.status_code == 200
    row, = summaries(caplog)
    for name in ("authentication", "authorization", "owned_game_load", "index_verification", "npc_receipt_lookup",
                 "action_receipt_lookup", "auth_transaction", "auth_transaction_body", "game_transaction",
                 "game_transaction_body", "receipt_insert", "response_projection"):
        assert row["spans_inclusive"][name]["count"] > 0
    assert row["spans_inclusive"]["auth_transaction_body"]["count"] == 1
    assert row["spans_inclusive"]["game_transaction_body"]["count"] == 1
    assert len(database["game_action_receipts"].docs) == 1
    text = json.dumps(row)
    for canary in (game_id, principal.user_id, principal.session_hash, principal.csrf_token,
                   "synthetic-private-auth-canary", "Alice", "countries", "soldiers"):
        assert canary not in text


def test_framework_response_tail_includes_real_fastapi_serialization(secured_api, catalog, monkeypatch, caplog):
    import fastapi.routing
    client, _, _, headers, path = npc_request(secured_api, catalog)
    original = fastapi.routing.serialize_response
    called = []
    async def observed(*args, **kwargs):
        await asyncio.sleep(.015)
        called.append(True)
        return await original(*args, **kwargs)
    monkeypatch.setattr(fastapi.routing, "serialize_response", observed)
    caplog.clear()
    response = client.post(path, headers=headers, json={"expected_revision": 0})
    assert response.status_code == 200 and called == [True]
    row, = summaries(caplog)
    assert row["post_route_framework_ms"] >= 15
    assert row["spans_inclusive"]["route_handler"]["total_ms"] >= row["post_route_framework_ms"]


@pytest.mark.parametrize("name", ["allocation", "attack_start", "dice_exchange", "conquest", "transfer", "end_turn", "skip"])
def test_real_service_instrumented_and_disabled_results_dice_writes_match(catalog, name):
    state = scenarios(catalog)[name]
    outputs = []
    for enabled in (False, True):
        repo, principal, _, game_id, database, _ = setup_store(catalog)
        database["games"].docs[ObjectId(game_id)].update(state.model_dump())
        dice = FixedDice([6, 1] * 200)
        service = AuthorizedGameService(repo, SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True),
                                        lambda: NOW, dice=dice, catalog=catalog)
        record = diag.RequestTimings() if enabled else None
        token = diag._current.set(record)
        try:
            result = service.npc_step(principal, game_id, state.revision)
            outputs.append((public_result(result), dice.calls, len(database["game_action_receipts"].docs)))
            if enabled:
                assert record.spans["game_transaction_body"]["count"] == 1
                assert record.spans["receipt_insert"]["count"] == 1
                assert record.spans["owned_game_load"]["count"] > 0
                assert record.spans["authorization"]["count"] > 0
                assert record.spans["index_verification"]["count"] > 0
        finally:
            diag._current.reset(token)
    assert outputs[0] == outputs[1]


def test_transaction_callback_retries_measured_without_extra_receipts_or_dice(catalog):
    repo, principal, _, game_id, database, client = setup_store(catalog)
    database["games"].docs[ObjectId(game_id)].update(scenarios(catalog)["dice_exchange"].model_dump())
    client.repeat = True  # Existing transaction double rolls back first callback.
    record = diag.RequestTimings()
    token = diag._current.set(record)
    dice = FixedDice([6, 1] * 200)
    try:
        service = AuthorizedGameService(repo, SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True),
                                        lambda: NOW, dice=dice, catalog=catalog)
        result = service.npc_step(principal, game_id, 1)
        assert record.spans["game_transaction_body"]["count"] == 2
        assert record.spans["engine_action"]["count"] == 1
        assert len(database["game_action_receipts"].docs) == 1
        before = dice.calls
        assert service.npc_step(principal, game_id, 1) == result
        assert dice.calls == before and len(database["game_action_receipts"].docs) == 1
    finally:
        diag._current.reset(token)


def test_full_asgi_lifecycle_concurrency_thread_context_and_interruption(caplog):
    async def run():
        barrier = asyncio.Event()
        entered = 0
        async def app(scope, receive, send):
            nonlocal entered
            entered += 1
            if entered == 2: barrier.set()
            await barrier.wait()
            def work():
                with diag.span("npc_decision"):
                    for _ in range(scope["count"]):
                        diag.NpcCommandListener().succeeded(SimpleNamespace(command_name="find", duration_micros=1000))
            await asyncio.to_thread(work)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        middleware = diag.NpcPerformanceMiddleware(app)
        messages = [[], []]
        async def request(index):
            async def send(message): messages[index].append(message)
            await middleware({"type": "http", "method": "POST", "path": "/games/not-logged/npc-steps", "count": index + 1}, None, send)
        await asyncio.gather(request(0), request(1))
        assert diag._current.get() is None
        return messages
    messages = asyncio.run(run())
    rows = summaries(caplog)
    assert len(rows) == 2
    by_trace = {row["trace_id"]: row for row in rows}
    for index, request_messages in enumerate(messages):
        trace = dict(request_messages[0]["headers"])[b"x-npc-trace-id"].decode()
        assert by_trace[trace]["mongo_commands"]["find"]["count"] == index + 1
        assert by_trace[trace]["spans_inclusive"]["npc_decision"]["count"] == 1
    assert "not-logged" not in json.dumps(rows)


@pytest.mark.parametrize("after_start", [False, True])
def test_interrupted_asgi_call_logs_partial_measurement_and_propagates(caplog, after_start):
    async def run():
        async def app(scope, receive, send):
            if after_start: await send({"type": "http.response.start", "status": 200, "headers": []})
            raise asyncio.CancelledError()
        async def send(message): pass
        with pytest.raises(asyncio.CancelledError):
            await diag.NpcPerformanceMiddleware(app)({"type": "http", "method": "POST", "path": "/games/x/npc-steps"}, None, send)
        assert diag._current.get() is None
    asyncio.run(run())
    row, = summaries(caplog)
    assert row["outcome"] == "interrupted" and not row["response_complete"]
    assert row["status"] == (200 if after_start else None)


class HeldLogHandler(logging.Handler):
    """A real handler held by an explicit event, not a precise timed sleep."""
    def __init__(self):
        super().__init__()
        self.entered, self.unblock, self.finished = Event(), Event(), Event()
        self.messages = []
        self.contexts = []

    def emit(self, record):
        self.entered.set()
        try:
            # Finite watchdog only, so a broken implementation fails instead
            # of hanging pytest. Positive assertions happen before release.
            self.unblock.wait(5)
            self.messages.append(record.getMessage())
            self.contexts.append(diag._current.get())
        finally:
            self.finished.set()


def held_logger(monkeypatch):
    handler = HeldLogHandler()
    isolated = logging.Logger(diag.logger.name, logging.INFO)
    isolated.addHandler(handler)
    monkeypatch.setattr(diag, "logger", isolated)
    return handler


async def local_asgi_response(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b'{"ok":true}'})


def test_held_handler_does_not_stall_unrelated_event_loop_requests(monkeypatch):
    handler = held_logger(monkeypatch)
    handoff = LogHandoff()
    assert handoff.start()
    middleware = diag.NpcPerformanceMiddleware(local_asgi_response, handoff=handoff)

    async def run():
        first, unrelated = [], []
        async def send_first(message): first.append(message)
        async def send_other(message): unrelated.append(message)
        await asyncio.wait_for(middleware({"type": "http", "method": "POST", "path": "/games/local/npc-steps"},
                                         None, send_first), timeout=2)
        assert await asyncio.wait_for(asyncio.to_thread(handler.entered.wait, 2), timeout=3)
        # Handler remains held while both an unrelated coroutine and a complete
        # unrelated ASGI response run. No sub-millisecond scheduler assertion.
        await asyncio.wait_for(asyncio.sleep(0), timeout=2)
        await asyncio.wait_for(middleware({"type": "http", "method": "GET", "path": "/health"},
                                         None, send_other), timeout=2)
        assert not handler.finished.is_set()
        assert first[-1]["body"] == unrelated[-1]["body"] == b'{"ok":true}'
        assert diag._current.get() is None
    try:
        asyncio.run(run())
    finally:
        handler.unblock.set()
        drained(handoff)
        handoff.stop()
        assert handoff.stopped.wait(2)
    assert handoff.failures == 0


def test_full_queue_drops_records_without_delaying_real_committed_responses(secured_api, catalog, monkeypatch):
    client, module, store, headers, path = npc_request(secured_api, catalog)
    handler = held_logger(monkeypatch)
    handoff = LogHandoff(capacity=1)
    assert handoff.start()
    layer = module.app.middleware_stack
    while not isinstance(layer, diag.NpcPerformanceMiddleware):
        layer = layer.app
    layer._handoff = handoff
    try:
        first = client.post(path, headers=headers, json={"expected_revision": 0})
        assert first.status_code == 200 and handler.entered.wait(2)
        snapshot = copy.deepcopy((store.games, store.receipts))
        traces = {first.headers["x-npc-trace-id"]}
        for _ in range(12):
            replay = client.post(path, headers=headers, json={"expected_revision": 0})
            assert replay.status_code == 200 and replay.content == first.content
            traces.add(replay.headers["x-npc-trace-id"])
        assert len(traces) == 13
        assert handoff._queue.qsize() == 1 and handoff.dropped == 11
        assert not handler.finished.is_set()
        assert snapshot == (store.games, store.receipts) and len(store.receipts) == 1
        # Shutdown is independent of the held Handler.lock and a full queue.
        handoff.stop()
        assert handoff._queue.qsize() == 0 and handoff.dropped == 12
        assert not handoff.stopped.is_set()  # Only the in-flight diagnostic remains.
        after_stop = client.post(path, headers=headers, json={"expected_revision": 0})
        assert after_stop.content == first.content and handoff.dropped == 13
    finally:
        handler.unblock.set()
        handoff.stop()
        assert handoff.stopped.wait(2)
    assert handoff.failures == 0


def test_handoff_has_bounded_payload_and_rejects_oversized_or_stopped_records():
    handoff = LogHandoff(capacity=1)
    assert handoff.submit("not-started") is False
    assert handoff.start()
    try:
        assert handoff.submit("x" * (handoff.MAX_RECORD_CHARS + 1)) is False
        assert handoff.submit({"not": "an immutable string"}) is False
        assert handoff.dropped == 3
    finally:
        handoff.stop()
        assert handoff.stopped.wait(2)
    assert handoff.start() is False
    assert handoff.submit("after-stop") is False
    handoff.stop()


def test_lifecycle_lock_contention_drops_without_waiting():
    handoff = LogHandoff()
    assert handoff.start()
    entered, unblock, finished = Event(), Event(), Event()
    def hold_lock():
        with handoff._lock:
            entered.set()
            unblock.wait(5)  # Finite watchdog if non-waiting submit regresses.
            finished.set()
    holder = Thread(target=hold_lock, daemon=True)
    holder.start()
    try:
        assert entered.wait(2)
        assert handoff.submit("contended") is False
        assert not finished.is_set()
    finally:
        unblock.set()
        holder.join(timeout=2)
        assert not holder.is_alive()
        handoff.stop()
        assert handoff.stopped.wait(2)


def test_worker_failure_is_isolated_and_later_records_continue(monkeypatch):
    calls = []
    def failing_once(message):
        calls.append(message)
        assert diag._current.get() is None
        if len(calls) == 1:
            raise RuntimeError("synthetic-handler-failure")
    monkeypatch.setattr(diag.logger, "info", failing_once)
    handoff = LogHandoff()
    assert handoff.start()
    try:
        assert handoff.submit('{"trace_id":"first"}')
        assert handoff.submit('{"trace_id":"second"}')
        drained(handoff)
        assert len(calls) == 2 and handoff.failures == 1
        assert not handoff.stopped.is_set()
    finally:
        handoff.stop()
        assert handoff.stopped.wait(2)


def test_worker_receives_detached_snapshot_without_request_context(monkeypatch):
    handler = held_logger(monkeypatch)
    handoff = LogHandoff()
    record = diag.RequestTimings()
    token = diag._current.set(record)
    try:
        # Start while a request context exists to prove explicit empty-context
        # startup rather than relying on thread inheritance defaults.
        assert handoff.start()
        snapshot = record.summary(200, "returned", True)
        original_trace = snapshot["trace_id"]
        assert handoff.submit(json.dumps(snapshot))
        assert handler.entered.wait(2)
        snapshot["trace_id"] = "changed-after-handoff"
        record.operation = "transfer"
    finally:
        diag._current.reset(token)
        handler.unblock.set()
        drained(handoff)
        handoff.stop()
        assert handoff.stopped.wait(2)
    assert handoff.failures == 0
    assert json.loads(handler.messages[0])["trace_id"] == original_trace
    assert handler.contexts == [None]


@pytest.mark.parametrize("enabled,failure", [(True, False), (True, True), (False, False)])
def test_asgi_lifespan_owns_worker_and_cleans_up_startup_failure(enabled, failure):
    handoff = LogHandoff()
    sent = []
    async def run():
        async def app(scope, receive, send):
            assert scope["type"] == "lifespan"
            assert (handoff._thread is not None) == enabled
            if failure:
                raise RuntimeError("synthetic-startup-failure")
            await send({"type": "lifespan.startup.complete"})
            await send({"type": "lifespan.shutdown.complete"})
        async def send(message): sent.append(message["type"])
        middleware = diag.NpcPerformanceMiddleware(app, enabled=enabled, handoff=handoff)
        if failure:
            with pytest.raises(RuntimeError, match="synthetic-startup-failure"):
                await middleware({"type": "lifespan"}, None, send)
        else:
            await middleware({"type": "lifespan"}, None, send)
    asyncio.run(run())
    assert handoff.stopped.wait(2)
    assert handoff.submit("after-lifespan") is False
    if not failure:
        assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


def test_worker_start_failure_is_best_effort(monkeypatch):
    class CannotStart:
        def __init__(self, **kwargs): pass
        def start(self): raise RuntimeError("synthetic-thread-failure")
    monkeypatch.setattr(diag, "Thread", CannotStart)
    handoff = LogHandoff()
    assert handoff.start() is False
    assert handoff.stopped.is_set()
    assert handoff.submit("dropped") is False
    handoff.stop()


def test_repeated_start_and_idle_stop_are_safe():
    handoff = LogHandoff()
    assert handoff.start()
    worker = handoff._thread
    assert handoff.start() and handoff._thread is worker
    handoff.stop()
    handoff.stop()
    assert handoff.stopped.wait(2)
