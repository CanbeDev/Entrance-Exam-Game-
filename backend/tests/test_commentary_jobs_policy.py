"""Durable consent uses fresh owner authorization, never browser impersonation."""
from dataclasses import replace
from datetime import timedelta

from bson import ObjectId
import pytest

from app.commentary_jobs.policy import CommentaryConsentService, MongoCommentaryPolicyStore
from app.commentary_jobs.settings import CommentaryJobSettings, load_commentary_job_settings
from app.commentary_jobs.runtime import build_commentary_jobs
from app.security.environment import ConfigurationError
from app.security.errors import SecurityError
from commentary_jobs_helpers import system
from test_phase4_services import seed_principal


def test_settings_disabled_and_runtime_has_zero_io():
    assert load_commentary_job_settings({}) == CommentaryJobSettings()
    class Forbidden:
        def __getattr__(self, name):
            raise AssertionError("Disabled runtime performed I/O")
    assert build_commentary_jobs(Forbidden(), None, None, CommentaryJobSettings(), None) is None


@pytest.mark.parametrize("settings", [
    {"COMMENTARY_JOBS_EXECUTION_ENABLED": "TRUE"},
    {"COMMENTARY_JOBS_DISCOVERY_ENABLED": "1"},
    {"COMMENTARY_JOBS_UNKNOWN": "true"},
])
def test_settings_fail_closed_on_unknown_or_malformed_flags(settings):
    with pytest.raises(ConfigurationError):
        load_commentary_job_settings(settings)


def test_consent_persists_across_service_restart_without_any_session_in_policy(catalog):
    s = system(catalog)
    restarted = MongoCommentaryPolicyStore(s.db)
    policy = restarted.get(s.game_id)
    assert policy.activation_revision == 1
    context = restarted.authorize(s.game_id, 2, "roll-0")
    assert context.user_id == s.principal.user_id
    assert not hasattr(context, "session_hash")
    assert not {"session_hash", "csrf_token", "cookie"} & policy.model_dump().keys()
    assert restarted.recheck(context) == context


def test_optout_and_reenable_uses_current_revision_not_historical_boundary(catalog):
    s = system(catalog)
    disabled = s.consent.set_enabled(s.principal, s.game_id, False, 1)
    assert not disabled.enabled
    with pytest.raises(SecurityError):
        s.policies.authorize(s.game_id, 2, "roll-0")
    enabled = s.consent.set_enabled(s.principal, s.game_id, True, 2)
    assert enabled.activation_revision == 3
    with pytest.raises(SecurityError):
        s.policies.authorize(s.game_id, 2, "roll-0")
    assert s.policies.authorize(s.game_id, 3, "future").policy_version == 3


def test_repeated_enable_preserves_boundary_and_policy_updates_are_cas(catalog):
    s = system(catalog)
    assert s.consent.set_enabled(s.principal, s.game_id, True, 1).activation_revision == 1
    with pytest.raises(SecurityError) as err:
        s.consent.set_enabled(s.principal, s.game_id, False, 1)
    assert err.value.status == 409
    assert s.policies.get(s.game_id).enabled


@pytest.mark.parametrize("change", ["disabled", "auth_version", "owner", "access_version", "bound_at", "missing_policy"])
def test_authorization_denies_changed_durable_owner_evidence(catalog, change):
    s = system(catalog)
    old = s.policies.authorize(s.game_id, 2, "roll-0")
    game = s.db.get_collection("games").docs[ObjectId(s.game_id)]
    user = s.db.get_collection("users").docs[ObjectId(s.principal.user_id)]
    if change == "disabled":
        user["status"] = "disabled"
    elif change == "auth_version":
        user["auth_version"] += 1
    elif change == "owner":
        game["access"]["owner_user_id"] = "1"*24
    elif change == "access_version":
        game["access"]["version"] += 1
    elif change == "bound_at":
        game["access"]["bound_at"] += timedelta(seconds=1)
    else:
        s.db.get_collection("commentary_policies").docs.clear()
    with pytest.raises(SecurityError):
        s.policies.recheck(old)


def test_consent_mutation_reuses_current_owner_session_and_rejects_other_account(catalog):
    s = system(catalog)
    other = seed_principal(s.store, "Other", token="other-session")
    with pytest.raises(SecurityError):
        s.consent.set_enabled(other, s.game_id, False, 1)
    s.store.sessions[s.principal.session_hash]["revoked_at"] = s.now[0]
    with pytest.raises(SecurityError):
        s.consent.set_enabled(s.principal, s.game_id, False, 1)


def test_policy_identity_read_failure_does_not_leak_driver_detail(catalog):
    s = system(catalog)
    s.db.get_collection("users").fail_before = "find_one"
    with pytest.raises(SecurityError) as err:
        s.policies.authorize(s.game_id, 2, "roll-0")
    assert err.value.status == 503 and "PRIVATE" not in str(err.value)


def test_uncertain_optout_write_is_durable_and_not_automatically_replayed(catalog):
    s = system(catalog)
    s.db.get_collection("commentary_policies").fail_after = "replace_one"
    with pytest.raises(SecurityError):
        s.consent.set_enabled(s.principal, s.game_id, False, 1)
    assert not s.policies.get(s.game_id).enabled
    with pytest.raises(SecurityError):
        s.consent.set_enabled(s.principal, s.game_id, True, 1)


def test_new_owner_requires_fresh_consent_and_new_activation_boundary(catalog):
    s = system(catalog)
    other = seed_principal(s.store, "NewOwner", token="new-owner-session")
    game = s.store.games[s.game_id]
    game["access"]["owner_user_id"] = other.user_id
    game["access"]["version"] += 1
    s.db.get_collection("games").docs[ObjectId(s.game_id)] = game
    s.db.get_collection("users").docs[ObjectId(other.user_id)] = s.store.users[other.user_id]
    with pytest.raises(SecurityError):
        s.policies.authorize(s.game_id, 2, "roll-0")
    new = s.consent.set_enabled(other, s.game_id, True, 1)
    assert new.owner_user_id == other.user_id and new.activation_revision == 3
    with pytest.raises(SecurityError):
        s.policies.authorize(s.game_id, 2, "roll-0")
    assert s.policies.authorize(s.game_id, 3, "future").user_id == other.user_id
