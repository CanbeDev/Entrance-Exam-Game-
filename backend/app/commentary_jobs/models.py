"""BSON-native job contract. Never serializes timestamps to ISO for storage."""
from datetime import datetime, timezone
from typing import Literal

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ERRORS = (
    "capacity_limited", "storage_unavailable", "authorization_unavailable", "consent_required",
    "evidence_mismatch", "not_configured", "provider_timeout", "provider_rate_limited",
    "provider_unavailable", "invalid_output", "admission_limited", "interrupted",
    "attempts_exhausted", "legacy_fallback", "unexpected_error",
)


def utc(value):
    if not isinstance(value, datetime):
        raise ValueError("BSON datetime required")
    value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


class CommentaryJob(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    id: ObjectId = Field(alias="_id")
    schema_version: Literal[1]
    game_id: str = Field(min_length=24, max_length=24, pattern=r"^[0-9a-f]{24}$")
    revision: int = Field(strict=True, ge=1)
    action_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    status: Literal["queued", "claimed", "ready", "failed"]
    created_at: datetime
    updated_at: datetime
    available_at: datetime
    lease_token: str | None = Field(pattern=r"^[A-Za-z0-9_-]{16,128}$", repr=False)
    lease_expires_at: datetime | None
    attempts: int = Field(strict=True, ge=0, le=3)
    max_attempts: int = Field(strict=True, ge=1, le=3)
    last_error: str | None
    failure_reason: str | None
    completed_at: datetime | None

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("Integer schema version required")
        return value

    @field_validator("created_at", "updated_at", "available_at", "lease_expires_at", "completed_at", mode="before")
    @classmethod
    def bson_dates(cls, value):
        return None if value is None else utc(value)

    @model_validator(mode="after")
    def valid_image(self):
        if self.attempts > self.max_attempts or self.updated_at < self.created_at:
            raise ValueError("Invalid processing budget/time")
        if any(reason is not None and reason not in ERRORS for reason in (self.last_error, self.failure_reason)):
            raise ValueError("Unknown job error")
        if self.status == "claimed":
            if (not self.lease_token or self.lease_expires_at is None or self.attempts < 1
                    or self.failure_reason is not None or self.completed_at is not None):
                raise ValueError("Invalid claimed job")
        elif self.lease_token is not None or self.lease_expires_at is not None:
            raise ValueError("Unexpected job lease")
        if self.status == "queued":
            if self.attempts >= self.max_attempts or self.failure_reason is not None or self.completed_at is not None:
                raise ValueError("Invalid queued job")
        if self.status in {"ready", "failed"} and self.completed_at is None:
            raise ValueError("Missing completion time")
        if self.status == "ready" and (self.failure_reason is not None or self.last_error is not None):
            raise ValueError("Ready job carries failure")
        if self.status == "failed" and self.failure_reason is None:
            raise ValueError("Missing terminal reason")
        return self

    def document(self):
        return self.model_dump(mode="python", by_alias=True)

    @classmethod
    def queued(cls, game_id, revision, action_id, now, max_attempts=3):
        now = utc(now)
        return cls.model_validate(dict(
            _id=ObjectId(), schema_version=1, game_id=game_id, revision=revision,
            action_id=action_id, status="queued", created_at=now, updated_at=now,
            available_at=now, lease_token=None, lease_expires_at=None, attempts=0,
            max_attempts=max_attempts, last_error=None, failure_reason=None, completed_at=None))
