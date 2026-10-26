"""Validated startup configuration. Never loads .env, connects or logs values."""
from dataclasses import dataclass, field
import json
import os
import re
from urllib.parse import parse_qsl

from pymongo.uri_parser import parse_uri, split_hosts

from app.security.config import SecuritySettings


class ConfigurationError(RuntimeError):
    def __init__(self, code="invalid_configuration"):
        super().__init__(code)


@dataclass(frozen=True)
class ApplicationSettings:
    mongodb_uri: str = field(repr=False)
    database_name: str
    security: SecuritySettings = field(default_factory=SecuritySettings)
    tls_required: bool = field(init=False)

    def __post_init__(self):
        try:
            if (not isinstance(self.mongodb_uri, str) or not self.mongodb_uri
                    or any(char.isspace() or ord(char) < 32 for char in self.mongodb_uri)
                    or "#" in self.mongodb_uri or re.search(r"%(?![0-9a-fA-F]{2})", self.mongodb_uri)):
                raise ValueError
            scheme, separator, remainder = self.mongodb_uri.partition("://")
            if not separator or scheme not in {"mongodb", "mongodb+srv"}:
                raise ValueError
            authority = re.split(r"[/?]", remainder, maxsplit=1)[0]
            nodes = split_hosts(authority.rsplit("@", 1)[-1], default_port=None if scheme == "mongodb+srv" else 27017)
            if any(any(char in host for char in "/\\%") for host, _ in nodes):
                raise ValueError
            if scheme == "mongodb+srv" and (len(nodes) != 1 or nodes[0][1] is not None):
                raise ValueError
            query = remainder.partition("?")[2]
            pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
            options = {key.lower(): value for key, value in pairs}
            allowed = {"appname", "authsource", "authmechanism", "replicaset", "retrywrites", "retryreads",
                       "w", "wtimeoutms", "readconcernlevel", "readpreference", "tls", "ssl",
                       "directconnection", "connecttimeoutms", "serverselectiontimeoutms", "sockettimeoutms"}
            if (len(options) != len(pairs) or set(options) - allowed or {"tls", "ssl"} <= options.keys()
                    or options.get("w") == "0" or options.get("readpreference", "primary") != "primary"):
                raise ValueError
            # The non-SRV parser validates grammar/options without DNS resolution.
            parse_uri("mongodb://" + remainder, validate=True, warn=False)
            remote = scheme == "mongodb+srv" or any(host not in {"localhost", "127.0.0.1", "::1"} for host, _ in nodes)
            tls = options.get("tls", options.get("ssl", "true" if remote else "false"))
            if tls not in {"true", "false"} or remote and tls != "true":
                raise ValueError
            if scheme == "mongodb+srv" and options.get("directconnection") == "true":
                raise ValueError
            if not isinstance(self.database_name, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,38}", self.database_name) is None:
                raise ValueError
            if not isinstance(self.security, SecuritySettings):
                raise ValueError
            if self.security.gameplay_writes_enabled and not self.security.auth_writes_enabled:
                raise ValueError
            if self.security.auth_writes_enabled and not self.security.trusted_origins:
                raise ValueError
            object.__setattr__(self, "tls_required", tls == "true")
        except Exception:
            raise ConfigurationError() from None


def load_application_settings(environ=None):
    """Read only named process settings at lifespan startup, not import time."""
    values = os.environ if environ is None else environ
    if not values.get("MONGODB_URI") or not values.get("MONGODB_DB_NAME"):
        raise ConfigurationError("missing_database_configuration")
    try:
        limit_names = ("idle_seconds", "absolute_seconds", "max_body_bytes", "login_account_limit",
                       "login_ip_limit", "register_ip_limit", "gameplay_limit")
        known = {"PHASE4_AUTH_WRITES_ENABLED", "PHASE4_GAMEPLAY_WRITES_ENABLED", "PHASE4_TRUSTED_ORIGINS",
                 *("PHASE4_" + name.upper() for name in limit_names)}
        if any(key.startswith("PHASE4_") and key not in known for key in values):
            raise ValueError
        def flag(name):
            value = values.get(name, "false")
            if value not in {"true", "false"}:
                raise ValueError
            return value == "true"

        origins = json.loads(values.get("PHASE4_TRUSTED_ORIGINS", "[]"))
        if not isinstance(origins, list) or any(not isinstance(origin, str) for origin in origins):
            raise ValueError
        limits = {}
        for name in limit_names:
            key = "PHASE4_" + name.upper()
            if key in values:
                value = values[key]
                if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]{0,8}", value) is None:
                    raise ValueError
                limits[name] = int(value)
        security = SecuritySettings(auth_writes_enabled=flag("PHASE4_AUTH_WRITES_ENABLED"),
            gameplay_writes_enabled=flag("PHASE4_GAMEPLAY_WRITES_ENABLED"),
            trusted_origins=tuple(origins), **limits)
        return ApplicationSettings(values["MONGODB_URI"], values["MONGODB_DB_NAME"], security)
    except Exception:
        raise ConfigurationError() from None
