"""Local cryptography/session/security contracts. No database dependencies."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.models.auth import Credentials
from app.security.config import SecuritySettings
from app.security.errors import SecurityError
from app.security.passwords import Passwords, validate_new_password
from app.services.auth_service import AuthService, token_hash
from phase2_helpers import NOW
from phase4_helpers import MemorySecurityStore

PASSWORD = "Several private words 27!"


@pytest.fixture(scope="module")
def passwords():
    return Passwords()


@pytest.fixture
def auth(passwords):
    moment = [NOW]
    clock = lambda: moment[0]
    store = MemorySecurityStore(clock=clock)
    settings = SecuritySettings(auth_writes_enabled=True, gameplay_writes_enabled=True,
                                trusted_origins=("https://testserver",))
    return AuthService(store, settings, clock, passwords), store, moment


def credentials(username="Alice", password=PASSWORD):
    return Credentials(username=username, password=password)


def registered(auth):
    service, store, moment = auth
    user = service.register(credentials(), "127.0.0.1")
    login = service.login(credentials(), "127.0.0.1")
    return service, store, moment, user, login


def test_argon2id_parameters_random_salts_and_password_verification(passwords):
    first, second = passwords.hash(PASSWORD), passwords.hash(PASSWORD)
    assert first != second
    assert first.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert passwords.verify(PASSWORD, first)
    assert not passwords.verify(PASSWORD.lower(), first)
    assert not passwords.verify(PASSWORD, None)
    assert not passwords.verify(PASSWORD, "corrupt-stored-hash")


def test_unicode_normalization_and_whitespace_preservation(passwords):
    value = "  Cafe\u0301 several words  "
    encoded = passwords.hash(value)
    assert passwords.verify("  Caf\u00e9 several words  ", encoded)
    assert not passwords.verify(value.strip(), encoded)


def test_hashing_concurrency_is_bounded(passwords):
    passwords._slots.acquire()
    passwords._slots.acquire()
    try:
        with pytest.raises(SecurityError) as error:
            passwords.hash(PASSWORD)
        assert error.value.code == "authentication_busy"
    finally:
        passwords._slots.release()
        passwords._slots.release()


@pytest.mark.parametrize("value", ["short", "passwordpassword", "123456789012345", "x" * 15,
                                  "x" * 129, "some\x00long password here"])
def test_password_policy_rejects_weak_or_oversized_values(value):
    with pytest.raises(SecurityError):
        validate_new_password(value, "Alice")


@pytest.mark.parametrize("value", ["lowercase words accepted", "spaces are fine here", "\u00e9" * 14 + "!", "a" * 127 + "!"])
def test_password_policy_does_not_require_arbitrary_composition(value):
    assert validate_new_password(value, "Alice") == value


@pytest.mark.parametrize("username", ["ab", "a" * 33, "a b", "someone@example.com", "\u0430lice", {"$ne": None}])
def test_username_and_nosql_input_validation(username):
    with pytest.raises(ValidationError):
        credentials(username=username)


def test_registration_uses_canonical_unique_username_and_never_stores_plaintext(auth):
    service, store, _ = auth
    user = service.register(credentials(), "127.0.0.1")
    stored = store.find_user("alice")
    assert stored["username"] == "Alice" and str(stored["_id"]) == user.id
    assert PASSWORD not in repr(stored)
    assert stored["password_hash"].startswith("$argon2id$")
    with pytest.raises(SecurityError) as error:
        service.register(credentials("ALICE"), "127.0.0.1")
    assert error.value.status == 409 and len(store.users) == 1


def test_competing_registration_has_one_unique_account(auth):
    service, store, _ = auth
    def register(name):
        try:
            return service.register(credentials(name), "127.0.0.1")
        except SecurityError as error:
            return error.status
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(register, ["Alice", "ALICE"]))
    assert len(store.users) == 1 and results.count(409) == 1


def test_session_store_contains_only_token_verifier_and_restart_recovers_login(auth):
    service, store, _, user, login = registered(auth)
    assert login.token not in repr(store.sessions)
    assert token_hash(login.token) in store.sessions
    assert login.token not in repr(login) and login.token not in login.model_dump_json()
    recovered = AuthService(store, service.settings, service.clock, service.passwords).authenticate(login.token)
    assert recovered.user_id == user.id
    assert recovered.csrf_token == login.csrf_token
    assert recovered.session_hash not in recovered.model_dump_json()


def test_login_is_case_insensitive_and_failures_are_generic(auth):
    service, store, _ = auth
    service.register(credentials(), "127.0.0.1")
    assert service.login(credentials("ALICE"), "127.0.0.1").user.username == "Alice"
    errors = []
    for supplied in (credentials("Missing"), credentials(password="A different long password!")):
        with pytest.raises(SecurityError) as error:
            service.login(supplied, "127.0.0.1")
        errors.append((error.value.status, error.value.code))
    assert errors == [(401, "invalid_credentials")] * 2
    assert len(store.sessions) == 1


@pytest.mark.parametrize("condition", ["idle", "absolute", "revoked", "disabled", "version"])
def test_session_rejection_at_expiry_or_revocation(auth, condition):
    service, store, moment, user, login = registered(auth)
    session = store.sessions[token_hash(login.token)]
    if condition == "idle":
        moment[0] += timedelta(seconds=1800)
    elif condition == "absolute":
        session["expires_at"] = NOW
    elif condition == "revoked":
        session["revoked_at"] = NOW
    elif condition == "disabled":
        store.users[user.id]["status"] = "disabled"
    else:
        store.users[user.id]["auth_version"] += 1
    with pytest.raises(SecurityError) as error:
        service.authenticate(login.token)
    assert error.value.status == 401


def test_session_touch_uses_server_clock_and_logout_revokes_stolen_copy(auth):
    service, store, moment, _, login = registered(auth)
    moment[0] += timedelta(minutes=20)
    principal = service.authenticate(login.token)
    assert store.sessions[token_hash(login.token)]["last_seen_at"] == moment[0]
    moment[0] += timedelta(minutes=20)
    principal = service.authenticate(login.token)
    service.logout(principal)
    with pytest.raises(SecurityError):
        service.authenticate(login.token)


def test_successful_login_rotates_presented_session(auth):
    service, store, _, _, first = registered(auth)
    second = service.login(credentials(), "127.0.0.1", previous_token=first.token)
    assert second.token != first.token and second.csrf_token != first.csrf_token
    with pytest.raises(SecurityError):
        service.authenticate(first.token)
    assert service.authenticate(second.token)


@pytest.mark.parametrize("value", [None, "", "short", "\u00e9" * 43, "A" * 5000, "a" * 43])
def test_malformed_or_forged_session_tokens_never_authenticate(auth, value):
    with pytest.raises(SecurityError) as error:
        auth[0].authenticate(value)
    assert error.value.status == 401


def test_rate_limits_are_shared_and_expire_without_ttl_cleanup(auth):
    service, store, moment = auth
    limited = AuthService(store, replace(service.settings, login_account_limit=2), service.clock, service.passwords)
    for _ in range(2):
        with pytest.raises(SecurityError) as error:
            limited.login(credentials("Missing"), "127.0.0.1")
        assert error.value.status == 401
    # A new service and different IP do not bypass the account counter.
    with pytest.raises(SecurityError) as error:
        limited.login(credentials("MISSING"), "127.0.0.2")
    assert error.value.status == 429
    moment[0] += timedelta(minutes=16)
    with pytest.raises(SecurityError) as error:
        limited.login(credentials("Missing"), "127.0.0.1")
    assert error.value.status == 401


def test_disabled_auth_gate_precedes_all_persistence_calls(auth, monkeypatch):
    service, store, _ = auth
    disabled = AuthService(store, SecuritySettings(), service.clock, service.passwords)
    monkeypatch.setattr(store, "consume_limit", lambda *args: pytest.fail("Disabled auth touched persistence"))
    for operation in (disabled.register, disabled.login):
        with pytest.raises(SecurityError) as error:
            operation(credentials(), "127.0.0.1")
        assert error.value.status == 503


@pytest.mark.parametrize("change", [{"auth_writes_enabled": "true"}, {"gameplay_writes_enabled": 1},
                                   {"idle_seconds": 0}, {"idle_seconds": 50000},
                                   {"trusted_origins": ("https://example.com/path",)},
                                   {"trusted_origins": ("http://public.example.com",)},
                                   {"cookie_name": "insecure-session"}])
def test_security_configuration_cannot_silently_relax_contract(change):
    with pytest.raises(ValueError):
        SecuritySettings(**change)
