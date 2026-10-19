import pytest
from pydantic import ValidationError

from app.engine.npc.evaluation import evaluate_board, project_soldiers, state_digest
from app.engine.npc.strategy import NpcStrategy
from npc_helpers import npc_state
from phase2_helpers import revise


def option(board, source, target):
    return next(a for a in board.attacks if a.source_id == source and a.target_id == target)


def test_entire_board_is_observed_without_mutation(catalog):
    state = npc_state(catalog)
    before = state.model_dump_json()
    board = evaluate_board(state)
    assert len(board.countries) == len(board.participants) == 10
    assert len(board.attacks) == 9
    assert board.actor_id == "npc-1"
    assert {c.id for c in board.countries} == {c.id for c in state.countries}
    assert sum(p.soldiers for p in board.participants) == sum(c.soldiers for c in state.countries)
    assert state.model_dump_json() == before
    with pytest.raises(ValidationError):
        board.countries[0].soldiers = 100
    assert state_digest(state) == state_digest(state)
    assert state_digest(project_soldiers(state, {state.countries[1].id: 1})) != state_digest(state)


def test_all_owned_sources_and_enemy_targets_have_no_geography_filter(catalog):
    state = npc_state(catalog, changes={2: {"owner_id": "npc-1"}})
    board = evaluate_board(state)
    assert len(board.attacks) == 2 * 8
    assert all(a.source_id != a.target_id for a in board.attacks)
    assert all(a.income_gain == a.income_denial == 2 for a in board.attacks)
    eliminated = next(p for p in board.participants if p.id == "npc-2")
    assert eliminated.countries == eliminated.reinforcement_income == 0


def test_precise_score_components(catalog):
    state = npc_state(catalog)
    a = option(evaluate_board(state), state.countries[1].id, state.countries[0].id)
    assert a.available == 5 and a.defenders == 1 and a.margin == 4
    expected = (4 * a.margin + 3 * a.reward + 12 + 4 * (a.income_gain + a.income_denial)
                + 24 * int(a.eliminates) + 80 * int(a.wins) + a.opponent_power_bonus
                + a.urgency_bonus - 8 * max(0, 1 - a.margin) - a.exposure_cost)
    assert a.score == expected and a.acceptable
    assert a.opponent_income == 2


@pytest.mark.parametrize("margin,acceptable", [(-2, False), (-1, True), (0, True), (1, True)])
def test_elimination_risk_preference_is_not_absolute_margin_one(catalog, margin, acceptable):
    state = npc_state(catalog, soldiers=1, source_soldiers=3, changes={0: {"soldiers": 2 - margin}})
    a = option(evaluate_board(state), state.countries[1].id, state.countries[0].id)
    assert a.eliminates and a.margin == margin and a.acceptable == acceptable


@pytest.mark.parametrize("margin,acceptable", [(-3, False), (-2, True), (-1, True), (0, True), (1, True)])
def test_world_conquest_can_justify_risk_but_not_unbounded_losses(catalog, margin, acceptable):
    changes = {i: {"owner_id": "npc-1"} for i in range(2, 10)}
    changes[0] = {"soldiers": 2 - margin}
    state = npc_state(catalog, source_soldiers=3, changes=changes)
    a = option(evaluate_board(state), state.countries[1].id, state.countries[0].id)
    assert a.wins and a.margin == margin and a.acceptable == acceptable


def test_enemy_strength_changes_exposure_and_score(catalog):
    weak = npc_state(catalog)
    strong = revise(weak, country_changes={9: {"soldiers": 25}})
    a = option(evaluate_board(weak), weak.countries[1].id, weak.countries[0].id)
    b = option(evaluate_board(strong), strong.countries[1].id, strong.countries[0].id)
    assert b.exposure_cost > a.exposure_cost and b.score < a.score
    assert evaluate_board(strong).defensive_exposure > evaluate_board(weak).defensive_exposure


def test_reinforcement_income_and_turn_order_are_recorded(catalog):
    state = npc_state(catalog, changes={2: {"owner_id": "human"}})
    board = evaluate_board(state)
    human = next(p for p in board.participants if p.id == "human")
    assert human.countries == 2 and human.reinforcement_income == 4 and human.turn_distance == 9
    a = option(board, state.countries[1].id, state.countries[0].id)
    assert a.opponent_income == 4 and not a.eliminates


def test_decision_and_all_evidence_containers_are_immutable(catalog):
    decision = NpcStrategy().decide(npc_state(catalog))
    with pytest.raises(ValidationError):
        decision.explanation = "Invented outcome"
    with pytest.raises(ValidationError):
        decision.evaluation.attacks[0].score = 999
