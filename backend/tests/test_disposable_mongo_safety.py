"""Exercise real-test safety gates with fake clients and forbidden DNS/sockets."""
import socket
from types import SimpleNamespace
from urllib.parse import quote_plus

import dns.resolver
import pytest
from pymongo.errors import PyMongoError

from integration import test_phase2_mongo as fixture_module
from integration.mongo_safety import parse_test_cluster_hosts, validate_disposable_uri


HOST = "disposable.example.mongodb.net"
SECOND_HOST = "disposable-shard-01.example.mongodb.net"
APPROVED_PHASE4_HOST = "geopoliticstestcluster.8kw5lci.mongodb.net"
URI = f"mongodb+srv://test-user:secret-canary@{HOST}/?retryWrites=true&w=majority"


@pytest.fixture(autouse=True)
def forbid_clients_and_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Safety validation attempted client creation or network access")
    monkeypatch.setattr(fixture_module, "MongoClient", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "gethostbyname", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(dns.resolver, "resolve", forbidden)
    monkeypatch.setattr(dns.resolver.Resolver, "resolve", forbidden)


def request_for(hosts=HOST, enabled=True):
    options = {"--disposable-mongodb": enabled, "--disposable-mongodb-hosts": None if hosts is None else [hosts]}
    return SimpleNamespace(config=SimpleNamespace(getoption=options.__getitem__))


def fixture_generator(hosts=HOST, enabled=True):
    return fixture_module.disposable_database.__wrapped__(request_for(hosts, enabled))


@pytest.mark.parametrize("hosts", [
    None, "", "   ", ",", HOST + ",", "," + HOST, HOST + ", " + HOST.upper(),
    "*.mongodb.net", ".mongodb.net", "mongodb.net.", "mongodb+srv://" + HOST,
    HOST + ":27017", "user@" + HOST, HOST + "/database", HOST + "?tls=true",
    "127.0.0.1", "[::1]", "bad_host.mongodb.net", "-bad.mongodb.net",
    "test..mongodb.net", "tést.mongodb.net", "a" * 64 + ".mongodb.net",
])
def test_missing_or_malformed_allowlist_stops_before_prompts_or_client(hosts, monkeypatch):
    def unexpected_prompt(*args, **kwargs):
        pytest.fail("Invalid allowlist must fail before requesting confirmation or credentials")
    monkeypatch.setattr("builtins.input", unexpected_prompt)
    monkeypatch.setattr(fixture_module.getpass, "getpass", unexpected_prompt)
    with pytest.raises(pytest.fail.Exception):
        next(fixture_generator(hosts))


@pytest.mark.parametrize("configured", [[], [HOST, HOST], [HOST, SECOND_HOST]])
def test_repeated_or_absent_allowlist_option_is_rejected(configured, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("Unexpected prompt"))
    options = {"--disposable-mongodb": True, "--disposable-mongodb-hosts": configured}
    request = SimpleNamespace(config=SimpleNamespace(getoption=options.__getitem__))
    with pytest.raises(pytest.fail.Exception, match="exactly once"):
        next(fixture_module.disposable_database.__wrapped__(request))


@pytest.mark.parametrize("uri", [
    "", "https://" + HOST, "mongodb+srv://", "mongodb://", URI + "#fragment",
    URI + "\n", URI.replace("secret-canary", "bad%escape"),
    URI.replace(HOST, "production.example.mongodb.net"),
    URI.replace(HOST, HOST + ".attacker.example"),
    URI.replace(HOST, "attacker." + HOST),
    URI.replace(HOST, HOST + ":27017"),
    URI.replace(HOST, HOST + "," + SECOND_HOST),
    URI.replace(HOST, HOST + "."), URI.replace(HOST, "%64isposable.example.mongodb.net"),
    URI.replace(HOST, "hidden@" + HOST), URI.replace("/?", "/bad/name?"),
    f"mongodb://{HOST}:0/", f"mongodb://{HOST}:65536/", f"mongodb://{HOST}:bad/",
    f"mongodb://{HOST},production.example.mongodb.net/", f"mongodb://{HOST},/",
    f"mongodb://{HOST}:27017,{HOST}:27018/", f"mongodb://%2Ftmp%2Fmongo.sock/",
    URI + "&retrywrites=false", URI + "&tls=true&ssl=true", URI + "&tls=invalid",
    URI + "&directConnection=true", URI + "&unknownOption=true", URI + "&proxyHost=localhost",
    URI + "&srvServiceName=other", URI + "&srvAllowedHostsSuffix=example.net",
    URI + "&tlsCAFile=%5C%5Cserver%5Cshare%5Cca.pem", URI + "&appName=one;tls=true",
    URI + "&missing-value", URI + "&authSource=", URI + "&appName=%FF",
])
def test_invalid_or_unapproved_uri_never_creates_client_or_resolves_dns(uri, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt: "DISPOSABLE")
    monkeypatch.setattr(fixture_module.getpass, "getpass", lambda prompt: uri)
    with pytest.raises(pytest.fail.Exception, match="Invalid or unapproved") as failure:
        next(fixture_generator(HOST + "," + SECOND_HOST))
    if uri:
        assert uri not in str(failure.value)
    assert "secret-canary" not in str(failure.value) + capsys.readouterr().out


@pytest.mark.parametrize("uri, hosts, expected", [
    (URI, HOST, (HOST,)),
    (URI.replace(HOST, HOST.upper()), " " + HOST.upper() + " ", (HOST,)),
    (URI.replace("secret-canary", "p%40ss%3Aword"), HOST, (HOST,)),
    (f"mongodb://test-user:password@{HOST}:27017/?tls=true&authSource=admin", HOST, (HOST,)),
    (f"mongodb://{HOST}:27017,{SECOND_HOST}:27018/?replicaSet=disposable&tls=true",
     HOST + ", " + SECOND_HOST, (HOST, SECOND_HOST)),
    ("mongodb://localhost:27017/?replicaSet=disposable", "localhost", ("localhost",)),
])
def test_valid_srv_and_standard_targets_are_parsed_entirely_offline(uri, hosts, expected):
    assert validate_disposable_uri(uri, parse_test_cluster_hosts(hosts)) == expected


@pytest.mark.parametrize("suffix", [
    "/", "/?appName=GeopoliticsTestCluster",
    "/?retryWrites=true&w=majority&appName=GeopoliticsTestCluster",
    "/phase4_disposable?authSource=admin&tls=true",
    "/?APPNAME=GeopoliticsTestCluster&RETRYWRITES=true&W=majority",
], ids=["bare", "atlas-appname", "atlas-options", "database-and-tls", "option-case"])
@pytest.mark.parametrize("dummy_password", [
    "synthetic-only", quote_plus("synthetic @:/?#[]%+ space"), quote_plus("synthetic-\u00e9"),
], ids=["simple", "encoded-reserved-characters", "encoded-unicode"])
def test_approved_phase4_srv_host_accepts_normal_atlas_forms_offline(suffix, dummy_password):
    # Entirely synthetic credentials; the real hostname is public test metadata.
    uri = f"mongodb+srv://synthetic-user:{dummy_password}@{APPROVED_PHASE4_HOST}{suffix}"
    allowed = parse_test_cluster_hosts(APPROVED_PHASE4_HOST.upper())
    assert validate_disposable_uri(uri, allowed) == (APPROVED_PHASE4_HOST,)


@pytest.mark.parametrize("uri, check", [
    ("", "URI_EMPTY_OR_TYPE"), (None, "URI_EMPTY_OR_TYPE"),
    (" " + URI, "URI_WHITESPACE_OR_CONTROL"), (URI + "\t", "URI_WHITESPACE_OR_CONTROL"),
    (URI.replace("secret-canary", "secret canary"), "URI_WHITESPACE_OR_CONTROL"),
    (URI + "#fragment", "URI_FRAGMENT"),
    (URI.replace("secret-canary", "secret%wrong"), "URI_PERCENT_ESCAPE"),
    ("'" + URI + "'", "URI_SCHEME"),
    (URI.replace(HOST, "other@" + HOST), "URI_AUTHORITY"),
    (f"mongodb://{HOST}:bad/", "URI_SEED_SYNTAX"),
    (f"mongodb://{HOST},{HOST}/", "URI_DUPLICATE_HOSTS"),
    (URI.replace(HOST, "production.example.mongodb.net"), "URI_HOST_NOT_ALLOWLISTED"),
    (URI.replace(HOST, HOST + ":27017"), "URI_SRV_SEED"),
    (URI.replace(HOST, HOST + "," + SECOND_HOST), "URI_SRV_SEED"),
    (URI + "&missing-value", "URI_QUERY_SYNTAX"),
    (URI + "&appName=one;tls=true", "URI_QUERY_SYNTAX"),
    (URI.split("?")[0] + "?", "URI_QUERY_SYNTAX"),
    (URI + "&retrywrites=false", "URI_DUPLICATE_OPTIONS"),
    (URI + "&maxPoolSize=10", "URI_UNSUPPORTED_OPTIONS"),
    (URI + "&proxyHost=localhost", "URI_UNSUPPORTED_OPTIONS"),
    (URI + "&tls=true&ssl=true", "URI_TLS_ALIASES"),
    (URI.replace("test-user:secret-canary", ":secret-canary"), "URI_CREDENTIAL_SYNTAX"),
    (URI.replace("secret-canary", "secret:canary"), "URI_CREDENTIAL_SYNTAX"),
    (URI + "&tls=invalid", "URI_DRIVER_SYNTAX"),
    (URI + "&authSource=", "URI_DRIVER_SYNTAX"),
    (URI + "&directConnection=true", "URI_SRV_DIRECT_CONNECTION"),
])
def test_rejection_identifies_only_fixed_safe_check_name(uri, check, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt: "DISPOSABLE")
    monkeypatch.setattr(fixture_module.getpass, "getpass", lambda prompt: uri)
    with pytest.raises(pytest.fail.Exception) as result:
        next(fixture_generator(HOST + "," + SECOND_HOST))
    message = str(result.value)
    assert message == ("Invalid or unapproved disposable MongoDB URI; "
                       f"check exact test hosts and supported options [{check}]")
    assert "secret-canary" not in message + capsys.readouterr().out
    assert HOST not in message and "production.example.mongodb.net" not in message


def test_diagnostic_also_sanitizes_underlying_driver_errors(monkeypatch):
    from integration import mongo_safety

    def reject(*args, **kwargs):
        raise PyMongoError("secret-canary " + URI)
    monkeypatch.setattr(mongo_safety, "parse_uri", reject)
    with pytest.raises(ValueError, match=r"\[URI_DRIVER_SYNTAX\]") as result:
        validate_disposable_uri(URI, parse_test_cluster_hosts(HOST))
    assert "secret-canary" not in str(result.value) and HOST not in str(result.value)
    assert result.value.__suppress_context__


@pytest.mark.parametrize("hosts", [None, frozenset(), frozenset({HOST.upper()})])
def test_validator_itself_requires_validated_nonempty_allowlist(hosts):
    with pytest.raises(ValueError, match="Invalid or unapproved"):
        validate_disposable_uri(URI, hosts)


def test_explicit_opt_in_is_still_required(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("Unexpected prompt"))
    with pytest.raises(pytest.skip.Exception):
        next(fixture_generator(enabled=False))


@pytest.mark.parametrize("confirmation", ["disposable", "DISPOSABLE ", "", "yes"])
def test_confirmation_must_remain_exact(confirmation, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: confirmation)
    monkeypatch.setattr(fixture_module.getpass, "getpass", lambda prompt: pytest.fail("Unexpected URI prompt"))
    with pytest.raises(pytest.fail.Exception, match="authorization was not provided"):
        next(fixture_generator())


class FakeClient:
    def __init__(self, hello=None, failure=None, cleanup_failure=False):
        self.admin = SimpleNamespace(command=self.command)
        self.hello = hello if hello is not None else {"logicalSessionTimeoutMinutes": 30, "setName": "disposable"}
        self.failure = failure
        self.cleanup_failure = cleanup_failure
        self.closed = 0
        self.dropped = []
        self.created = []

    def command(self, name):
        assert name == "hello"
        if self.failure == "hello":
            raise PyMongoError("secret-canary")
        return self.hello

    def __getitem__(self, name):
        self.database = SimpleNamespace(name=name, create_collection=self.create_collection)
        return self.database

    def create_collection(self, name):
        self.created.append(name)
        if self.failure == "collection":
            raise PyMongoError("secret-canary")
        if self.failure == "unexpected":
            raise RuntimeError("Injected setup failure")

    def drop_database(self, name):
        assert name == self.database.name and name.startswith("geo_p2_")
        self.dropped.append(name)
        if self.cleanup_failure:
            raise PyMongoError("secret-canary")

    def close(self):
        self.closed += 1


def fake_target(monkeypatch, client):
    monkeypatch.setattr("builtins.input", lambda prompt: "DISPOSABLE")
    monkeypatch.setattr(fixture_module.getpass, "getpass", lambda prompt: URI)
    def construct(uri, **kwargs):
        assert uri == URI and kwargs == {"serverSelectionTimeoutMS": 5000}
        return client
    monkeypatch.setattr(fixture_module, "MongoClient", construct)
    return fixture_generator()


@pytest.mark.parametrize("hello", [{}, {"logicalSessionTimeoutMinutes": 30}, {"setName": "disposable"}])
def test_unsupported_topology_closes_client_without_creating_or_dropping_database(hello, monkeypatch):
    client = FakeClient(hello=hello)
    with pytest.raises(pytest.fail.Exception, match="Transactions require"):
        next(fake_target(monkeypatch, client))
    assert client.closed == 1 and client.created == [] and client.dropped == []


@pytest.mark.parametrize("failure", ["hello", "collection", "unexpected"])
def test_every_setup_failure_closes_client_and_restricts_cleanup(failure, monkeypatch, capsys):
    client = FakeClient(failure=failure)
    exception = RuntimeError if failure == "unexpected" else pytest.fail.Exception
    with pytest.raises(exception) as result:
        next(fake_target(monkeypatch, client))
    assert client.closed == 1
    assert len(client.dropped) == (0 if failure == "hello" else 1)
    assert "secret-canary" not in str(result.value) + capsys.readouterr().out


def test_successful_teardown_drops_only_generated_database_and_closes_client(monkeypatch):
    client = FakeClient()
    generator = fake_target(monkeypatch, client)
    actual_client, database = next(generator)
    assert actual_client is client and len(database.name.encode("utf-8")) == 31
    assert client.created == ["games", "game_action_receipts"]
    generator.close()
    assert client.dropped == [database.name] and client.closed == 1


def test_cleanup_failure_is_reported_without_secrets_and_still_closes_client(monkeypatch):
    client = FakeClient(cleanup_failure=True)
    generator = fake_target(monkeypatch, client)
    _, database = next(generator)
    with pytest.raises(pytest.fail.Exception, match="cleanup failed") as result:
        generator.close()
    assert database.name in str(result.value) and "secret-canary" not in str(result.value)
    assert client.dropped == [database.name] and client.closed == 1


def test_setup_and_cleanup_failure_still_closes_client(monkeypatch):
    client = FakeClient(failure="collection", cleanup_failure=True)
    with pytest.raises(pytest.fail.Exception, match="cleanup failed"):
        next(fake_target(monkeypatch, client))
    assert client.closed == 1 and len(client.dropped) == 1
