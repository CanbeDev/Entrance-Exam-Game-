import pytest
from bson import ObjectId

from integration import test_phase2_mongo as fixture_module


def test_disposable_database_name_respects_atlas_byte_limit():
    name = fixture_module.generate_disposable_database_name()
    assert name.startswith("geo_p2_")
    assert len(name.encode("utf-8")) == 31
    assert len(name.encode("utf-8")) <= 38
    identifier = name.removeprefix("geo_p2_")
    assert len(identifier) == 24 and ObjectId.is_valid(identifier)


def test_disposable_database_names_preserve_unique_identifiers():
    names = {fixture_module.generate_disposable_database_name() for _ in range(100)}
    assert len(names) == 100
    assert all(len(name.encode("utf-8")) <= 38 for name in names)


def test_disposable_database_name_rejects_oversized_prefix(monkeypatch):
    monkeypatch.setattr(fixture_module, "DISPOSABLE_DATABASE_PREFIX", "x" * 15)
    with pytest.raises(ValueError, match="38-byte"):
        fixture_module.generate_disposable_database_name()
