import pytest

from app.engine.actions import apply_action
from app.engine.errors import GameRuleError
from app.engine.npc.evaluation import evaluate_board, project_soldiers
from app.engine.npc.explanations import validate_decision
from app.engine.npc.strategy import NpcStrategy, SeededTieBreaker, StableTieBreaker
from app.models.actions import Allocate, EndTurn, Roll, Skip, StartAttack, StopAttack, Transfer
from npc_helpers import npc_state
from phase2_helpers import FixedDice, NOW, context, make_runtime, revise, step


def test_attack_and_factual_reason(catalog):
    state = npc_state(catalog)
    decision = NpcStrategy().decide(state)
    assert isinstance(decision.action, StartAttack)
    assert decision.action.source_id == state.countries[1].id
    assert "5 available" in decision.explanation
    assert "capture is not guaranteed" in decision.explanation
    assert "would eliminate" in decision.explanation
    validate_decision(state, context(state), decision.action, decision)


def test_skips_unprofitable_board(catalog):
    decision = NpcStrategy().decide(npc_state(catalog, soldiers=100, source_soldiers=2))
    assert isinstance(decision.action, Skip) and decision.reason == "skip"


def test_prefers_elimination_to_cheaper_non_elimination(catalog):
    # Remaining countries all belong to the human except npc-2's sole holding.
    changes = {i: {"owner_id": "human"} for i in range(10) if i not in (1, 2)}
    changes[2] = {"soldiers": 3}
    state = npc_state(catalog, source_soldiers=6, changes=changes)
    decision = NpcStrategy().decide(state)
    assert isinstance(decision.action, StartAttack)
    assert decision.action.target_id == state.countries[2].id


def test_start_and_exchange_remain_separate(catalog):
    state = npc_state(catalog)
    decision = NpcStrategy().decide(state)
    dice = FixedDice()
    selection = apply_action(state, context(state), decision.action, dice, NOW)
    assert dice.calls == 0 and selection.state.countries == state.countries
    continuation = NpcStrategy().decide(selection.state)
    assert isinstance(continuation.action, Roll)


def test_reassesses_after_actual_exchange_and_stops(catalog):
    state = npc_state(catalog, source_soldiers=3, changes={0: {"soldiers": 3}})
    state = step(state, StartAttack(source_id=state.countries[1].id, target_id=state.countries[0].id)).state
    assert isinstance(NpcStrategy().decide(state).action, Roll)  # Elimination exception at -1.
    # One loss, one tie: source 2, defenders still 3 => margin -2, unacceptable.
    after = step(state, Roll(), [1, 3, 6, 3]).state
    decision = NpcStrategy().decide(after)
    assert isinstance(decision.action, StopAttack)
    assert "1 available against 3 defenders" in decision.explanation
    assert step(after, decision.action).state.current_turn != 1


def test_tied_exchange_keeps_battle_and_reevaluates(catalog):
    state = npc_state(catalog, source_soldiers=3, changes={0: {"soldiers": 2}})
    state = step(state, StartAttack(source_id=state.countries[1].id, target_id=state.countries[0].id)).state
    before = NpcStrategy().decide(state)
    after = step(state, Roll(), [3, 3, 3, 3]).state
    decision = NpcStrategy().decide(after)
    assert isinstance(before.action, Roll) and isinstance(decision.action, Roll)
    assert after.countries == state.countries
    assert before.state_digest != decision.state_digest


def test_complete_strategic_reinforcement_allocation(catalog):
    state = npc_state(catalog, changes={2: {"owner_id": "npc-1"}}, round=2,
                      phase="allocating", pending_reinforcements=4)
    before = state.model_dump_json()
    decision = NpcStrategy().decide(state)
    assert isinstance(decision.action, Allocate)
    assert sum(item.amount for item in decision.action.allocations) == 4
    assert {item.country_id for item in decision.action.allocations} <= {state.countries[1].id, state.countries[2].id}
    assert "full 4-soldier budget" in decision.explanation
    result = step(state, decision.action)
    assert result.state.phase == "deciding" and result.state.pending_reinforcements == 0
    assert state.model_dump_json() == before


def test_beneficial_transfers_strictly_improve_and_cannot_reverse(catalog):
    state = npc_state(catalog, changes={2: {"owner_id": "npc-1", "soldiers": 6}})
    seen = set()
    transfers = 0
    for _ in range(30):
        signature = tuple(c.soldiers for c in state.countries)
        assert signature not in seen
        seen.add(signature)
        decision = NpcStrategy().decide(state)
        if not isinstance(decision.action, Transfer):
            break
        before = evaluate_board(state).potential
        after = step(state, decision.action).state
        assert evaluate_board(after).potential > before
        assert after.country(decision.action.source_id).soldiers >= 1
        assert sum(c.soldiers for c in after.countries) == sum(c.soldiers for c in state.countries)
        state = after
        transfers += 1
    assert transfers > 0 and not isinstance(NpcStrategy().decide(state).action, Transfer)


def test_post_attack_never_chooses_another_attack(catalog):
    state = npc_state(catalog, phase="post_attack", attack_used=True)
    decision = NpcStrategy().decide(state)
    assert isinstance(decision.action, EndTurn)


def test_policy_cannot_act_for_human_or_finished_game(catalog):
    with pytest.raises(GameRuleError):
        NpcStrategy().decide(make_runtime(catalog))
    state = npc_state(catalog)
    changes = {i: {"owner_id": "npc-1"} for i in range(10)}
    finished = revise(state, country_changes=changes, status="completed", phase="finished", winner="npc-1")
    with pytest.raises(GameRuleError):
        NpcStrategy().decide(finished)


def test_stable_and_seeded_ties_are_reproducible(catalog):
    assert StableTieBreaker().choose(["a", "b"], "context") == "a"
    assert SeededTieBreaker(42).choose(["a", "b"], "context") == SeededTieBreaker(42).choose(["a", "b"], "context")
    changes = {i: {"owner_id": "human"} for i in range(10) if i != 1}
    state = npc_state(catalog, source_soldiers=8, changes=changes)
    decisions = [NpcStrategy(SeededTieBreaker(seed)).decide(state) for seed in range(10)]
    assert all(d.tie_break_used for d in decisions)
    assert len({d.action.target_id for d in decisions}) > 1
    assert NpcStrategy().decide(state) == NpcStrategy().decide(state)
    assert NpcStrategy(SeededTieBreaker(42)).decide(state) == NpcStrategy(SeededTieBreaker(42)).decide(state)


@pytest.mark.parametrize("seed", range(8))
def test_injected_ties_never_choose_inferior_attack(catalog, seed):
    state = npc_state(catalog)
    decision = NpcStrategy(SeededTieBreaker(seed)).decide(state)
    chosen = next(a for a in decision.evaluation.attacks if a.source_id == decision.action.source_id and a.target_id == decision.action.target_id)
    assert (chosen.wins, chosen.eliminates, chosen.score) == max((a.wins, a.eliminates, a.score) for a in decision.evaluation.attacks if a.acceptable)


@pytest.mark.parametrize("index", range(1, 10))
def test_all_nine_npcs_use_the_same_policy_and_engine(catalog, index):
    state = npc_state(catalog)
    state = revise(state, country_changes={1: {"soldiers": 1}, index: {"soldiers": 6}}, current_turn=index)
    decision = NpcStrategy().decide(state)
    assert decision.evaluation.actor_id == f"npc-{index}"
    assert isinstance(decision.action, StartAttack)
    assert step(state, decision.action).state.phase == "attacking"


@pytest.mark.parametrize("seed", [True, "42", 1.5, None])
def test_invalid_tie_seed(seed):
    with pytest.raises(GameRuleError):
        SeededTieBreaker(seed)


def test_reinforcements_strengthen_a_world_conquest_opportunity(catalog):
    changes = {i: {"owner_id": "npc-1"} for i in range(2, 10)}
    changes[0] = {"soldiers": 8}
    state = npc_state(catalog, changes=changes, round=2, phase="allocating", pending_reinforcements=18)
    decision = NpcStrategy().decide(state)
    strongest_id = state.countries[1].id
    assert any(a.country_id == strongest_id and a.amount >= 3 for a in decision.action.allocations)
    assert decision.projected_potential[0] == 1  # A viable world-conquest opportunity.
    assert "Projected best-attack score" in decision.explanation
