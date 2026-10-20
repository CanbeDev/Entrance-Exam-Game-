"""Account-scoped adapter around the unchanged authoritative receipt protocol."""
from app.models.game_access import GameAccess, runtime_payload
from app.repositories.action_repository import MongoActionRepository
from app.security.errors import SecurityError


class ScopedMongoActionRepository(MongoActionRepository):
    def __init__(self, security, principal, game_id: str, now, idle_seconds: int, *, gameplay_writes_enabled=False,
                 expected_access: GameAccess | None = None):
        super().__init__(security._client, security._database, gameplay_writes_enabled=gameplay_writes_enabled)
        self._security, self._principal = security, principal
        self._game_id, self._now, self._idle = game_id, now, idle_seconds
        self._access = expected_access

    def _authorize_access(self, game_id: str, *, session=None) -> None:
        if game_id != self._game_id:
            raise SecurityError(403, "game_not_owned")
        _, access = self._security._owned(game_id, self._principal, self._now(), self._idle, session=session)
        if self._access is not None and access != self._access:
            raise SecurityError(403, "game_access_changed")
        self._access = access

    def _scope_update(self, query: dict) -> dict:
        if self._access is None:
            raise SecurityError(403, "game_not_owned")
        return {**query, "access.owner_user_id": self._principal.user_id,
                "access.human_player_id": self._access.human_player_id, "access.version": self._access.version}

    def load_game(self, game_id: str) -> dict | None:
        document = super().load_game(game_id)
        return None if document is None else runtime_payload(document)
