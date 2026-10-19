import copy
import hashlib
import json

import pytest

from app.engine.actions import apply_action
from app.engine.errors import ActionIdConflict, GameRuleError, PersistenceUnavailable, RevisionConflict
from app.engine.npc.strategy import NpcStrategy
from app.models.actions import ActionCommand, ActorContext, Roll, Skip, StartAttack
from app.models.events import ActionResult
from app.services.game_action_service import ActionReceipt, GameActionService, command_fingerprint
from npc_helpers import controller_for, npc_state
from phase2_helpers import FixedDice, MemoryActionStore, NOW, context, make_runtime, revise, step


def test_committed_evidence_and_original_events_are_replayed(catalog):
    state = npc_state(catalog)
    store, _, controller = controller_for(state)
    submission = controller.prepare(store.game_id)
    before = copy.deepcopy(store.document)
    assert store.writes == 0 and store.document == before
    first = controller.submit(submission)
    assert first.npc_decision == submission.decision
    assert first.events[0].type == "attack_started"
    assert first.state.schema_version == 3 and "npc_decision" not in store.document
    assert controller.submit(submission) == first and store.writes == 1
    loaded = ActionReceipt.model_validate(store.receipts[(store.game_id, submission.command.action_id)].model_dump(mode="json"))
    assert loaded.result == first


@pytest.mark.parametrize("tamper", ["prose", "score", "digest", "action", "ties"])
def test_false_or_mismatched_evidence_cannot_modify_state(catalog, tamper):
    state = npc_state(catalog)
    store, service, controller = controller_for(state)
    submission = controller.prepare(store.game_id)
    data = submission.decision.model_dump(mode="json")
    if tamper == "prose":
        data["explanation"] = "This will definitely win; I rolled a six."
    elif tamper == "score":
        data["evaluation"]["attacks"][0]["score"] += 999
    elif tamper == "digest":
        data["state_digest"] = "0" * 64
    elif tamper == "action":
        data["action"] = {"type": "skip"}
    else:
        data["tie_breaker"] = "seeded:invalid"
    from app.models.npc import NpcDecision
    evidence = NpcDecision.model_validate(data)
    before = copy.deepcopy(store.document)
    with pytest.raises(GameRuleError):
        service.execute(store.game_id, submission.actor, submission.command, npc_decision=evidence)
    assert store.document == before and store.writes == 0


def test_changed_explanation_cannot_reuse_committed_action_id(catalog):
    store, service, controller = controller_for(npc_state(catalog))
    submission = controller.prepare(store.game_id)
    controller.submit(submission)
    changed = submission.decision.model_copy(update={"explanation": "Different claim"})
    with pytest.raises(ActionIdConflict):
        service.execute(store.game_id, submission.actor, submission.command, npc_decision=changed)
    assert store.writes == 1


def test_historical_human_fingerprint_and_receipt_are_unchanged(catalog):
    state = make_runtime(catalog)
    actor = context(state)
    command = ActionCommand(action_id="historical", expected_revision=0, action=Skip())
    old_content = {"actor": actor.model_dump(mode="json"), "command": command.model_dump(mode="json")}
    old_hash = hashlib.sha256(json.dumps(old_content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert command_fingerprint(actor, command) == command_fingerprint(actor, command, None) == old_hash
    result = step(state, command.action)
    document = ActionReceipt(game_id="0" * 24, fingerprint=old_hash, actor=actor, command=command, result=result).model_dump(mode="json")
    document["result"].pop("npc_decision")
    old_receipt = ActionReceipt.model_validate(document)
    assert old_receipt.result.npc_decision is None
    store = MemoryActionStore(result.state.model_dump())
    store.receipts[(store.game_id, command.action_id)] = old_receipt
    assert GameActionService(store, FixedDice()).execute(store.game_id, actor, command) == result
    assert store.writes == 0


def test_human_cannot_attach_npc_evidence(catalog):
    state = make_runtime(catalog)
    store = MemoryActionStore(state.model_dump())
    evidence = NpcStrategy().decide(npc_state(catalog))
    with pytest.raises(GameRuleError, match="Human"):
        GameActionService(store).execute(store.game_id, context(state),
            ActionCommand(action_id="human", expected_revision=0, action=Skip()), npc_decision=evidence)
    assert store.writes == 0


def test_evidence_does_not_affect_authoritative_dice_or_battle(catalog):
    state = npc_state(catalog, source_soldiers=3, changes={0: {"soldiers": 2}})
    state = step(state, StartAttack(source_id=state.countries[1].id, target_id=state.countries[0].id)).state
    dice = FixedDice([1, 4, 2, 3])
    store, _, controller = controller_for(state, dice)
    submission = controller.prepare(store.game_id)
    assert dice.calls == 0 and isinstance(submission.command.action, Roll)
    result = controller.submit(submission)
    plain = apply_action(state, context(state), Roll(), FixedDice([1, 4, 2, 3]), NOW)
    assert result.state == plain.state and result.events == plain.events and dice.calls == 4
    # Swap only participant kinds to model the same actor controlled by a human.
    raw = state.model_dump()
    raw["players"][0]["kind"] = "npc"
    raw["players"][1]["kind"] = "human"
    from app.models.runtime_game import RuntimeGame
    human_state = RuntimeGame.model_validate(raw)
    human_result = apply_action(human_state, ActorContext(player_id="npc-1", kind="human"), Roll(), FixedDice([1, 4, 2, 3]), NOW)
    assert human_result.events == result.events
    assert human_result.state.model_dump(exclude={"players"}) == result.state.model_dump(exclude={"players"})


def test_stale_proposal_cannot_commit_or_roll(catalog):
    state = npc_state(catalog)
    store, _, controller = controller_for(state)
    submission = controller.prepare(store.game_id)
    controller.submit(submission)
    # New ID prevents replay, but its stale revision is rejected.
    changed = submission.model_copy(update={"command": submission.command.model_copy(update={"action_id": "stale-new"})})
    with pytest.raises(RevisionConflict):
        controller.submit(changed)
    assert store.writes == 1


def test_evidence_fingerprint_is_versioned_separately(catalog):
    store, _, controller = controller_for(npc_state(catalog))
    submission = controller.prepare(store.game_id)
    old = command_fingerprint(submission.actor, submission.command)
    new = command_fingerprint(submission.actor, submission.command, submission.decision)
    assert old != new
    assert new == command_fingerprint(submission.actor, submission.command, submission.decision)
