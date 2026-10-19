from pydantic import ValidationError

from app.engine.errors import UnsupportedGame
from app.models.game import InitializedGame
from app.models.runtime_game import RuntimeGame


def load_runtime(document: dict) -> RuntimeGame:
    """Read-only adaptation; never infer a playable board from a waiting record."""
    raw = {key: value for key, value in document.items() if key != "_id"}
    try:
        if raw.get("schema_version") == 3:
            return RuntimeGame.model_validate(raw)
        if raw.get("schema_version") != 2:
            raise UnsupportedGame("This legacy game is readable but does not support actions")
        initial = InitializedGame.model_validate(raw)
        data = initial.model_dump(exclude={"schema_version"})
        return RuntimeGame(**data, updated_at=initial.created_at)
    except ValidationError:
        raise UnsupportedGame("Stored game state is invalid or unsupported") from None
