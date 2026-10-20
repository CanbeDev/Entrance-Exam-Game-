"""Prepared real Phase 4 verification. Skipped unless separately authorized.

Importing only defines tests. The reused guarded fixture requires the existing
opt-in flag, explicit test-host allowlist, DISPOSABLE confirmation and validated
hidden dedicated URI before any client,
collection, index or write operation. Never loads .env or production configuration.
"""
import hashlib
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId
from pymongo.errors import PyMongoError

from app.engine.errors import PersistenceUnavailable, RevisionConflict
from app.models.actions import ActionCommand, Roll, Skip, StartAttack
from app.models.auth import Credentials
from app.models.game import GameSetupRequest
from app.repositories.phase4_indexes import provision_phase4_indexes, verify_required_indexes
from app.repositories.security_repository import MongoSecurityRepository
from app.repositories.scoped_action_repository import ScopedMongoActionRepository
from app.security.config import SecuritySettings
from app.security.errors import SecurityError
from app.security.passwords import Passwords
from app.services.auth_service import AuthService, token_hash
from app.services.authorized_game_service import AuthorizedGameService
from integration.test_phase2_mongo import disposable_database
from npc_helpers import npc_state
from phase2_helpers import FixedDice, context, make_runtime, revise, step

pytestmark = pytest.mark.disposable_mongo

PASSWORD = "Disposable test words 2027!"


@pytest.fixture(scope="module")
def phase4_disposable_target(disposable_database):
    # The shared fixture enforces the offline hostname gate before client creation.
    client, database = disposable_database
    assert database.name.startswith("geo_p2_")
    assert len(database.name.encode("utf-8")) <= 38
    provision_phase4_indexes(database)
    verify_required_indexes(database)
    return client, database


@pytest.fixture
def real_security(phase4_disposable_target, catalog):
    client, database = phase4_disposable_target
    now = datetime.now(timezone.utc)
    moment = [now.replace(microsecond=(now.microsecond // 1000) * 1000)]
    clock = lambda: moment[0]
    settings = SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True,
                                trusted_origins=("https://testserver",))
    repository = MongoSecurityRepository(client, database, auth_writes_enabled=True,
                                         gameplay_writes_enabled=True)
    passwords = Passwords()
    auth = AuthService(repository, settings, clock, passwords)
    credentials = Credentials(username=f"P4_{ObjectId()}", password=PASSWORD)
    ip = f"disposable-{ObjectId()}"
    user = auth.register(credentials, ip)
    login = auth.login(credentials, ip)
    principal = auth.authenticate(login.token)
    games = AuthorizedGameService(repository, settings, clock, FixedDice(), catalog, random.Random(7))
    return SimpleNamespace(client=client, database=database, repository=repository,
                           settings=settings, moment=moment, clock=clock, passwords=passwords,
                           auth=auth, credentials=credentials, ip=ip, user=user, login=login,
                           principal=principal, games=games, catalog=catalog)


def _owned(bundle, state):
    return bundle.repository.create_owned_game(bundle.principal, state, str(ObjectId()),
                                               "disposable-seed", bundle.clock(), 1800)


def _fresh_games(bundle, *, dice=None):
    repository = MongoSecurityRepository(bundle.client, bundle.database, auth_writes_enabled=True,
                                         gameplay_writes_enabled=True)
    return AuthorizedGameService(repository, bundle.settings, bundle.clock,
                                 dice if dice is not None else FixedDice(), bundle.catalog)


def _request(state, action=None, action_id="real-phase4-action"):
    return ActionCommand(action_id=action_id, expected_revision=state.revision, action=action or Skip())


def test_real_phase4_unique_username_concurrent_registration(real_security):
    bundle = real_security
    credentials = Credentials(username=f"Race_{ObjectId()}", password=PASSWORD)
    barrier = threading.Barrier(2, timeout=15)
    def register(index):
        barrier.wait()
        try:
            return bundle.auth.register(credentials, f"register-race-{index}-{ObjectId()}")
        except SecurityError as error:
            assert error.status == 409 and error.code == "username_unavailable"
            return None
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(register, [0, 1]))
    assert sum(result is not None for result in results) == 1
    users = list(bundle.database.users.find({"username_key": credentials.username.lower()}))
    assert len(users) == 1
    assert users[0]["password_hash"].startswith("$argon2id$")
    assert PASSWORD not in repr(users[0])
    assert bundle.database.users.index_information()["username_key_unique"]["unique"] is True


def test_real_phase4_session_restart_expiry_and_logout(real_security):
    bundle = real_security
    stored = bundle.database.auth_sessions.find_one({"_id": token_hash(bundle.login.token)})
    assert stored is not None and bundle.login.token not in repr(stored)
    fresh_repository = MongoSecurityRepository(bundle.client, bundle.database, auth_writes_enabled=True)
    fresh_auth = AuthService(fresh_repository, bundle.settings, bundle.clock, bundle.passwords)
    assert fresh_auth.authenticate(bundle.login.token).user_id == bundle.user.id
    fresh_auth.logout(bundle.principal)
    with pytest.raises(SecurityError) as error:
        bundle.auth.authenticate(bundle.login.token)
    assert error.value.status == 401
    new_login = bundle.auth.login(bundle.credentials, bundle.ip)
    bundle.moment[0] += timedelta(seconds=bundle.settings.idle_seconds)
    with pytest.raises(SecurityError) as error:
        fresh_auth.authenticate(new_login.token)
    assert error.value.status == 401
    # The row still exists: application expiry must work before eventual TTL cleanup.
    assert bundle.database.auth_sessions.find_one({"_id": token_hash(new_login.token)}) is not None
    bundle.moment[0] -= timedelta(seconds=bundle.settings.idle_seconds)
    bundle.database.auth_sessions.update_one({"_id": token_hash(new_login.token)},
                                              {"$set": {"expires_at": bundle.clock()}})
    with pytest.raises(SecurityError) as error:
        fresh_auth.authenticate(new_login.token)
    assert error.value.status == 401


def test_real_phase4_owned_creation_concurrent_idempotency(real_security):
    bundle = real_security
    request = GameSetupRequest(game_name="Disposable independent game", starting_country_id="south-africa")
    key = f"create-{ObjectId()}"
    barrier = threading.Barrier(2, timeout=15)
    def create(_):
        service = _fresh_games(bundle)
        barrier.wait()
        return service.create_game(bundle.principal, request, key)
    with ThreadPoolExecutor(max_workers=2) as workers:
        documents = list(workers.map(create, [0, 1]))
    assert documents[0] == documents[1]
    match = {"access.owner_user_id": bundle.user.id, "creation.key": key}
    assert bundle.database.games.count_documents(match) == 1
    assert documents[0]["schema_version"] == 3 and documents[0]["revision"] == 0
    with pytest.raises(SecurityError) as error:
        bundle.games.create_game(bundle.principal, request.model_copy(update={"game_name": "Changed"}), key)
    assert error.value.status == 409
    other = bundle.games.create_game(bundle.principal, request, f"another-{ObjectId()}")
    assert other["_id"] != documents[0]["_id"]
    listed = bundle.games.list_games(bundle.principal)
    assert {doc["_id"] for doc in listed["games"]} == {other["_id"], documents[0]["_id"]}


def test_real_phase4_action_atomic_state_receipt_and_auth_fence_rollback(real_security, monkeypatch):
    bundle = real_security
    state = revise(make_runtime(bundle.catalog), country_changes={0: {"soldiers": 3}, 1: {"soldiers": 2}})
    state = step(state, StartAttack(source_id=state.countries[0].id, target_id=state.countries[1].id)).state
    game_id = str(_owned(bundle, state)["_id"])
    game_match = {"_id": ObjectId(game_id)}
    session_match = {"_id": bundle.principal.session_hash}
    user_match = {"_id": ObjectId(bundle.user.id)}
    before = {"game": bundle.database.games.find_one(game_match),
              "session": bundle.database.auth_sessions.find_one(session_match),
              "user": bundle.database.users.find_one(user_match)}
    seen = []
    original_insert = bundle.repository._receipts.insert_one
    original_action_store = bundle.repository.action_store
    def instrumented_action_store(*args, **kwargs):
        scoped = original_action_store(*args, **kwargs)
        # PyMongo database[name] constructs separate Collection handles. Bind the
        # explicit instrumented handle so the hook observes the actual INSERT.
        scoped._receipts = bundle.repository._receipts
        return scoped
    monkeypatch.setattr(bundle.repository, "action_store", instrumented_action_store)
    def fail_after_actual_updates(document, *, session):
        staged_game = bundle.database.games.find_one(game_match, session=session)
        staged_session = bundle.database.auth_sessions.find_one(session_match, session=session)
        staged_user = bundle.database.users.find_one(user_match, session=session)
        assert staged_game["revision"] == state.revision + 1
        assert next(c for c in staged_game["countries"] if c["id"] == state.countries[0].id)["soldiers"] == 2
        assert next(c for c in staged_game["countries"] if c["id"] == state.countries[1].id)["soldiers"] == 1
        assert staged_session["revision"] > before["session"]["revision"]
        assert staged_user["authorization_revision"] > before["user"]["authorization_revision"]
        assert document["result"]["events"][0]["type"] == "dice_exchange"
        seen.append(True)
        raise PyMongoError("Disposable deliberate failure after observed transaction updates")
    monkeypatch.setattr(bundle.repository._receipts, "insert_one", fail_after_actual_updates)
    bundle.games.dice = FixedDice([1, 4, 2, 3])
    request = _request(state, Roll())
    with pytest.raises(PersistenceUnavailable):
        bundle.games.human_action(bundle.principal, game_id, request)
    assert seen
    assert bundle.database.games.find_one(game_match) == before["game"]
    assert bundle.database.auth_sessions.find_one(session_match) == before["session"]
    assert bundle.database.users.find_one(user_match) == before["user"]
    assert bundle.database.game_action_receipts.count_documents({"game_id": game_id}) == 0
    monkeypatch.setattr(bundle.repository._receipts, "insert_one", original_insert)
    bundle.games.dice = FixedDice([1, 4, 2, 3])
    committed = bundle.games.human_action(bundle.principal, game_id, request)
    assert committed.state.revision == state.revision + 1
    assert committed.events[0].attacker_losses == committed.events[0].defender_losses == 1
    assert bundle.database.game_action_receipts.count_documents({"game_id": game_id}) == 1


def test_real_phase4_duplicate_owner_denial_and_historical_human_hash(real_security, monkeypatch):
    bundle = real_security
    state = make_runtime(bundle.catalog)
    game_id = str(_owned(bundle, state)["_id"])
    request = _request(state)
    original = bundle.games.human_action(bundle.principal, game_id, request)
    actor = context(state)
    payload = {"actor": actor.model_dump(mode="json"), "command": request.model_dump(mode="json")}
    historical_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    match = {"game_id": game_id, "command.action_id": request.action_id}
    receipt = bundle.database.game_action_receipts.find_one(match)
    assert receipt["fingerprint"] == historical_hash
    bundle.database.game_action_receipts.update_one(match, {"$unset": {"result.npc_decision": ""}})
    fresh = _fresh_games(bundle)
    assert fresh.human_action(bundle.principal, game_id, request) == original
    other_credentials = Credentials(username=f"Other_{ObjectId()}", password=PASSWORD)
    other = bundle.auth.register(other_credentials, f"other-{ObjectId()}")
    other_login = bundle.auth.login(other_credentials, f"other-{ObjectId()}")
    other_principal = bundle.auth.authenticate(other_login.token)
    assert other.id != bundle.user.id
    def forbidden_lookup(*args, **kwargs):
        pytest.fail("Unauthorized caller reached action receipt lookup")
    monkeypatch.setattr(ScopedMongoActionRepository, "find_receipt", forbidden_lookup)
    with pytest.raises(SecurityError) as error:
        bundle.games.human_action(other_principal, game_id, request)
    assert error.value.status == 403


def test_real_phase4_concurrent_logout_during_dice_prevents_commit(real_security):
    bundle = real_security
    ready, release = threading.Event(), threading.Event()
    class BlockingDice(FixedDice):
        def roll(self):
            if self.calls == 0:
                ready.set()
                assert release.wait(15)
            return super().roll()
    state = revise(make_runtime(bundle.catalog), country_changes={0: {"soldiers": 2}, 1: {"soldiers": 1}})
    state = step(state, StartAttack(source_id=state.countries[0].id, target_id=state.countries[1].id)).state
    game_id = str(_owned(bundle, state)["_id"])
    before = bundle.database.games.find_one({"_id": ObjectId(game_id)})
    bundle.games.dice = BlockingDice([6, 1])
    with ThreadPoolExecutor(max_workers=1) as workers:
        pending = workers.submit(bundle.games.human_action, bundle.principal, game_id, _request(state, Roll()))
        try:
            assert ready.wait(15)
            bundle.auth.logout(bundle.principal)
        finally:
            release.set()
        with pytest.raises(SecurityError) as error:
            pending.result(timeout=15)
    assert error.value.status == 401
    assert bundle.database.games.find_one({"_id": ObjectId(game_id)}) == before
    assert bundle.database.game_action_receipts.count_documents({"game_id": game_id}) == 0


def test_real_phase4_account_revocation_prevents_receipt_lookup(real_security, monkeypatch):
    bundle = real_security
    state = make_runtime(bundle.catalog)
    game_id = str(_owned(bundle, state)["_id"])
    bundle.database.users.update_one({"_id": ObjectId(bundle.user.id)}, {"$inc": {"auth_version": 1}})
    monkeypatch.setattr(ScopedMongoActionRepository, "find_receipt",
                        lambda *args, **kwargs: pytest.fail("Revoked account reached receipt lookup"))
    with pytest.raises(SecurityError) as error:
        bundle.games.human_action(bundle.principal, game_id, _request(state))
    assert error.value.status == 401
    assert bundle.database.game_action_receipts.count_documents({"game_id": game_id}) == 0


def test_real_phase4_npc_step_atomic_evidence_and_fresh_service_replay(real_security, monkeypatch):
    from app.engine.npc.strategy import NpcStrategy
    bundle = real_security
    state = npc_state(bundle.catalog, source_soldiers=3, changes={0: {"soldiers": 2}})
    state = step(state, StartAttack(source_id=state.countries[1].id, target_id=state.countries[0].id)).state
    game_id = str(_owned(bundle, state)["_id"])
    bundle.games.dice = FixedDice([1, 4, 2, 3])
    result = bundle.games.npc_step(bundle.principal, game_id, state.revision)
    assert result.npc_decision is not None
    assert result.state.country(state.battle.source_id).soldiers == 2
    assert result.state.country(state.battle.target_id).soldiers == 1
    receipt = bundle.database.game_action_receipts.find_one({"game_id": game_id})
    assert receipt["result"]["npc_decision"] == result.npc_decision.model_dump(mode="json")
    assert receipt["result"]["events"] == [event.model_dump(mode="json") for event in result.events]
    monkeypatch.setattr(NpcStrategy, "decide", lambda *args: pytest.fail("Replay reran strategy"))
    fresh_dice = FixedDice()
    fresh = _fresh_games(bundle, dice=fresh_dice)
    assert fresh.npc_step(bundle.principal, game_id, state.revision) == result
    assert fresh_dice.calls == 0
    assert bundle.database.game_action_receipts.count_documents({"game_id": game_id}) == 1
    public = fresh.events(game_id)
    assert len(public["events"]) == 1 and public["events"][0]["npc_decision"] is not None
    assert "fingerprint" not in repr(public) and "owner_user_id" not in repr(public)


@pytest.mark.parametrize("same_id", [False, True], ids=["distinct-action-ids", "identical-action-id"])
def test_real_phase4_competing_authorized_actions(real_security, monkeypatch, same_id):
    bundle = real_security
    state = make_runtime(bundle.catalog)
    game_id = str(_owned(bundle, state)["_id"])
    barrier = threading.Barrier(2, timeout=15)
    original_load = ScopedMongoActionRepository.load_game

    def synchronized_load(repository, identifier):
        document = original_load(repository, identifier)
        barrier.wait()
        return document

    monkeypatch.setattr(ScopedMongoActionRepository, "load_game", synchronized_load)

    def submit(index):
        service = _fresh_games(bundle)
        action_id = "same-authorized-action" if same_id else f"authorized-action-{index}"
        try:
            return service.human_action(bundle.principal, game_id, _request(state, action_id=action_id))
        except RevisionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(submit, [0, 1]))
    if same_id:
        assert results[0] == results[1] and results[0] is not None
    else:
        assert sum(result is not None for result in results) == 1
    assert bundle.database.games.find_one({"_id": ObjectId(game_id)})["revision"] == state.revision + 1
    assert bundle.database.game_action_receipts.count_documents({"game_id": game_id}) == 1


def test_real_phase4_shared_rate_limit_and_expiry_without_ttl(real_security):
    bundle = real_security
    key = f"disposable-limit-{ObjectId()}"

    def consume(_):
        repository = MongoSecurityRepository(bundle.client, bundle.database, auth_writes_enabled=True)
        return repository.consume_limit(key, 3, 60, bundle.clock())

    with ThreadPoolExecutor(max_workers=4) as workers:
        accepted = list(workers.map(consume, range(8)))
    assert sum(accepted) == 3
    # Advance the injected clock, not the database TTL worker or a real sleep.
    bundle.moment[0] += timedelta(seconds=61)
    assert bundle.repository.consume_limit(key, 3, 60, bundle.clock())


def test_real_phase4_missing_index_blocks_enabled_repository(real_security):
    bundle = real_security
    assert bundle.repository.consume_limit(f"ready-{ObjectId()}", 1, 60, bundle.clock())
    before = bundle.database.users.count_documents({})
    # Only inside the confirmed generated disposable DB; restore before teardown.
    bundle.database.users.drop_index("username_key_unique")
    try:
        with pytest.raises(SecurityError) as failure:
            bundle.auth.register(Credentials(username=f"NoIndex_{ObjectId()}", password=PASSWORD),
                                 f"missing-index-{ObjectId()}")
        assert failure.value.code == "security_indexes_not_ready"
        assert bundle.database.users.count_documents({}) == before
    finally:
        provision_phase4_indexes(bundle.database)
        verify_required_indexes(bundle.database)
