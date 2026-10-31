"""Offline narration against actual committed engine receipts, never Atlas/Groq."""
import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock
from types import SimpleNamespace

import pytest

from app.models.actions import EndTurn, Roll, StartAttack
from app.security.errors import SecurityError
from app.services.commentary_service import CommentaryService
from app.services.groq_commentary import GroqNarrator, NarrationUnavailable
from npc_helpers import npc_state
from phase2_helpers import FixedDice, NOW, make_runtime, revise
from test_phase4_services import command, owned_document, seed_principal, service_for


class MemoryCommentaryRepository:
    """Atomic claim contract double; not evidence of actual MongoDB durability."""
    def __init__(self):
        self.documents, self.tokens = {}, {}
        self.lock = RLock()
        self.reads = self.claims = self.finishes = 0
        self.fail_claim = self.fail_finish = False

    def get(self, game_id, revision):
        with self.lock:
            self.reads += 1
            return deepcopy(self.documents.get((game_id, revision)))

    def claim(self, game_id, revision, document, token):
        with self.lock:
            self.claims += 1
            key = (game_id, revision)
            if key in self.documents:
                return False
            self.documents[key], self.tokens[key] = deepcopy(document), token
            if self.fail_claim:
                raise SecurityError(503, "commentary_storage_unavailable")
            return True

    def finish(self, game_id, revision, document, token):
        with self.lock:
            self.finishes += 1
            key = (game_id, revision)
            if self.fail_finish or self.tokens.get(key) != token or self.documents[key]["status"] != "pending":
                raise SecurityError(503, "commentary_storage_unavailable")
            self.documents[key].update(deepcopy(document))
            self.tokens.pop(key)


class Narrator:
    def __init__(self, reason=None):
        self.reason, self.calls = reason, []

    async def generate(self, facts):
        self.calls.append(deepcopy(facts))
        if self.reason:
            raise NarrationUnavailable(self.reason)
        return "Tension hangs over the battlefield as a fierce clash unfolds."


def battle(catalog, *, npc=False, games=None, store=None, principal=None):
    if games is None:
        store, games = service_for(catalog, dice=FixedDice([6, 1] * 60))
        principal = seed_principal(store)
    state = (npc_state(catalog) if npc else revise(make_runtime(catalog),
             country_changes={0: {"soldiers": 3}, 1: {"soldiers": 1}}))
    game_id = str(owned_document(store, principal, state)["_id"])
    if npc:
        games.npc_step(principal, game_id, 0)
        result = games.npc_step(principal, game_id, 1)
    else:
        source, target = state.countries[:2]
        games.human_action(principal, game_id, command(StartAttack(source_id=source.id, target_id=target.id)))
        result = games.human_action(principal, game_id, command(Roll(), revision=1, action_id="human-roll"))
    assert any(event.type == "dice_exchange" for event in result.events)
    return store, games, principal, game_id, result


def service(games, *, repository=None, narrator=None, clock=lambda: NOW, max_concurrent=2):
    repository = repository if repository is not None else MemoryCommentaryRepository()
    narrator = narrator if narrator is not None else Narrator()
    return CommentaryService(games, repository, narrator, clock=clock, max_concurrent=max_concurrent)


@pytest.mark.parametrize("npc", [False, True], ids=["human", "npc"])
def test_success_is_grounded_in_committed_dice_losses_conquest_and_elimination(catalog, npc):
    store, games, principal, game_id, result = battle(catalog, npc=npc)
    before = deepcopy((store.games, store.receipts))
    commentary = service(games)
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    dice = next(event for event in result.events if event.type == "dice_exchange")
    names = {country.id: country.name for country in result.state.countries}
    assert answer.status == "ready" and answer.source == "groq"
    assert answer.facts.actor_kind == ("npc" if npc else "human")
    assert answer.facts.attacker == names[dice.source_id]
    assert answer.facts.defender == names[dice.target_id]
    assert answer.facts.attacker_dice == dice.attacker_dice
    assert answer.facts.defender_dice == dice.defender_dice
    assert answer.facts.attacker_losses == dice.attacker_losses
    assert answer.facts.defender_losses == dice.defender_losses
    assert answer.facts.conquered == any(event.type == "conquered" for event in result.events)
    assert answer.facts.conquered and answer.facts.eliminated
    assert answer.text == "Tension hangs over the battlefield as a fierce clash unfolds."
    assert "attacker dice" not in answer.text and "soldier losses" not in answer.text
    context = answer.facts.model_dump(mode="json")
    context.update(attacker_dice_count=len(dice.attacker_dice), defender_dice_count=len(dice.defender_dice))
    assert commentary.narrator.calls == [context]
    assert (store.games, store.receipts) == before
    assert commentary.read(game_id, result.state.revision) == answer


def test_public_read_without_generation_is_read_only_and_returns_actual_facts(catalog):
    store, games, _, game_id, result = battle(catalog)
    commentary = service(games)
    before = deepcopy((store.games, store.receipts, store.sessions, store.limits))
    answer = commentary.read(game_id, result.state.revision)
    assert answer.status == "not_generated" and answer.source == "deterministic"
    assert commentary.narrator.calls == []
    assert commentary.repository.documents == {}
    assert (store.games, store.receipts, store.sessions, store.limits) == before


@pytest.mark.parametrize("count", [5, 20])
def test_more_than_three_dice_keep_original_pair_order_and_losses(catalog, count):
    attacker = [6, 2, 5, 1, 4] * (count // 5)
    defender = [1, 6, 3, 2, 4] * (count // 5)
    store, games = service_for(catalog, dice=FixedDice(attacker + defender))
    principal = seed_principal(store)
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": count + 2}, 1: {"soldiers": count}})
    game_id = str(owned_document(store, principal, state)["_id"])
    games.human_action(principal, game_id, command(StartAttack(
        source_id=state.countries[0].id, target_id=state.countries[1].id)))
    result = games.human_action(principal, game_id, command(Roll(), revision=1, action_id="large-exchange"))
    commentary = service(games)
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert answer.facts.attacker_dice == tuple(attacker)
    assert answer.facts.defender_dice == tuple(defender)
    assert answer.facts.attacker_losses == answer.facts.defender_losses == 2 * (count // 5)
    assert answer.facts.conquered is False
    assert "attacker dice" not in answer.text
    payload = commentary.narrator.calls[0]
    assert payload["attacker_dice"] == attacker[:12] and payload["attacker_dice_count"] == count
    assert payload["defender_dice"] == defender[:12] and payload["defender_dice_count"] == count


def test_missing_local_key_persists_fallback_without_opening_a_provider_client(catalog):
    _, games, principal, game_id, result = battle(catalog)
    commentary = service(games, narrator=GroqNarrator(None))
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert answer.status == "fallback" and answer.source == "deterministic"
    assert answer.reason == "not_configured"
    assert commentary.read(game_id, result.state.revision) == answer
    assert asyncio.run(commentary.generate(principal, game_id, result.state.revision)) == answer
    assert commentary.repository.claims == commentary.repository.finishes == 1


@pytest.mark.parametrize("reason", ["provider_timeout", "provider_rate_limited", "provider_unavailable", "invalid_output"])
def test_provider_failure_persists_safe_fallback_without_retries(catalog, reason):
    store, games, principal, game_id, result = battle(catalog)
    before = deepcopy((store.games, store.receipts))
    commentary = service(games, narrator=Narrator(reason))
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert answer.status == "fallback" and answer.reason == reason
    assert answer.source == "deterministic" and "attacker dice" in answer.text
    assert "Tension" not in answer.text
    for _ in range(3):
        assert asyncio.run(commentary.generate(principal, game_id, result.state.revision)) == answer
    assert len(commentary.narrator.calls) == 1
    assert (store.games, store.receipts) == before


@pytest.mark.parametrize("failure", [TimeoutError, RuntimeError])
def test_unexpected_provider_error_and_total_deadline_are_sanitized(catalog, failure):
    _, games, principal, game_id, result = battle(catalog)
    class BrokenNarrator:
        async def generate(self, facts):
            raise failure("NEVER_EXPOSE_SECRET_OR_PROVIDER_ERROR")
    commentary = service(games, narrator=BrokenNarrator())
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert answer.reason == ("provider_timeout" if failure is TimeoutError else "provider_unavailable")
    assert "NEVER_EXPOSE" not in answer.model_dump_json()


def test_provider_cannot_mutate_authoritative_receipts_or_grounding(catalog):
    store, games, principal, game_id, result = battle(catalog)
    before = deepcopy((store.games, store.receipts))
    class MutatingNarrator:
        async def generate(self, facts):
            facts["attacker_dice"].append(99)
            facts["defender_losses"] = 999
            return "Tension hangs over the battlefield as a fierce clash unfolds."
    commentary = service(games, narrator=MutatingNarrator())
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert 99 not in answer.facts.attacker_dice and answer.facts.defender_losses != 999
    assert (store.games, store.receipts) == before


def test_concurrent_same_battle_and_restarted_services_allow_one_provider_call(catalog):
    _, games, principal, game_id, result = battle(catalog)
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        narrator = Narrator()
        original = narrator.generate
        async def blocked(facts):
            entered.set()
            await release.wait()
            return await original(facts)
        narrator.generate = blocked
        commentary = service(games, narrator=narrator)
        restarted = service(games, repository=commentary.repository, narrator=narrator)
        first = asyncio.create_task(commentary.generate(principal, game_id, result.state.revision))
        await asyncio.wait_for(entered.wait(), 2)
        admitted_counts = deepcopy(games.store.limits)
        duplicates = await asyncio.gather(*[
            (commentary if index % 2 else restarted).generate(principal, game_id, result.state.revision)
            for index in range(12)])
        assert all(answer.status == "pending" for answer in duplicates)
        assert games.store.limits == admitted_counts
        release.set()
        answer = await first
        assert answer.status == "ready"
        assert await restarted.generate(principal, game_id, result.state.revision) == answer
        assert games.store.limits == admitted_counts
        assert len(narrator.calls) == 1
        assert commentary.repository.claims == 1
    asyncio.run(run())


def test_different_battles_have_bounded_inflight_capacity_and_no_hidden_queue(catalog):
    store, games, principal, game_id, result = battle(catalog)
    other = [battle(catalog, games=games, store=store, principal=principal) for _ in range(2)]
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        narrator = Narrator()
        original = narrator.generate
        active = 0
        async def blocked(facts):
            nonlocal active
            active += 1
            if active == 2:
                entered.set()
            await release.wait()
            return await original(facts)
        narrator.generate = blocked
        commentary = service(games, narrator=narrator)
        first = asyncio.create_task(commentary.generate(principal, game_id, result.state.revision))
        second = asyncio.create_task(commentary.generate(principal, other[0][3], other[0][4].state.revision))
        await asyncio.wait_for(entered.wait(), 2)
        with pytest.raises(SecurityError) as error:
            await commentary.generate(principal, other[1][3], other[1][4].state.revision)
        assert error.value.status == 429 and error.value.code == "commentary_capacity_limited"
        assert commentary.repository.claims == 2
        release.set()
        answers = await asyncio.gather(first, second)
        assert all(answer.status == "ready" for answer in answers)
        assert len(narrator.calls) == 2
    asyncio.run(run())


@pytest.mark.parametrize("bucket", ["minute", "hour", "account"])
def test_durable_rate_buckets_enforce_provider_spending_caps(catalog, bucket):
    store, games, principal, game_id, _ = battle(catalog)
    now = [NOW]
    commentary = service(games, clock=lambda: now[0])
    allowed = {"minute": 10, "hour": 60, "account": 20}[bucket]
    for index in range(allowed):
        if bucket == "hour":
            now[0] = NOW + timedelta(minutes=index // 2)
        elif bucket == "account":
            now[0] = NOW + timedelta(minutes=index)
        caller = SimpleNamespace(user_id=f"account-{index}") if bucket == "hour" else principal
        commentary._rate(caller, f"{index:024x}" if bucket == "hour" else game_id)
    if bucket == "hour":
        now[0] = NOW + timedelta(minutes=30)
    elif bucket == "account":
        now[0] = NOW + timedelta(minutes=20)
    restarted = service(games, clock=lambda: now[0])
    with pytest.raises(SecurityError) as error:
        restarted._rate(principal, game_id)
    assert error.value.code == "commentary_rate_limited"
    assert error.value.status == 429 and 0 < error.value.retry_after <= 3600
    assert store.limits


@pytest.mark.parametrize("failure", ["claim", "finish"])
def test_uncertain_storage_does_not_enable_followup_billing(catalog, failure):
    _, games, principal, game_id, result = battle(catalog)
    commentary = service(games)
    setattr(commentary.repository, "fail_" + failure, True)
    with pytest.raises(SecurityError):
        asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert len(commentary.narrator.calls) == (0 if failure == "claim" else 1)
    previous = len(commentary.narrator.calls)
    restarted = service(games, repository=commentary.repository, narrator=commentary.narrator,
                        clock=lambda: NOW + timedelta(seconds=31))
    answer = asyncio.run(restarted.generate(principal, game_id, result.state.revision))
    assert answer.status == "fallback" and answer.reason == "interrupted"
    assert len(commentary.narrator.calls) == previous
    assert commentary.repository.claims == 1
    assert commentary.repository.get(game_id, result.state.revision)["status"] == "pending"


def test_stale_pending_get_is_read_only_and_never_reclaimed(catalog):
    _, games, principal, game_id, result = battle(catalog)
    commentary = service(games)
    base = commentary.read(game_id, result.state.revision)
    pending = {**base.model_dump(mode="json"), "status": "pending", "reason": "in_progress",
               "claimed_at": NOW - timedelta(days=1)}
    commentary.repository.claim(game_id, result.state.revision, pending, "synthetic-claim")
    before = deepcopy(commentary.repository.documents)
    answer = commentary.read(game_id, result.state.revision)
    assert answer.status == "fallback" and answer.reason == "interrupted"
    assert commentary.repository.documents == before
    assert asyncio.run(commentary.generate(principal, game_id, result.state.revision)) == answer
    assert commentary.narrator.calls == []


def test_stored_commentary_from_other_evidence_is_never_displayed(catalog):
    _, games, _, game_id, result = battle(catalog)
    commentary = service(games)
    base = commentary.read(game_id, result.state.revision)
    altered = base.model_dump(mode="json")
    altered["facts"]["attacker_losses"] = 999
    commentary.repository.documents[(game_id, result.state.revision)] = altered
    with pytest.raises(SecurityError, match="^commentary_evidence_mismatch$"):
        commentary.read(game_id, result.state.revision)


@pytest.mark.parametrize("game,revision", [("bad", 2), ("0" * 24, 0), ("0" * 24, True)])
def test_invalid_public_identity_is_rejected_without_generation(catalog, game, revision):
    _, games, _, _, _ = battle(catalog)
    commentary = service(games)
    with pytest.raises(SecurityError):
        commentary.read(game, revision)
    assert commentary.narrator.calls == []


def test_nonbattle_receipt_and_unknown_revision_do_not_trigger_provider(catalog):
    _, games, principal, game_id, result = battle(catalog)
    commentary = service(games)
    for revision in [1, result.state.revision + 1]:
        with pytest.raises(SecurityError) as error:
            asyncio.run(commentary.generate(principal, game_id, revision))
        assert error.value.code == "battle_not_found"
    assert commentary.narrator.calls == [] and commentary.repository.claims == 0


def test_tied_dice_preserve_zero_losses_and_do_not_invent_conquest(catalog):
    store, games = service_for(catalog, dice=FixedDice([3] * 10))
    principal = seed_principal(store)
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": 7}, 1: {"soldiers": 5}})
    game_id = str(owned_document(store, principal, state)["_id"])
    games.human_action(principal, game_id, command(StartAttack(
        source_id=state.countries[0].id, target_id=state.countries[1].id)))
    result = games.human_action(principal, game_id, command(Roll(), revision=1, action_id="all-tied"))
    before = deepcopy((store.games, store.receipts))
    commentary = service(games)
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert answer.facts.attacker_dice == answer.facts.defender_dice == (3,) * 5
    assert answer.facts.attacker_losses == answer.facts.defender_losses == 0
    assert answer.facts.conquered is False and answer.facts.eliminated == ()
    assert "soldier losses" not in answer.text
    assert "conquered" not in answer.text and "eliminated" not in answer.text
    assert (store.games, store.receipts) == before


def test_later_game_revisions_cannot_change_historical_narration(catalog):
    store, games, principal, game_id, result = battle(catalog)
    commentary = service(games)
    original = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    games.human_action(principal, game_id, command(EndTurn(), revision=result.state.revision,
                                                 action_id="after-battle"))
    assert store.games[game_id]["revision"] == result.state.revision + 1
    restarted = service(games, repository=commentary.repository, narrator=commentary.narrator)
    assert restarted.read(game_id, result.state.revision) == original
    assert asyncio.run(restarted.generate(principal, game_id, result.state.revision)) == original
    assert len(commentary.narrator.calls) == 1


def test_cancellation_after_claim_preserves_identity_and_prevents_rebilling(catalog):
    store, games, principal, game_id, result = battle(catalog)
    async def run():
        entered = asyncio.Event()
        calls = []
        class CancelledNarrator:
            async def generate(self, facts):
                calls.append(deepcopy(facts))
                entered.set()
                await asyncio.Event().wait()
        commentary = service(games, narrator=CancelledNarrator(), max_concurrent=1)
        task = asyncio.create_task(commentary.generate(principal, game_id, result.state.revision))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert commentary.repository.get(game_id, result.state.revision)["status"] == "pending"
        restarted = service(games, repository=commentary.repository, narrator=commentary.narrator,
                            clock=lambda: NOW + timedelta(seconds=31))
        answer = await restarted.generate(principal, game_id, result.state.revision)
        assert answer.status == "fallback" and answer.reason == "interrupted"
        assert len(calls) == 1 and commentary.repository.claims == 1
        # Cancellation must also release capacity for a different battle.
        another = battle(catalog, games=games, store=store, principal=principal)
        commentary.narrator = Narrator()
        assert (await commentary.generate(principal, another[3], another[4].state.revision)).status == "ready"
    asyncio.run(run())


@pytest.mark.parametrize("operation", ["read", "generate"])
def test_commentary_read_failure_never_dispatches_provider(catalog, operation, monkeypatch):
    _, games, principal, game_id, result = battle(catalog)
    commentary = service(games)
    def unavailable(*args):
        raise SecurityError(503, "commentary_storage_unavailable")
    monkeypatch.setattr(commentary.repository, "get", unavailable)
    with pytest.raises(SecurityError, match="^commentary_storage_unavailable$"):
        if operation == "read":
            commentary.read(game_id, result.state.revision)
        else:
            asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert commentary.narrator.calls == [] and commentary.repository.claims == 0


def daily_bucket(store, label, now=NOW, count=0):
    key = hashlib.sha256(("commentary:" + label).encode()).hexdigest()
    identifier = (key, 86400, int(now.timestamp()) // 86400)
    store.limits[identifier] = count
    return identifier


@pytest.mark.parametrize("scope,limit", [("global", 100), ("game", 30)])
def test_exact_daily_allowance_survives_service_restart_and_denies_the_next_admission(catalog, scope, limit):
    store, games, principal, game_id, _ = battle(catalog)
    now = [NOW]
    commentary = service(games, clock=lambda: now[0])
    for index in range(limit):
        # Keep existing hour/minute/account limits below their own ceilings.
        now[0] = NOW + timedelta(minutes=index * 2)
        caller = SimpleNamespace(user_id=f"daily-account-{index}")
        target = f"{index + 1:024x}" if scope == "global" else game_id
        commentary._rate(caller, target)
    restarted = service(games, clock=lambda: now[0] + timedelta(minutes=2))
    with pytest.raises(SecurityError) as denied:
        restarted._rate(SimpleNamespace(user_id="last-account"), game_id)
    assert denied.value.status == 429 and denied.value.code == "commentary_rate_limited"
    label = "global-day" if scope == "global" else "game-day:" + game_id
    key = hashlib.sha256(("commentary:" + label).encode()).hexdigest()
    assert store.limits[(key, 86400, int(NOW.timestamp()) // 86400)] == limit + 1


@pytest.mark.parametrize("scope,limit", [("global", 100), ("game", 30)])
def test_daily_admission_resets_at_utc_midnight_with_offset_aware_clock(catalog, scope, limit):
    store, games, principal, game_id, _ = battle(catalog)
    # Both local representations straddle midnight UTC, not midnight local time.
    offset = timezone(timedelta(hours=2))
    now = [datetime(2026, 10, 31, 1, 59, 59, tzinfo=offset)]
    label = "global-day" if scope == "global" else "game-day:" + game_id
    previous = daily_bucket(store, label, now[0], limit)
    commentary = service(games, clock=lambda: now[0])
    with pytest.raises(SecurityError):
        commentary._rate(principal, game_id)
    now[0] += timedelta(seconds=1)
    restarted = service(games, clock=lambda: now[0])
    restarted._rate(principal, game_id)
    key = hashlib.sha256(("commentary:" + label).encode()).hexdigest()
    assert store.limits[previous] == limit + 1
    assert store.limits[(key, 86400, int(now[0].timestamp()) // 86400)] == 1


@pytest.mark.parametrize("scope,limit", [("global", 100), ("game", 30)])
def test_concurrent_final_daily_allowance_can_admit_only_one(catalog, scope, limit):
    store, games, principal, game_id, _ = battle(catalog)
    label = "global-day" if scope == "global" else "game-day:" + game_id
    daily_bucket(store, label, count=limit - 1)
    def attempt(index):
        instance = service(games)  # Independent processes/services share only storage.
        try:
            instance._rate(SimpleNamespace(user_id=f"parallel-{index}"), game_id)
            return True
        except SecurityError as error:
            assert error.status == 429
            return False
    with ThreadPoolExecutor(max_workers=8) as executor:
        granted = list(executor.map(attempt, range(8)))
    assert sum(granted) == 1


@pytest.mark.parametrize("scope,limit", [("global", 100), ("game", 30)])
def test_exhausted_daily_limit_persists_fallback_without_provider_or_repeated_charges(catalog, scope, limit):
    store, games, principal, game_id, result = battle(catalog)
    label = "global-day" if scope == "global" else "game-day:" + game_id
    daily_bucket(store, label, count=limit)
    commentary = service(games)
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert answer.status == "fallback" and answer.reason == "admission_limited"
    assert answer.source == "deterministic" and "attacker dice" in answer.text
    assert commentary.narrator.calls == []
    counts = deepcopy(store.limits)
    restarted = service(games, repository=commentary.repository, narrator=commentary.narrator)
    assert asyncio.run(restarted.generate(principal, game_id, result.state.revision)) == answer
    assert restarted.read(game_id, result.state.revision) == answer
    assert store.limits == counts


def test_failed_provider_admission_consumes_daily_counters_once(catalog):
    store, games, principal, game_id, result = battle(catalog)
    commentary = service(games, narrator=Narrator("provider_unavailable"))
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert answer.status == "fallback"
    for label in ("global-day", "game-day:" + game_id):
        key = hashlib.sha256(("commentary:" + label).encode()).hexdigest()
        assert store.limits[(key, 86400, int(NOW.timestamp()) // 86400)] == 1
    counts = deepcopy(store.limits)
    assert asyncio.run(commentary.generate(principal, game_id, result.state.revision)) == answer
    assert store.limits == counts and len(commentary.narrator.calls) == 1


def test_claim_race_loser_returns_existing_record_without_consuming_any_allowance(catalog):
    store, games, principal, game_id, result = battle(catalog)
    commentary = service(games)
    before = deepcopy(store.limits)
    original_claim = commentary.repository.claim
    def another_caller_wins(game, revision, document, token):
        assert original_claim(game, revision, document, token)
        return False
    commentary.repository.claim = another_caller_wins
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert answer.status == "pending"
    assert commentary.narrator.calls == [] and store.limits == before


def test_multiple_rolls_in_one_attack_have_distinct_commentary_records(catalog):
    store, games = service_for(catalog, dice=FixedDice([3] * 20))
    principal = seed_principal(store)
    state = revise(make_runtime(catalog), country_changes={0: {"soldiers": 7}, 1: {"soldiers": 5}})
    game_id = str(owned_document(store, principal, state)["_id"])
    games.human_action(principal, game_id, command(StartAttack(
        source_id=state.countries[0].id, target_id=state.countries[1].id)))
    first = games.human_action(principal, game_id, command(Roll(), revision=1, action_id="exchange-one"))
    second = games.human_action(principal, game_id, command(Roll(), revision=2, action_id="exchange-two"))
    assert first.state.phase == second.state.phase == "attacking"
    assert sum(event.type == "dice_exchange" for event in first.events) == 1
    assert sum(event.type == "dice_exchange" for event in second.events) == 1
    commentary = service(games)
    answers = [asyncio.run(commentary.generate(principal, game_id, revision)) for revision in (2, 3)]
    assert [answer.action_id for answer in answers] == ["exchange-one", "exchange-two"]
    assert len(commentary.narrator.calls) == 2 and len(commentary.repository.documents) == 2
