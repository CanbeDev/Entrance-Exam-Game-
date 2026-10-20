from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import Field

from app.api.dependencies import authenticated, authenticated_mutation, get_context
from app.models.actions import ActionCommand, FrozenModel
from app.models.game import GameSetupRequest
from app.models.game_api import PublicGameList, PublicGame, PublicActionResult, PublicEventPage
from app.services.public_game_service import public_game, public_result

router = APIRouter(tags=["game sessions"])


class NpcStepRequest(FrozenModel):
    expected_revision: int = Field(ge=0, strict=True)


@router.post("/games", status_code=201, response_model=PublicGame, response_model_exclude_unset=True)
def create_game(request: GameSetupRequest,
                idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1,
                                                       max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")],
                principal=Depends(authenticated_mutation), context=Depends(get_context)):
    return public_game(context.games.create_game(principal, request, idempotency_key))


@router.get("/me/games", response_model=PublicGameList, response_model_exclude_unset=True)
def list_games(status: Literal["waiting", "active", "completed"] | None = None,
               query: Annotated[str, Query(max_length=100)] = "",
               cursor: Annotated[str | None, Query(pattern=r"^[0-9a-fA-F]{24}$")] = None,
               limit: Annotated[int, Query(ge=1, le=100)] = 20,
               principal=Depends(authenticated), context=Depends(get_context)):
    result = context.games.list_games(principal, status=status, query=query, cursor=cursor, limit=limit)
    data = {"games": [public_game(game) for game in result["games"]], "next_cursor": result["next_cursor"]}
    return PublicGameList.model_validate(data).model_dump(mode="json", by_alias=True, exclude_unset=True)


@router.post("/games/{game_id}/actions", response_model=PublicActionResult, response_model_exclude_unset=True)
def human_action(game_id: str, command: ActionCommand,
                 principal=Depends(authenticated_mutation), context=Depends(get_context)):
    return public_result(context.games.human_action(principal, game_id, command))


@router.post("/games/{game_id}/npc-steps", response_model=PublicActionResult, response_model_exclude_unset=True)
def npc_step(game_id: str, request: NpcStepRequest,
             principal=Depends(authenticated_mutation), context=Depends(get_context)):
    return public_result(context.games.npc_step(principal, game_id, request.expected_revision))


@router.get("/games/{game_id}/events", response_model=PublicEventPage, response_model_exclude_unset=True)
def events(game_id: str, after_revision: Annotated[int, Query(ge=0)] = 0,
           limit: Annotated[int, Query(ge=1, le=100)] = 20,
           context=Depends(get_context)):
    return context.games.events(game_id, after_revision=after_revision, limit=limit)
