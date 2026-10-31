"""Commentary HTTP security and gameplay isolation with injected memory stores."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import asyncio
import threading

import pytest

from app.models.actions import Roll, StartAttack
from app.services.commentary_service import CommentaryService
from npc_helpers import npc_state
from phase2_helpers import NOW, revise
from test_commentary_service import MemoryCommentaryRepository, Narrator
from test_phase4_api import ORIGIN, make_human_active, owned_game, secured_api, sign_in
from test_phase4_services import command, owned_document


@pytest.fixture
def commentary_api(secured_api, catalog):
    client, module, store, auth, games = secured_api
    headers, _ = sign_in(client)
    game = owned_game(client, headers)
    game_id = game["_id"]
    make_human_active(store, game_id, catalog)
    document = store.games[game_id]
    document["countries"][0]["soldiers"] = 3
    document["countries"][1]["soldiers"] = 1
    source, target = document["countries"][:2]
    started = client.post(f"/games/{game_id}/actions", headers=headers, json={
        "action_id": "commentary-start", "expected_revision": 0,
        "action": {"type": "start_attack", "source_id": source["id"], "target_id": target["id"]}})
    assert started.status_code == 200, started.text
    rolled = client.post(f"/games/{game_id}/actions", headers=headers, json={
        "action_id": "commentary-roll", "expected_revision": 1, "action": {"type": "roll"}})
    assert rolled.status_code == 200, rolled.text
    narrator, repository = Narrator(), MemoryCommentaryRepository()
    commentary = CommentaryService(games, repository, narrator, clock=lambda: NOW)
    module.app.state.commentary = commentary
    return client, module, store, auth, games, commentary, headers, game_id


def test_owner_generation_and_saved_anonymous_retrieval_preserve_gameplay(commentary_api):
    client, _, store, _, _, commentary, headers, game_id = commentary_api
    before = deepcopy((store.games, store.receipts))
    path = f"/games/{game_id}/commentary/2"
    response = client.post(path, headers=headers, json={})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready" and response.json()["source"] == "groq"
    assert response.json()["game_id"] == game_id and response.json()["revision"] == 2
    assert client.post(path, headers=headers, json={}).json() == response.json()
    assert len(commentary.narrator.calls) == 1
    client.cookies.clear()
    untouched = deepcopy((store.games, store.receipts, store.sessions, store.limits, commentary.repository.documents))
    saved = client.get(path)
    assert saved.status_code == 200 and saved.json() == response.json()
    assert (store.games, store.receipts, store.sessions, store.limits, commentary.repository.documents) == untouched
    assert (store.games, store.receipts) == before
    assert response.headers["cache-control"] == saved.headers["cache-control"] == "no-store"
    for value in [response.text, saved.text]:
        assert "claim_token" not in value and "claimed_at" not in value and "session_hash" not in value


def test_anonymous_can_read_fallback_facts_but_cannot_generate(commentary_api):
    client, _, _, _, _, commentary, _, game_id = commentary_api
    client.cookies.clear()
    path = f"/games/{game_id}/commentary/2"
    public = client.get(path)
    assert public.status_code == 200 and public.json()["status"] == "not_generated"
    assert client.post(path, headers={"Origin": ORIGIN}, json={}).status_code == 401
    assert commentary.narrator.calls == [] and commentary.repository.claims == 0


@pytest.mark.parametrize("failure", ["missing_origin", "wrong_origin", "missing_csrf", "wrong_csrf"])
def test_generation_retains_origin_and_csrf_guards(commentary_api, failure):
    client, _, _, _, _, commentary, headers, game_id = commentary_api
    headers = dict(headers)
    if failure == "missing_origin":
        headers.pop("Origin")
    elif failure == "wrong_origin":
        headers["Origin"] = "https://untrusted.invalid"
    elif failure == "missing_csrf":
        headers.pop("X-CSRF-Token")
    else:
        headers["X-CSRF-Token"] = "synthetic-invalid"
    assert client.post(f"/games/{game_id}/commentary/2", headers=headers, json={}).status_code == 403
    assert commentary.narrator.calls == [] and commentary.repository.claims == 0


def test_different_account_cannot_generate_for_someone_elses_game(commentary_api):
    client, _, _, _, _, commentary, _, game_id = commentary_api
    headers, _ = sign_in(client, username="Other_Player")
    denied = client.post(f"/games/{game_id}/commentary/2", headers=headers, json={})
    assert denied.status_code == 403
    assert commentary.narrator.calls == [] and commentary.repository.claims == 0


def test_expired_session_cannot_start_billable_generation(commentary_api):
    client, _, store, _, _, commentary, headers, game_id = commentary_api
    for session in store.sessions.values():
        session["expires_at"] = NOW - timedelta(seconds=1)
    assert client.post(f"/games/{game_id}/commentary/2", headers=headers, json={}).status_code == 401
    assert commentary.narrator.calls == [] and commentary.repository.claims == 0


@pytest.mark.parametrize("path,body", [("2", {"facts": {"attacker_losses": 999}}),
                                    ("0", {}), ("-1", {}), ("not-a-revision", {})])
def test_path_and_body_do_not_accept_client_supplied_battle_facts(commentary_api, path, body):
    client, _, _, _, _, commentary, headers, game_id = commentary_api
    response = client.post(f"/games/{game_id}/commentary/{path}", headers=headers, json=body)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request"}}
    assert commentary.narrator.calls == [] and commentary.repository.claims == 0


@pytest.mark.parametrize("revision", [1, 99])
def test_nonbattle_and_unknown_receipts_cannot_bill(commentary_api, revision):
    client, _, _, _, _, commentary, headers, game_id = commentary_api
    response = client.post(f"/games/{game_id}/commentary/{revision}", headers=headers, json={})
    assert response.status_code == 404 and response.json()["detail"]["code"] == "battle_not_found"
    assert commentary.narrator.calls == [] and commentary.repository.claims == 0


def test_commentary_provider_failure_is_safe_and_does_not_change_game(commentary_api):
    client, _, store, _, _, commentary, headers, game_id = commentary_api
    commentary.narrator.reason = "provider_unavailable"
    before = deepcopy((store.games, store.receipts))
    response = client.post(f"/games/{game_id}/commentary/2", headers=headers, json={})
    assert response.status_code == 200 and response.json()["status"] == "fallback"
    assert response.json()["source"] == "deterministic"
    assert (store.games, store.receipts) == before


def test_blocked_commentary_does_not_delay_authoritative_human_or_npc_routes(commentary_api, catalog):
    client, module, store, auth, games, commentary, headers, game_id = commentary_api
    entered, release = threading.Event(), threading.Event()
    class BlockingNarrator:
        async def generate(self, facts):
            entered.set()
            assert await asyncio.to_thread(release.wait, 5)
            return "Tension hangs over the battlefield as a fierce clash unfolds."
    commentary.narrator = BlockingNarrator()
    # Two independent legal games use exactly the existing authorized routes.
    principal = next(iter(store.sessions.values()))
    authenticated = store.authorize(principal["_id"], NOW, 1800)
    human = owned_game(client, headers, key="parallel-human")
    make_human_active(store, human["_id"], catalog)
    npc_document = owned_document(store, authenticated, npc_state(catalog))
    npc_id = str(npc_document["_id"])
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(client.post, f"/games/{game_id}/commentary/2", headers=headers, json={})
        try:
            assert entered.wait(3)
            human_move = client.post(f"/games/{human['_id']}/actions", headers=headers, json={
                "action_id": "parallel-human-skip", "expected_revision": 0, "action": {"type": "skip"}})
            npc_move = client.post(f"/games/{npc_id}/npc-steps", headers=headers, json={"expected_revision": 0})
            assert human_move.status_code == npc_move.status_code == 200
            assert human_move.json()["state"]["revision"] == npc_move.json()["state"]["revision"] == 1
            assert not running.done(), "Gameplay must complete while the independent provider is still blocked"
            assert module.app.state.commentary is commentary
        finally:
            release.set()
        assert running.result(timeout=5).status_code == 200


def test_repeated_spectator_reads_never_generate_or_modify_saved_data(commentary_api):
    client, _, store, _, _, commentary, headers, game_id = commentary_api
    path = f"/games/{game_id}/commentary/2"
    generated = client.post(path, headers=headers, json={})
    assert generated.status_code == 200
    client.cookies.clear()
    before = deepcopy((store.games, store.receipts, store.sessions, store.limits,
                       commentary.repository.documents))
    for _ in range(12):
        saved = client.get(path)
        assert saved.status_code == 200 and saved.json() == generated.json()
    assert len(commentary.narrator.calls) == commentary.repository.claims == 1
    assert (store.games, store.receipts, store.sessions, store.limits,
            commentary.repository.documents) == before
