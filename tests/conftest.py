"""Fixtures: la base de datos se reemplaza por un fake en memoria (no hay Oracle)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import hash_password

# Credenciales ficticias, solo para tests.
TEST_USER = "sistema-test"
TEST_PASSWORD = "contraseña-de-prueba-1"
OTHER_USER = "sistema-otro"
OTHER_PASSWORD = "otra-contraseña-de-prueba"
INACTIVE_USER = "sistema-baja"
INACTIVE_PASSWORD = "contraseña-usuario-baja"
JWT_SECRET = "secreto-jwt-solo-para-tests-0000000000000001"
TOKEN_URL = "/v1/auth/token"


class FakeDatabase:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.total = 0
        self.detail: dict[str, Any] | None = None
        self.ping_result: Any = 1
        self.error: Exception | None = None
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def _record(self, kind: str, sql: str, binds: Any) -> None:
        self.calls.append((kind, sql, dict(binds)))
        if self.error is not None:
            raise self.error

    def fetch_all(self, sql: str, binds: Any) -> list[dict[str, Any]]:
        self._record("all", sql, binds)
        return list(self.rows)

    def fetch_one(self, sql: str, binds: Any) -> dict[str, Any] | None:
        self._record("one", sql, binds)
        return self.detail

    def scalar(self, sql: str, binds: Any) -> Any:
        self._record("scalar", sql, binds)
        return self.total if "COUNT(*)" in sql else self.ping_result

    def close(self) -> None:
        pass

    def last(self, kind: str) -> tuple[str, dict[str, Any]]:
        for call_kind, sql, binds in reversed(self.calls):
            if call_kind == kind:
                return sql, binds
        raise AssertionError(f"no {kind} call recorded")


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "env": "test",
        "jwt_secret": JWT_SECRET,
        "users_file": "no-existe-users.json",
        "rate_limit": "1000/minute",
        "cors_origins": "http://localhost:3000",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def fake_db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture(scope="session")
def password_hashes() -> dict[str, str]:
    # rounds=4: hashes válidos pero baratos, para que los tests sean rápidos.
    return {
        user: hash_password(password, rounds=4).decode("ascii")
        for user, password in (
            (TEST_USER, TEST_PASSWORD),
            (OTHER_USER, OTHER_PASSWORD),
            (INACTIVE_USER, INACTIVE_PASSWORD),
        )
    }


def write_users(path: Path, entries: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"users": entries}), encoding="utf-8")


@pytest.fixture
def users_file(tmp_path: Path, password_hashes: dict[str, str]) -> Path:
    path = tmp_path / "users.json"
    write_users(
        path,
        [
            {"username": TEST_USER, "password_hash": password_hashes[TEST_USER]},
            {"username": OTHER_USER, "password_hash": password_hashes[OTHER_USER]},
            {
                "username": INACTIVE_USER,
                "password_hash": password_hashes[INACTIVE_USER],
                "active": False,
            },
        ],
    )
    return path


@pytest.fixture
def make_client(fake_db: FakeDatabase, users_file: Path) -> Callable[..., TestClient]:
    def _make(**overrides: Any) -> TestClient:
        overrides.setdefault("users_file", str(users_file))
        return TestClient(create_app(make_settings(**overrides), database=fake_db))

    return _make


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()


def login(client: TestClient, username: str = TEST_USER, password: str = TEST_PASSWORD):
    return client.post(TOKEN_URL, data={"username": username, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def token(client: TestClient) -> str:
    response = login(client)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def auth(token: str) -> dict[str, str]:
    return bearer(token)
