import copy
import socket
from types import SimpleNamespace

import pytest
from bson import ObjectId

from app.services.country_catalog import CountryCatalog


def pytest_addoption(parser):
    parser.addoption("--disposable-mongodb", action="store_true", default=False,
                     help="Explicitly run real transaction tests against a prompted disposable MongoDB target")


@pytest.fixture(autouse=True)
def no_external_connections(monkeypatch, request):
    """Block external connections; Windows asyncio needs an internal loopback pipe."""
    if request.node.get_closest_marker("disposable_mongo") and request.config.getoption("--disposable-mongodb"):
        return
    original_connect = socket.socket.connect

    def guarded_connect(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        raise AssertionError("Network access is forbidden in isolated tests")

    def deny(*args, **kwargs):
        raise AssertionError("External connection creation is forbidden in isolated tests")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", deny)


@pytest.fixture
def catalog():
    return CountryCatalog.load()


class MemoryCollection:
    def __init__(self):
        self.documents = {}
        self.insert_count = 0

    def insert_one(self, document):
        object_id = ObjectId()
        self.documents[object_id] = {**copy.deepcopy(document), "_id": object_id}
        self.insert_count += 1
        return SimpleNamespace(inserted_id=object_id)

    def find_one(self, query):
        return copy.deepcopy(self.documents.get(query["_id"]))


@pytest.fixture
def collection():
    return MemoryCollection()
