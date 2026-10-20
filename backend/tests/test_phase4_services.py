"""Security facade contracts with injected memory storage, never live MongoDB."""
import copy
import hashlib
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from bson import BSON, ObjectId

from app.engine.errors import GameRuleError, RevisionConflict
from app.models.actions import ActionCommand, Skip, StartAttack, Roll
from app.models.auth import Principal
from app.models.game import GameSetupRequest
from app.security.config import SecuritySettings
from app.security.errors import SecurityError
from app.services.authorized_game_service import AuthorizedGameService
from npc_helpers import npc_state
from phase2_helpers import FixedDice, NOW, context, make_runtime, revise, step
from phase4_helpers import MemorySecurityStore


def seed_principal(store, username="Alice", *, token="first-session", now=NOW):
    user_id = store.create_user({"username": username, "username_key": username.lower(),
                                "password_hash": "test-hash-not-a-password", "status": "active",
                                "auth_version": 1, "authorization_revision": 0, "created_at": now})
    session_hash = hashlib.sha256(token.encode()).hexdigest()
    store.sessions[session_hash] = {"_id": session_hash, "user_id": user_id, "auth_version": 1,
                                   "csrf_token": f"csrf-{token}", "created_at": now, "last_seen_at": now,
                                   "expires_at": now + timedelta(hours=12), "revoked_at": None, "revision": 0}
    return Principal(user_id=user_id, username=username, session_hash=session_hash,
                     csrf_token=f"csrf-{token}", auth_version=1)


def service_for(catalog, *, store=None, dice=None, settings=None, clock=lambda: NOW):
    store = store if store is not None else MemorySecurityStore(clock=clock)
    settings = settings or SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True)
    service = AuthorizedGameService(store, settings, clock=clock, dice=dice or FixedDice(),
                                    catalog=catalog, setup_rng=random.Random(7))
    return store, service


def owned_document(store, principal, state):
    return store.create_owned_game(principal, state, str(ObjectId()), "seed-fingerprint", NOW, 1800)


def command(action=None, *, revision=0, action_id="human-step"):
    return ActionCommand(action_id=action_id, expected_revision=revision, action=action or Skip())


def test_owned_creation_replays_original_board_and_rejects_changed_payload(catalog):
    store, service = service_for(catalog)
    principal = seed_principal(store)
    request = GameSetupRequest(game_name="Independent one", starting_country_id="south-africa")
    first = service.create_game(principal, request, "creation-one")
    replay = service.create_game(principal, request, "creation-one")
    assert replay == first
    assert len(store.games) == 1
    assert first["access"]["owner_user_id"] == principal.user_id
    assert first["schema_version"] == 3
    assert "updated_at" in first
    assert BSON.encode(first)
    with pytest.raises(SecurityError) as error:
        service.create_game(principal, request.model_copy(update={"game_name": "Changed"}), "creation-one")
    assert error.value.status == 409
    assert len(store.games) == 1


def test_two_owned_games_resume_independently_and_list_is_owner_scoped(catalog):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    bob = seed_principal(store, "Bob", token="bob-session")
    first = owned_document(store, alice, make_runtime(catalog))
    second = owned_document(store, alice, make_runtime(catalog))
    owned_document(store, bob, make_runtime(catalog))
    first_id, second_id = str(first["_id"]), str(second["_id"])
    service.human_action(alice, first_id, command())
    assert store.games[first_id]["revision"] == 1
    assert store.games[second_id]["revision"] == 0
    page = service.list_games(alice, limit=1)
    assert len(page["games"]) == 1
    assert page["next_cursor"] is not None
    page_two = service.list_games(alice, cursor=page["next_cursor"], limit=1)
    assert len(page_two["games"]) == 1
    assert page_two["games"][0]["_id"] != page["games"][0]["_id"]
    assert all(doc["access"]["owner_user_id"] == alice.user_id
               for doc in page["games"] + page_two["games"])


def test_competing_creation_retries_keep_one_original_randomized_board(catalog):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    request = GameSetupRequest(game_name="Same request", starting_country_id="south-africa")
    barrier = threading.Barrier(2)
    def create(_):
        barrier.wait(timeout=5)
        return service.create_game(alice, request, "same-creation")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, [0, 1]))
    assert results[0] == results[1]
    assert len(store.games) == 1
    assert len(results[0]["countries"]) == 10


@pytest.mark.parametrize("failure", ["other_owner", "revoked", "disabled", "auth_version", "idle", "absolute"])
def test_authorization_precedes_receipts_dice_and_game_mutation(catalog, failure):
    dice = FixedDice([6, 1])
    store, service = service_for(catalog, dice=dice)
    alice = seed_principal(store)
    document = owned_document(store, alice, make_runtime(catalog))
    game_id = str(document["_id"])
    original = copy.deepcopy(store.games)
    caller = alice
    if failure == "other_owner":
        caller = seed_principal(store, "Bob", token="bob-session")
    elif failure == "revoked":
        store.revoke_session(alice.session_hash, NOW)
    elif failure == "disabled":
        store.users[alice.user_id]["status"] = "disabled"
    elif failure == "auth_version":
        store.users[alice.user_id]["auth_version"] += 1
    elif failure == "idle":
        store.sessions[alice.session_hash]["last_seen_at"] = NOW - timedelta(minutes=30)
    else:
        store.sessions[alice.session_hash]["expires_at"] = NOW
    with pytest.raises(SecurityError):
        service.human_action(caller, game_id, command())
    assert store.receipt_reads == 0
    assert dice.calls == 0
    assert store.games == original
    assert not store.receipts


@pytest.mark.parametrize("npc", [False, True])
def test_access_change_between_facade_read_and_first_scoped_query_is_rejected(catalog, monkeypatch, npc):
    dice = FixedDice([6, 1])
    store, service = service_for(catalog, dice=dice)
    alice = seed_principal(store)
    state = npc_state(catalog) if npc else make_runtime(catalog)
    game_id = str(owned_document(store, alice, state)["_id"])
    def revoke_after_initial_read(principal, identifier):
        with store.lock:
            store.games[game_id]["access"]["version"] += 1
    monkeypatch.setattr(service, "_rate", revoke_after_initial_read)
    with pytest.raises(SecurityError) as error:
        if npc:
            service.npc_step(alice, game_id, state.revision)
        else:
            service.human_action(alice, game_id, command())
    assert error.value.status == 403
    assert store.receipt_reads == 0
    assert dice.calls == 0
    assert store.games[game_id]["revision"] == 0
    assert not store.receipts


def test_committed_duplicate_replay_still_requires_current_ownership_and_session(catalog):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    game_id = str(owned_document(store, alice, make_runtime(catalog))["_id"])
    request = command()
    first = service.human_action(alice, game_id, request)
    assert service.human_action(alice, game_id, request) == first
    store.revoke_session(alice.session_hash, NOW)
    reads = store.receipt_reads
    with pytest.raises(SecurityError) as error:
        service.human_action(alice, game_id, request)
    assert error.value.status == 401
    assert store.receipt_reads == reads
    assert len(store.receipts) == 1


def test_game_id_case_canonicalization_preserves_replay_and_public_event_history(catalog):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    generated_id = str(owned_document(store, alice, make_runtime(catalog))["_id"])
    game_id = "abcdef012345abcdef012345"
    store.games[game_id] = store.games.pop(generated_id)
    store.games[game_id]["_id"] = ObjectId(game_id)
    first = service.human_action(alice, game_id.upper(), command())
    assert service.human_action(alice, game_id, command()) == first
    assert len(service.events(game_id.upper())["events"]) == 1
    assert len(service.events(game_id)["events"]) == 1


def test_npc_replay_does_not_rerun_strategy_or_dice(catalog, monkeypatch):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    game_id = str(owned_document(store, alice, npc_state(catalog))["_id"])
    first = service.npc_step(alice, game_id, 0)
    from app.engine.npc.strategy import NpcStrategy
    monkeypatch.setattr(NpcStrategy, "decide", lambda *args: pytest.fail("Replay reran NPC policy"))
    assert service.npc_step(alice, game_id, 0) == first
    assert len(store.receipts) == 1


@pytest.mark.parametrize("expected_revision", [0, 1])
def test_npc_step_cannot_act_for_human_and_rejects_stale_revision(catalog, expected_revision):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    game_id = str(owned_document(store, alice, make_runtime(catalog))["_id"])
    with pytest.raises(GameRuleError):
        service.npc_step(alice, game_id, expected_revision)
    assert not store.receipts


def test_human_cannot_take_server_reserved_npc_action_id(catalog):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    game_id = str(owned_document(store, alice, make_runtime(catalog))["_id"])
    with pytest.raises(SecurityError):
        service.human_action(alice, game_id, command(action_id="npc-balanced-v1-0-0"))
    assert not store.receipts


def test_historical_human_receipt_with_old_npc_prefix_remains_replayable(catalog):
    from app.services.game_action_service import GameActionService, command_fingerprint
    store, service = service_for(catalog)
    alice = seed_principal(store)
    state = make_runtime(catalog)
    game_id = str(owned_document(store, alice, state)["_id"])
    request = command(action_id="npc-old-human-identifier")
    historical = GameActionService(store.action_store(alice, game_id, lambda: NOW, 1800, enabled=True),
                                   FixedDice(), lambda: NOW).execute(game_id, context(state), request)
    saved = store.receipts[(game_id, request.action_id)]
    assert saved.fingerprint == command_fingerprint(context(state), request)
    assert service.human_action(alice, game_id, request) == historical
    assert len(store.receipts) == 1


def test_injected_after_game_update_failure_rolls_back_state_and_receipt(catalog):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    game_id = str(owned_document(store, alice, make_runtime(catalog))["_id"])
    before = copy.deepcopy(store.games)
    def fail_after_update(receipt):
        assert store.games[game_id]["revision"] == 1
        raise RuntimeError("Injected local rollback")
    store.after_game_update = fail_after_update
    with pytest.raises(RuntimeError):
        service.human_action(alice, game_id, command())
    assert store.games == before
    assert not store.receipts


@pytest.mark.parametrize("revocation", ["logout", "disabled", "auth_version", "access_version"])
def test_concurrent_revocation_during_dice_prevents_later_commit(catalog, revocation):
    rolling, release = threading.Event(), threading.Event()
    class BlockingDice(FixedDice):
        def roll(self):
            if self.calls == 0:
                rolling.set()
                assert release.wait(5)
            return super().roll()
    dice = BlockingDice([6, 1])
    store, service = service_for(catalog, dice=dice)
    alice = seed_principal(store)
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": 2}, 1: {"soldiers": 1}})
    state = step(state, StartAttack(source_id=state.countries[0].id, target_id=state.countries[1].id)).state
    game_id = str(owned_document(store, alice, state)["_id"])
    before = copy.deepcopy(store.games)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(service.human_action, alice, game_id,
                                  command(Roll(), revision=state.revision))
        assert rolling.wait(5)
        with store.lock:
            if revocation == "logout":
                store.revoke_session(alice.session_hash, NOW)
            elif revocation == "disabled":
                store.users[alice.user_id]["status"] = "disabled"
            elif revocation == "auth_version":
                store.users[alice.user_id]["auth_version"] += 1
            else:
                store.games[game_id]["access"]["version"] += 1
                before[game_id]["access"]["version"] += 1
        release.set()
        with pytest.raises(SecurityError):
            pending.result(timeout=5)
    assert store.games == before
    assert not store.receipts


@pytest.mark.parametrize("same_id", [True, False])
def test_competing_gameplay_requests_have_one_commit(catalog, same_id):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    game_id = str(owned_document(store, alice, make_runtime(catalog))["_id"])
    barrier = threading.Barrier(2)
    def submit(index):
        barrier.wait(timeout=5)
        try:
            return service.human_action(alice, game_id, command(action_id="same" if same_id else f"step-{index}"))
        except RevisionConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, [0, 1]))
    assert len(store.receipts) == 1
    assert store.games[game_id]["revision"] == 1
    assert sum(result is not None for result in results) == (2 if same_id else 1)


def test_legacy_ownerless_game_cannot_be_claimed_through_actions(catalog):
    store, service = service_for(catalog)
    alice = seed_principal(store)
    game_id = str(ObjectId())
    store.games[game_id] = {"_id": ObjectId(game_id), **make_runtime(catalog).model_dump(mode="json")}
    with pytest.raises(SecurityError) as error:
        service.human_action(alice, game_id, command())
    assert error.value.status == 403
    assert store.receipt_reads == 0
    assert not store.receipts


def test_both_disabled_gates_cannot_be_overridden_by_valid_principal(catalog):
    store, service = service_for(catalog, settings=SecuritySettings())
    alice = seed_principal(store)
    game_id = str(owned_document(store, alice, make_runtime(catalog))["_id"])
    with pytest.raises(SecurityError) as error:
        service.human_action(alice, game_id, command())
    assert error.value.status == 503
    with pytest.raises(SecurityError) as error:
        service.create_game(alice, GameSetupRequest(game_name="Disabled", starting_country_id="south-africa"), "create")
    assert error.value.status == 503
    assert not store.receipts
