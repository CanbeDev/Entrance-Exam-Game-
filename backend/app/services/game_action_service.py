import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Protocol

from app.engine.actions import apply_action
from app.engine.battle import DiceProvider, RandomDice
from app.engine.errors import ActionIdConflict, GameRuleError, RevisionConflict
from app.engine.state_adapter import load_runtime
from app.models.actions import ActionCommand, ActorContext, FrozenModel
from app.models.events import ActionResult


class ActionReceipt(FrozenModel):
    game_id: str
    fingerprint: str
    actor: ActorContext
    command: ActionCommand
    result: ActionResult


def command_fingerprint(actor: ActorContext, command: ActionCommand) -> str:
    content = {"actor": actor.model_dump(mode="json"), "command": command.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def replay_receipt(receipt: ActionReceipt, fingerprint: str) -> ActionResult:
    if receipt.fingerprint != fingerprint:
        raise ActionIdConflict("Action ID was already used with different content")
    return receipt.result


class ActionStore(Protocol):
    def find_receipt(self, game_id: str, action_id: str) -> ActionReceipt | None: ...
    def load_game(self, game_id: str) -> dict | None: ...
    def commit(self, receipt: ActionReceipt) -> ActionResult: ...


class GameActionService:
    """Trusted local interface only. Actor context is not account authentication."""
    def __init__(self, repository: ActionStore, dice: DiceProvider | None = None,
                 clock: Callable[[], datetime] | None = None):
        self._repository = repository
        self._dice = dice if dice is not None else RandomDice()
        self._clock = clock if clock is not None else lambda: datetime.now(timezone.utc)

    def execute(self, game_id: str, actor: ActorContext, command: ActionCommand) -> ActionResult:
        # Revalidate even model_copy/model_construct callers before using their data.
        actor = ActorContext.model_validate(actor.model_dump())
        command = ActionCommand.model_validate(command.model_dump())
        fingerprint = command_fingerprint(actor, command)
        receipt = self._repository.find_receipt(game_id, command.action_id)
        if receipt is not None:
            return replay_receipt(receipt, fingerprint)
        document = self._repository.load_game(game_id)
        if document is None:
            raise GameRuleError("Game not found")
        state = load_runtime(document)
        if state.revision != command.expected_revision:
            # Another identical submission may have committed after our first read.
            receipt = self._repository.find_receipt(game_id, command.action_id)
            if receipt is not None:
                return replay_receipt(receipt, fingerprint)
            raise RevisionConflict("Game revision changed; reload before submitting a new action")
        result = apply_action(state, actor, command.action, self._dice, self._clock())
        receipt = ActionReceipt(game_id=game_id, fingerprint=fingerprint, actor=actor,
                                command=command, result=result)
        return self._repository.commit(receipt)
