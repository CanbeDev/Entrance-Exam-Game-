from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SecuritySettings:
    # Explicit composition; validated environment loading is separate.
    auth_writes_enabled: bool = False
    gameplay_writes_enabled: bool = False
    trusted_origins: tuple[str, ...] = ()
    idle_seconds: int = 1800
    absolute_seconds: int = 43200
    cookie_name: str = "__Host-geopolitics_session"
    max_body_bytes: int = 16384
    login_account_limit: int = 10
    login_ip_limit: int = 30
    register_ip_limit: int = 5
    gameplay_limit: int = 120

    def __post_init__(self):
        if type(self.auth_writes_enabled) is not bool or type(self.gameplay_writes_enabled) is not bool:
            raise ValueError("Write gates must be explicit booleans")
        for value in (self.idle_seconds, self.absolute_seconds, self.max_body_bytes,
                      self.login_account_limit, self.login_ip_limit, self.register_ip_limit, self.gameplay_limit):
            if type(value) is not int or value <= 0:
                raise ValueError("Security limits must be positive integers")
        if self.idle_seconds > self.absolute_seconds:
            raise ValueError("Idle timeout exceeds absolute lifetime")
        if self.cookie_name != "__Host-geopolitics_session":
            raise ValueError("The secure cookie contract cannot be relaxed")
        if (not isinstance(self.trusted_origins, tuple) or
                any(not isinstance(origin, str) for origin in self.trusted_origins) or
                len(set(self.trusted_origins)) != len(self.trusted_origins)):
            raise ValueError("Trusted origins must be distinct exact origins")
        for origin in self.trusted_origins:
            parsed = urlsplit(origin)
            # Accessing port validates malformed/out-of-range numeric ports.
            parsed.port
            if ("*" in origin or "\\" in origin or origin.endswith(":")
                    or any(char.isspace() or ord(char) < 32 for char in origin)
                    or parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
                    or origin != f"{parsed.scheme}://{parsed.netloc}"):
                raise ValueError("Trusted origins must be exact origins")
            if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("Production origins require HTTPS")

    def require_auth_writes(self):
        from app.security.errors import SecurityError
        if not self.auth_writes_enabled:
            raise SecurityError(503, "authentication_disabled")

    def require_gameplay_writes(self):
        from app.security.errors import SecurityError
        if not self.gameplay_writes_enabled:
            raise SecurityError(503, "gameplay_writes_disabled")
