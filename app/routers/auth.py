"""Login: intercambia usuario y contraseña por un token JWT."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.security import TOKEN_URL, authenticate, create_access_token, unauthorized
from app.users import UserStore, get_user_store

logger = logging.getLogger("api.auth")

MAX_USERNAME_LENGTH = 64
MAX_PASSWORD_LENGTH = 128

router = APIRouter(tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - tipo de token OAuth2, no es un secreto
    expires_in: int


@router.post(TOKEN_URL, response_model=TokenResponse)
def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[UserStore, Depends(get_user_store)],
) -> TokenResponse:
    """Recibe `username` y `password` como application/x-www-form-urlencoded."""
    username = form.username
    if len(username) > MAX_USERNAME_LENGTH or len(form.password) > MAX_PASSWORD_LENGTH:
        raise unauthorized()

    user = authenticate(store, username, form.password)
    if user is None:
        # Se loguea el usuario intentado (nunca la contraseña) para detectar abusos.
        logger.warning("login failed", extra={"attempted_user": username})
        raise unauthorized()

    request.state.user = user.username
    token, expires_in = create_access_token(settings, user.username)
    logger.info("login ok", extra={"user": user.username})
    return TokenResponse(access_token=token, expires_in=expires_in)
