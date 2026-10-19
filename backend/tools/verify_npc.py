"""Labelled deterministic NPC demo. No MongoDB, .env, network or production writes.

From backend: .venv/Scripts/python.exe -m tools.verify_npc
The in-memory demonstration store is explicit test scaffolding, never a fallback.
"""
import copy
import random
from datetime import datetime, timezone

from app.engine.errors import RevisionConflict
from app.engine.game_setup import initialize_game
from app.engine.state_adapter import load_runtime
from app.models.game import GameSetupRequest
from app.models.runtime_game import RuntimeGame
from app.services.country_catalog import CountryCatalog
from app.services.game_action_service import GameActionService, replay_receipt
from app.services.npc_service import NpcController


class DemoStore:
    def __init__(self, state):
        self.document = state.model_dump(mode="json")
        self.receipts = {}

    def load_game(self, game_id):
        return copy.deepcopy(self.document) if game_id == "labelled-demo" else None

    def find_receipt(self, game_id, action_id):
        return self.receipts.get((game_id, action_id))

    def commit(self, receipt):
        key = (receipt.game_id, receipt.command.action_id)
        if key in self.receipts:
            return replay_receipt(self.receipts[key], receipt.fingerprint)
        if self.document["revision"] != receipt.command.expected_revision:
            raise RevisionConflict("Demo revision conflict")
        self.document = receipt.result.state.model_dump(mode="json")
        self.receipts[key] = receipt
        return receipt.result


class DemoDice:
    """Explicit demonstration dice injected into the engine, never the strategy."""
    def __init__(self):
        self._values = iter([6, 1])

    def roll(self):
        return next(self._values)


def main():
    initial = initialize_game(GameSetupRequest(game_name="LABELLED NPC demonstration", starting_country_id="south-africa"),
                              CountryCatalog.load(), random.Random(7))
    raw = load_runtime(initial.model_dump()).model_dump(mode="json")
    raw["turn_order"] = [player.id for player in initial.players]
    raw["current_turn"] = 1
    for index, country in enumerate(raw["countries"]):
        country.update(owner_id="npc-1" if index == 1 else "human", soldiers=6 if index == 1 else 1)
    state = RuntimeGame.model_validate(raw)
    store = DemoStore(state)
    service = GameActionService(store, DemoDice(), lambda: datetime(2026, 10, 20, 12, tzinfo=timezone.utc))
    controller = NpcController(store, service)
    print("LABELLED deterministic scenario using an explicit in-memory demonstration store.")
    print("All decisions use the shared NPC policy; only the engine receives the demonstration dice.")
    batch = controller.run_until_human("labelled-demo", max_actions=16)
    for result in batch.committed:
        decision = result.npc_decision
        print(f"\nCommitted revision {result.state.revision}: {decision.explanation}")
        for event in result.events:
            if event.type == "dice_exchange":
                print(f"  Dice {event.attacker_dice} vs {event.defender_dice}; losses {event.attacker_losses}/{event.defender_losses}")
            else:
                print(f"  Event: {event.type}")
    print(f"\nStopped: {batch.reason}; {len(batch.committed)} committed demo actions.")
    print("No database connection or production write occurred. No authentication or frontend is provided by this demo.")


if __name__ == "__main__":
    main()
