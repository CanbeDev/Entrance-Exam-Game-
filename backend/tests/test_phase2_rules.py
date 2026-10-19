import pytest

from app.engine.actions import apply_action
from app.engine.battle import RandomDice, conquest_reward, roll_exchange
from app.engine.errors import GameRuleError
from app.engine.turns import calculate_reinforcements
from app.models.actions import ActorContext, Allocate, Allocation, EndTurn, Roll, Skip, StartAttack, StopAttack, Transfer
from phase2_helpers import FixedDice, NOW, make_runtime, revise, step


@pytest.mark.parametrize("attack,defend,count", [(10, 2, 2), (3, 5, 2), (2, 5, 1), (9, 9, 8)])
def test_official_dice_counts(attack, defend, count):
    result = roll_exchange(attack, defend, FixedDice([6] * count + [1] * count))
    assert len(result.attacker_dice) == len(result.defender_dice) == count
    assert result.defender_losses == count and result.attacker_losses == 0


def test_official_pairing_example_and_ties():
    exchange = roll_exchange(10, 2, FixedDice([1, 4, 2, 3]))
    assert (exchange.attacker_losses, exchange.defender_losses) == (1, 1)
    tied = roll_exchange(3, 2, FixedDice([3, 6, 3, 6]))
    assert tied.attacker_losses == tied.defender_losses == 0


@pytest.mark.parametrize("value", [0, 7, True, 1.5, "6"])
def test_invalid_dice_rejected(value):
    with pytest.raises(GameRuleError):
        roll_exchange(2, 1, FixedDice([value, 1]))


@pytest.mark.parametrize("attack,defend", [(1, 5), (0, 1), (2, 0), (True, 1), (2, -1)])
def test_invalid_battle_counts(attack, defend):
    dice = FixedDice()
    with pytest.raises(GameRuleError):
        roll_exchange(attack, defend, dice)
    assert dice.calls == 0


@pytest.mark.parametrize("base,reward", [(1, 2), (2, 2), (3, 2), (4, 2), (5, 2), (6, 3), (7, 3), (8, 4), (9, 4)])
def test_rewards(base, reward):
    assert conquest_reward(base) == reward


@pytest.mark.parametrize("base", [0, 10, True, 1.5])
def test_invalid_reward(base):
    with pytest.raises(GameRuleError):
        conquest_reward(base)


@pytest.mark.parametrize("round_number,count,reward", [(1, 1, 0), (1, 3, 0), (2, 1, 2), (2, 3, 6), (3, 5, 10), (2, 0, 0)])
def test_reinforcement_formula(round_number, count, reward):
    assert calculate_reinforcements(round_number, count) == reward


def test_default_dice_range():
    dice = RandomDice()
    assert all(1 <= dice.roll() <= 6 for _ in range(100))


def test_round_boundary_and_allocation(catalog):
    state = make_runtime(catalog)
    for index in range(10):
        assert state.current_turn == index and state.round == 1
        state = step(state, Skip()).state
    assert state.current_turn == 0 and state.round == 2 and state.phase == "allocating"
    assert state.pending_reinforcements == 2 and state.turn_sequence == 10
    old = state.countries[0].soldiers
    allocated = step(state, Allocate(allocations=(Allocation(country_id=state.countries[0].id, amount=2),)))
    assert allocated.state.countries[0].soldiers == old + 2
    assert allocated.state.pending_reinforcements == 0 and allocated.state.phase == "deciding"
    with pytest.raises(GameRuleError):
        step(allocated.state, Allocate(allocations=(Allocation(country_id=state.countries[0].id, amount=2),)))


def test_eliminated_slots_skip_across_original_boundary(catalog):
    state = revise(make_runtime(catalog), country_changes={9: {"owner_id": "human"}, 1: {"owner_id": "human"}}, current_turn=8)
    state = step(state, Skip()).state
    assert state.current_turn == 0 and state.round == 2
    assert state.pending_reinforcements == 6
    state = step(state, Allocate(allocations=(Allocation(country_id=state.countries[0].id, amount=6),))).state
    state = step(state, Skip()).state
    assert state.current_turn == 2 and state.round == 2


def test_transfer_conserves_and_does_not_advance(catalog):
    state = revise(make_runtime(catalog), country_changes={1: {"owner_id": "human"}})
    before = sum(c.soldiers for c in state.countries)
    result = step(state, Transfer(source_id=state.countries[0].id, target_id=state.countries[1].id, amount=4))
    assert result.state.countries[0].soldiers == 1
    assert sum(c.soldiers for c in result.state.countries) == before
    assert result.state.current_turn == 0 and result.state.revision == 1
    assert state.countries[0].soldiers == 5


def start(state):
    return step(state, StartAttack(source_id=state.countries[0].id, target_id=state.countries[1].id)).state


def test_start_then_multiple_exchanges_then_stop(catalog):
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": 3}, 1: {"soldiers": 2}})
    initial = state.model_dump_json()
    battle = start(state)
    assert state.model_dump_json() == initial and battle.countries == state.countries
    result = step(battle, Roll(), [1, 4, 2, 3])
    assert result.state.countries[0].soldiers == 2 and result.state.countries[1].soldiers == 1
    assert result.state.phase == "attacking" and result.state.battle == battle.battle
    tied = step(result.state, Roll(), [3, 3])
    assert tied.state.countries == result.state.countries
    stopped = step(tied.state, StopAttack()).state
    assert stopped.current_turn == 1 and stopped.phase == "deciding" and stopped.battle is None
    assert stopped.countries == tied.state.countries


def test_conquest_keeps_survivors_rewards_capture_and_eliminates(catalog):
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": 10}, 1: {"soldiers": 1}})
    result = step(start(state), Roll(), [6, 1])
    assert result.state.countries[0].soldiers == 10
    assert result.state.countries[1].owner_id == "human"
    assert result.state.countries[1].soldiers == conquest_reward(state.countries[1].base_soldier_value)
    assert result.state.phase == "post_attack" and result.state.attack_used
    assert any(e.type == "eliminated" and e.player_id == "npc-1" for e in result.events)
    transferred = step(result.state, Transfer(source_id=state.countries[0].id, target_id=state.countries[1].id, amount=9)).state
    assert transferred.countries[0].soldiers == 1
    with pytest.raises(GameRuleError):
        start(transferred)
    ended = step(transferred, EndTurn()).state
    assert ended.current_turn == 2  # Eliminated npc-1 is skipped.


def test_source_reduced_to_one_keeps_territory(catalog):
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": 2}, 1: {"soldiers": 5}})
    result = step(start(state), Roll(), [1, 6])
    assert result.state.phase == "post_attack" and result.state.countries[0].soldiers == 1
    assert result.state.countries[0].owner_id == "human" and result.state.countries[1].owner_id == "npc-1"
    assert result.state.countries[1].soldiers == 5
    assert step(result.state, EndTurn()).state.current_turn == 1


def test_final_conquest_completes_immediately(catalog):
    state = make_runtime(catalog)
    changes = {i: {"owner_id": "human"} for i in range(2, 10)}
    changes[1] = {"soldiers": 1}
    state = revise(state, country_changes=changes)
    result = step(start(state), Roll(), [6, 1])
    assert result.state.status == "completed" and result.state.winner == "human"
    assert result.state.phase == "finished" and result.state.current_turn == 0
    assert result.state.countries[0].soldiers == 5
    assert result.events[-1].type == "victory"
    with pytest.raises(GameRuleError):
        step(result.state, EndTurn())


@pytest.mark.parametrize("kind", ["wrong_actor", "wrong_kind", "friendly", "source_enemy", "single_soldier", "unknown", "roll", "end", "transfer_enemy", "transfer_self", "transfer_all"])
def test_invalid_action_never_mutates_or_rolls(catalog, kind):
    state = make_runtime(catalog)
    source, target = state.countries[:2]
    actor = ActorContext(player_id="human", kind="human")
    action = StartAttack(source_id=source.id, target_id=target.id)
    if kind == "wrong_actor":
        actor = ActorContext(player_id="npc-1", kind="npc")
    elif kind == "wrong_kind":
        actor = ActorContext(player_id="human", kind="npc")
    elif kind == "friendly":
        action = StartAttack(source_id=source.id, target_id=source.id)
    elif kind == "source_enemy":
        action = StartAttack(source_id=target.id, target_id=source.id)
    elif kind == "single_soldier":
        state = revise(state, country_changes={0: {"soldiers": 1}})
    elif kind == "unknown":
        action = StartAttack(source_id=source.id, target_id="unknown")
    elif kind == "roll":
        action = Roll()
    elif kind == "end":
        action = EndTurn()
    elif kind == "transfer_enemy":
        action = Transfer(source_id=source.id, target_id=target.id, amount=1)
    elif kind == "transfer_self":
        action = Transfer(source_id=source.id, target_id=source.id, amount=1)
    else:
        state = revise(state, country_changes={1: {"owner_id": "human"}})
        action = Transfer(source_id=source.id, target_id=target.id, amount=source.soldiers)
    before = state.model_dump_json()
    dice = FixedDice()
    with pytest.raises(GameRuleError):
        apply_action(state, actor, action, dice, NOW)
    assert state.model_dump_json() == before and dice.calls == 0


@pytest.mark.parametrize("action_type", ["skip", "transfer", "start_attack", "end_turn", "allocate"])
def test_locked_battle_rejects_other_actions(catalog, action_type):
    state = start(make_runtime(catalog))
    actions = {"skip": Skip(), "transfer": Transfer(source_id=state.countries[0].id, target_id=state.countries[1].id, amount=1),
               "start_attack": StartAttack(source_id=state.countries[0].id, target_id=state.countries[2].id),
               "end_turn": EndTurn(), "allocate": Allocate(allocations=(Allocation(country_id=state.countries[0].id, amount=2),))}
    before = state.model_dump_json()
    with pytest.raises(GameRuleError):
        step(state, actions[action_type])
    assert state.model_dump_json() == before


@pytest.mark.parametrize("kind", ["under", "over", "foreign", "skip", "attack", "transfer"])
def test_pending_reinforcement_validation(catalog, kind):
    state = revise(make_runtime(catalog), round=2, phase="allocating", pending_reinforcements=2)
    country_id = state.countries[1 if kind == "foreign" else 0].id
    amount = 1 if kind == "under" else 3 if kind == "over" else 2
    action = Allocate(allocations=(Allocation(country_id=country_id, amount=amount),))
    if kind == "skip":
        action = Skip()
    elif kind == "attack":
        action = StartAttack(source_id=country_id, target_id=state.countries[1].id)
    elif kind == "transfer":
        action = Transfer(source_id=country_id, target_id=state.countries[1].id, amount=1)
    before = state.model_dump_json()
    with pytest.raises(GameRuleError):
        step(state, action)
    assert state.model_dump_json() == before


def test_split_reinforcements_among_owned_countries(catalog):
    state = revise(make_runtime(catalog), country_changes={1: {"owner_id": "human"}, 2: {"owner_id": "human"}},
                   round=2, phase="allocating", pending_reinforcements=6)
    action = Allocate(allocations=(Allocation(country_id=state.countries[0].id, amount=1),
                                   Allocation(country_id=state.countries[2].id, amount=5)))
    result = step(state, action)
    assert result.state.countries[0].soldiers == state.countries[0].soldiers + 1
    assert result.state.countries[2].soldiers == state.countries[2].soldiers + 5
    assert result.state.countries[1].soldiers == state.countries[1].soldiers
    assert sum(c.soldiers for c in result.state.countries) == sum(c.soldiers for c in state.countries) + 6


def test_recapture_rewards_base_not_accumulated_defenders(catalog):
    state = make_runtime(catalog)
    # npc-1 previously captured human's original country, but human still owns a
    # different country. Original assignments stay unchanged and are not ownership.
    state = revise(state, country_changes={0: {"owner_id": "npc-1", "soldiers": 1},
                                           1: {"owner_id": "human", "soldiers": 30}})
    battle = step(state, StartAttack(source_id=state.countries[1].id, target_id=state.countries[0].id)).state
    result = step(battle, Roll(), [6, 1])
    assert result.state.countries[0].base_soldier_value == 5
    assert result.state.countries[0].soldiers == 2
    assert result.state.countries[1].soldiers == 30


def test_npc_can_win_after_human_elimination(catalog):
    state = make_runtime(catalog)
    changes = {i: {"owner_id": "npc-1"} for i in range(2, 10)}
    changes.update({0: {"soldiers": 1}, 1: {"soldiers": 2}})
    state = revise(state, country_changes=changes, current_turn=1)
    battle = step(state, StartAttack(source_id=state.countries[1].id, target_id=state.countries[0].id)).state
    result = step(battle, Roll(), [6, 1])
    assert result.state.status == "completed" and result.state.winner == "npc-1"
    assert any(e.type == "eliminated" and e.player_id == "human" for e in result.events)


def test_bad_dice_never_mutate_battle(catalog):
    state = start(make_runtime(catalog))
    count = min(state.countries[0].soldiers - 1, state.countries[1].soldiers)
    before = state.model_dump_json()
    with pytest.raises(GameRuleError, match="dice"):
        step(state, Roll(), [7] * (count * 2))
    assert state.model_dump_json() == before
