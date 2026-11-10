"""Administración de usuarios de la API (archivo users.json con hashes bcrypt).

Uso (desde la carpeta del proyecto):

    .venv\\Scripts\\python scripts\\manage_users.py add sistema-a        # pide la contraseña
    .venv\\Scripts\\python scripts\\manage_users.py passwd sistema-a     # cambia la contraseña
    .venv\\Scripts\\python scripts\\manage_users.py disable sistema-a    # bloquea (y sus tokens)
    .venv\\Scripts\\python scripts\\manage_users.py enable sistema-a
    .venv\\Scripts\\python scripts\\manage_users.py remove sistema-a
    .venv\\Scripts\\python scripts\\manage_users.py list

Opciones:
    --file RUTA         archivo de usuarios (default: USERS_FILE del .env, o users.json)
    --password-stdin    lee la contraseña de la entrada estándar en vez de pedirla

La API relee el archivo automáticamente: no hace falta reiniciarla.
"""

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.security import hash_password  # noqa: E402
from app.users import (  # noqa: E402
    MAX_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    USERNAME_PATTERN,
    User,
    read_users_file,
    write_users_file,
)


def _default_users_file() -> Path:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("USERS_FILE=") and line.split("=", 1)[1].strip():
                path = Path(line.split("=", 1)[1].strip())
                return path if path.is_absolute() else ROOT / path
    return ROOT / "users.json"


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Contraseña: ")
        if getpass.getpass("Repetir contraseña: ") != password:
            sys.exit("Las contraseñas no coinciden.")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        sys.exit(f"La contraseña no puede superar {MAX_PASSWORD_BYTES} bytes.")
    return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Administra los usuarios de la API.")
    parser.add_argument("command", choices=["add", "passwd", "disable", "enable", "remove", "list"])
    parser.add_argument("username", nargs="?")
    parser.add_argument("--file", type=Path, default=None)
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()

    path: Path = args.file or _default_users_file()
    users: dict[str, User] = read_users_file(path) if path.exists() else {}

    if args.command == "list":
        if not users:
            print(f"Sin usuarios en {path}")
        for user in sorted(users.values(), key=lambda u: u.username):
            print(f"{user.username:<30} {'activo' if user.active else 'DESACTIVADO'}")
        return

    username = args.username
    if not username or not USERNAME_PATTERN.fullmatch(username):
        sys.exit("Usuario inválido: 3 a 64 caracteres (letras, números, punto, guion, guion bajo).")

    if args.command == "add":
        if username in users:
            sys.exit(
                f"El usuario '{username}' ya existe. Usar 'passwd' para cambiar la contraseña."
            )
        users[username] = User(username, hash_password(_read_password(args.password_stdin)))
    else:
        if username not in users:
            sys.exit(f"El usuario '{username}' no existe.")
        current = users[username]
        if args.command == "passwd":
            new_hash = hash_password(_read_password(args.password_stdin))
            users[username] = User(username, new_hash, current.active)
        elif args.command in ("disable", "enable"):
            users[username] = User(username, current.password_hash, args.command == "enable")
        elif args.command == "remove":
            del users[username]

    write_users_file(path, users)
    print(f"OK: {args.command} {username} ({path})")


if __name__ == "__main__":
    main()
