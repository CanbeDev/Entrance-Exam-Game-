from app.models.actions import ActionCommand, Allocate, Allocation, EndTurn, Roll, Skip, StartAttack
from app.services.game_action_service import GameActionService
from phase2_helpers import FixedDice, MemoryActionStore, NOW, context, make_runtime, revise


def test_service_complete_match(catalog):
    """Labelled scripted scenario, not an NPC intelligence implementation."""
    state = make_runtime(catalog)
    state = revise(state, country_changes={i: {"soldiers": 100 if i == 0 else 1} for i in range(10)})
    store = MemoryActionStore(state.model_dump())
    source_id = state.countries[0].id
    exchanges = captures = allocations = 0
    for sequence in range(500):
        if state.status == "completed":
            break
        dice_values = []
        if state.phase == "allocating":
            owned = next(c for c in state.countries if c.owner_id == state.active_player_id)
            action = Allocate(allocations=(Allocation(country_id=owned.id, amount=state.pending_reinforcements),))
            allocations += 1
        elif state.active_player_id != "human":
            action = Skip()
        elif state.phase == "post_attack":
            action = EndTurn()
        elif state.phase == "attacking":
            count = min(state.country(source_id).soldiers - 1, state.country(state.battle.target_id).soldiers)
            dice_values = [6] * count + [1] * count
            action = Roll()
            exchanges += 1
        else:
            target = next(c for c in state.countries if c.owner_id != "human")
            action = StartAttack(source_id=source_id, target_id=target.id)
        before = sum(c.soldiers for c in state.countries)
        result = GameActionService(store, FixedDice(dice_values), lambda: NOW).execute(
            store.game_id, context(state), ActionCommand(action_id=f"match-{sequence}", expected_revision=state.revision, action=action))
        expected_delta = 0
        for event in result.events:
            if event.type == "allocated":
                expected_delta += event.amount
            elif event.type == "dice_exchange":
                expected_delta -= event.attacker_losses + event.defender_losses
            elif event.type == "conquered":
                expected_delta += event.amount
                captures += 1
        state = result.state
        assert sum(c.soldiers for c in state.countries) == before + expected_delta
        assert all(c.soldiers >= 1 for c in state.countries)
    assert state.status == "completed" and state.winner == "human"
    assert captures == exchanges == 9 and allocations > 0 and state.round > 1
    assert len(store.receipts) == store.writes == state.revision
