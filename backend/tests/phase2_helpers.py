import copy
import random
from datetime import datetime, timezone

from app.engine.actions import apply_action
from app.engine.game_setup import initialize_game
from app.engine.state_adapter import load_runtime
from app.models.actions import ActorContext
from app.models.game import GameSetupRequest
from app.models.runtime_game import RuntimeGame

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


class FixedDice:
    def __init__(self, values=()):
        self.values = iter(values)
        self.calls = 0

    def roll(self):
        self.calls += 1
        return next(self.values)


def make_runtime(catalog):
    initial = initialize_game(GameSetupRequest(game_name="Labelled Phase 2 test scenario",
                                              starting_country_id="south-africa"), catalog, random.Random(7))
    data = load_runtime(initial.model_dump()).model_dump()
    data["turn_order"] = [p.id for p in initial.players]
    return RuntimeGame.model_validate(data)


def revise(state, *, country_changes=None, **fields):
    data = state.model_dump()
    countries = list(data["countries"])
    for index, changes in (country_changes or {}).items():
        countries[index].update(changes)
    data["countries"] = countries
    data.update(fields)
    return RuntimeGame.model_validate(data)


def context(state):
    player = next(p for p in state.players if p.id == state.active_player_id)
    return ActorContext(player_id=player.id, kind=player.kind)


def step(state, action, values=()):
    return apply_action(state, context(state), action, FixedDice(values), NOW)


class MemoryActionStore:
    """Service contract double, not evidence of real MongoDB atomicity."""
    def __init__(self, document, game_id="0" * 24):
        self.game_id = game_id
        self.document = copy.deepcopy(document)
        self.receipts = {}
        self.writes = 0

    def load_game(self, game_id):
        return copy.deepcopy(self.document) if game_id == self.game_id else None

    def find_receipt(self, game_id, action_id):
        return self.receipts.get((game_id, action_id))

    def commit(self, receipt):
        from app.engine.errors import RevisionConflict
        from app.services.game_action_service import replay_receipt
        existing = self.find_receipt(receipt.game_id, receipt.command.action_id)
        if existing:
            return replay_receipt(existing, receipt.fingerprint)
        if self.document.get("revision", 0) != receipt.command.expected_revision:
            raise RevisionConflict("Simulated stale revision")
        self.document.update(receipt.result.state.model_dump(mode="json"))
        self.receipts[(receipt.game_id, receipt.command.action_id)] = receipt
        self.writes += 1
        return receipt.result
