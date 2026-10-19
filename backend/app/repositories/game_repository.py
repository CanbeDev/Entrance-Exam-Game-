
from bson import ObjectId
from bson.errors import InvalidId

from app.database import db
from app.models.game import Game, GameCreate


games_collection = db["games"]


def create_game(game_data: GameCreate):
    game = Game(game_name=game_data.game_name)

    result = games_collection.insert_one(
        game.model_dump()
    )

    return str(result.inserted_id)


def get_game(game_id: str):
    try:
        object_id = ObjectId(game_id)
    except (InvalidId, TypeError):
        return None

    game = games_collection.find_one(
        {"_id": object_id}
    )

    if game is None:
        return None

    game["_id"] = str(game["_id"])

    return game
