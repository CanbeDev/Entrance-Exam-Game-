from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.models.actions import FrozenModel


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def no_nul(cls, value):
        if "\x00" in value.get_secret_value():
            raise ValueError("Invalid password")
        return value


class Principal(FrozenModel):
    user_id: str
    username: str
    session_hash: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False, exclude=True)
    csrf_token: str = Field(repr=False, exclude=True)
    auth_version: int = Field(ge=1)


class UserPublic(FrozenModel):
    id: str
    username: str


class UserRecord(FrozenModel):
    id: str
    username: str
    username_key: str
    password_hash: str = Field(repr=False, exclude=True)
    status: Literal["active", "disabled"] = "active"
    auth_version: int = 1
    created_at: datetime


class LoginResult(FrozenModel):
    user: UserPublic
    token: str = Field(repr=False, exclude=True)
    csrf_token: str = Field(repr=False, exclude=True)
    expires_at: datetime
