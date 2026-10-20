from fastapi import FastAPI, HTTPException
from pymongo.errors import PyMongoError
from pydantic import ValidationError
from app.database import client
from app.repositories.game_repository import get_game
from app.api.countries import router as countries_router
from app.services.public_game_service import public_game
from app.api.auth import router as auth_router
from app.api.games import router as games_router
from app.api.dependencies import Phase4SecurityMiddleware, install_security_handlers


app = FastAPI(
    title="Geopolitics Game API",
    description="UCT INF4001N Entrance Exam 2027"
)

app.include_router(countries_router)
app.state.phase4 = None  # Explicitly injected locally; production writes stay disabled.
app.add_middleware(Phase4SecurityMiddleware)
install_security_handlers(app)
app.include_router(auth_router)
app.include_router(games_router)

@app.get("/")
def home():
    return {
        "message": "Geopolitics Game API is running"
    }

@app.get("/health")
def health():
    try:
        client.admin.command("ping")

        return {
            "status": "healthy",
            "database": "connected"
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="MongoDB Atlas connection failed"
        )


@app.get("/games/{game_id}")
def read_game(game_id: str):
    try:
        game = get_game(game_id)

        if game is None:
            raise HTTPException(
                status_code=404,
                detail="Game not found"
            )

        return public_game(game)

    except HTTPException:
        raise

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable"
        )

    except (ValidationError, ValueError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="Saved game temporarily unavailable"
        ) from None
