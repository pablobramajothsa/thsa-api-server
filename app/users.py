"""Usuarios de la API, leídos de un archivo JSON con contraseñas hasheadas (bcrypt).

Formato del archivo (administrarlo con scripts/manage_users.py):

    {"users": [{"username": "sistema-a", "password_hash": "$2b$12$...", "active": true}]}

El archivo se relee automáticamente cuando cambia, así que dar de alta, cambiar la
contraseña o desactivar un usuario no requiere reiniciar la API. Desactivar un usuario
invalida en el acto los tokens que ya tenga.
"""

import json
import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

logger = logging.getLogger("api.users")

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
MAX_PASSWORD_BYTES = 72  # límite de bcrypt
MIN_PASSWORD_LENGTH = 12


class UsersFileError(ValueError):
    pass


@dataclass(frozen=True)
class User:
    username: str
    password_hash: bytes
    active: bool = True


def parse_users(raw: object) -> dict[str, User]:
    if not isinstance(raw, dict) or not isinstance(raw.get("users"), list):
        raise UsersFileError("users file must be an object with a 'users' list")
    users: dict[str, User] = {}
    for index, entry in enumerate(raw["users"]):
        if not isinstance(entry, dict):
            raise UsersFileError(f"users[{index}] must be an object")
        username = entry.get("username")
        password_hash = entry.get("password_hash")
        active = entry.get("active", True)
        if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username):
            raise UsersFileError(f"users[{index}]: invalid username")
        if not isinstance(password_hash, str) or not password_hash.startswith("$2"):
            raise UsersFileError(f"users[{index}]: password_hash must be a bcrypt hash")
        if not isinstance(active, bool):
            raise UsersFileError(f"users[{index}]: active must be true or false")
        if username in users:
            raise UsersFileError(f"duplicate username '{username}'")
        users[username] = User(username, password_hash.encode("ascii"), active)
    return users


def read_users_file(path: Path) -> dict[str, User]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UsersFileError(f"invalid JSON in users file: {exc.msg}") from None
    return parse_users(raw)


def write_users_file(path: Path, users: dict[str, User]) -> None:
    """Escritura atómica: se escribe un temporal y se reemplaza el archivo."""
    payload = {
        "users": [
            {
                "username": u.username,
                "password_hash": u.password_hash.decode("ascii"),
                "active": u.active,
            }
            for u in sorted(users.values(), key=lambda u: u.username)
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".users-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(payload, tmp, indent=2)
            tmp.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class UserStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._users: dict[str, User] = {}
        self._mtime: int | None = None
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> int:
        """Carga inicial. Lanza UsersFileError si el archivo existe pero es inválido."""
        with self._lock:
            self._reload(strict=True)
            return len(self._users)

    def get_count(self) -> int:
        with self._lock:
            self._reload(strict=False)
            return len(self._users)

    def get(self, username: str) -> User | None:
        with self._lock:
            self._reload(strict=False)
            return self._users.get(username)

    def _reload(self, *, strict: bool) -> None:
        try:
            mtime = self._path.stat().st_mtime_ns
        except FileNotFoundError:
            if self._mtime is not None or strict:
                logger.warning("users file not found", extra={"users_file": str(self._path)})
            self._users, self._mtime = {}, None
            return
        if mtime == self._mtime:
            return
        try:
            self._users = read_users_file(self._path)
            self._mtime = mtime
            logger.info("users file loaded", extra={"users": len(self._users)})
        except (OSError, UsersFileError):
            if strict:
                raise
            # Se conservan los usuarios anteriores para no dejar la API sin acceso.
            logger.exception("users file could not be reloaded; keeping previous users")


def get_user_store(request: Request) -> UserStore:
    return request.app.state.users
