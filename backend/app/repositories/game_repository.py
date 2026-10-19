
from bson import ObjectId
from bson.errors import InvalidId

from app.models.game import Game, GameCreate, InitializedGame


class MongoGameRepository:
    """Inject a collection for tests; resolve the existing Atlas setup lazily."""

    def __init__(self, collection=None):
        self._collection = collection

    @property
    def collection(self):
        if self._collection is None:
            from app.database import db
            self._collection = db["games"]
        return self._collection

    def save_initialized_game(self, game: InitializedGame) -> str:
        # Revalidate at the persistence boundary in case mutable state was changed.
        validated = InitializedGame.model_validate(game.model_dump())
        document = validated.model_dump()
        # BSON cannot encode date objects; keep the snapshot date as ISO text.
        document["population_snapshot"]["retrieved_on"] = validated.population_snapshot.retrieved_on.isoformat()
        return str(self.collection.insert_one(document).inserted_id)

    def get_game(self, game_id: str):
        try:
            object_id = ObjectId(game_id)
        except (InvalidId, TypeError):
            return None
        game = self.collection.find_one({"_id": object_id})
        if game is None:
            return None
        # Return a copy; legacy documents are never migrated or rewritten on read.
        return {**game, "_id": str(game["_id"])}


_repository = MongoGameRepository()


def create_game(game_data: GameCreate):
    game = Game(game_name=game_data.game_name)

    result = _repository.collection.insert_one(
        game.model_dump()
    )

    return str(result.inserted_id)


def get_game(game_id: str):
    return _repository.get_game(game_id)
