"""ASGI entry point. Importing defines routes only; lifespan owns persistence."""
from fastapi import FastAPI, HTTPException, Request
from pymongo.errors import PyMongoError
from pydantic import ValidationError
from starlette.middleware.cors import CORSMiddleware

from app.api.countries import router as countries_router
from app.api.auth import router as auth_router
from app.api.games import router as games_router
from app.api.dependencies import Phase4SecurityMiddleware, install_security_handlers
from app.security.environment import load_application_settings
from app.services.public_game_service import public_game
from app.startup import application_lifespan, create_client


class TrustedOriginCORS:
    """Exact startup origins only; CORS never replaces POST Origin/CSRF checks."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        context = getattr(scope.get("app").state, "phase4", None) if scope.get("app") else None
        if scope["type"] != "http" or context is None:
            return await self.app(scope, receive, send)
        origins = [value.decode("latin-1") for key, value in scope.get("headers", [])
                   if key.lower() == b"origin"]
        if len(origins) != 1 or origins[0] not in context.settings.trusted_origins:
            # Preserve the existing no-CORS contract for untrusted callers,
            # including no credential header on rejected preflights.
            return await self.app(scope, receive, send)
        cors = CORSMiddleware(self.app, allow_origins=list(context.settings.trusted_origins),
                              allow_credentials=True, allow_methods=["GET", "POST"],
                              allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"])
        await cors(scope, receive, send)


def create_app(*, settings_loader=load_application_settings, client_factory=create_client):
    application = FastAPI(title="Geopolitics Game API", description="UCT INF4001N Entrance Exam 2027",
                          lifespan=application_lifespan(settings_loader, client_factory))
    application.state.phase4 = None
    application.state.mongo_client = None
    application.state.game_reader = None
    application.state.phase4_readiness = "not_started"
    application.include_router(countries_router)
    application.add_middleware(Phase4SecurityMiddleware)
    application.add_middleware(TrustedOriginCORS)
    install_security_handlers(application)
    application.include_router(auth_router)
    application.include_router(games_router)

    @application.get("/")
    def home():
        return {"message": "Geopolitics Game API is running"}

    @application.get("/health")
    def health(request: Request):
        client = request.app.state.mongo_client
        if client is None:
            raise HTTPException(status_code=503, detail="MongoDB Atlas connection failed")
        try:
            client.admin.command("ping")
            return {"status": "healthy", "database": "connected"}
        except PyMongoError:
            raise HTTPException(status_code=503, detail="MongoDB Atlas connection failed") from None

    @application.get("/games/{game_id}")
    def read_game(game_id: str, request: Request):
        reader = request.app.state.game_reader
        if reader is None:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")
        try:
            game = reader(game_id)
            if game is None:
                raise HTTPException(status_code=404, detail="Game not found")
            return public_game(game)
        except HTTPException:
            raise
        except PyMongoError:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable") from None
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(status_code=503, detail="Saved game temporarily unavailable") from None

    return application


app = create_app()
