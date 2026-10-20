"""Argon2id password handling. Passwords never go to a network blocklist service."""
import unicodedata
from threading import BoundedSemaphore

from app.security.errors import SecurityError

# Original project-curated baseline, NOT a comprehensive breach corpus.
COMMON_PASSWORDS = frozenset({
    "123456789012345", "1234567890123456", "12345678901234567890",
    "passwordpassword", "password123456789", "password12345678",
    "qwertyuiopasdfgh", "qwertyuiop123456", "letmeinletmein123",
    "iloveyouiloveyou", "adminadminadmin", "administrator123",
    "geopoliticsgame123", "geopoliticsgame2027", "entranceexam2027",
    "correcthorsebatterystaple",
})


def normalize_password(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def validate_new_password(value: str, username: str) -> str:
    value = normalize_password(value)
    if not 15 <= len(value) <= 128 or "\x00" in value:
        raise SecurityError(422, "password_policy")
    if (value.casefold() in COMMON_PASSWORDS or len(set(value)) == 1
            or value.casefold() == username.casefold()):
        raise SecurityError(422, "password_blocklisted")
    return value


class Passwords:
    def __init__(self):
        from pwdlib import PasswordHash
        from pwdlib.hashers.argon2 import Argon2Hasher
        self._hash = PasswordHash((Argon2Hasher(time_cost=2, memory_cost=19456, parallelism=1),))
        self._slots = BoundedSemaphore(2)
        self._dummy = self._hash.hash("Public dummy input; not an account password")

    def _run(self, operation):
        if not self._slots.acquire(blocking=False):
            raise SecurityError(503, "authentication_busy")
        try:
            return operation()
        finally:
            self._slots.release()

    def hash(self, value: str) -> str:
        return self._run(lambda: self._hash.hash(normalize_password(value)))

    def verify(self, value: str, encoded: str | None) -> bool:
        def verify():
            from pwdlib.exceptions import UnknownHashError
            try:
                valid = self._hash.verify(normalize_password(value), encoded or self._dummy)
                return valid and encoded is not None
            except (UnknownHashError, ValueError):
                self._hash.verify(normalize_password(value), self._dummy)
                return False
        return self._run(verify)
