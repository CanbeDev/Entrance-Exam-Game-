import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is missing")

client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=5000
)

db = client[
    os.getenv("MONGODB_DB_NAME", "geopolitics_game")
]