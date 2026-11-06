"""Independent optional gates; parsing never loads credentials or connects."""
from dataclasses import dataclass
import os

from app.security.environment import ConfigurationError


@dataclass(frozen=True)
class CommentaryJobSettings:
    discovery_enabled: bool = False
    execution_enabled: bool = False
    batch_size: int = 50
    lease_seconds: int = 30
    max_attempts: int = 3

    def __post_init__(self):
        if (type(self.discovery_enabled) is not bool or type(self.execution_enabled) is not bool
                or type(self.batch_size) is not int or not 1 <= self.batch_size <= 100
                or type(self.lease_seconds) is not int or self.lease_seconds != 30
                or type(self.max_attempts) is not int or self.max_attempts != 3):
            raise ConfigurationError("invalid_commentary_jobs_configuration")


def load_commentary_job_settings(environ=None):
    values = os.environ if environ is None else environ
    names = {"COMMENTARY_JOBS_DISCOVERY_ENABLED", "COMMENTARY_JOBS_EXECUTION_ENABLED"}
    if any(key.startswith("COMMENTARY_JOBS_") and key not in names for key in values):
        raise ConfigurationError("invalid_commentary_jobs_configuration")

    def flag(name):
        value = values.get(name, "false")
        if value not in {"true", "false"}:
            raise ConfigurationError("invalid_commentary_jobs_configuration")
        return value == "true"

    return CommentaryJobSettings(
        discovery_enabled=flag("COMMENTARY_JOBS_DISCOVERY_ENABLED"),
        execution_enabled=flag("COMMENTARY_JOBS_EXECUTION_ENABLED"))
