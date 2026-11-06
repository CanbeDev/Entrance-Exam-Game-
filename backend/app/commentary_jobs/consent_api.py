"""Owner-only policy controls. No scheduler/provider dispatch from settings."""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.api.dependencies import authenticated, authenticated_mutation, get_context
from app.models.actions import FrozenModel
from app.commentary_jobs.policy import CommentaryConsentService, access_fingerprint
from app.commentary_jobs.readiness import verify_optional_storage
from app.security.errors import SecurityError

router = APIRouter(tags=["Battle commentary preferences"])


class CommentaryPreference(FrozenModel):
    game_id: str
    mode: Literal["browser", "worker", "unavailable"]
    enabled: bool
    version: int = Field(strict=True, ge=0)
    activation_revision: int | None = Field(strict=True, ge=1)


class CommentaryPreferenceRequest(FrozenModel):
    enabled: bool = Field(strict=True)
    expected_version: int = Field(strict=True, ge=0)


def preference(request, principal, game_id, context):
    principal, game = context.games._owned(principal, game_id)
    mode = getattr(request.app.state, "commentary_mode", "browser")
    if mode != "worker":
        return CommentaryPreference(game_id=game_id, mode=mode, enabled=False, version=0, activation_revision=None)
    policies = request.app.state.commentary_policies
    policy = policies.get(game_id)
    enabled = bool(policy and policy.enabled and policy.owner_user_id == principal.user_id
        and policy.owner_auth_version == principal.auth_version
        and policy.access_fingerprint == access_fingerprint(game))
    return CommentaryPreference(game_id=game_id, mode="worker", enabled=enabled,
        version=policy.version if policy else 0,
        activation_revision=policy.activation_revision if enabled else None)


@router.get("/games/{game_id}/commentary-preference", response_model=CommentaryPreference)
def read_preference(game_id: str, request: Request, principal=Depends(authenticated), context=Depends(get_context)):
    return preference(request, principal, game_id, context)


@router.post("/games/{game_id}/commentary-preference", response_model=CommentaryPreference)
def save_preference(game_id: str, body: CommentaryPreferenceRequest, request: Request,
                    principal=Depends(authenticated_mutation), context=Depends(get_context)):
    # Check current owner even when the optional runtime is unavailable.
    context.games._owned(principal, game_id)
    if getattr(request.app.state, "commentary_mode", "browser") != "worker":
        raise SecurityError(503, "commentary_worker_disabled")
    policies = request.app.state.commentary_policies
    verify_optional_storage(policies.database)
    CommentaryConsentService(context.games, policies, context.games.clock).set_enabled(
        principal, game_id, body.enabled, body.expected_version)
    return preference(request, principal, game_id, context)
