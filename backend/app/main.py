from fastapi import FastAPI, HTTPException
from pymongo.errors import PyMongoError
from app.database import client
from app.repositories.game_repository import get_game
from app.api.countries import router as countries_router


app = FastAPI(
    title="Geopolitics Game API",
    description="UCT INF4001N Entrance Exam 2027"
)

app.include_router(countries_router)

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

        return game

    except HTTPException:
        raise

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database temporarily unavailable"
        )
