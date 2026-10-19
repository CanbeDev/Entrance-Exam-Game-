import random
from typing import Protocol, Sequence, TypeVar

from app.engine.errors import GameRuleError
from app.engine.npc.evaluation import evaluate_board, project_soldiers, state_digest
from app.engine.npc.explanations import explain
from app.models.actions import Allocate, Allocation, EndTurn, Roll, Skip, StartAttack, StopAttack, Transfer
from app.models.npc import NpcDecision

T = TypeVar("T")


class TieBreaker(Protocol):
    identity: str
    def choose(self, options: Sequence[T], context: str) -> T: ...


class StableTieBreaker:
    identity = "stable"

    def choose(self, options, context):
        return options[0]


class SeededTieBreaker:
    """Stateless, context-seeded policy randomness; never the battle RNG."""
    def __init__(self, seed: int):
        if type(seed) is not int:
            raise GameRuleError("NPC tie-break seed must be an integer")
        self.identity = f"seeded:{seed}"

    def choose(self, options, context):
        return random.Random(f"{self.identity}:{context}").choice(options)


class NpcStrategy:
    def __init__(self, tie_breaker: TieBreaker | None = None):
        self._ties = tie_breaker if tie_breaker is not None else StableTieBreaker()

    def decide(self, state) -> NpcDecision:
        player = next(p for p in state.players if p.id == state.active_player_id)
        if state.status != "active" or player.kind != "npc":
            raise GameRuleError("NPC policy requires an active NPC turn")
        board = evaluate_board(state)
        digest = state_digest(state)
        used_tie = False

        def pick(items, rank, key, label):
            nonlocal used_tie
            best = max(rank(item) for item in items)
            tied = sorted((item for item in items if rank(item) == best), key=key)
            used_tie |= len(tied) > 1
            return self._ties.choose(tied, f"{digest}:{label}")

        if state.phase == "allocating":
            projected = state
            amounts = {}
            for unit in range(state.pending_reinforcements):
                options = []
                for country in projected.countries:
                    if country.owner_id == player.id:
                        candidate = project_soldiers(projected, {country.id: 1})
                        options.append((country.id, candidate, evaluate_board(candidate).potential))
                country_id, projected, _ = pick(options, lambda item: item[2], lambda item: item[0], f"allocation-{unit}")
                amounts[country_id] = amounts.get(country_id, 0) + 1
            action = Allocate(allocations=tuple(Allocation(country_id=key, amount=value) for key, value in sorted(amounts.items())))
        elif state.phase == "attacking":
            locked = next(a for a in board.attacks if a.source_id == state.battle.source_id and a.target_id == state.battle.target_id)
            action = Roll() if locked.acceptable else StopAttack()
        else:
            transfers = self._transfers(state, board)
            if transfers:
                action, _ = pick(transfers, lambda item: item[1], lambda item: (item[0].source_id, item[0].target_id, item[0].amount), "transfer")
            elif state.phase == "post_attack":
                action = EndTurn()
            else:
                attacks = [a for a in board.attacks if a.acceptable]
                if attacks:
                    option = pick(attacks, lambda a: (a.wins, a.eliminates, a.score), lambda a: (a.source_id, a.target_id), "attack")
                    action = StartAttack(source_id=option.source_id, target_id=option.target_id)
                else:
                    action = Skip()
        projected_potential = None
        if isinstance(action, Allocate):
            changes = {item.country_id: item.amount for item in action.allocations}
            projected_potential = evaluate_board(project_soldiers(state, changes)).potential
        elif isinstance(action, Transfer):
            changes = {action.source_id: -action.amount, action.target_id: action.amount}
            projected_potential = evaluate_board(project_soldiers(state, changes)).potential
        reason, explanation = explain(action, board, state.battle, projected_potential)
        return NpcDecision(state_digest=digest, action=action, evaluation=board, reason=reason,
                           explanation=explanation, tie_breaker=self._ties.identity, tie_break_used=used_tie,
                           projected_potential=projected_potential)

    @staticmethod
    def _transfers(state, board):
        """Finite candidate set and strictly increasing integer potential prevent cycles."""
        owned = sorted((c for c in state.countries if c.owner_id == state.active_player_id), key=lambda c: c.id)
        enemies = [c for c in state.countries if c.owner_id != state.active_player_id]
        strongest = max((c.soldiers - 1 for c in enemies), default=0)
        options = []
        for source in owned:
            for target in owned:
                if source.id == target.id:
                    continue
                amounts = {1, source.soldiers - 1, source.soldiers // 2,
                           (source.soldiers - target.soldiers) // 2, strongest - target.soldiers}
                for enemy in enemies:
                    for margin in (1, 0, -1, -2):
                        amounts.add(enemy.soldiers + margin + 1 - target.soldiers)
                for amount in sorted(amounts):
                    if not 1 <= amount < source.soldiers:
                        continue
                    projected = project_soldiers(state, {source.id: -amount, target.id: amount})
                    potential = evaluate_board(projected).potential
                    if potential > board.potential:
                        options.append((Transfer(source_id=source.id, target_id=target.id, amount=amount), potential))
        return options
