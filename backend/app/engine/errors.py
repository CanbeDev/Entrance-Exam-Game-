class GameRuleError(ValueError):
    """Rejected command or invalid persisted game; no state change is permitted."""


class UnsupportedGame(GameRuleError):
    pass


class RevisionConflict(GameRuleError):
    pass


class ActionIdConflict(GameRuleError):
    pass


class GameplayWritesDisabled(RuntimeError):
    pass


class PersistenceUnavailable(RuntimeError):
    """Sanitized persistence error; its text must never contain connection details."""
