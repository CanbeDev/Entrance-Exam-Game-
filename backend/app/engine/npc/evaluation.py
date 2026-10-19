import hashlib
import json

from app.engine.battle import conquest_reward
from app.models.npc import AttackEvaluation, BoardEvaluation, CountryObservation, ParticipantObservation
from app.models.runtime_game import RuntimeGame


def state_digest(state: RuntimeGame) -> str:
    content = json.dumps(state.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode()).hexdigest()


def evaluate_board(state: RuntimeGame) -> BoardEvaluation:
    """balanced-v1 integer heuristics; scores are NOT capture probabilities."""
    actor = state.active_player_id
    owned = [c for c in state.countries if c.owner_id == actor]
    enemies = [c for c in state.countries if c.owner_id != actor]
    participants = []
    for player in state.players:
        holdings = [c for c in state.countries if c.owner_id == player.id]
        participants.append(ParticipantObservation(
            id=player.id, kind=player.kind, countries=len(holdings),
            soldiers=sum(c.soldiers for c in holdings), reinforcement_income=2 * len(holdings),
            turn_distance=(state.turn_order.index(player.id) - state.current_turn) % 10))
    by_player = {p.id: p for p in participants}
    strongest = max((c.soldiers - 1 for c in enemies), default=0)
    attacks = []
    for source in sorted(owned, key=lambda c: c.id):
        for target in sorted(enemies, key=lambda c: c.id):
            available, defenders = source.soldiers - 1, target.soldiers
            margin = available - defenders
            reward = conquest_reward(target.base_soldier_value)
            opponent = by_player[target.owner_id]
            eliminates, wins = opponent.countries == 1, len(owned) == 9
            # One-for-one attrition is a deliberately labelled planning heuristic.
            projected_source = max(1, source.soldiers - defenders)
            other_threat = max((c.soldiers - 1 for c in enemies if c.id != target.id), default=0)
            source_cost = max(0, strongest - projected_source) - max(0, strongest - source.soldiers)
            exposure_cost = source_cost + max(0, other_threat - reward)
            power_bonus = min(12, opponent.soldiers // 4)
            urgency = 10 - opponent.turn_distance
            score = (4 * margin + 3 * reward + 12 + 4 * (2 + 2)
                     + 24 * int(eliminates) + 80 * int(wins)
                     + power_bonus + urgency - 8 * max(0, 1 - margin) - exposure_cost)
            risk_ok = (margin >= 1 or (eliminates and margin >= -1)
                       or (wins and margin >= -2) or (reward >= 4 and margin >= 0))
            attacks.append(AttackEvaluation(
                source_id=source.id, target_id=target.id, available=available, defenders=defenders,
                margin=margin, reward=reward, eliminates=eliminates, wins=wins,
                opponent_income=opponent.reinforcement_income, income_gain=2, income_denial=2,
                exposure_cost=exposure_cost, opponent_power_bonus=power_bonus, urgency_bonus=urgency,
                score=score, acceptable=available >= 1 and risk_ok and score > 0))
    return BoardEvaluation(actor_id=actor, revision=state.revision, turn_sequence=state.turn_sequence,
                           round=state.round,
                           countries=tuple(CountryObservation(**c.model_dump(include={"id", "name", "owner_id", "soldiers", "base_soldier_value"}))
                                           for c in sorted(state.countries, key=lambda c: c.id)),
                           participants=tuple(participants), attacks=tuple(attacks),
                           defensive_exposure=sum(max(0, strongest - c.soldiers) for c in owned),
                           concentration=sum(c.soldiers ** 2 for c in owned))


def project_soldiers(state: RuntimeGame, changes: dict[str, int]) -> RuntimeGame:
    """Hypothetical policy analysis only; never runs dice or modifies input state."""
    data = state.model_dump()
    for country in data["countries"]:
        country["soldiers"] += changes.get(country["id"], 0)
    return RuntimeGame.model_validate(data)
