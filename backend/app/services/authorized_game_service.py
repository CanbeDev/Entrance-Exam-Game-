import hashlib
import json
import re
from datetime import datetime, timezone

from app.engine.errors import GameRuleError, RevisionConflict
from app.engine.game_setup import initialize_game
from app.engine.state_adapter import load_runtime
from app.models.actions import ActionCommand, ActorContext
from app.models.auth import Principal
from app.models.game import GameSetupRequest
from app.models.game_access import access_from_document, runtime_payload
from app.security.config import SecuritySettings
from app.security.errors import SecurityError
from app.services.country_catalog import CountryCatalog
from app.services.game_action_service import GameActionService
from app.services.npc_service import NpcController


class AuthorizedGameService:
    """Account authorization facade; engine actors remain game-local participants."""
    def __init__(self, store, settings: SecuritySettings, clock=None, dice=None, catalog=None, setup_rng=None):
        self.store = store
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.dice = dice
        self.catalog = catalog if catalog is not None else CountryCatalog.load()
        self.setup_rng = setup_rng

    def _principal(self, principal):
        self.settings.require_auth_writes()
        actual = self.store.authorize(principal.session_hash, self.clock(), self.settings.idle_seconds)
        if actual.user_id != principal.user_id or actual.auth_version != principal.auth_version:
            raise SecurityError(401, "authentication_required")
        return actual

    def _owned(self, principal, game_id):
        principal = self._principal(principal)
        record = self.store.load_owned_game(game_id, principal, self.clock(), self.settings.idle_seconds)
        return principal, record

    def _actions(self, principal, game_id, access):
        scoped = self.store.action_store(principal, game_id, self.clock, self.settings.idle_seconds,
                                         enabled=self.settings.gameplay_writes_enabled, expected_access=access)
        return scoped, GameActionService(scoped, self.dice, self.clock)

    def _rate(self, principal, game_id):
        key = hashlib.sha256(f"gameplay:{principal.user_id}:{game_id}".encode()).hexdigest()
        now = self.clock()
        if not self.store.consume_limit(key, self.settings.gameplay_limit, 60, now):
            raise SecurityError(429, "rate_limited", retry_after=60 - int(now.timestamp()) % 60)

    def create_game(self, principal: Principal, request: GameSetupRequest, key: str):
        principal = self._principal(principal)
        self.settings.require_gameplay_writes()
        if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", key):
            raise SecurityError(422, "invalid_idempotency_key")
        request = GameSetupRequest.model_validate(request.model_dump())
        self._rate(principal, "create")
        fingerprint = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        initial = initialize_game(request, self.catalog, self.setup_rng).model_dump()
        initial["created_at"] = self.clock()
        state = load_runtime(initial)
        return self.store.create_owned_game(principal, state, key, fingerprint, self.clock(), self.settings.idle_seconds)

    def list_games(self, principal: Principal, *, status=None, query="", cursor=None, limit=20):
        principal = self._principal(principal)
        if status not in {None, "waiting", "active", "completed"} or type(limit) is not int or not 1 <= limit <= 100:
            raise SecurityError(422, "invalid_game_filter")
        if not isinstance(query, str) or len(query) > 100:
            raise SecurityError(422, "invalid_game_filter")
        return self.store.list_owned_games(principal, status=status, query=query, cursor=cursor, limit=limit,
                                           now=self.clock(), idle_seconds=self.settings.idle_seconds)

    def human_action(self, principal: Principal, game_id: str, command: ActionCommand):
        principal, record = self._owned(principal, game_id)
        game_id = str(record["_id"])
        self.settings.require_gameplay_writes()
        command = ActionCommand.model_validate(command.model_dump())
        access = access_from_document(record)
        state = load_runtime(runtime_payload(record))
        human = next((p for p in state.players if p.id == access.human_player_id and p.kind == "human"), None)
        if human is None:
            raise SecurityError(403, "invalid_human_binding")
        self._rate(principal, game_id)
        scoped, actions = self._actions(principal, game_id, access)
        if command.action_id.startswith("npc-"):
            # Existing human receipts retain their exact fingerprints/replay path.
            historical = scoped.find_receipt(game_id, command.action_id)
            if historical is None or historical.actor.kind != "human":
                raise SecurityError(422, "reserved_action_id")
        return actions.execute(game_id, ActorContext(player_id=human.id, kind="human"), command)

    def npc_step(self, principal: Principal, game_id: str, expected_revision: int):
        principal, record = self._owned(principal, game_id)
        game_id = str(record["_id"])
        self.settings.require_gameplay_writes()
        if type(expected_revision) is not int or expected_revision < 0:
            raise SecurityError(422, "invalid_revision")
        self._rate(principal, game_id)
        scoped, actions = self._actions(principal, game_id, access_from_document(record))
        # Retain the access tuple observed at facade entry, including on replay.
        scoped.load_game(game_id)
        saved = self.store.find_npc_result(principal, game_id, expected_revision, self.clock(), self.settings.idle_seconds)
        if saved is not None:
            return saved
        state = load_runtime(runtime_payload(record))
        if state.revision != expected_revision:
            raise RevisionConflict("Game revision changed")
        controller = NpcController(scoped, actions)
        submission = controller.prepare(game_id)
        if submission is None:
            raise GameRuleError("No active NPC action")
        if submission.command.expected_revision != expected_revision:
            raise RevisionConflict("Game revision changed")
        return controller.submit(submission)

    def events(self, game_id: str, after_revision=0, limit=20):
        from bson import ObjectId
        from bson.errors import InvalidId
        from app.services.public_game_service import public_event_page
        if (type(after_revision) is not int or after_revision < 0
                or type(limit) is not int or not 1 <= limit <= 100):
            raise SecurityError(422, "invalid_event_cursor")
        try:
            game_id = str(ObjectId(game_id))
        except (InvalidId, TypeError):
            raise SecurityError(404, "game_not_found") from None
        return public_event_page(self.store.public_events(game_id, after_revision, limit), after_revision, limit)
