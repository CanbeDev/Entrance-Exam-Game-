from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.api.dependencies import authenticated_mutation
from app.models.commentary import BattleCommentary, CommentaryRequest
from app.security.errors import SecurityError

router = APIRouter(tags=["AI battle commentary"])


def commentary_service(request: Request):
    service = getattr(request.app.state, "commentary", None)
    if service is None:
        raise SecurityError(503, "commentary_unavailable")
    return service


@router.get("/games/{game_id}/commentary/{revision}", response_model=BattleCommentary)
def read_commentary(game_id: str, revision: Annotated[int, Path(ge=1)], service=Depends(commentary_service)):
    return service.read(game_id, revision)


@router.post("/games/{game_id}/commentary/{revision}", response_model=BattleCommentary)
async def generate_commentary(game_id: str, revision: Annotated[int, Path(ge=1)], body: CommentaryRequest,
                              principal=Depends(authenticated_mutation), service=Depends(commentary_service)):
    return await service.generate(principal, game_id, revision)
