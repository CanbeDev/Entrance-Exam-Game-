"""Injected Phase 4 access boundary. No production connection or enabled gates."""
import secrets

from fastapi import Depends, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from pymongo.errors import PyMongoError

from app.engine.errors import (ActionIdConflict, GameRuleError, GameplayWritesDisabled,
                               PersistenceUnavailable, RevisionConflict, UnsupportedGame)
from app.security.errors import SecurityError


def phase4_path(path: str) -> bool:
    if path in {"/auth/register", "/auth/login", "/auth/logout", "/auth/me", "/auth/csrf",
                "/games", "/me/games"}:
        return True
    pieces = path.strip("/").split("/")
    return len(pieces) == 3 and pieces[0] == "games" and pieces[2] in {"actions", "npc-steps", "events"}


def error_response(error: SecurityError) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if error.status == 429:
        headers["Retry-After"] = str(error.retry_after or 60)
    return JSONResponse(status_code=error.status, content={"detail": {"code": error.code}}, headers=headers)


def get_context(request: Request):
    context = getattr(request.app.state, "phase4", None)
    if context is None:
        raise SecurityError(503, "phase4_disabled")
    return context


def authenticated(request: Request, context=Depends(get_context)):
    return context.auth.authenticate(request.cookies.get(context.settings.cookie_name, ""))


def authenticated_mutation(request: Request, principal=Depends(authenticated)):
    supplied = request.headers.get("X-CSRF-Token", "")
    if (not supplied or len(supplied) > 256
            or not secrets.compare_digest(supplied.encode(), principal.csrf_token.encode())):
        raise SecurityError(403, "csrf_rejected")
    return principal


def client_ip(request: Request) -> str:
    # Forwarded headers are untrusted until the deployment proxy configuration
    # has been separately verified. Account throttling does not depend on them.
    return request.client.host if request.client is not None else "unknown"


class Phase4SecurityMiddleware:
    """Bound actual streamed bodies before framework parsing; sanitize failures."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not phase4_path(scope.get("path", "")):
            return await self.app(scope, receive, send)

        started = False

        async def no_store(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message = {**message, "headers": [(key, value) for key, value in message.get("headers", [])
                                                   if key.lower() != b"cache-control"]
                           + [(b"cache-control", b"no-store")]}
            await send(message)

        if scope.get("method") == "POST":
            context = getattr(scope["app"].state, "phase4", None)
            if context is None:
                return await error_response(SecurityError(503, "phase4_disabled"))(scope, receive, no_store)
            if not context.settings.auth_writes_enabled:
                return await error_response(SecurityError(503, "authentication_disabled"))(scope, receive, no_store)
            origins = [value.decode("latin-1") for key, value in scope.get("headers", []) if key.lower() == b"origin"]
            if len(origins) != 1 or origins[0] not in context.settings.trusted_origins:
                return await error_response(SecurityError(403, "origin_rejected"))(scope, receive, no_store)
            body = bytearray()
            try:
                while True:
                    message = await receive()
                    if message["type"] != "http.request":
                        raise ValueError("Request body unavailable")
                    body.extend(message.get("body", b""))
                    if len(body) > context.settings.max_body_bytes:
                        return await error_response(SecurityError(413, "request_too_large"))(scope, receive, no_store)
                    if not message.get("more_body", False):
                        break
            except Exception:
                return await error_response(SecurityError(400, "request_body_unavailable"))(scope, receive, no_store)
            content_types = [value.decode("latin-1").split(";", 1)[0].strip().lower()
                             for key, value in scope.get("headers", []) if key.lower() == b"content-type"]
            if not (scope["path"] == "/auth/logout" and not body):
                if content_types != ["application/json"]:
                    return await error_response(SecurityError(415, "json_required"))(scope, receive, no_store)
            delivered = False
            source_receive = receive

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await source_receive()

            receive = bounded_receive
        try:
            await self.app(scope, receive, no_store)
        except Exception:
            # The response never contains exception/driver text, passwords,
            # connection strings or request bodies. No details are logged here.
            if started:
                raise
            await error_response(SecurityError(503, "service_unavailable"))(scope, receive, no_store)


def install_security_handlers(app):
    @app.exception_handler(SecurityError)
    async def security_error(request, error):
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def request_validation(request, error):
        if phase4_path(request.url.path):
            return error_response(SecurityError(422, "invalid_request"))
        return await request_validation_exception_handler(request, error)

    @app.exception_handler(GameRuleError)
    async def invalid_action(request, error):
        code = "invalid_game_action"
        if isinstance(error, RevisionConflict):
            code = "revision_conflict"
        elif isinstance(error, ActionIdConflict):
            code = "action_id_conflict"
        elif isinstance(error, UnsupportedGame):
            code = "unsupported_game"
        return error_response(SecurityError(409, code))

    @app.exception_handler(GameplayWritesDisabled)
    async def writes_disabled(request, error):
        return error_response(SecurityError(503, "gameplay_writes_disabled"))

    @app.exception_handler(PersistenceUnavailable)
    @app.exception_handler(PyMongoError)
    @app.exception_handler(ValidationError)
    async def persistence_error(request, error):
        return error_response(SecurityError(503, "service_unavailable"))
