from datetime import datetime

from pydantic import Field

from app.models.actions import FrozenModel


class GameAccess(FrozenModel):
    owner_user_id: str
    human_player_id: str
    version: int = Field(default=1, ge=1)
    bound_at: datetime


def runtime_payload(document: dict) -> dict:
    """Remove only explicitly recognized persistence envelope fields, never game fields."""
    return {key: value for key, value in document.items() if key not in {"access", "creation"}}


def access_from_document(document: dict) -> GameAccess:
    from app.security.errors import SecurityError
    from pydantic import ValidationError
    try:
        return GameAccess.model_validate(document.get("access"))
    except ValidationError:
        raise SecurityError(403, "game_not_owned") from None
