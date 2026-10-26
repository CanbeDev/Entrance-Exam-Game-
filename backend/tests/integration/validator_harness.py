"""Opt-in validator integration targets. Importing never connects or reads settings.

Remote DDL is confined to this test harness and its newly generated databases.
The operational provisioning CLI remains loopback-only.
"""
import getpass
import re
import warnings
from contextlib import contextmanager
from urllib.parse import parse_qsl

import pytest
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.repositories.mongo_provisioning import ProvisioningError, provisioning_plan, verify_database
from app.repositories.phase4_indexes import phase4_indexes
from integration.mongo_safety import parse_test_cluster_hosts, validate_disposable_uri

ATLAS_TEST_HOST = "geopoliticstestcluster.8kw5lci.mongodb.net"
LOCAL_URI = "mongodb://127.0.0.1:27017/?directConnection=true"
_NAME = re.compile(r"geo_prov_[0-9a-f]{24}", re.ASCII)
_MARKER = "__validator_test_ownership"


def authorized_uri(request, *, read_only=False):
    """All authorization/URI checks run offline, before constructing a client."""
    local = request.config.getoption("--local-provisioning-mongodb")
    atlas = request.config.getoption("--atlas-validator-mongodb")
    if local and atlas:
        pytest.fail("Choose exactly one validator integration target", pytrace=False)
    if local:
        if request.config.getoption("--disposable-mongodb"):
            pytest.fail("Local validator mode cannot be combined with remote opt-in", pytrace=False)
        return LOCAL_URI, False
    if not atlas:
        pytest.skip("Requires --local-provisioning-mongodb or separately authorized Atlas validator flags")
    if not request.config.getoption("--disposable-mongodb"):
        pytest.fail("Atlas validators also require --disposable-mongodb", pytrace=False)
    configured = request.config.getoption("--disposable-mongodb-hosts")
    if not configured or len(configured) != 1:
        pytest.fail("Specify --disposable-mongodb-hosts exactly once", pytrace=False)
    try:
        allowed = parse_test_cluster_hosts(configured[0])
    except ValueError as error:
        pytest.fail(str(error), pytrace=False)
    if allowed != frozenset({ATLAS_TEST_HOST}):
        pytest.fail("Validator Atlas mode requires the pinned dedicated TEST seed only", pytrace=False)
    purpose = ("read-only TEST startup checks; no provisioning or cleanup" if read_only
               else "generated TEST database creation and cleanup")
    if input(f"Type DISPOSABLE to authorize {purpose}: ") != "DISPOSABLE":
        pytest.fail("Disposable database authorization was not provided", pytrace=False)
    try:
        # Do not permit getpass's echoing fallback in redirected/noninteractive runs.
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            uri = getpass.getpass("Dedicated Atlas TEST URI (hidden; never read from .env): ")
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        pytest.fail("A working hidden credential prompt is required", pytrace=False)
    try:
        validate_disposable_uri(uri, allowed)
        if not uri.startswith("mongodb+srv://"):
            raise ValueError("Atlas validator mode requires the pinned SRV seed")
        options = {key.lower(): value.lower() for key, value in parse_qsl(uri.partition("?")[2])}
        if options.get("tls", options.get("ssl", "true")) != "true":
            raise ValueError("Atlas validator mode requires verified TLS")
    except ValueError as error:
        pytest.fail(str(error), pytrace=False)
    return uri, True


@contextmanager
def authorized_client(request, *, read_only=False, client_factory=None):
    uri, atlas = authorized_uri(request, read_only=read_only)
    client = None
    try:
        try:
            client = (MongoClient(uri, serverSelectionTimeoutMS=5000) if client_factory is None
                      else client_factory(uri))
            hello = client.admin.command("hello")
            if not hello.get("logicalSessionTimeoutMinutes") or not (
                    hello.get("setName") or hello.get("msg") == "isdbgrid"):
                pytest.fail("Transactions require sessions and a replica set or sharded topology", pytrace=False)
            # A pinned SRV seed + normal TLS verification identifies the intended
            # cluster; reject unrelated discovered peers before any fixture DDL.
            if atlas:
                suffix = "." + ATLAS_TEST_HOST.split(".", 1)[1]
                if not client.nodes or any(not host.endswith(suffix) for host, _ in client.nodes):
                    pytest.fail("Discovered deployment is outside the pinned TEST cluster", pytrace=False)
            elif not client.nodes or any(host not in {"localhost", "127.0.0.1", "::1"}
                                         for host, _ in client.nodes):
                pytest.fail("Local validator target must remain loopback-only", pytrace=False)
        except (PyMongoError, ValueError):
            pytest.fail("Validator test target unavailable [TARGET_UNAVAILABLE]; no fallback", pytrace=False)
        yield client
    finally:
        if client is not None:
            client.close()


@contextmanager
def fresh_database(client, *, provision=True):
    """Claim a new generated DB; cleanup only the exact DB with our marker."""
    name = "geo_prov_" + str(ObjectId())
    assert _NAME.fullmatch(name) and len(name.encode("utf-8")) <= 38
    database = client[name]
    owner = str(ObjectId())
    claimed = False
    try:
        try:
            if name in client.list_database_names():
                pytest.fail("Generated disposable database already exists; refusing reuse", pytrace=False)
            marker = database.create_collection(_MARKER)
            marker.insert_one({"_id": owner})
            claimed = True
            if provision:
                # No remote provisioning entry point is added to application code.
                # Only this claimed empty disposable fixture installs the manifest.
                for collection, item in provisioning_plan().items():
                    options = {key: item[key] for key in ("validator", "validationLevel", "validationAction")}
                    database.create_collection(collection, **options)
                    database[collection].create_indexes(list(phase4_indexes()[collection]))
                verify_database(database)
        except (PyMongoError, ProvisioningError):
            pytest.fail(f"Disposable validator setup failed [SETUP_FAILED] for '{name}'; "
                        "inspect this generated database if cleanup was not confirmed; no fallback", pytrace=False)
        yield database
    finally:
        if claimed:
            try:
                if (database.name != name or not _NAME.fullmatch(name)
                        or database[_MARKER].find_one({"_id": owner}) is None):
                    pytest.fail(f"Disposable cleanup ownership check failed [CLEANUP_REFUSED] for '{name}'", pytrace=False)
                client.drop_database(name)
            except PyMongoError:
                pytest.fail(f"Disposable cleanup failed [CLEANUP_FAILED] for '{name}'; "
                            "inspect and remove only that database on the authorized TEST target", pytrace=False)
