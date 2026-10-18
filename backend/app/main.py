from fastapi import FastAPI, HTTPException
from pymongo.errors import PyMongoError
from app.database import client

app = FastAPI(
    title="Geopolitics Game API",
    description="UCT INF4001N Entrance Exam 2027"
)

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