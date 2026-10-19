import copy

import pytest

from app.engine.errors import ActionIdConflict, GameRuleError, PersistenceUnavailable, RevisionConflict
from app.models.actions import ActionCommand, EndTurn, Roll, Skip, StartAttack
from app.services.game_action_service import GameActionService
from phase2_helpers import FixedDice, MemoryActionStore, NOW, context, make_runtime, revise, step


def command(state, action, action_id="action-1"):
    return ActionCommand(action_id=action_id, expected_revision=state.revision, action=action)


def test_service_resume_and_duplicate_preserves_dice_events(catalog):
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": 2}, 1: {"soldiers": 1}})
    store = MemoryActionStore(state.model_dump(mode="json"))
    dice = FixedDice([3, 3])
    service = GameActionService(store, dice, lambda: NOW)
    selection = service.execute(store.game_id, context(state), command(state, StartAttack(source_id=state.countries[0].id, target_id=state.countries[1].id)))
    assert dice.calls == 0 and store.writes == 1
    roll_command = command(selection.state, Roll(), "roll-1")
    first = service.execute(store.game_id, context(state), roll_command)
    assert dice.calls == 2 and store.writes == 2
    # A fresh service models restart/return next day; no new dice are available.
    repeated = GameActionService(store, FixedDice(), lambda: NOW).execute(store.game_id, context(state), roll_command)
    assert repeated == first and store.writes == 2
    assert repeated.events[0].attacker_dice == (3,)
    assert repeated.state.battle == selection.state.battle


def test_same_action_id_different_content_rejected(catalog):
    state = make_runtime(catalog)
    store = MemoryActionStore(state.model_dump())
    service = GameActionService(store)
    service.execute(store.game_id, context(state), command(state, Skip()))
    before = copy.deepcopy(store.document)
    with pytest.raises(ActionIdConflict):
        service.execute(store.game_id, context(state), command(state, EndTurn()))
    assert store.document == before and store.writes == 1


def test_invalid_or_stale_actions_never_commit(catalog):
    state = make_runtime(catalog)
    store = MemoryActionStore(state.model_dump())
    dice = FixedDice()
    service = GameActionService(store, dice)
    with pytest.raises(GameRuleError):
        service.execute(store.game_id, context(state), command(state, Roll()))
    assert store.writes == 0 and dice.calls == 0
    service.execute(store.game_id, context(state), command(state, Skip()))
    with pytest.raises(RevisionConflict):
        service.execute(store.game_id, context(state), command(state, Skip(), "other"))
    assert store.writes == 1 and dice.calls == 0


def test_absent_game(catalog):
    state = make_runtime(catalog)
    store = MemoryActionStore(state.model_dump())
    with pytest.raises(GameRuleError, match="not found"):
        GameActionService(store).execute("1" * 24, context(state), command(state, Skip()))
    assert store.writes == 0


def test_uncertain_commit_retry_recovers_original_result(catalog):
    state = make_runtime(catalog)
    store = MemoryActionStore(state.model_dump())
    original_commit = store.commit
    def lost_ack(receipt):
        original_commit(receipt)
        raise PersistenceUnavailable("Simulated lost acknowledgement")
    store.commit = lost_ack
    request = command(state, Skip())
    with pytest.raises(PersistenceUnavailable):
        GameActionService(store).execute(store.game_id, context(state), request)
    result = GameActionService(store).execute(store.game_id, context(state), request)
    assert result.state.revision == 1 and store.writes == 1


def test_no_write_after_persistence_failure(catalog):
    state = make_runtime(catalog)
    store = MemoryActionStore(state.model_dump())
    before = copy.deepcopy(store.document)
    def fail(receipt):
        raise PersistenceUnavailable("Simulated failure before commit")
    store.commit = fail
    with pytest.raises(PersistenceUnavailable):
        GameActionService(store).execute(store.game_id, context(state), command(state, Skip()))
    assert store.document == before and store.writes == 0


def test_identical_submission_race_before_revision_check(catalog):
    state = make_runtime(catalog)
    store = MemoryActionStore(state.model_dump())
    request = command(state, Skip())
    result = GameActionService(store).execute(store.game_id, context(state), request)
    original_find = store.find_receipt
    reads = 0
    def stale_initial_read(game_id, action_id):
        nonlocal reads
        reads += 1
        return None if reads == 1 else original_find(game_id, action_id)
    store.find_receipt = stale_initial_read
    assert GameActionService(store).execute(store.game_id, context(state), request) == result
    assert store.writes == 1


def test_phase1_saved_game_upgrades_only_on_valid_action(catalog):
    import random
    from app.engine.game_setup import initialize_game
    from app.models.game import GameSetupRequest
    from app.engine.state_adapter import load_runtime
    initial = initialize_game(GameSetupRequest(game_name="Saved Phase 1", starting_country_id="india"), catalog, random.Random(3))
    store = MemoryActionStore(initial.model_dump())
    state = load_runtime(store.document)
    with pytest.raises(GameRuleError):
        GameActionService(store).execute(store.game_id, context(state), command(state, Roll()))
    assert store.document["schema_version"] == 2
    result = GameActionService(store).execute(store.game_id, context(state), command(state, Skip()))
    assert store.document["schema_version"] == 3 and result.state.revision == 1
    assert result.state.turn_order == tuple(initial.turn_order)


def test_gameplay_cannot_change_legacy_waiting_records(catalog):
    from app.engine.errors import UnsupportedGame
    state = make_runtime(catalog)
    legacy = {"game_name": "My First Game", "countries": [], "players": [], "status": "waiting"}
    store = MemoryActionStore(legacy)
    with pytest.raises(UnsupportedGame):
        GameActionService(store).execute(store.game_id, context(state), command(state, Skip()))
    assert store.document == legacy and store.writes == 0


def test_duplicate_roll_replays_original_receipt_after_later_turns(catalog):
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": 2}, 1: {"soldiers": 1}})
    state = step(state, StartAttack(source_id=state.countries[0].id, target_id=state.countries[1].id)).state
    store = MemoryActionStore(state.model_dump())
    request = command(state, Roll(), "capture")
    result = GameActionService(store, FixedDice([6, 1]), lambda: NOW).execute(store.game_id, context(state), request)
    later = GameActionService(store).execute(store.game_id, context(result.state), command(result.state, EndTurn(), "end"))
    assert later.state.revision == result.state.revision + 1
    assert GameActionService(store, FixedDice()).execute(store.game_id, context(state), request) == result
    assert store.writes == 2
