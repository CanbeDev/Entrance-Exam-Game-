"""Separate, owner-requested narration of immutable committed battle receipts.

There is deliberately no import/call from authoritative mutation services.
Durable claims are never retried, including after a process restart.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import secrets
import threading

from bson import ObjectId
from bson.errors import InvalidId
from starlette.concurrency import run_in_threadpool

from app.models.commentary import BattleCommentary, BattleFacts
from app.security.errors import SecurityError
from app.services.groq_commentary import NarrationUnavailable
from app.services.public_game_service import _receipt


def factual_summary(facts: BattleFacts) -> str:
    def dice(values):
        shown = ", ".join(str(value) for value in values[:12])
        return shown if len(values) <= 12 else f"{shown}, ... ({len(values)} dice total; full rolls in battle details)"
    result = (f"{facts.attacker} attacks {facts.defender}: attacker dice [{dice(facts.attacker_dice)}], "
              f"defender dice [{dice(facts.defender_dice)}]; soldier losses {facts.attacker_losses} "
              f"for the attacker and {facts.defender_losses} for the defender")
    if facts.conquered:
        result += f"; {facts.defender} is conquered"
    if facts.eliminated:
        eliminated = ", ".join(facts.eliminated)
        result += "; eliminated participants: " + (eliminated if len(eliminated) <= 400
            else f"{len(facts.eliminated)} (see committed battle details)")
    return result + "."


class CommentaryService:
    def __init__(self, games, repository, narrator, *, clock=None, max_concurrent=2, capacity=None):
        self.games, self.repository, self.narrator = games, repository, narrator
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.slots = threading.BoundedSemaphore(max_concurrent)
        self.capacity = capacity

    def _battle(self, game_id, revision):
        try:
            game_id = str(ObjectId(game_id))
        except (InvalidId, TypeError):
            raise SecurityError(404, "game_not_found") from None
        if type(revision) is not int or revision < 1:
            raise SecurityError(422, "invalid_revision")
        rows = self.games.store.public_events(game_id, revision - 1, 1)
        if not rows:
            raise SecurityError(404, "battle_not_found")
        receipt = _receipt(rows[0])
        if receipt.game_id != game_id or receipt.result.state.revision != revision:
            raise SecurityError(404, "battle_not_found")
        exchanges = [event for event in receipt.result.events if event.type == "dice_exchange"]
        if len(exchanges) != 1:
            raise SecurityError(404, "battle_not_found")
        event = exchanges[0]
        state = receipt.result.state
        countries = {country.id: country.name for country in state.countries}
        participants = {player.id: countries[player.starting_country_id] for player in state.players}
        if (event.source_id not in countries or event.target_id not in countries
                or event.actor_id != receipt.actor.player_id
                or not event.attacker_dice or not event.defender_dice
                or any(type(die) is not int or not 1 <= die <= 6 for die in (*event.attacker_dice, *event.defender_dice))):
            raise SecurityError(503, "battle_evidence_unavailable")
        facts = BattleFacts(attacker=countries[event.source_id], defender=countries[event.target_id],
            attacker_dice=event.attacker_dice, defender_dice=event.defender_dice,
            attacker_losses=event.attacker_losses, defender_losses=event.defender_losses,
            conquered=any(item.type == "conquered" and item.target_id == event.target_id for item in receipt.result.events),
            eliminated=tuple(participants.get(item.player_id, "Participant") for item in receipt.result.events if item.type == "eliminated"),
            round=event.round, actor_kind=receipt.actor.kind)
        return BattleCommentary(game_id=game_id, revision=revision, action_id=receipt.command.action_id,
            status="not_generated", source="deterministic", text=factual_summary(facts), reason=None, facts=facts)

    def _stored(self, base, document):
        if document is None:
            return base
        public = {key: document[key] for key in BattleCommentary.model_fields if key in document}
        result = BattleCommentary.model_validate(public)
        if (result.game_id, result.revision, result.action_id, result.facts) != (base.game_id, base.revision, base.action_id, base.facts):
            raise SecurityError(503, "commentary_evidence_mismatch")
        if result.status == "pending":
            claimed = document.get("claimed_at")
            if not isinstance(claimed, datetime):
                raise SecurityError(503, "commentary_evidence_mismatch")
            claimed = claimed.replace(tzinfo=timezone.utc) if claimed.tzinfo is None else claimed
            if (self.clock() - claimed).total_seconds() >= 30:
                return base.model_copy(update={"status": "fallback", "reason": "interrupted"})
        return result

    def read(self, game_id, revision):
        base = self._battle(game_id, revision)
        return self._stored(base, self.repository.get(base.game_id, revision))

    def _authorize(self, principal, game_id):
        # Reuse the existing fresh-session and owned-game access boundary.
        return self.games._owned(principal, game_id)[0]

    def _rate(self, principal, game_id):
        now = self.clock()
        # Durable existing TTL buckets bound spend across workers and restarts.
        for label, limit, seconds in (("global-minute", 10, 60), ("global-hour", 60, 3600),
                                     ("account:" + principal.user_id, 20, 3600),
                                     ("global-day", 100, 86400), ("game-day:" + game_id, 30, 86400)):
            key = hashlib.sha256(("commentary:" + label).encode()).hexdigest()
            if not self.games.store.consume_limit(key, limit, seconds, now):
                raise SecurityError(429, "commentary_rate_limited", retry_after=seconds - int(now.timestamp()) % seconds)

    async def generate(self, principal, game_id, revision):
        return await self._generate(game_id, revision, lambda: self._authorize(principal, game_id))

    async def generate_internal(self, policies, game_id, revision, action_id, *, before_dispatch):
        """Trusted server-only adapter. No Principal/session fabrication or route."""
        if self.capacity is None:
            raise SecurityError(503, "commentary_shared_capacity_required")
        context = await run_in_threadpool(policies.authorize, game_id, revision, action_id)
        return await self._generate(game_id, revision, lambda: policies.recheck(context),
            expected_action_id=action_id, before_dispatch=before_dispatch)

    async def _generate(self, game_id, revision, authorize, *, expected_action_id=None, before_dispatch=None):
        principal = await run_in_threadpool(authorize)
        base = await run_in_threadpool(self._battle, game_id, revision)
        if expected_action_id is not None and base.action_id != expected_action_id:
            raise SecurityError(503, "commentary_evidence_mismatch")
        existing = await run_in_threadpool(self.repository.get, base.game_id, revision)
        if existing is not None:
            return self._stored(base, existing)
        slot = await run_in_threadpool(self.capacity.try_acquire) if self.capacity else None
        acquired = slot is not None if self.capacity else self.slots.acquire(blocking=False)
        if not acquired:
            raise SecurityError(429, "commentary_capacity_limited", retry_after=2)
        provider_uncertain = False
        try:
            await run_in_threadpool(authorize)
            if before_dispatch is not None:
                await run_in_threadpool(before_dispatch)
            token = secrets.token_urlsafe(24)
            pending = base.model_copy(update={"status": "pending", "reason": "in_progress"})
            claimed = await run_in_threadpool(self.repository.claim, base.game_id, revision,
                {**pending.model_dump(mode="json"), "claimed_at": self.clock()}, token)
            if not claimed:
                existing = await run_in_threadpool(self.repository.get, base.game_id, revision)
                if existing is None:
                    raise SecurityError(503, "commentary_storage_unavailable")
                return self._stored(base, existing)
            try:
                # Only the unique claim winner reserves allowance. A concurrent
                # duplicate must return the record without touching counters.
                try:
                    await run_in_threadpool(self._rate, principal, base.game_id)
                except SecurityError as error:
                    if error.status != 429:
                        raise
                    result = base.model_copy(update={"status": "fallback", "reason": "admission_limited"})
                    await run_in_threadpool(self.repository.finish, base.game_id, revision,
                        result.model_dump(mode="json"), token)
                    return result
                context = base.facts.model_dump(mode="json")
                # Input tokens stay bounded even when a legal battle has many
                # dice. Exact full arrays remain in facts and committed history.
                for name in ("attacker_dice", "defender_dice"):
                    context[name + "_count"] = len(context[name])
                    context[name] = context[name][:12]
                if before_dispatch is not None:
                    await run_in_threadpool(authorize)
                    await run_in_threadpool(before_dispatch)
                provider_uncertain = True
                lead = await asyncio.wait_for(self.narrator.generate(context), timeout=8.5)
                provider_uncertain = False
                # Keep narrative and exact results separate. Facts/dice remain
                # unchanged in their authoritative fields and existing UI.
                result = base.model_copy(update={"status": "ready", "source": "groq", "text": lead})
            except NarrationUnavailable as error:
                # Only these classified responses prove no remote call remains
                # uncertain. Other outcomes conservatively quarantine capacity.
                if error.reason in {"not_configured", "invalid_output", "provider_rate_limited"}:
                    provider_uncertain = False
                result = base.model_copy(update={"status": "fallback", "reason": error.reason})
            except SecurityError:
                # Storage/counter uncertainty keeps the durable claim closed.
                raise
            except asyncio.TimeoutError:
                result = base.model_copy(update={"status": "fallback", "reason": "provider_timeout"})
            except Exception:
                result = base.model_copy(update={"status": "fallback", "reason": "provider_unavailable"})
            result = BattleCommentary.model_validate(result.model_dump())
            await run_in_threadpool(self.repository.finish, base.game_id, revision, result.model_dump(mode="json"), token)
            return result
        finally:
            if self.capacity:
                await asyncio.shield(run_in_threadpool(self.capacity.release, slot, not provider_uncertain))
            else:
                self.slots.release()
