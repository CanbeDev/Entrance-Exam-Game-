"""Offline URI checks for the opt-in disposable harness; never loads settings."""
import re
from urllib.parse import parse_qsl

from pymongo.errors import PyMongoError
from pymongo.uri_parser import parse_uri, parse_userinfo, split_hosts


# Deliberately accept ordinary Atlas/replica-set options only. In particular,
# proxies, SRV overrides and file-based TLS/auth options cannot redirect this
# test harness or cause file/network access during URI validation.
_OPTIONS = frozenset({
    "appname", "authsource", "authmechanism", "replicaset", "retrywrites",
    "retryreads", "w", "wtimeoutms", "readconcernlevel", "readpreference",
    "tls", "ssl", "directconnection", "loadbalanced", "connecttimeoutms",
    "serverselectiontimeoutms", "sockettimeoutms",
})
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.ASCII)


def _hostname(value):
    """Exact ASCII DNS names only: no wildcard/suffix matching, ports or IPs."""
    host = value.lower()
    if (len(host) > 253 or not any("a" <= char <= "z" for char in host)
            or not all(_LABEL.fullmatch(label) for label in host.split("."))):
        raise ValueError("Use exact ASCII DNS hostnames, without ports, wildcards or URI components")
    return host


def parse_test_cluster_hosts(configured_hosts):
    if not isinstance(configured_hosts, str) or not configured_hosts.strip():
        raise ValueError("--disposable-mongodb-hosts must explicitly list the dedicated test cluster hostnames")
    hosts = tuple(_hostname(value.strip()) for value in configured_hosts.split(","))
    if len(set(hosts)) != len(hosts):
        raise ValueError("Duplicate test-cluster hostnames are ambiguous")
    return frozenset(hosts)


def validate_disposable_uri(uri, allowed_hosts):
    """Validate BOTH URI forms without ever asking PyMongo to resolve SRV DNS.

    PyMongo's public parse_uri performs DNS on mongodb+srv URIs. We validate its
    seed and SRV-only constraints ourselves, then use the non-SRV parser for the
    remaining grammar/options. Never return parser errors containing credentials.
    """
    # Only these fixed check names may appear in errors, never URI components or
    # driver exception text. They diagnose hidden-prompt mistakes without secrets.
    check = "ALLOWLIST"
    try:
        # Require a validated, nonempty set even when called outside the fixture.
        if (not isinstance(allowed_hosts, frozenset) or not allowed_hosts
                or any(_hostname(host) != host for host in allowed_hosts)):
            raise ValueError
        check = "URI_EMPTY_OR_TYPE"
        if not isinstance(uri, str) or not uri:
            raise ValueError
        check = "URI_WHITESPACE_OR_CONTROL"
        if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in uri):
            raise ValueError
        check = "URI_FRAGMENT"
        if "#" in uri:
            raise ValueError
        check = "URI_PERCENT_ESCAPE"
        if re.search(r"%(?![0-9a-fA-F]{2})", uri):
            raise ValueError
        check = "URI_SCHEME"
        scheme, separator, remainder = uri.partition("://")
        if not separator or scheme not in {"mongodb", "mongodb+srv"}:
            raise ValueError
        check = "URI_AUTHORITY"
        authority = re.split(r"[/?]", remainder, maxsplit=1)[0]
        if authority.count("@") > 1:
            raise ValueError
        seeds = authority.rsplit("@", 1)[-1]
        srv = scheme == "mongodb+srv"
        check = "URI_SEED_SYNTAX"
        nodes = split_hosts(seeds, default_port=None if srv else 27017)
        hosts = tuple(_hostname(host) for host, _ in nodes)
        check = "URI_DUPLICATE_HOSTS"
        if len(set(hosts)) != len(hosts):
            raise ValueError
        check = "URI_HOST_NOT_ALLOWLISTED"
        if not set(hosts).issubset(allowed_hosts):
            raise ValueError
        check = "URI_SRV_SEED"
        if srv and (len(nodes) != 1 or nodes[0][1] is not None or "." not in hosts[0]):
            raise ValueError
        check = "URI_QUERY_SYNTAX"
        _, query_separator, query = remainder.partition("?")
        if query_separator and (not query or ";" in query or "?" in query):
            raise ValueError
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True,
                          encoding="utf-8", errors="strict")
        keys = [key.lower() for key, _ in pairs]
        check = "URI_DUPLICATE_OPTIONS"
        if len(set(keys)) != len(keys):
            raise ValueError
        check = "URI_UNSUPPORTED_OPTIONS"
        if not set(keys).issubset(_OPTIONS):
            raise ValueError
        check = "URI_TLS_ALIASES"
        if {"ssl", "tls"}.issubset(keys):
            raise ValueError
        check = "URI_CREDENTIAL_SYNTAX"
        if "@" in authority:
            parse_userinfo(authority.rsplit("@", 1)[0])
        # ALWAYS mongodb:// here: even an approved SRV seed is not resolved yet.
        check = "URI_DRIVER_SYNTAX"
        parsed = parse_uri("mongodb://" + remainder, validate=True, warn=False)
        options = {key.lower(): value for key, value in parsed["options"].items()}
        check = "URI_SRV_DIRECT_CONNECTION"
        if srv and options.get("directconnection"):
            raise ValueError
        return hosts
    except (PyMongoError, ValueError, TypeError, UnicodeError):
        raise ValueError("Invalid or unapproved disposable MongoDB URI; "
                         f"check exact test hosts and supported options [{check}]") from None
