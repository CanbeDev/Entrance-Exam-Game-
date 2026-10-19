from typing import Literal

from app.engine.errors import ActionIdConflict, GameRuleError, PersistenceUnavailable, RevisionConflict
from app.engine.npc.strategy import NpcStrategy
from app.engine.state_adapter import load_runtime
from app.models.actions import ActorContext, ActionCommand, FrozenModel
from app.models.events import ActionResult
from app.models.npc import NpcSubmission
from app.services.game_action_service import ActionStore, GameActionService


class NpcBatch(FrozenModel):
    committed: tuple[ActionResult, ...]
    reason: Literal["human_turn", "completed", "processing_limit", "conflict", "persistence_error"]
    pending: NpcSubmission | None = None


class NpcController:
    """Trusted local orchestration, not authentication or a public API.

    All writes still go through GameActionService and the existing repository gate.
    Persisted outcomes only are returned in committed. Pending is an uncommitted
    proposal to retry unchanged after uncertain persistence, never a completed move.
    """
    def __init__(self, repository: ActionStore, action_service: GameActionService,
                 strategy: NpcStrategy | None = None):
        self._repository = repository
        self._actions = action_service
        self._strategy = strategy if strategy is not None else NpcStrategy()

    def _load(self, game_id):
        document = self._repository.load_game(game_id)
        if document is None:
            raise GameRuleError("Game not found")
        return load_runtime(document)

    def prepare(self, game_id: str) -> NpcSubmission | None:
        state = self._load(game_id)
        if state.status == "completed":
            return None
        player = next(p for p in state.players if p.id == state.active_player_id)
        if player.kind == "human":
            return None
        decision = self._strategy.decide(state)
        command = ActionCommand(action_id=f"npc-{decision.strategy_version}-{state.turn_sequence}-{state.revision}",
                                expected_revision=state.revision, action=decision.action)
        return NpcSubmission(game_id=game_id, actor=ActorContext(player_id=player.id, kind="npc"),
                             command=command, decision=decision)

    def submit(self, submission: NpcSubmission) -> ActionResult:
        submission = NpcSubmission.model_validate(submission.model_dump())
        if submission.actor.kind != "npc":
            raise GameRuleError("NPC controller cannot act for a human")
        return self._actions.execute(submission.game_id, submission.actor, submission.command,
                                     npc_decision=submission.decision)

    def run_until_human(self, game_id: str, *, max_actions: int = 32) -> NpcBatch:
        if type(max_actions) is not int or not 1 <= max_actions <= 256:
            raise GameRuleError("Processing budget must be an integer between 1 and 256")
        committed = []
        for _ in range(max_actions):
            submission = None
            try:
                submission = self.prepare(game_id)
                if submission is None:
                    state = self._load(game_id)
                    return NpcBatch(committed=tuple(committed), reason="completed" if state.status == "completed" else "human_turn")
                result = self.submit(submission)
            except (RevisionConflict, ActionIdConflict):
                return NpcBatch(committed=tuple(committed), reason="conflict")
            except PersistenceUnavailable:
                return NpcBatch(committed=tuple(committed), reason="persistence_error", pending=submission)
            committed.append(result)
            if result.state.status == "completed":
                return NpcBatch(committed=tuple(committed), reason="completed")
            next_player = next(p for p in result.state.players if p.id == result.state.active_player_id)
            if next_player.kind == "human":
                return NpcBatch(committed=tuple(committed), reason="human_turn")
        return NpcBatch(committed=tuple(committed), reason="processing_limit")
