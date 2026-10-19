from app.services.game_action_service import GameActionService
from app.services.npc_service import NpcController
from phase2_helpers import FixedDice, MemoryActionStore, NOW, make_runtime, revise


def npc_state(catalog, *, soldiers=1, source_soldiers=6, changes=None, **fields):
    state = make_runtime(catalog)
    country_changes = {i: {"soldiers": soldiers} for i in range(10)}
    country_changes[1]["soldiers"] = source_soldiers
    for index, updates in (changes or {}).items():
        country_changes[index].update(updates)
    return revise(state, country_changes=country_changes, current_turn=1, **fields)


def controller_for(state, dice=None, strategy=None):
    store = MemoryActionStore(state.model_dump(mode="json"))
    service = GameActionService(store, dice if dice is not None else FixedDice(), lambda: NOW)
    return store, service, NpcController(store, service, strategy)
