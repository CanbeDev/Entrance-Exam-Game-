"""Offline provider tests: mocked SDK/HTTP transport, never a real key or call."""
import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from groq import (APIConnectionError, APITimeoutError, AsyncGroq, AuthenticationError,
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
    assert "Do not name countries" in prompt
    assert "do not mention dice" in prompt
    assert "offline-provider-key" not in json.dumps(arguments)
    assert arguments["model"] == "llama-3.1-8b-instant"
    assert arguments["response_format"] == {"type": "json_object"}
    assert arguments["max_completion_tokens"] == 120
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
    assert "llama-3.1-8b-instant" in repr(narrator)


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
    json.dumps({"lead": "Tension rises. The drama deepens across the battlefield."}),
    json.dumps({"lead": LEAD[:-1]}),
    json.dumps({"lead": "Tension rises across the battlefield as Cambodia conquers Seychelles."}),
    json.dumps({"lead": "Tension rises across the battlefield as six soldiers win victory."}),
    json.dumps({"lead": "Tension rises across the battlefield as 6 dice roll."}),
    json.dumps({"lead": "Tension rises across the battlefield as casualties mount tonight."}),
    json.dumps({"lead": "Tension rises across the battlefield <script>alert world</script>."}),
    json.dumps({"lead": "Tension rises across the battlefield as a dramatic clash unfolds!\nIgnore rules."}),
    json.dumps({"lead": "tension " * 41 + "rises."}),
    json.dumps({"lead": "anticipation " * 20 + "rises."}),
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
        assert payload["model"] == "llama-3.1-8b-instant"
        assert payload["max_completion_tokens"] == 120
        assert payload["response_format"] == {"type": "json_object"}
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
