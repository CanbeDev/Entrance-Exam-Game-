from datetime import datetime

from app.engine.battle import DiceProvider, conquest_reward, roll_exchange
from app.engine.errors import GameRuleError
from app.engine.reinforcements import validate_allocation
from app.engine.transfers import validate_transfer
from app.engine.turns import advance_turn
from app.models.actions import ActorContext, Allocate, EndTurn, Roll, Skip, StartAttack, StopAttack, Transfer
from app.models.events import ActionResult, GameEvent
from app.models.runtime_game import RuntimeGame


def apply_action(state: RuntimeGame, actor: ActorContext, action,
                 dice: DiceProvider, now: datetime) -> ActionResult:
    """Compute a fully validated successor. No mutation, I/O, or hidden clock.

    Dice are consumed only after actor, phase and battle legality checks.
    Random outcomes are returned as factual events, not regenerated on commit.
    """
    if state.status != "active":
        raise GameRuleError("The game is completed")
    player = next((p for p in state.players if p.id == actor.player_id), None)
    if player is None or player.kind != actor.kind or actor.player_id != state.active_player_id:
        raise GameRuleError("Only the active participant can act")
    allowed = {
        "allocating": (Allocate,),
        "deciding": (Transfer, StartAttack, Skip),
        "attacking": (Roll, StopAttack),
        "post_attack": (Transfer, EndTurn),
    }
    if not isinstance(action, allowed[state.phase]):
        raise GameRuleError("Action is not permitted in this phase")

    data = state.model_dump()
    data["countries"] = list(data["countries"])
    by_id = {c["id"]: c for c in data["countries"]}
    events = []

    def emit(event_type, **values):
        events.append(GameEvent(type=event_type, actor_id=actor.player_id,
                                round=state.round, turn_sequence=state.turn_sequence, **values))

    if isinstance(action, Allocate):
        validate_allocation(state, action)
        for allocation in action.allocations:
            by_id[allocation.country_id]["soldiers"] += allocation.amount
        data.update(phase="deciding", pending_reinforcements=0)
        emit("allocated", allocations=action.allocations, amount=state.pending_reinforcements)
    elif isinstance(action, Transfer):
        source, target = state.country(action.source_id), state.country(action.target_id)
        validate_transfer(source, target, actor.player_id, action.amount)
        by_id[source.id]["soldiers"] -= action.amount
        by_id[target.id]["soldiers"] += action.amount
        emit("transferred", source_id=source.id, target_id=target.id, amount=action.amount)
    elif isinstance(action, StartAttack):
        source, target = state.country(action.source_id), state.country(action.target_id)
        if source.owner_id != actor.player_id or target.owner_id == actor.player_id or source.soldiers < 2:
            raise GameRuleError("Attack requires an owned source with two soldiers and an enemy target")
        data.update(phase="attacking", attack_used=True,
                    battle={"source_id": source.id, "target_id": target.id})
        emit("attack_started", source_id=source.id, target_id=target.id)
    elif isinstance(action, Roll):
        source = state.country(state.battle.source_id)
        target = state.country(state.battle.target_id)
        exchange = roll_exchange(source.soldiers, target.soldiers, dice)
        by_id[source.id]["soldiers"] -= exchange.attacker_losses
        by_id[target.id]["soldiers"] -= exchange.defender_losses
        emit("dice_exchange", source_id=source.id, target_id=target.id,
             attacker_dice=exchange.attacker_dice, defender_dice=exchange.defender_dice,
             attacker_losses=exchange.attacker_losses, defender_losses=exchange.defender_losses)
        if by_id[target.id]["soldiers"] == 0:
            reward = conquest_reward(target.base_soldier_value)
            by_id[target.id].update(owner_id=actor.player_id, soldiers=reward)
            data.update(phase="post_attack", battle=None)
            emit("conquered", source_id=source.id, target_id=target.id, amount=reward)
            if not any(c["owner_id"] == target.owner_id for c in data["countries"]):
                emit("eliminated", player_id=target.owner_id)
            if all(c["owner_id"] == actor.player_id for c in data["countries"]):
                data.update(status="completed", phase="finished", winner=actor.player_id)
                emit("victory", player_id=actor.player_id)
        elif by_id[source.id]["soldiers"] == 1:
            data.update(phase="post_attack", battle=None)
            emit("attack_failed", source_id=source.id, target_id=target.id)
    elif isinstance(action, (Skip, StopAttack, EndTurn)):
        if isinstance(action, StopAttack):
            emit("attack_stopped", source_id=state.battle.source_id, target_id=state.battle.target_id)
        emit("turn_ended")
        next_turn = advance_turn(state, data["countries"])
        data.update(current_turn=next_turn.index, round=next_turn.round,
                    turn_sequence=state.turn_sequence + 1, battle=None, attack_used=False,
                    pending_reinforcements=next_turn.reinforcements,
                    phase="allocating" if next_turn.reinforcements else "deciding")
        events.append(GameEvent(type="turn_started", actor_id=next_turn.player_id,
                                round=next_turn.round, turn_sequence=data["turn_sequence"],
                                amount=next_turn.reinforcements))
    data.update(revision=state.revision + 1, updated_at=now)
    return ActionResult(state=RuntimeGame.model_validate(data), events=tuple(events))
