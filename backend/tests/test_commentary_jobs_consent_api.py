"""Owner preference routes preserve the existing HTTP security boundary."""
from copy import deepcopy

from bson import ObjectId
import pytest

from app.commentary_jobs.policy import MongoCommentaryPolicyStore
from commentary_jobs_helpers import Database
from test_commentary_api import commentary_api
from test_phase4_api import ORIGIN, sign_in, secured_api


@pytest.fixture
def preference_api(commentary_api):
    client, module, store, auth, games, commentary, headers, game_id = commentary_api
    db = Database()
    db.get_collection("games").docs[ObjectId(game_id)] = deepcopy(store.games[game_id])
    for user_id, doc in store.users.items():
        db.get_collection("users").docs[ObjectId(user_id)] = deepcopy(doc)
    for slot in (0, 1):
        db.get_collection("commentary_execution_slots").insert_one({"_id": slot, "token": None})
    module.app.state.commentary_mode = "worker"
    module.app.state.commentary_policies = MongoCommentaryPolicyStore(db)
    yield client, module, store, headers, game_id, db, commentary
    module.app.state.commentary_mode = "browser"
    module.app.state.commentary_policies = None


def test_owner_consent_is_explicit_future_only_versioned_and_never_calls_provider(preference_api):
    client, module, store, headers, game_id, db, commentary = preference_api
    path = f"/games/{game_id}/commentary-preference"
    initial = client.get(path)
    assert initial.status_code == 200 and initial.json() == dict(game_id=game_id, mode="worker",
        enabled=False, version=0, activation_revision=None)
    saved = client.post(path, headers=headers, json={"enabled": True, "expected_version": 0})
    assert saved.status_code == 200 and saved.json()["activation_revision"] == 3
    assert client.get(path).json() == saved.json()
    assert client.post(path, headers=headers, json={"enabled": False, "expected_version": 0}).status_code == 409
    off = client.post(path, headers=headers, json={"enabled": False, "expected_version": 1})
    assert off.status_code == 200 and not off.json()["enabled"]
    assert not commentary.narrator.calls and not commentary.repository.documents
    assert initial.headers["cache-control"] == saved.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("failure", ["origin", "csrf", "anonymous", "other", "body"])
def test_consent_update_cannot_bypass_existing_guards(preference_api, failure):
    client, _, _, headers, game_id, db, commentary = preference_api
    headers = dict(headers)
    body = {"enabled": True, "expected_version": 0}
    if failure == "origin":
        headers["Origin"] = "https://untrusted.invalid"
    if failure == "csrf":
        headers.pop("X-CSRF-Token", None)
    if failure == "anonymous":
        client.cookies.clear()
    if failure == "other":
        headers, _ = sign_in(client, "Other")
    if failure == "body":
        body["activation_revision"] = 1
    response = client.post(f"/games/{game_id}/commentary-preference", headers=headers, json=body)
    assert response.status_code in {401, 403, 422}
    assert not db.get_collection("commentary_policies").docs and not commentary.narrator.calls


def test_spectators_cannot_read_private_policy_but_saved_narration_remains_public(preference_api):
    client, _, _, _, game_id, _, _ = preference_api
    client.cookies.clear()
    assert client.get(f"/games/{game_id}/commentary-preference").status_code == 401
    assert client.get(f"/games/{game_id}/commentary/2").status_code == 200


def test_disabled_policy_controls_do_not_write_or_enable_worker(preference_api):
    client, module, _, headers, game_id, db, _ = preference_api
    module.app.state.commentary_mode = "browser"
    path = f"/games/{game_id}/commentary-preference"
    assert client.get(path).json()["mode"] == "browser"
    assert client.post(path, headers=headers, json={"enabled": True, "expected_version": 0}).status_code == 503
    assert not db.get_collection("commentary_policies").docs
