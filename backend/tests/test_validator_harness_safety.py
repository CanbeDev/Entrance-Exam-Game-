"""Offline proofs of validator harness authorization, ownership and cleanup gates."""
import socket
from types import SimpleNamespace

import dns.resolver
import pytest
from pymongo.errors import PyMongoError

from app.repositories.mongo_validators import mongo_validators
from app.repositories.phase4_indexes import phase4_indexes
from integration import validator_harness as harness
from integration.test_mongo_provisioning import phase_scenario
from phase2_helpers import FixedDice, MemoryActionStore, context
from app.models.actions import ActionCommand
from app.services.game_action_service import GameActionService
from test_mongo_provisioning import matches

URI = f"mongodb+srv://synthetic:secret-canary@{harness.ATLAS_TEST_HOST}/?retryWrites=true&w=majority"


def request_for(*, local=False, atlas=True, disposable=True, hosts=None):
    values = {"--local-provisioning-mongodb": local, "--atlas-validator-mongodb": atlas,
              "--disposable-mongodb": disposable,
              "--disposable-mongodb-hosts": [harness.ATLAS_TEST_HOST] if hosts is None else hosts}
    return SimpleNamespace(config=SimpleNamespace(getoption=values.__getitem__))


@pytest.fixture(autouse=True)
def no_clients_or_dns(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Harness safety check attempted a real client or network connection")
    monkeypatch.setattr(harness, "MongoClient", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(dns.resolver, "resolve", forbidden)
    monkeypatch.setattr(dns.resolver.Resolver, "resolve", forbidden)


def prompts(monkeypatch, *, confirmation="DISPOSABLE", uri=URI):
    monkeypatch.setattr("builtins.input", lambda prompt: confirmation)
    monkeypatch.setattr(harness.getpass, "getpass", lambda prompt: uri)


@pytest.mark.parametrize("options", [
    {"local": True}, {"local": True, "atlas": False}, {"disposable": False},
    {"hosts": []}, {"hosts": [harness.ATLAS_TEST_HOST, harness.ATLAS_TEST_HOST]},
    {"hosts": ["production.example.mongodb.net"]},
    {"hosts": [harness.ATLAS_TEST_HOST + ",production.example.mongodb.net"]},
])
def test_invalid_target_flags_and_allowlist_refused_before_prompts(options, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("Unexpected confirmation prompt"))
    with pytest.raises(pytest.fail.Exception):
        harness.authorized_uri(request_for(**options))


def test_missing_explicit_validator_flag_skips_before_client():
    with pytest.raises(pytest.skip.Exception):
        with harness.authorized_client(request_for(atlas=False)):
            pytest.fail("Unexpected target")


def test_local_target_never_prompts_or_reads_environment(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: pytest.fail("Unexpected prompt"))
    assert harness.authorized_uri(request_for(local=True, atlas=False, disposable=False)) == (harness.LOCAL_URI, False)


@pytest.mark.parametrize("confirmation", ["", "yes", "disposable", "DISPOSABLE "])
def test_exact_disposable_confirmation_precedes_hidden_credentials(confirmation, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: confirmation)
    monkeypatch.setattr(harness.getpass, "getpass", lambda prompt: pytest.fail("Unexpected credential prompt"))
    with pytest.raises(pytest.fail.Exception, match="authorization was not provided"):
        harness.authorized_uri(request_for())


@pytest.mark.parametrize("uri", [
    URI.replace(harness.ATLAS_TEST_HOST, "production.example.mongodb.net"),
    URI.replace("mongodb+srv://", "mongodb://"), URI + "&tls=false", URI + "&ssl=false",
    URI + "&tlsAllowInvalidCertificates=true", URI + "&tlsAllowInvalidHostnames=true",
    URI + "&tlsInsecure=true", URI + "&proxyHost=localhost", URI + "&srvServiceName=other",
])
def test_unapproved_uri_or_insecure_tls_rejected_before_client(uri, monkeypatch, capsys):
    prompts(monkeypatch, uri=uri)
    with pytest.raises(pytest.fail.Exception) as failure:
        with harness.authorized_client(request_for()):
            pytest.fail("Unexpected target")
    assert "secret-canary" not in str(failure.value) + capsys.readouterr().out


def test_working_hidden_prompt_is_required(monkeypatch):
    prompts(monkeypatch)
    def unavailable(prompt):
        raise harness.getpass.GetPassWarning("would echo secret-canary")
    monkeypatch.setattr(harness.getpass, "getpass", unavailable)
    with pytest.raises(pytest.fail.Exception, match="hidden credential prompt") as failure:
        harness.authorized_uri(request_for())
    assert "secret-canary" not in str(failure.value)


def test_pinned_srv_and_verified_tls_are_accepted_entirely_offline(monkeypatch):
    prompts(monkeypatch)
    assert harness.authorized_uri(request_for()) == (URI, True)


class FakeCollection:
    def __init__(self, client):
        self.client = client
        self.documents = {}

    def insert_one(self, document):
        if self.client.failure == "marker_insert":
            raise PyMongoError("secret-canary")
        self.documents[document["_id"]] = document

    def find_one(self, query):
        if self.client.failure == "ownership_missing":
            return None
        return self.documents.get(query["_id"])

    def create_indexes(self, indexes):
        self.client.index_calls.append(indexes)


class FakeDatabase:
    def __init__(self, client, name):
        self.client, self.name = client, name
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection(self.client))

    def create_collection(self, name, **options):
        if self.client.failure == "collection" and name == "users":
            raise PyMongoError("secret-canary")
        self.client.created.append((name, options))
        return self[name]


class FakeClient:
    def __init__(self, *, hello=None, nodes=None, failure=None, preexisting=False):
        self.hello = hello if hello is not None else {"logicalSessionTimeoutMinutes": 30, "setName": "test"}
        self.nodes = nodes if nodes is not None else {("test-shard.8kw5lci.mongodb.net", 27017)}
        self.failure, self.preexisting = failure, preexisting
        self.admin = SimpleNamespace(command=self.command)
        self.created, self.dropped, self.index_calls, self.closed = [], [], [], 0

    def command(self, command):
        assert command == "hello"
        if self.failure == "hello":
            raise PyMongoError("secret-canary")
        return self.hello

    def __getitem__(self, name):
        self.database = FakeDatabase(self, name)
        return self.database

    def list_database_names(self):
        return [self.database.name] if self.preexisting else []

    def drop_database(self, name):
        self.dropped.append(name)
        if self.failure == "cleanup":
            raise PyMongoError("secret-canary")

    def close(self):
        self.closed += 1


def fake_target(monkeypatch, client):
    prompts(monkeypatch)
    def construct(uri, **options):
        assert uri == URI and options == {"serverSelectionTimeoutMS": 5000}
        return client
    monkeypatch.setattr(harness, "MongoClient", construct)
    return harness.authorized_client(request_for())


@pytest.mark.parametrize("hello,nodes", [
    ({}, None), ({"logicalSessionTimeoutMinutes": 30}, None),
    ({"setName": "test"}, None),
    (None, {("production.example.mongodb.net", 27017)}), (None, set()),
])
def test_topology_or_discovered_peer_rejection_closes_without_ddl(hello, nodes, monkeypatch):
    client = FakeClient(hello=hello, nodes=nodes)
    with pytest.raises(pytest.fail.Exception):
        with fake_target(monkeypatch, client):
            pytest.fail("Unexpected target")
    assert client.closed == 1 and client.created == [] and client.dropped == []


def test_connection_failure_sanitized_without_fallback(monkeypatch):
    client = FakeClient(failure="hello")
    with pytest.raises(pytest.fail.Exception, match="TARGET_UNAVAILABLE") as failure:
        with fake_target(monkeypatch, client):
            pytest.fail("Unexpected target")
    assert "secret-canary" not in str(failure.value) and client.closed == 1


def test_generated_database_collision_is_never_dropped():
    client = FakeClient(preexisting=True)
    with pytest.raises(pytest.fail.Exception, match="already exists"):
        with harness.fresh_database(client, provision=False):
            pytest.fail("Unexpected database")
    assert client.created == [] and client.dropped == []


def test_harness_installs_exact_manifest_and_cleans_only_claimed_database(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(harness, "verify_database", lambda database: None)
    with fake_target(monkeypatch, client):
        with harness.fresh_database(client) as database:
            name = database.name
            assert len(name.encode("utf-8")) <= 38 and harness._NAME.fullmatch(name)
    assert client.dropped == [name] and client.closed == 1
    assert [name for name, _ in client.created] == [harness._MARKER, *harness.provisioning_plan()]
    for name, options in client.created[1:]:
        item = harness.provisioning_plan()[name]
        assert options == {key: item[key] for key in ("validator", "validationLevel", "validationAction")}
    expected = [[model.document for model in phase4_indexes()[name]] for name in harness.provisioning_plan()]
    assert [[model.document for model in indexes] for indexes in client.index_calls] == expected


@pytest.mark.parametrize("failure", ["collection", "marker_insert", "cleanup", "ownership_missing"])
def test_partial_setup_and_cleanup_failures_remain_narrow_and_sanitized(failure, monkeypatch):
    client = FakeClient(failure=failure)
    monkeypatch.setattr(harness, "verify_database", lambda database: None)
    with pytest.raises(pytest.fail.Exception) as result:
        with fake_target(monkeypatch, client):
            with harness.fresh_database(client):
                pass
    assert "secret-canary" not in str(result.value) and client.closed == 1
    assert len(client.dropped) == (1 if failure in {"collection", "cleanup"} else 0)
    assert all(harness._NAME.fullmatch(name) for name in client.dropped)
    if failure in {"collection", "marker_insert", "cleanup"}:
        assert client.database.name in str(result.value)


@pytest.mark.parametrize("final", [False, True])
def test_real_phase_scenarios_generate_valid_documents_offline(catalog, final):
    state, actions = phase_scenario(catalog, final=final)
    store = MemoryActionStore(state.model_dump(mode="json"))
    service = GameActionService(store, FixedDice([6, 1]), lambda: state.updated_at)
    schemas = mongo_validators()
    expected = ["attacking", "finished"] if final else ["deciding", "attacking", "post_attack", "allocating"]
    for index, (action, phase) in enumerate(zip(actions, expected)):
        result = service.execute(store.game_id, context(state), ActionCommand(
            action_id=f"offline-phase-{index}", expected_revision=state.revision, action=action))
        state = result.state
        assert state.phase == phase
        assert matches(store.document, schemas["games"]["$jsonSchema"])
        receipt = store.find_receipt(store.game_id, f"offline-phase-{index}")
        assert matches(receipt.model_dump(mode="json"), schemas["game_action_receipts"]["$jsonSchema"])


def test_read_only_smoke_reuses_guards_without_authorizing_setup(monkeypatch):
    prompts(monkeypatch)
    seen = []
    monkeypatch.setattr("builtins.input", lambda prompt: seen.append(prompt) or "DISPOSABLE")
    client = FakeClient()
    def factory(uri):
        assert uri == URI
        return client
    with harness.authorized_client(request_for(), read_only=True, client_factory=factory) as selected:
        assert selected is client
    assert len(seen) == 1 and "read-only" in seen[0] and "no provisioning" in seen[0]
    assert "authorize generated TEST database creation" not in seen[0]
    assert client.closed == 1 and not client.created and not client.dropped
