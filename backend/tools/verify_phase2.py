"""No-write, no-network demonstration of approved gameplay transitions.

From backend: .venv/Scripts/python.exe -m tools.verify_phase2
This is a labelled deterministic scenario, not production game setup.
"""
from datetime import datetime, timezone

from app.engine.actions import apply_action
from app.engine.game_setup import initialize_game
from app.engine.state_adapter import load_runtime
from app.models.actions import ActorContext, EndTurn, Roll, StartAttack, Transfer
from app.models.game import GameSetupRequest
from app.models.runtime_game import RuntimeGame
from app.services.country_catalog import CountryCatalog


class DemonstrationDice:
    def roll(self):
        return next(self.values)

    def __init__(self):
        self.values = iter([6, 1])


def main():
    initial = initialize_game(GameSetupRequest(game_name="LABELLED Phase 2 demo", starting_country_id="south-africa"),
                              CountryCatalog.load())
    raw = load_runtime(initial.model_dump()).model_dump(mode="json")
    raw["turn_order"] = [p.id for p in initial.players]
    raw["countries"][1]["soldiers"] = 1
    state = RuntimeGame.model_validate(raw)
    source, target = state.countries[:2]
    actions = [StartAttack(source_id=source.id, target_id=target.id), Roll(),
               Transfer(source_id=source.id, target_id=target.id, amount=1), EndTurn()]
    dice = DemonstrationDice()
    print("LABELLED deterministic scenario; no database, credentials, or network used.")
    for action in actions:
        player = next(p for p in state.players if p.id == state.active_player_id)
        result = apply_action(state, ActorContext(player_id=player.id, kind=player.kind), action,
                              dice, datetime.now(timezone.utc))
        state = result.state
        print(f"{action.type}: revision={state.revision}, phase={state.phase}, round={state.round}, active={state.active_player_id}")
        for event in result.events:
            print(event.model_dump_json(exclude_none=True))
    print(f"Source soldiers: {state.country(source.id).soldiers}; captured soldiers: {state.country(target.id).soldiers}")
    print("No writes performed. For real transaction verification follow docs/phase2-verification.md.")


if __name__ == "__main__":
    main()
