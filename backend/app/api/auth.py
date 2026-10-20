from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import (authenticated, authenticated_mutation, client_ip, get_context)
from app.models.auth import Credentials, UserPublic

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", status_code=201, response_model=UserPublic)
def register(credentials: Credentials, request: Request, context=Depends(get_context)):
    return context.auth.register(credentials, client_ip(request))


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response, context=Depends(get_context)):
    result = context.auth.login(credentials, client_ip(request),
                                previous_token=request.cookies.get(context.settings.cookie_name))
    response.set_cookie(key=context.settings.cookie_name, value=result.token,
                        max_age=context.settings.absolute_seconds, expires=result.expires_at,
                        path="/", secure=True, httponly=True, samesite="lax")
    return {"user": result.user.model_dump(), "expires_at": result.expires_at}


@router.post("/logout", status_code=204)
def logout(response: Response, principal=Depends(authenticated_mutation), context=Depends(get_context)):
    context.auth.logout(principal)
    response.delete_cookie(context.settings.cookie_name, path="/", secure=True,
                           httponly=True, samesite="lax")
    response.status_code = 204
    return response


@router.get("/me")
def me(principal=Depends(authenticated)):
    return UserPublic(id=principal.user_id, username=principal.username)


@router.get("/csrf")
def csrf(principal=Depends(authenticated)):
    return {"csrf_token": principal.csrf_token}
