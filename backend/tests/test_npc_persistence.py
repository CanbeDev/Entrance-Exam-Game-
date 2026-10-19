import copy

import pytest
from bson import BSON, ObjectId

from app.engine.errors import GameplayWritesDisabled, PersistenceUnavailable
from app.models.actions import StartAttack
from app.repositories.action_repository import MongoActionRepository
from app.services.game_action_service import GameActionService
from app.services.npc_service import NpcController
from npc_helpers import npc_state
from phase2_helpers import FixedDice, NOW, step
from test_phase2_repository import database_for


@pytest.mark.parametrize("repeat_transaction", [False, True])
def test_atomic_decision_receipt_and_retry_preserve_actual_rolls(catalog, repeat_transaction):
    state = npc_state(catalog, source_soldiers=2, changes={0: {"soldiers": 1}})
    state = step(state, StartAttack(source_id=state.countries[1].id, target_id=state.countries[0].id)).state
    game_id, database, client = database_for(state)
    client.repeat = repeat_transaction
    repository = MongoActionRepository(client, database, gameplay_writes_enabled=True)
    dice = FixedDice([3, 3])
    controller = NpcController(repository, GameActionService(repository, dice, lambda: NOW))
    submission = controller.prepare(game_id)
    result = controller.submit(submission)
    assert dice.calls == 2 and result.npc_decision == submission.decision
    saved = repository.find_receipt(game_id, submission.command.action_id)
    assert saved.result == result and controller.submit(submission) == result
    assert dice.calls == 2 and len(database["game_action_receipts"].docs) == 1
    assert result.events[0].attacker_dice == (3,)
    assert "npc_decision" not in repository.load_game(game_id)
    BSON.encode(next(iter(database["game_action_receipts"].docs.values())))


def test_evidence_rolls_back_with_state_and_receipt(catalog):
    state = npc_state(catalog)
    game_id, database, client = database_for(state)
    before = copy.deepcopy(database["games"].docs)
    database["game_action_receipts"].fail_insert = True
    repository = MongoActionRepository(client, database, gameplay_writes_enabled=True)
    controller = NpcController(repository, GameActionService(repository))
    batch = controller.run_until_human(game_id)
    assert batch.reason == "persistence_error" and batch.committed == ()
    assert database["games"].docs == before and database["game_action_receipts"].docs == {}


def test_new_npc_controller_cannot_enable_repository_writes(catalog):
    game_id, database, client = database_for(npc_state(catalog))
    repository = MongoActionRepository(client, database)
    controller = NpcController(repository, GameActionService(repository))
    with pytest.raises(GameplayWritesDisabled):
        controller.run_until_human(game_id)
    assert client.sessions == 0 and database["games"].docs[ObjectId(game_id)]["revision"] == 0
