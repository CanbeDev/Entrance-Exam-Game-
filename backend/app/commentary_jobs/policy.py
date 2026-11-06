"""Durable explicit owner consent and non-session worker authorization."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.commentary_jobs.models import utc
from app.commentary_jobs.storage import collection, SIMPLE, unavailable
from app.models.game_access import GameAccess
from app.security.errors import SecurityError


class CommentaryPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    game_id: str = Field(alias="_id", pattern=r"^[0-9a-f]{24}$")
    owner_user_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    owner_auth_version: int = Field(strict=True, ge=1)
    access_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    enabled: bool = Field(strict=True)
    version: int = Field(strict=True, ge=1)
    activation_revision: int = Field(strict=True, ge=1)
    updated_at: datetime

    @field_validator("updated_at", mode="before")
    @classmethod
    def date(cls, value):
        return utc(value)


@dataclass(frozen=True)
class WorkerAuthorization:
    """Internal evidence of an authorization snapshot, never a browser Principal."""
    user_id: str
    auth_version: int
    policy_version: int
    game_id: str
    revision: int
    action_id: str


def access_fingerprint(game):
    access = GameAccess.model_validate(game["access"])
    data = access.model_dump(mode="json")
    data["bound_at"] = utc(access.bound_at).isoformat()
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class MongoCommentaryPolicyStore:
    def __init__(self, database):
        self.database = database

    def get(self, game_id):
        try:
            row = collection(self.database, "commentary_policies").find_one({"_id": game_id}, collation=SIMPLE)
            return CommentaryPolicy.model_validate(row) if row else None
        except (PyMongoError, ValueError):
            raise unavailable() from None

    def enabled_page(self, after_game_id="", limit=50):
        try:
            return [CommentaryPolicy.model_validate(row) for row in collection(
                self.database, "commentary_policies").find(
                {"enabled": True, "_id": {"$gt": after_game_id}}, collation=SIMPLE
            ).sort([("_id", 1)]).limit(limit)]
        except (PyMongoError, ValueError):
            raise unavailable() from None

    def save(self, policy, expected_version):
        row = policy.model_dump(mode="python", by_alias=True)
        try:
            rows = collection(self.database, "commentary_policies")
            if expected_version == 0:
                result = rows.insert_one(row)
                matched = True
            else:
                result = rows.replace_one({"_id": policy.game_id, "version": expected_version}, row, collation=SIMPLE)
                matched = result.matched_count == 1
            if not result.acknowledged:
                raise unavailable()
            if not matched:
                raise SecurityError(409, "commentary_policy_changed")
            return policy
        except DuplicateKeyError:
            raise SecurityError(409, "commentary_policy_changed") from None
        except PyMongoError:
            raise unavailable() from None

    def identity(self, game_id):
        try:
            game = collection(self.database, "games").find_one(
                {"_id": ObjectId(game_id)}, {"access": 1, "revision": 1})
            owner = game["access"]["owner_user_id"]
            account = collection(self.database, "users").find_one(
                {"_id": ObjectId(owner)}, {"status": 1, "auth_version": 1})
            if account is None:
                raise ValueError
            return owner, account, access_fingerprint(game)
        except PyMongoError:
            raise unavailable() from None
        except (ValueError, TypeError, KeyError):
            raise SecurityError(403, "commentary_consent_required") from None

    def authorize(self, game_id, revision, action_id):
        policy = self.get(game_id)
        if policy is None or not policy.enabled or revision < policy.activation_revision:
            raise SecurityError(403, "commentary_consent_required")
        owner, account, fingerprint = self.identity(game_id)
        if (owner != policy.owner_user_id or account.get("status") != "active"
                or not isinstance(account.get("auth_version"), int) or isinstance(account.get("auth_version"), bool)
                or account["auth_version"] != policy.owner_auth_version):
            raise SecurityError(403, "commentary_consent_required")
        if fingerprint != policy.access_fingerprint:
            raise SecurityError(403, "commentary_consent_required")
        return WorkerAuthorization(owner, account["auth_version"], policy.version, game_id, revision, action_id)

    def recheck(self, context):
        current = self.authorize(context.game_id, context.revision, context.action_id)
        if current != context:
            raise SecurityError(403, "commentary_consent_required")
        return current


class CommentaryConsentService:
    """Local service boundary only. No route or credential persistence added."""
    def __init__(self, games, policies, clock):
        self.games, self.policies, self.clock = games, policies, clock

    def set_enabled(self, principal, game_id, enabled, expected_version):
        if type(enabled) is not bool or type(expected_version) is not int or expected_version < 0:
            raise SecurityError(422, "invalid_commentary_policy")
        principal, game = self.games._owned(principal, game_id)
        current = self.policies.get(game_id)
        if (current.version if current else 0) != expected_version:
            raise SecurityError(409, "commentary_policy_changed")
        revision = game.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise SecurityError(503, "battle_evidence_unavailable")
        same_grant = (current and current.enabled and enabled
            and current.owner_user_id == principal.user_id
            and current.owner_auth_version == principal.auth_version
            and current.access_fingerprint == access_fingerprint(game))
        policy = CommentaryPolicy.model_validate(dict(
            _id=game_id, owner_user_id=principal.user_id, owner_auth_version=principal.auth_version,
            access_fingerprint=access_fingerprint(game),
            enabled=enabled, version=expected_version + 1,
            activation_revision=current.activation_revision if same_grant else revision + 1,
            updated_at=utc(self.clock())))
        return self.policies.save(policy, expected_version)
