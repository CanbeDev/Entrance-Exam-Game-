from dataclasses import dataclass

from app.security.config import SecuritySettings
from app.services.auth_service import AuthService
from app.services.authorized_game_service import AuthorizedGameService


@dataclass(frozen=True)
class Phase4Context:
    settings: SecuritySettings
    auth: AuthService
    games: AuthorizedGameService


def build_phase4_context(client, database, settings: SecuritySettings, *, clock=None, dice=None):
    """Compose injected services after managed startup readiness checks.

    The caller supplies an already authorized database dependency. Constructors do
    not provision collections/indexes; gates stay disabled unless explicitly set.
    """
    from app.repositories.security_repository import MongoSecurityRepository
    store = MongoSecurityRepository(client, database, auth_writes_enabled=settings.auth_writes_enabled,
                                    gameplay_writes_enabled=settings.gameplay_writes_enabled)
    return Phase4Context(settings, AuthService(store, settings, clock=clock),
                         AuthorizedGameService(store, settings, clock=clock, dice=dice))
