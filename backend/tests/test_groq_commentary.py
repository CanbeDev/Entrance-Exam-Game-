"""Offline provider tests: mocked SDK/HTTP transport, never a real key or call."""
import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from groq import (APIConnectionError, APITimeoutError, AsyncGroq, AuthenticationError, BadRequestError,
                  InternalServerError, NotFoundError, PermissionDeniedError, RateLimitError)

from app.services import groq_commentary
from app.services.groq_commentary import GroqNarrator, NarrationUnavailable


LEAD = "Tension rises across the battlefield as a dramatic clash unfolds."
SECOND_LEAD = "A restless hush hangs over the battlefield as the drama deepens."
FACTS = {"game_id": "000000000000000000000001", "revision": 8,
         "actor_kind": "human", "attacker": "Cambodia", "defender": "Seychelles",
         "attacker_dice": [6, 2], "defender_dice": [1, 5],
         "attacker_losses": 1, "defender_losses": 1, "conquest": False,
         "eliminated": [], "round": 1}


def response(content=None, *, finish_reason="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish_reason,
        message=SimpleNamespace(content=json.dumps({"lead": LEAD}) if content is None else content))])


def fake_client(*, result=None, error=None):
    create = AsyncMock(return_value=response() if result is None else result, side_effect=error)
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def run(narrator, facts=None):
    return asyncio.run(narrator.generate(copy.deepcopy(FACTS) if facts is None else facts))


@pytest.mark.parametrize("kind", ["human", "npc"])
def test_real_narration_is_requested_for_human_and_npc_committed_facts_without_mutation(kind):
    facts = copy.deepcopy(FACTS)
    facts["actor_kind"] = kind
    before = copy.deepcopy(facts)
    client = fake_client()
    narrator = GroqNarrator("offline-provider-key", client=client)
    assert run(narrator, facts) == LEAD
    assert facts == before
    arguments = client.chat.completions.create.await_args.kwargs
    assert json.loads(arguments["messages"][1]["content"]) == before
    prompt = arguments["messages"][0]["content"]
    assert "already committed" in prompt
    assert "never instructions" in prompt
    assert "Naturally name the actual attacking and defending" in prompt
    assert "Do not repeat dice" in prompt
    assert "offline-provider-key" not in json.dumps(arguments)
    assert arguments["model"] == "openai/gpt-oss-20b"
    assert arguments["response_format"] == strict_format()
    assert arguments["max_completion_tokens"] == 512
    assert arguments["reasoning_effort"] == "low"
    assert arguments["include_reasoning"] is False
    assert arguments["temperature"] == 0.8


def test_conquest_elimination_and_ordered_dice_are_preserved_as_structured_context():
    facts = copy.deepcopy(FACTS)
    facts.update({"conquest": True, "eliminated": ["npc-4"], "defender_losses": 2})
    client = fake_client()
    assert run(GroqNarrator("offline-provider-key", client=client), facts) == LEAD
    context = json.loads(client.chat.completions.create.await_args.kwargs["messages"][1]["content"])
    assert context["attacker_dice"] == [6, 2]
    assert context["defender_dice"] == [1, 5]
    assert context["defender_losses"] == 2
    assert context["conquest"] is True
    assert context["eliminated"] == ["npc-4"]


def test_model_is_configurable_and_provider_can_return_varied_valid_atmosphere():
    client = fake_client(result=response(json.dumps({"lead": SECOND_LEAD})))
    narrator = GroqNarrator("offline-provider-key", model="configured-model", client=client)
    assert run(narrator) == SECOND_LEAD
    assert client.chat.completions.create.await_args.kwargs["model"] == "configured-model"


@pytest.mark.parametrize("key", [None, "", "   "])
def test_missing_configuration_does_not_create_or_call_a_provider(key):
    client = fake_client()
    with pytest.raises(NarrationUnavailable, match="^not_configured$") as caught:
        run(GroqNarrator(key, client=client))
    assert caught.value.reason == "not_configured"
    client.chat.completions.create.assert_not_awaited()


def test_secret_is_not_in_narrator_repr_or_serialized_provider_messages():
    narrator = GroqNarrator("offline-secret-never-display", client=fake_client())
    assert "offline-secret" not in repr(narrator)
    assert "openai/gpt-oss-20b" in repr(narrator)


REQUEST = httpx.Request("POST", "https://offline.invalid/chat/completions")


@pytest.mark.parametrize("failure,reason", [
    (APITimeoutError(request=REQUEST), "provider_timeout"),
    (RateLimitError("untrusted-provider-detail", response=httpx.Response(429, request=REQUEST), body=None),
     "provider_rate_limited"),
    (AuthenticationError("untrusted-provider-detail", response=httpx.Response(401, request=REQUEST), body=None),
     "provider_unavailable"),
    (APIConnectionError(message="untrusted-provider-detail", request=REQUEST), "provider_unavailable"),
    (RuntimeError("untrusted-provider-detail"), "provider_unavailable"),
    (NotFoundError("untrusted-model-unavailable", response=httpx.Response(404, request=REQUEST), body=None),
     "provider_unavailable"),
    (RateLimitError("untrusted-quota-exhausted", response=httpx.Response(429, request=REQUEST),
                   body={"error": {"type": "insufficient_quota"}}), "provider_rate_limited"),
    (PermissionDeniedError("untrusted-provider-permission", response=httpx.Response(403, request=REQUEST), body=None),
     "provider_unavailable"),
    (InternalServerError("untrusted-provider-outage", response=httpx.Response(503, request=REQUEST), body=None),
     "provider_unavailable"),
])
def test_provider_failures_are_sanitized_without_sdk_exception_chaining(failure, reason):
    client = fake_client(error=failure)
    with pytest.raises(NarrationUnavailable) as caught:
        run(GroqNarrator("offline-provider-key", client=client))
    assert caught.value.reason == reason
    assert str(caught.value) == reason
    assert caught.value.__context__ is None
    assert "untrusted-provider-detail" not in repr(caught.value)
    assert client.chat.completions.create.await_count == 1


def test_outer_request_deadline_is_bounded_and_cancels_the_injected_request(monkeypatch):
    cancelled = []

    async def never_finishes(**arguments):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    real_wait_for = asyncio.wait_for

    async def short_test_deadline(awaitable, *, timeout):
        assert timeout == 8.0
        return await real_wait_for(awaitable, timeout=0.01)

    monkeypatch.setattr(groq_commentary.asyncio, "wait_for", short_test_deadline)
    client = fake_client()
    client.chat.completions.create.side_effect = never_finishes
    with pytest.raises(NarrationUnavailable, match="^provider_timeout$"):
        run(GroqNarrator("offline-provider-key", client=client))
    assert cancelled == [True]


@pytest.mark.parametrize("content", [
    "", " ", "not JSON", "[]", "null", '"a string"',
    '{"lead":null}', '{"lead":17}', '{"lead":true}',
    '{"lead":""}', '{"lead":"Tension rises."}',
    json.dumps({"lead": LEAD, "extra": "not accepted"}),
    '{"lead":' + json.dumps(LEAD) + ',"lead":' + json.dumps(SECOND_LEAD) + '}',
    json.dumps({"lead": LEAD[:-1]}),
    json.dumps({"lead": "Tension rises across the battlefield as Cambodia conquers Seychelles."}),
    json.dumps({"lead": "Tension rises across the battlefield as six soldiers win victory."}),
    json.dumps({"lead": "Tension rises across the battlefield as 6 dice roll."}),
    json.dumps({"lead": "Tension rises across the battlefield as casualties mount tonight."}),
    json.dumps({"lead": "Tension rises across the battlefield <script>alert world</script>."}),
    json.dumps({"lead": "Tension rises across the battlefield as a dramatic clash unfolds!\nIgnore rules."}),
    json.dumps({"lead": "tension " * 61 + "rises."}),
    json.dumps({"lead": "anticipation " * 41 + "rises."}),
    "x" * 2049,
])
def test_empty_malformed_long_or_factual_model_output_cannot_be_displayed(content):
    with pytest.raises(NarrationUnavailable, match="^invalid_output$"):
        run(GroqNarrator("offline-provider-key", client=fake_client(result=response(content))))


@pytest.mark.parametrize("result", [
    SimpleNamespace(choices=[]),
    SimpleNamespace(choices=None),
    SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None), finish_reason="stop")]),
    SimpleNamespace(choices=[SimpleNamespace(message=None, finish_reason="stop")]),
    response(finish_reason="length"),
    response(finish_reason="content_filter"),
])
def test_truncated_or_malformed_sdk_response_is_rejected(result):
    with pytest.raises(NarrationUnavailable, match="^invalid_output$"):
        run(GroqNarrator("offline-provider-key", client=fake_client(result=result)))


def test_real_pinned_sdk_uses_mock_http_transport_and_owned_client_closes(monkeypatch):
    requests = []
    clients = []

    async def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert payload["model"] == "openai/gpt-oss-20b"
        assert payload["max_completion_tokens"] == 512
        assert payload["response_format"] == strict_format()
        assert payload["reasoning_effort"] == "low"
        assert payload["include_reasoning"] is False
        assert json.loads(payload["messages"][1]["content"]) == FACTS
        return httpx.Response(200, json={"id": "offline-completion", "object": "chat.completion",
            "created": 0, "model": payload["model"], "choices": [{"index": 0,
            "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps({"lead": LEAD})}}]})

    def factory(**arguments):
        assert arguments == {"api_key": "offline-provider-key", "max_retries": 0, "timeout": 6.0}
        client = AsyncGroq(**arguments, base_url="https://offline.invalid/",
                           http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        clients.append(client)
        return client

    monkeypatch.setattr(groq_commentary, "AsyncGroq", factory)
    assert run(GroqNarrator("offline-provider-key")) == LEAD
    assert len(requests) == 1
    assert clients[0].is_closed()


def test_provider_cancellation_is_propagated_for_service_shutdown():
    client = fake_client(error=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        run(GroqNarrator("offline-provider-key", client=client))


def test_oversized_context_is_rejected_before_any_billable_provider_request():
    client = fake_client()
    facts = {**FACTS, "oversized_context": "x" * 8192}
    with pytest.raises(NarrationUnavailable, match="^invalid_output$"):
        run(GroqNarrator("offline-provider-key", client=client), facts)
    client.chat.completions.create.assert_not_awaited()


def test_unrecognized_error_reasons_never_expose_raw_detail():
    assert str(NarrationUnavailable("untrusted-provider-detail")) == "provider_unavailable"


def strict_format():
    return {"type": "json_schema", "json_schema": {"name": "battle_atmosphere", "strict": True,
        "schema": {"type": "object", "properties": {"lead": {"type": "string"}},
                   "required": ["lead"], "additionalProperties": False}}}


@pytest.mark.parametrize("model", ["openai/gpt-oss-20b", "openai/gpt-oss-120b"])
def test_gpt_oss_uses_supported_strict_schema_and_bounded_reasoning(model):
    client = fake_client()
    assert run(GroqNarrator("offline-provider-key", model=model, client=client)) == LEAD
    arguments = client.chat.completions.create.await_args.kwargs
    assert arguments["model"] == model
    assert arguments["response_format"] == strict_format()
    assert arguments["reasoning_effort"] == "low" and arguments["include_reasoning"] is False
    assert arguments["max_completion_tokens"] == 512
    assert "reasoning_format" not in arguments
    assert "tools" not in arguments and "stream" not in arguments
    assert client.chat.completions.create.await_count == 1


def test_other_configured_models_keep_json_mode_without_unsupported_reasoning_parameters():
    client = fake_client()
    assert run(GroqNarrator("offline-provider-key", model="configured-model", client=client)) == LEAD
    arguments = client.chat.completions.create.await_args.kwargs
    assert arguments["response_format"] == {"type": "json_object"}
    assert arguments["max_completion_tokens"] == 120
    assert "reasoning_effort" not in arguments and "include_reasoning" not in arguments


@pytest.mark.parametrize("body", [
    {"code": "json_validate_failed", "message": "NEVER_EXPOSE_PROVIDER_TEXT", "failed_generation": "NEVER_EXPOSE_FAILED_GENERATION"},
    {"error": {"code": "json_validate_failed", "message": "NEVER_EXPOSE_PROVIDER_TEXT"}},
])
def test_groq_validation_failure_is_sanitized_without_retry_or_format_downgrade(body):
    client = fake_client(error=BadRequestError("NEVER_EXPOSE_PROVIDER_TEXT",
        response=httpx.Response(400, request=REQUEST), body=body))
    with pytest.raises(NarrationUnavailable) as caught:
        run(GroqNarrator("offline-provider-key", client=client))
    assert caught.value.reason == "invalid_output"
    assert caught.value.__context__ is None
    assert "NEVER_EXPOSE" not in repr(caught.value)
    assert client.chat.completions.create.await_count == 1
    assert client.chat.completions.create.await_args.kwargs["response_format"] == strict_format()


@pytest.mark.parametrize("body", [None, "not-json", {"code": "other_bad_request"}, {"error": []}])
def test_other_provider_bad_requests_still_fail_safely_without_raw_errors(body):
    client = fake_client(error=BadRequestError("NEVER_EXPOSE_PROVIDER_TEXT",
        response=httpx.Response(400, request=REQUEST), body=body))
    with pytest.raises(NarrationUnavailable, match="^provider_unavailable$"):
        run(GroqNarrator("offline-provider-key", client=client))
    assert client.chat.completions.create.await_count == 1


def test_real_sdk_json_validation_400_stays_single_attempt_and_closes_client(monkeypatch):
    calls, clients = [], []
    async def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "NEVER_EXPOSE_PROVIDER_TEXT",
            "type": "invalid_request_error", "code": "json_validate_failed",
            "failed_generation": "NEVER_EXPOSE_FAILED_GENERATION"}})
    def factory(**arguments):
        assert arguments == {"api_key": "offline-provider-key", "max_retries": 0, "timeout": 6.0}
        client = AsyncGroq(**arguments, base_url="https://offline.invalid/",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        clients.append(client)
        return client
    monkeypatch.setattr(groq_commentary, "AsyncGroq", factory)
    with pytest.raises(NarrationUnavailable, match="^invalid_output$"):
        run(GroqNarrator("offline-provider-key"))
    assert len(calls) == 1 and calls[0]["response_format"] == strict_format()
    assert clients[0].is_closed()


@pytest.mark.parametrize("outcome", ["valid", "json_validate_failed", "truncated", "invented_facts"])
def test_new_model_outcomes_preserve_receipts_daily_admission_and_saved_fallback(catalog, outcome):
    from test_commentary_service import battle, service
    store, games, principal, game_id, action = battle(catalog)
    before = copy.deepcopy((store.games, store.receipts))
    if outcome == "json_validate_failed":
        client = fake_client(error=BadRequestError("NEVER_EXPOSE_PROVIDER_TEXT",
            response=httpx.Response(400, request=REQUEST), body={"code": "json_validate_failed"}))
    elif outcome == "truncated":
        client = fake_client(result=response('{"lead":"Tension rises', finish_reason="length"))
    elif outcome == "invented_facts":
        client = fake_client(result=response(json.dumps({"lead": "Cambodia conquers Seychelles with six soldiers."})))
    else:
        client = fake_client()
    commentary = service(games, narrator=GroqNarrator("offline-provider-key", model="openai/gpt-oss-20b", client=client))
    answer = asyncio.run(commentary.generate(principal, game_id, action.state.revision))
    assert answer.status == ("ready" if outcome == "valid" else "fallback")
    if outcome == "valid":
        assert answer.text.startswith(LEAD)
    else:
        assert answer.source == "deterministic" and answer.reason == "invalid_output"
        assert "NEVER_EXPOSE" not in answer.model_dump_json()
    assert answer.facts.attacker_losses >= 0
    if outcome == "valid":
        assert answer.text == LEAD and "attacker dice" not in answer.text
    else:
        assert "attacker dice" in answer.text
    assert (store.games, store.receipts) == before
    counters = copy.deepcopy(store.limits)
    # Existing deterministic fallback records are retained even after a fixed
    # model is available. A deployment never reclaims them or rebills the event.
    fixed_client = fake_client()
    restarted = service(games, repository=commentary.repository,
        narrator=GroqNarrator("offline-provider-key", model="openai/gpt-oss-20b", client=fixed_client))
    assert asyncio.run(restarted.generate(principal, game_id, action.state.revision)) == answer
    assert restarted.read(game_id, action.state.revision) == answer
    assert store.limits == counters and (store.games, store.receipts) == before
    client.chat.completions.create.assert_awaited_once()
    fixed_client.chat.completions.create.assert_not_awaited()


CONQUEST = ("Cambodia's relentless offensive broke Seychelles' final resistance. "
            "The conquest shifts the contest's balance, giving this fierce exchange a triumphant ending.")
STALEMATE = ("Cambodia pressed Seychelles, but neither side could seize the advantage. "
             "Stubborn resistance kept the contest balanced, leaving the outcome of this tense struggle unresolved.")
SETBACK = ("Cambodia's assault met defiant resistance from Seychelles. "
           "The offensive fell short in this exchange, leaving the defenders with the stronger answer and the struggle unresolved.")


@pytest.mark.parametrize("text,facts", [
    (CONQUEST, {**FACTS, "conquest": True, "eliminated": ["Seychelles"]}),
    (STALEMATE, FACTS),
    (SETBACK, {**FACTS, "attacker_losses": 2, "defender_losses": 0}),
    ("Tension rises. The drama deepens across the battlefield.", FACTS),
    ("Cambodia\u2019s assault met Seychelles\u2019 stubborn resistance\u2014the advantage remained out of reach. "
     "A tense exchange left the contest balanced, with the struggle still unresolved.", FACTS),
    ("South Sudan pressed Sudan, but neither side could gain an advantage. The struggle remained balanced and unresolved.",
     {**FACTS, "attacker": "South Sudan", "defender": "Sudan"}),
])
def test_ordinary_creative_outcome_grounded_narration_is_accepted_without_truncation(text, facts):
    client = fake_client(result=response(json.dumps({"lead": text})))
    before = copy.deepcopy(facts)
    assert run(GroqNarrator("offline-provider-key", client=client), facts) == text
    assert facts == before
    client.chat.completions.create.assert_awaited_once()


@pytest.mark.parametrize("text,facts", [
    (CONQUEST, FACTS),
    (STALEMATE, {**FACTS, "conquest": True}),
    ("Cambodia eliminated Seychelles and claimed victory, leaving the opposition unable to continue the contest.", FACTS),
    ("Seychelles conquered Cambodia and seized control, marking a triumphant ending to the tense confrontation.", {**FACTS, "conquest": True}),
    ("Cambodia was eliminated, leaving Seychelles to claim victory after a fierce and dramatic confrontation.", {**FACTS, "conquest": True, "eliminated": ["Seychelles"]}),
    ("Cambodia attacked France, but neither side could gain the advantage in this tense and unresolved contest.", FACTS),
    ("Cambodia called reinforcements and tanks into the struggle, overwhelming Seychelles with a relentless offensive.", FACTS),
    ("The alliance with France changed the contest as Cambodia pressed Seychelles with a relentless offensive.", FACTS),
    ("Cambodia swept across the mountains and river, overwhelming Seychelles with a bold and relentless offensive.", FACTS),
    ("Cambodia withdrew its troops to the flank, leaving Seychelles to face a new and unexpected ambush.", FACTS),
    ("Both sides emerged unscathed as neither could seize the advantage in this tense and unresolved exchange.", FACTS),
    ("Cambodia won the game after the conquest, claiming total victory as Seychelles' resistance finally gave way.", {**FACTS, "conquest": True}),
    ("Neither side could seize the advantage as the struggle ended in an evenly matched stalemate.", {**FACTS, "attacker_losses": 2, "defender_losses": 0}),
    ("Cambodia pressed Seychelles. The struggle remained unresolved. Nobody could seize the advantage.", FACTS),
])
def test_unestablished_contradictory_or_unusable_narration_still_falls_back(text, facts):
    client = fake_client(result=response(json.dumps({"lead": text})))
    with pytest.raises(NarrationUnavailable, match="^invalid_output$"):
        run(GroqNarrator("offline-provider-key", client=client), facts)
    client.chat.completions.create.assert_awaited_once()


def test_gpt_oss_reasoning_field_is_never_used_as_display_narration():
    good = response(json.dumps({"lead": STALEMATE}))
    good.choices[0].message.reasoning = "NEVER_DISPLAY_REASONING"
    client = fake_client(result=good)
    assert run(GroqNarrator("offline-provider-key", client=client)) == STALEMATE
    good.choices[0].message.content = None
    with pytest.raises(NarrationUnavailable, match="^invalid_output$"):
        run(GroqNarrator("offline-provider-key", client=client))


def test_harmless_sentence_whitespace_is_normalized_without_dropping_words():
    text = STALEMATE.replace(". ", ".\n\t")
    client = fake_client(result=response(json.dumps({"lead": text})))
    assert run(GroqNarrator("offline-provider-key", client=client)) == STALEMATE


@pytest.mark.parametrize("npc", [False, True])
def test_creative_conquest_is_saved_ready_and_retrieved_without_mechanical_recap(catalog, npc):
    from test_commentary_service import battle, service
    store, games, principal, game_id, result = battle(catalog, npc=npc)
    exchange = next(event for event in result.events if event.type == "dice_exchange")
    source, target = exchange.source_id, exchange.target_id
    countries = {country.id: country.name for country in result.state.countries}
    text = (f"{countries[source]}'s relentless offensive broke {countries[target]}'s final resistance. "
            "The conquest shifts the contest's balance, giving this fierce exchange a triumphant ending.")
    client = fake_client(result=response(json.dumps({"lead": text})))
    commentary = service(games, narrator=GroqNarrator("offline-provider-key", client=client))
    before = copy.deepcopy((store.games, store.receipts))
    answer = asyncio.run(commentary.generate(principal, game_id, result.state.revision))
    assert answer.status == "ready" and answer.source == "groq" and answer.text == text
    assert answer.facts.conquered and answer.facts.eliminated
    assert (store.games, store.receipts) == before
    assert commentary.read(game_id, result.state.revision) == answer
    counts = copy.deepcopy(store.limits)
    assert asyncio.run(commentary.generate(principal, game_id, result.state.revision)) == answer
    assert store.limits == counts and client.chat.completions.create.await_count == 1
