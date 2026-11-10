"""Autenticación con usuario y contraseña (OAuth2 password flow) y tokens JWT.

1. El cliente hace POST /v1/auth/token con `username` y `password` (form-urlencoded).
2. Recibe un `access_token` JWT con vencimiento.
3. Lo envía en cada request: `Authorization: Bearer <token>`.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from app.config import Settings, get_settings
from app.users import MAX_PASSWORD_BYTES, User, UserStore, get_user_store

logger = logging.getLogger("api.auth")

TOKEN_URL = "/v1/auth/token"  # noqa: S105 - es una ruta, no un secreto
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "apis_server"
JWT_AUDIENCE = "apis_server"
BCRYPT_ROUNDS = 12

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl=TOKEN_URL, auto_error=False)

# Hash de una contraseña aleatoria: se verifica contra él cuando el usuario no existe
# para que la respuesta tarde lo mismo y no revele qué usuarios existen.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt(BCRYPT_ROUNDS))


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )


def hash_password(password: str, rounds: int = BCRYPT_ROUNDS) -> bytes:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds))


def verify_password(password: str, password_hash: bytes) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        bcrypt.checkpw(b"x", _DUMMY_HASH)  # mismo costo, resultado descartado
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash)
    except ValueError:
        return False


def authenticate(store: UserStore, username: str, password: str) -> User | None:
    user = store.get(username)
    if user is None or not user.active:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None


def create_access_token(settings: Settings, username: str) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_in = settings.jwt_expire_minutes * 60
    claims = {
        "sub": username,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=expires_in),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(settings: Settings, token: str) -> str:
    """Devuelve el usuario (claim `sub`). Lanza jwt.PyJWTError si el token no es válido."""
    claims = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[JWT_ALGORITHM],  # lista fija: rechaza "none" y otros algoritmos
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        leeway=10,
        options={"require": ["exp", "iat", "sub", "iss", "aud"]},
    )
    subject = claims["sub"]
    if not isinstance(subject, str):
        raise jwt.InvalidTokenError("invalid subject")
    return subject


def require_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[UserStore, Depends(get_user_store)],
    token: Annotated[str | None, Depends(_oauth2_scheme)] = None,
) -> str:
    """Valida el token Bearer y que el usuario siga existiendo y activo."""
    if not token:
        raise unauthorized()
    try:
        username = decode_access_token(settings, token)
    except jwt.PyJWTError as exc:
        logger.info("invalid token", extra={"reason": type(exc).__name__})
        raise unauthorized() from None
    user = store.get(username)
    if user is None or not user.active:
        raise unauthorized()
    request.state.user = username
    return username
