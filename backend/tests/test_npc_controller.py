import copy

import pytest

from app.engine.errors import GameRuleError, PersistenceUnavailable, RevisionConflict
from app.models.actions import StartAttack
from npc_helpers import controller_for, npc_state
from phase2_helpers import make_runtime, revise, step
from phase2_helpers import FixedDice


class TiedDice:
    def __init__(self):
        self.calls = 0

    def roll(self):
        self.calls += 1
        return 3


def test_stops_at_human_without_creating_actions(catalog):
    store, _, controller = controller_for(make_runtime(catalog))
    assert controller.prepare(store.game_id) is None
    batch = controller.run_until_human(store.game_id)
    assert batch.reason == "human_turn" and batch.committed == () and store.writes == 0


def test_stops_when_already_completed(catalog):
    state = npc_state(catalog)
    state = revise(state, country_changes={i: {"owner_id": "npc-1"} for i in range(10)},
                   status="completed", phase="finished", winner="npc-1")
    store, _, controller = controller_for(state)
    batch = controller.run_until_human(store.game_id)
    assert batch.reason == "completed" and not batch.committed and store.writes == 0


def test_processing_limit_preserves_tied_battle_without_forcing_skip(catalog):
    state = npc_state(catalog, source_soldiers=2, changes={0: {"soldiers": 1}})
    state = step(state, StartAttack(source_id=state.countries[1].id, target_id=state.countries[0].id)).state
    dice = TiedDice()
    store, _, controller = controller_for(state, dice)
    batch = controller.run_until_human(store.game_id, max_actions=3)
    assert batch.reason == "processing_limit" and len(batch.committed) == store.writes == 3
    assert dice.calls == 6
    after = batch.committed[-1].state
    assert after.phase == "attacking" and after.battle == state.battle
    assert after.current_turn == state.current_turn and after.countries == state.countries
    resumed = controller.run_until_human(store.game_id, max_actions=1)
    assert resumed.reason == "processing_limit" and store.writes == 4


def test_only_committed_results_are_reported_and_uncertain_action_can_retry(catalog):
    store, _, controller = controller_for(npc_state(catalog))
    original = store.commit
    def lost_ack(receipt):
        original(receipt)
        raise PersistenceUnavailable("Simulated lost acknowledgement")
    store.commit = lost_ack
    batch = controller.run_until_human(store.game_id)
    assert batch.reason == "persistence_error" and batch.committed == ()
    assert batch.pending is not None and store.writes == 1
    recovered = controller.submit(batch.pending)
    assert recovered.npc_decision == batch.pending.decision and store.writes == 1


def test_failed_transaction_is_not_a_completed_npc_action(catalog):
    store, _, controller = controller_for(npc_state(catalog))
    before = copy.deepcopy(store.document)
    def fail(receipt):
        raise PersistenceUnavailable("Simulated database outage")
    store.commit = fail
    batch = controller.run_until_human(store.game_id)
    assert batch.reason == "persistence_error" and batch.committed == ()
    assert store.document == before and store.writes == 0


def test_conflict_yields_without_retrying_against_another_board(catalog):
    store, _, controller = controller_for(npc_state(catalog))
    def fail(receipt):
        raise RevisionConflict("Simulated competing worker")
    store.commit = fail
    batch = controller.run_until_human(store.game_id)
    assert batch.reason == "conflict" and not batch.committed and store.writes == 0


def test_last_npc_skip_stops_at_human(catalog):
    state = npc_state(catalog, soldiers=100, source_soldiers=2)
    state = revise(state, country_changes={9: {"soldiers": 1}}, current_turn=9)
    store, _, controller = controller_for(state)
    batch = controller.run_until_human(store.game_id)
    assert batch.reason == "human_turn" and len(batch.committed) == 1
    assert batch.committed[0].npc_decision.reason == "skip"
    assert batch.committed[0].state.current_turn == 0


def test_two_workers_prepare_identical_commands_without_dice(catalog):
    state = npc_state(catalog)
    store, service, controller = controller_for(state)
    from app.services.npc_service import NpcController
    other = NpcController(store, service)
    first, second = controller.prepare(store.game_id), other.prepare(store.game_id)
    assert first == second and store.writes == 0
    result = controller.submit(first)
    assert other.submit(second) == result and store.writes == 1


@pytest.mark.parametrize("budget", [0, -1, 257, True, 1.5, "3"])
def test_invalid_processing_budget_never_writes(catalog, budget):
    store, _, controller = controller_for(npc_state(catalog))
    with pytest.raises(GameRuleError):
        controller.run_until_human(store.game_id, max_actions=budget)
    assert store.writes == 0


def test_full_npc_sequence_yields_to_human_without_acting_for_them(catalog):
    state = npc_state(catalog, source_soldiers=1, changes={0: {"soldiers": 100}})
    store, _, controller = controller_for(state)
    batch = controller.run_until_human(store.game_id)
    assert batch.reason == "human_turn" and len(batch.committed) == 9
    assert [r.npc_decision.evaluation.actor_id for r in batch.committed] == [f"npc-{i}" for i in range(1, 10)]
    assert all(r.npc_decision.reason == "skip" for r in batch.committed)
    assert batch.committed[-1].state.active_player_id == "human"
    assert batch.committed[-1].state.phase == "allocating"


def test_automation_stops_immediately_after_world_conquest(catalog):
    changes = {i: {"owner_id": "npc-1"} for i in range(2, 10)}
    state = npc_state(catalog, changes=changes)
    store, _, controller = controller_for(state, FixedDice([6, 1]))
    batch = controller.run_until_human(store.game_id)
    assert batch.reason == "completed" and len(batch.committed) == 2
    assert batch.committed[-1].state.winner == "npc-1"
    assert batch.committed[-1].events[-1].type == "victory"
    assert store.writes == 2
