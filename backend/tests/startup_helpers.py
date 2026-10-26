"""Read-only startup doubles. No clients, settings files or network access."""
from types import SimpleNamespace

from app.repositories.mongo_validators import mongo_validators
from app.repositories.phase4_indexes import phase4_indexes
from conftest import MemoryCollection


class StartupCollection(MemoryCollection):
    def __init__(self, indexes):
        super().__init__()
        self.indexes = {model.document["name"]: {**dict(model.document),
                       "key": list(model.document["key"].items())} for model in indexes}

    def index_information(self):
        return self.indexes


class StartupDatabase:
    def __init__(self):
        self.collections = {name: StartupCollection(indexes) for name, indexes in phase4_indexes().items()}
        self.metadata = [{"name": name, "type": "collection", "options": {
            "validator": validator, "validationLevel": "strict", "validationAction": "error"}}
            for name, validator in mongo_validators().items()]

    def __getitem__(self, name):
        return self.collections[name]

    def list_collections(self):
        return self.metadata


class StartupClient:
    def __init__(self):
        self.database = StartupDatabase()
        self.closed, self.commands = 0, []
        self.hello = {"logicalSessionTimeoutMinutes": 30, "setName": "test",
                      "isWritablePrimary": True, "maxWireVersion": 25}
        self.admin = SimpleNamespace(command=self.command)

    def command(self, command):
        self.commands.append(command)
        assert command in {"ping", "hello"}, "Startup must never run DDL"
        return self.hello if command == "hello" else {"ok": 1}

    def __getitem__(self, name):
        return self.database

    def close(self):
        self.closed += 1
