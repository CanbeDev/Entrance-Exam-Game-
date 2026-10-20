"""HTTP security boundary with explicit in-memory dependencies; never Atlas."""
import copy
import hashlib
import importlib
import random
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.models.auth import Credentials
from app.security.config import SecuritySettings
from app.services.auth_service import AuthService
from app.services.authorized_game_service import AuthorizedGameService
from app.services.phase4_context import Phase4Context
from npc_helpers import npc_state
from phase2_helpers import FixedDice, NOW, make_runtime
from phase4_helpers import MemorySecurityStore

ORIGIN = "https://testserver"
PASSWORD = "Test account phrase 47"


class FastPasswords:
    """HTTP tests isolate policy/authorization; dedicated tests exercise Argon2."""
    def hash(self, value):
        return hashlib.sha256(value.encode()).hexdigest()

    def verify(self, value, encoded):
        return encoded == self.hash(value)


@pytest.fixture
def secured_api(monkeypatch, collection, catalog):
    fake = ModuleType("app.database")
    fake.client = SimpleNamespace(admin=SimpleNamespace(command=lambda command: {"ok": 1}))
    fake.db = {"games": collection}
    monkeypatch.setitem(sys.modules, "app.database", fake)
    previous = sys.modules.pop("app.main", None)
    module = importlib.import_module("app.main")
    settings = SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True,
                                trusted_origins=(ORIGIN,), register_ip_limit=30)
    store = MemorySecurityStore()
    auth = AuthService(store, settings, lambda: NOW, passwords=FastPasswords())
    games = AuthorizedGameService(store, settings, lambda: NOW, catalog=catalog,
                                  dice=FixedDice([6, 6, 6, 1, 1, 1] * 10), setup_rng=random.Random(2))
    module.app.state.phase4 = Phase4Context(settings, auth, games)
    monkeypatch.setattr(module, "get_game", lambda game_id: copy.deepcopy(store.games.get(game_id)))
    with TestClient(module.app, base_url=ORIGIN) as client:
        yield client, module, store, auth, games
    sys.modules.pop("app.main", None)
    if previous is not None:
        sys.modules["app.main"] = previous


def sign_in(client, username="Player_1"):
    credentials = {"username": username, "password": PASSWORD}
    registered = client.post("/auth/register", json=credentials, headers={"Origin": ORIGIN})
    assert registered.status_code == 201, registered.text
    response = client.post("/auth/login", json=credentials, headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    csrf = client.get("/auth/csrf")
    assert csrf.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf.json()["csrf_token"]}, response


def owned_game(client, headers, key="create-1"):
    response = client.post("/games", headers={**headers, "Idempotency-Key": key},
                           json={"game_name": "Owned Game", "starting_country_id": "south-africa"})
    assert response.status_code == 201, response.text
    return response.json()


def make_human_active(store, game_id, catalog):
    previous = store.games[game_id]
    state = make_runtime(catalog).model_dump(mode="json")
    human = next(player for player in state["players"] if player["kind"] == "human")
    store.games[game_id] = {**state, "_id": previous["_id"],
                            "access": {**previous["access"], "human_player_id": human["id"]},
                            "creation": previous["creation"]}


def test_default_dependencies_leave_all_new_writes_disabled(secured_api):
    client, module, store, _, _ = secured_api
    module.app.state.phase4 = None
    for path in ("/auth/register", "/auth/login", "/auth/logout", "/games",
                 "/games/" + "0" * 24 + "/actions", "/games/" + "0" * 24 + "/npc-steps"):
        response = client.post(path, json={}, headers={"Origin": ORIGIN})
        assert response.status_code == 503
        assert response.json() == {"detail": {"code": "phase4_disabled"}}
    assert not store.users and not store.sessions and not store.games and not store.receipts


def test_registration_login_cookie_and_public_user_contract(secured_api):
    client, _, store, _, _ = secured_api
    _, response = sign_in(client)
    cookie = response.headers["set-cookie"]
    for flag in ("__Host-geopolitics_session=", "HttpOnly", "Secure", "Path=/", "SameSite=lax", "Max-Age=43200"):
        assert flag in cookie
    assert "Domain=" not in cookie
    assert set(response.json()) == {"user", "expires_at"}
    assert set(response.json()["user"]) == {"id", "username"}
    assert PASSWORD not in response.text and "password_hash" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/auth/me").json() == response.json()["user"]
    assert len(store.sessions) == 1


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example", ORIGIN + "/", "http://testserver"])
def test_registration_and_login_reject_untrusted_origins(secured_api, origin):
    client, _, store, _, _ = secured_api
    headers = {} if origin is None else {"Origin": origin}
    for path in ("/auth/register", "/auth/login"):
        response = client.post(path, json={"username": "Account", "password": PASSWORD}, headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "origin_rejected"
    assert not store.users and not store.sessions


def test_anonymous_game_writes_and_account_reads_are_rejected(secured_api):
    client, _, store, _, _ = secured_api
    for path, body in (("/games", {}), ("/games/" + "0" * 24 + "/actions", {}),
                       ("/games/" + "0" * 24 + "/npc-steps", {"expected_revision": 0})):
        response = client.post(path, json=body, headers={"Origin": ORIGIN})
        assert response.status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/csrf").status_code == 401
    assert client.get("/me/games").status_code == 401
    assert not store.games and not store.receipts


@pytest.mark.parametrize("token", [None, "wrong", "x" * 257])
def test_csrf_required_before_game_creation(secured_api, token):
    client, _, store, _, _ = secured_api
    sign_in(client)
    headers = {"Origin": ORIGIN, "Idempotency-Key": "create"}
    if token is not None:
        headers["X-CSRF-Token"] = token
    response = client.post("/games", headers=headers,
                           json={"game_name": "Protected", "starting_country_id": "south-africa"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_rejected"
    assert not store.games


def test_create_retry_list_and_anonymous_public_read_are_safe(secured_api):
    client, _, store, _, _ = secured_api
    headers, _ = sign_in(client)
    game = owned_game(client, headers)
    repeated = owned_game(client, headers)
    assert repeated == game and len(store.games) == 1
    listed = client.get("/me/games?query=owned&status=active&limit=1")
    assert listed.status_code == 200
    assert listed.json()["games"][0]["_id"] == game["_id"]
    assert "countries" not in listed.json()["games"][0]
    client.cookies.clear()
    before = copy.deepcopy((store.games, store.receipts, store.sessions))
    public = client.get("/games/" + game["_id"])
    events = client.get("/games/" + game["_id"] + "/events")
    assert public.status_code == events.status_code == 200
    assert public.json() == game and events.json()["events"] == []
    assert (store.games, store.receipts, store.sessions) == before
    for response in (public, listed):
        assert "owner_user_id" not in response.text and "fingerprint" not in response.text


def test_human_action_is_authorized_and_duplicate_replays_without_mutation(secured_api, catalog):
    client, _, store, _, _ = secured_api
    headers, _ = sign_in(client)
    game = owned_game(client, headers)
    make_human_active(store, game["_id"], catalog)
    action = {"action_id": "human-1", "expected_revision": 0, "action": {"type": "skip"}}
    url = f"/games/{game['_id']}/actions"
    result = client.post(url, json=action, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["state"]["revision"] == 1
    snapshot = copy.deepcopy((store.games, store.receipts))
    repeated = client.post(url, json=action, headers=headers)
    assert repeated.status_code == 200 and repeated.json() == result.json()
    assert (store.games, store.receipts) == snapshot
    client.cookies.clear()
    public = client.get(f"/games/{game['_id']}/events")
    assert len(public.json()["events"]) == 1
    assert "fingerprint" not in public.text


def test_non_owner_cannot_read_receipts_or_submit_human_npc_actions(secured_api, catalog):
    client, _, store, _, _ = secured_api
    owner_headers, _ = sign_in(client)
    game = owned_game(client, owner_headers)
    make_human_active(store, game["_id"], catalog)
    client.cookies.clear()
    other_headers, _ = sign_in(client, "Other_Player")
    before = copy.deepcopy((store.games, store.receipts))
    receipt_reads = store.receipt_reads
    for suffix, body in (("actions", {"action_id": "attacker", "expected_revision": 0,
                                      "action": {"type": "skip"}}),
                          ("npc-steps", {"expected_revision": 0})):
        response = client.post(f"/games/{game['_id']}/{suffix}", headers=other_headers, json=body)
        assert response.status_code == 403
    assert client.get("/me/games").json()["games"] == []
    assert (store.games, store.receipts) == before and store.receipt_reads == receipt_reads


def test_npc_step_uses_server_policy_and_replays_original_decision(secured_api, catalog):
    client, _, store, _, _ = secured_api
    headers, _ = sign_in(client)
    game = owned_game(client, headers)
    previous = store.games[game["_id"]]
    store.games[game["_id"]] = {**npc_state(catalog).model_dump(mode="json"), "_id": previous["_id"],
                                "access": previous["access"], "creation": previous["creation"]}
    path = f"/games/{game['_id']}/npc-steps"
    result = client.post(path, json={"expected_revision": 0}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["npc_decision"]["reason"] == "attack"
    assert result.json()["npc_decision"]["explanation"]
    snapshot = copy.deepcopy((store.games, store.receipts))
    replayed = client.post(path, json={"expected_revision": 0}, headers=headers)
    assert replayed.json() == result.json() and (store.games, store.receipts) == snapshot
    assert "state_digest" not in result.text and "tie_breaker" not in result.text


def test_logout_cookie_revocation_and_csrf_protection(secured_api):
    client, _, store, _, _ = secured_api
    headers, _ = sign_in(client)
    old_cookie = client.cookies.get("__Host-geopolitics_session")
    rejected = client.post("/auth/logout", headers={"Origin": ORIGIN})
    assert rejected.status_code == 403 and not any(item["revoked_at"] for item in store.sessions.values())
    response = client.post("/auth/logout", headers=headers)
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"] and "Secure" in response.headers["set-cookie"]
    client.cookies.set("__Host-geopolitics_session", old_cookie)
    assert client.get("/auth/me").status_code == 401


@pytest.mark.parametrize("body", [
    {"username": "Ab", "password": "private-validation-marker"},
    {"username": "Account", "password": "private-validation-marker", "owner_user_id": "injected"},
    {"username": "Account", "password": {"secret": "private-validation-marker"}},
])
def test_auth_validation_never_echoes_password_or_request_input(secured_api, body):
    client, _, _, _, _ = secured_api
    response = client.post("/auth/register", json=body, headers={"Origin": ORIGIN})
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request"}}
    assert "private-validation-marker" not in response.text


def test_game_payload_rejects_injected_actor_owner_dice_or_npc_metadata(secured_api):
    client, _, store, _, _ = secured_api
    headers, _ = sign_in(client)
    game = owned_game(client, headers)
    before = copy.deepcopy((store.games, store.receipts))
    response = client.post(f"/games/{game['_id']}/actions", headers=headers, json={
        "action_id": "tamper", "expected_revision": 0, "action": {"type": "skip"},
        "actor": {"kind": "npc"}, "owner_user_id": "attacker", "dice": [6], "npc_decision": {}})
    assert response.status_code == 422
    assert (store.games, store.receipts) == before


def test_actual_streamed_body_limit_and_json_content_type(secured_api):
    client, _, store, _, _ = secured_api
    oversized = (b"x" * 1024 for _ in range(17))
    response = client.post("/auth/register", content=oversized,
                           headers={"Origin": ORIGIN, "Content-Type": "application/json"})
    assert response.status_code == 413
    response = client.post("/auth/register", content="username=Account&password=private-marker",
                           headers={"Origin": ORIGIN, "Content-Type": "application/x-www-form-urlencoded"})
    assert response.status_code == 415 and "private-marker" not in response.text
    assert not store.users


def test_duplicate_origin_and_forged_forwarded_ip_cannot_bypass_limits(secured_api):
    client, module, _, _, _ = secured_api
    response = client.post("/auth/register", json={"username": "Account", "password": PASSWORD},
                           headers=[("Origin", ORIGIN), ("Origin", "https://evil.example")])
    assert response.status_code == 403
    calls = []
    module.app.state.phase4.auth.register = lambda credentials, ip: calls.append(ip) or {"id": "id", "username": "Account"}
    response = client.post("/auth/register", json={"username": "Account", "password": PASSWORD},
                           headers={"Origin": ORIGIN, "X-Forwarded-For": "trusted-proxy-forgery"})
    assert response.status_code == 201 and calls == ["testclient"]


def test_unexpected_service_error_is_sanitized(secured_api):
    client, module, _, _, _ = secured_api
    def fail(*args, **kwargs):
        raise RuntimeError("private-driver-password-marker")
    module.app.state.phase4.auth.register = fail
    response = client.post("/auth/register", json={"username": "Account", "password": PASSWORD},
                           headers={"Origin": ORIGIN})
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "service_unavailable"}}
    assert "private-driver-password-marker" not in response.text


def test_gameplay_gate_remains_closed_despite_successful_authentication(secured_api):
    client, module, store, _, _ = secured_api
    headers, _ = sign_in(client)
    module.app.state.phase4.games.settings = SecuritySettings(auth_writes_enabled=True, trusted_origins=(ORIGIN,))
    response = client.post("/games", headers={**headers, "Idempotency-Key": "blocked"},
                           json={"game_name": "Blocked", "starting_country_id": "south-africa"})
    assert response.status_code == 503 and response.json()["detail"]["code"] == "gameplay_writes_disabled"
    assert not store.games


def test_csrf_does_not_enable_cors_or_cross_origin_credentials(secured_api):
    client, _, _, _, _ = secured_api
    sign_in(client)
    response = client.options("/auth/me", headers={"Origin": "https://evil.example",
                                                   "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


def test_http_rate_limit_reports_the_actual_account_window(secured_api):
    from dataclasses import replace
    client, module, _, _, _ = secured_api
    module.app.state.phase4.auth.settings = replace(module.app.state.phase4.auth.settings, login_account_limit=1)
    payload = {"username": "Missing", "password": PASSWORD}
    headers = {"Origin": ORIGIN}
    assert client.post("/auth/login", json=payload, headers=headers).status_code == 401
    response = client.post("/auth/login", json=payload, headers=headers)
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) == 900 - int(NOW.timestamp()) % 900
    assert response.json() == {"detail": {"code": "rate_limited"}}
    assert PASSWORD not in response.text
