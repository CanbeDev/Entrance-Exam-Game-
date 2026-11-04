"""Request-local NPC timings. Never inspect bodies, queries, identities or errors.

All observers are best-effort and cannot change a gameplay result. Inclusive
spans overlap; driver command/checkout durations are separate, not additive.
"""
from contextlib import contextmanager
from contextvars import Context, ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
import logging
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import perf_counter_ns
from uuid import uuid4

from fastapi.routing import APIRoute
from pymongo import monitoring

logger = logging.getLogger("uvicorn.error.npc_performance")
_current = ContextVar("npc_performance", default=None)
_active_spans = ContextVar("npc_performance_spans", default=frozenset())
_SPANS = frozenset({
    "route_handler", "route_function", "authentication", "csrf_check",
    "authorization", "owned_game_load", "index_verification", "npc_receipt_lookup",
    "action_receipt_lookup", "npc_state_load", "npc_decision", "npc_evidence_validation",
    "engine_action", "receipt_commit", "auth_transaction", "auth_transaction_body",
    "game_transaction", "game_transaction_body", "receipt_insert", "response_projection",
})
_COMMANDS = {
    "find": "read", "getMore": "read", "insert": "write", "update": "write",
    "findAndModify": "write", "delete": "write", "listIndexes": "metadata",
    "listCollections": "metadata", "commitTransaction": "transaction",
    "abortTransaction": "transaction", "killCursors": "other",
}
_OPERATIONS = frozenset({"allocate", "start_attack", "roll", "stop_attack", "transfer", "skip", "end_turn"})


class DiagnosticLogHandoff:
    """One bounded, best-effort logging worker per middleware lifespan.

    Only detached JSON strings cross this boundary. No handlers/formatters run
    on the producer. Shutdown drops backlog and never joins a stuck handler;
    the daemon may finish its single in-flight record after stop. One-shot:
    stopping never spawns a replacement for a potentially blocked worker.
    """
    CAPACITY = 128
    MAX_RECORD_CHARS = 16_384

    def __init__(self, *, capacity=CAPACITY):
        if type(capacity) is not int or not 1 <= capacity <= self.CAPACITY:
            raise ValueError("Invalid diagnostic queue capacity")
        self._queue = Queue(maxsize=capacity)
        self._lock = Lock()
        self._stop = Event()
        self.stopped = Event()
        self._thread = None
        self._accepting = False
        self.dropped = 0
        self.failures = 0

    def start(self):
        try:
            with self._lock:
                if self._stop.is_set():
                    return False
                if self._thread is not None:
                    return self._accepting
                # Explicit empty context, also on Python builds that inherit
                # thread context. The consumer never consults request state.
                self._thread = Thread(target=Context().run, args=(self._run,),
                                      name="npc-diagnostic-log", daemon=True)
                self._accepting = True
                self._thread.start()
            return True
        except Exception:
            self.stop()
            self.stopped.set()
            return False

    def submit(self, message):
        # No waiting for capacity, handler locks, sink I/O or worker completion.
        # A contended lifecycle lock also loses the diagnostic, never gameplay.
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if (not self._accepting or type(message) is not str
                    or len(message) > self.MAX_RECORD_CHARS):
                self.dropped += 1
                return False
            try:
                self._queue.put_nowait(message)
                return True
            except Full:
                self.dropped += 1
                return False
        except Exception:
            return False
        finally:
            self._lock.release()

    def stop(self):
        with self._lock:
            self._accepting = False
            self._stop.set()
        # At most CAPACITY entries, no sentinel insertion into a full queue and
        # no join/flush of handlers. Producers can no longer add entries.
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                break
            else:
                self._queue.task_done()
                with self._lock:
                    self.dropped += 1
        if self._thread is None:
            self.stopped.set()

    def _run(self):
        try:
            while not self._stop.is_set():
                try:
                    message = self._queue.get(timeout=.05)
                except Empty:
                    continue
                try:
                    if self._stop.is_set():
                        with self._lock:
                            self.dropped += 1
                    else:
                        try:
                            logger.info(message)
                        except Exception:
                            with self._lock:
                                self.failures += 1
                finally:
                    self._queue.task_done()
        finally:
            self.stopped.set()


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class RequestTimings:
    def __init__(self):
        self.trace_id = uuid4().hex
        self.started_utc = _utc()
        self.started_ns = perf_counter_ns()
        self.lock = Lock()
        self.spans = {}
        self.commands = {}
        self.transaction_commands = {}
        self.pool = {}
        self.marks = {}
        self.operation = None
        self.closed = False

    def add(self, group, key, elapsed_ns, *, failed=False):
        with self.lock:
            if self.closed:
                return
            row = group.setdefault(key, {"count": 0, "total_ns": 0, "max_ns": 0, "failed": 0})
            row["count"] += 1
            row["total_ns"] += max(0, int(elapsed_ns))
            row["max_ns"] = max(row["max_ns"], max(0, int(elapsed_ns)))
            row["failed"] += int(failed)

    def mark(self, key):
        with self.lock:
            if not self.closed:
                self.marks[key] = perf_counter_ns()

    def summary(self, status, outcome, response_complete):
        ended_ns, ended_utc = perf_counter_ns(), _utc()
        with self.lock:
            self.closed = True

            def rows(group):
                return {key: {"count": row["count"], "total_ms": round(row["total_ns"] / 1e6, 3),
                              "max_ms": round(row["max_ns"] / 1e6, 3), "failed": row["failed"]}
                        for key, row in sorted(group.items())}

            categories = {}
            for name, row in self.commands.items():
                target = categories.setdefault(_COMMANDS.get(name, "other"),
                                               {"count": 0, "total_ns": 0, "max_ns": 0, "failed": 0})
                for key in ("count", "total_ns", "failed"):
                    target[key] += row[key]
                target["max_ns"] = max(target["max_ns"], row["max_ns"])
            result = {"event": "npc_request_performance", "version": 1, "trace_id": self.trace_id,
                      "started_utc": self.started_utc, "completed_utc": ended_utc,
                      "status": status, "outcome": outcome, "response_complete": response_complete,
                      "app_total_ms": round((ended_ns - self.started_ns) / 1e6, 3),
                      "spans_inclusive": rows(self.spans), "mongo_commands": rows(self.commands),
                      "mongo_by_category": rows(categories),
                      "mongo_transaction_commands": rows(self.transaction_commands),
                      "mongo_pool": rows(self.pool)}
            if self.operation in _OPERATIONS:
                result["operation"] = self.operation
            for key in ("response_start", "response_body_sent"):
                if key in self.marks:
                    result[key + "_ms"] = round((self.marks[key] - self.started_ns) / 1e6, 3)
            if "route_returned" in self.marks and "handler_returned" in self.marks:
                # Includes worker handoff and framework response validation/JSON
                # serialization. Do not mislabel this as pure serializer CPU.
                result["post_route_framework_ms"] = round(
                    (self.marks["handler_returned"] - self.marks["route_returned"]) / 1e6, 3)
            return result


@contextmanager
def span(name):
    record = _current.get()
    active = _active_spans.get()
    if record is None or name not in _SPANS or name in active:
        yield
        return
    try:
        started = perf_counter_ns()
        token = _active_spans.set(active | {name})
    except Exception:
        yield
        return
    failed = True
    try:
        yield
        failed = False
    finally:
        try:
            record.add(record.spans, name, perf_counter_ns() - started, failed=failed)
        except Exception:
            pass
        finally:
            _active_spans.reset(token)


def timed(name):
    def decorate(function):
        @wraps(function)
        def measured(*args, **kwargs):
            with span(name):
                result = function(*args, **kwargs)
            if name == "route_function":
                mark("route_returned")
            return result
        return measured
    return decorate


def mark(name):
    try:
        record = _current.get()
        if record is not None:
            record.mark(name)
    except Exception:
        pass


def operation(name):
    try:
        record = _current.get()
        if record is not None and name in _OPERATIONS:
            record.operation = name
    except Exception:
        pass


class NpcTimingRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def measured(request):
            with span("route_handler"):
                result = await handler(request)
            mark("handler_returned")
            return result
        return measured


class NpcPerformanceMiddleware:
    """Outer user middleware, before security/body buffering and dependencies.

    Measures entry through ASGI return/failure, including final send await. This
    cannot observe Uvicorn/proxy queues before entry or delivery to the browser.
    """
    def __init__(self, app, *, enabled=True, handoff=None):
        self.app, self.enabled = app, enabled
        self._handoff = handoff if handoff is not None else DiagnosticLogHandoff()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            try:
                if self.enabled:
                    self._handoff.start()
                await self.app(scope, receive, send)
            finally:
                self._handoff.stop()
            return
        pieces = scope.get("path", "").strip("/").split("/")
        if (not self.enabled or scope["type"] != "http" or scope.get("method") != "POST"
                or len(pieces) != 3 or pieces[0] != "games" or pieces[2] != "npc-steps"):
            return await self.app(scope, receive, send)
        try:
            enabled = logger.isEnabledFor(logging.INFO)
            record = RequestTimings() if enabled else None
        except Exception:
            record = None
        if record is None:
            return await self.app(scope, receive, send)
        token = _current.set(record)
        status, complete, outcome = None, False, "returned"

        async def measured_send(message):
            nonlocal status, complete
            if message["type"] == "http.response.start":
                status = message["status"]
                mark("response_start")
                # Generated locally. Never reflect an incoming trace header.
                message = {**message, "headers": [(key, value) for key, value in message.get("headers", [])
                           if key.lower() != b"x-npc-trace-id"] + [(b"x-npc-trace-id", record.trace_id.encode("ascii"))]}
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                complete = True
                mark("response_body_sent")

        try:
            await self.app(scope, receive, measured_send)
        except BaseException:
            outcome = "interrupted"
            raise
        finally:
            try:
                # Finalize/copy all allowlisted values before leaving request
                # context. Only an immutable string reaches the logging thread.
                self._handoff.submit(json.dumps(record.summary(status, outcome, complete),
                                                separators=(",", ":"), allow_nan=False))
            except Exception:
                # Logging/formatting/handler failures never turn a commit into an
                # HTTP failure, retry a mutation, or expose exception text.
                pass
            finally:
                _current.reset(token)


class NpcCommandListener(monitoring.CommandListener):
    def started(self, event):
        pass  # Never inspect command documents, database/server names or replies.

    def _finished(self, event, failed):
        try:
            record = _current.get()
            if record is not None:
                name = event.command_name if event.command_name in _COMMANDS else "other"
                record.add(record.commands, name, event.duration_micros * 1000, failed=failed)
                if name in {"commitTransaction", "abortTransaction"}:
                    active = _active_spans.get()
                    kind = "auth" if "auth_transaction" in active else (
                        "game" if "game_transaction" in active else "other")
                    record.add(record.transaction_commands, kind + "." + name,
                               event.duration_micros * 1000, failed=failed)
        except Exception:
            pass

    def succeeded(self, event):
        self._finished(event, False)

    def failed(self, event):
        self._finished(event, True)


class NpcPoolListener(monitoring.ConnectionPoolListener):
    def _duration(self, event, category, failed=False):
        try:
            record = _current.get()
            if record is not None and event.duration is not None:
                record.add(record.pool, category, event.duration * 1e9, failed=failed)
        except Exception:
            pass

    def connection_checked_out(self, event):
        self._duration(event, "checkout")

    def connection_check_out_failed(self, event):
        self._duration(event, "checkout", True)

    def connection_ready(self, event):
        self._duration(event, "connection_setup")

    # All abstract callbacks implemented; background/unattributed events ignored.
    def pool_created(self, event): pass
    def pool_ready(self, event): pass
    def pool_cleared(self, event): pass
    def pool_closed(self, event): pass
    def connection_created(self, event): pass
    def connection_closed(self, event): pass
    def connection_check_out_started(self, event): pass
    def connection_checked_in(self, event): pass


def mongo_listeners():
    return [NpcCommandListener(), NpcPoolListener()]
