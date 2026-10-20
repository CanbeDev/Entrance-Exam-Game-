import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from app.models.auth import Credentials, LoginResult, Principal, UserPublic
from app.security.config import SecuritySettings
from app.security.errors import SecurityError
from app.security.passwords import Passwords, validate_new_password
from app.services.phase4_contracts import SecurityStore


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class AuthService:
    def __init__(self, store: SecurityStore, settings: SecuritySettings, clock=None, passwords=None):
        self.store = store
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.passwords = passwords if passwords is not None else Passwords()

    def _limit(self, scope, subject, limit, seconds):
        key = hashlib.sha256(f"{scope}:{subject}".encode()).hexdigest()
        now = self.clock()
        if not self.store.consume_limit(key, limit, seconds, now):
            raise SecurityError(429, "rate_limited", retry_after=seconds - int(now.timestamp()) % seconds)

    def register(self, credentials: Credentials, ip: str) -> UserPublic:
        self.settings.require_auth_writes()
        credentials = Credentials.model_validate(credentials.model_dump())
        self._limit("register-ip", ip, self.settings.register_ip_limit, 3600)
        password = validate_new_password(credentials.password.get_secret_value(), credentials.username)
        document = {"username": credentials.username, "username_key": credentials.username.lower(),
                    "password_hash": self.passwords.hash(password), "status": "active", "auth_version": 1,
                    "authorization_revision": 0, "created_at": self.clock()}
        user_id = self.store.create_user(document)
        return UserPublic(id=user_id, username=credentials.username)

    def login(self, credentials: Credentials, ip: str, previous_token: str | None = None) -> LoginResult:
        self.settings.require_auth_writes()
        credentials = Credentials.model_validate(credentials.model_dump())
        self._limit("login-ip", ip, self.settings.login_ip_limit, 300)
        self._limit("login-account", credentials.username.lower(), self.settings.login_account_limit, 900)
        user = self.store.find_user(credentials.username.lower())
        encoded = user.get("password_hash") if user else None
        valid = self.passwords.verify(credentials.password.get_secret_value(), encoded)
        if not valid or user is None or user.get("status") != "active":
            raise SecurityError(401, "invalid_credentials")
        now = self.clock()
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        expires = now + timedelta(seconds=self.settings.absolute_seconds)
        document = {"_id": token_hash(token), "user_id": str(user["_id"]), "auth_version": user["auth_version"],
                    "csrf_token": csrf, "created_at": now, "last_seen_at": now, "expires_at": expires,
                    "revoked_at": None, "revision": 0}
        previous_hash = None
        if isinstance(previous_token, str) and re.fullmatch(r"[a-zA-Z0-9_-]{43}", previous_token):
            previous_hash = token_hash(previous_token)
        self.store.issue_session(document, encoded, previous_hash)
        return LoginResult(user=UserPublic(id=str(user["_id"]), username=user["username"]),
                           token=token, csrf_token=csrf, expires_at=expires)

    def authenticate(self, raw_token: str | None) -> Principal:
        if not isinstance(raw_token, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{43}", raw_token):
            raise SecurityError(401, "authentication_required")
        self.settings.require_auth_writes()
        return self.store.authorize(token_hash(raw_token), self.clock(), self.settings.idle_seconds, touch=True)

    def logout(self, principal: Principal) -> None:
        self.settings.require_auth_writes()
        actual = self.store.authorize(principal.session_hash, self.clock(), self.settings.idle_seconds)
        if actual.user_id != principal.user_id or actual.auth_version != principal.auth_version:
            raise SecurityError(401, "authentication_required")
        self.store.revoke_session(principal.session_hash, self.clock())
