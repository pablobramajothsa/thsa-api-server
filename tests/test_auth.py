import logging
import os
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.main import create_app
from app.security import JWT_ALGORITHM, JWT_AUDIENCE, JWT_ISSUER
from app.users import UsersFileError
from tests.conftest import (
    INACTIVE_PASSWORD,
    INACTIVE_USER,
    JWT_SECRET,
    OTHER_PASSWORD,
    OTHER_USER,
    TEST_PASSWORD,
    TEST_USER,
    TOKEN_URL,
    bearer,
    login,
    make_settings,
    write_users,
)


def _token(sub=TEST_USER, secret=JWT_SECRET, algorithm=JWT_ALGORITHM, **claims):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    payload.update(claims)
    return jwt.encode(payload, secret, algorithm=algorithm)


# --- Login -----------------------------------------------------------------


def test_login_correcto_devuelve_token(client):
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 30 * 60
    claims = jwt.decode(
        body["access_token"], JWT_SECRET, algorithms=[JWT_ALGORITHM], audience=JWT_AUDIENCE
    )
    assert claims["sub"] == TEST_USER
    assert claims["iss"] == JWT_ISSUER


def test_duracion_del_token_configurable(make_client):
    response = login(make_client(jwt_expire_minutes=5))
    assert response.json()["expires_in"] == 300


@pytest.mark.parametrize(
    ("username", "password"),
    [
        (TEST_USER, "contraseña-incorrecta"),
        ("no-existe", TEST_PASSWORD),
        (INACTIVE_USER, INACTIVE_PASSWORD),
        (TEST_USER, "x" * 200),
        ("u" * 100, TEST_PASSWORD),
    ],
)
def test_login_invalido_devuelve_401_generico(client, username, password):
    response = login(client, username, password)

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_requiere_formulario(client):
    # JSON en vez de application/x-www-form-urlencoded
    response = client.post(TOKEN_URL, json={"username": TEST_USER, "password": TEST_PASSWORD})
    assert response.status_code == 422


@pytest.mark.parametrize(
    "data",
    [{"username": TEST_USER}, {"password": TEST_PASSWORD}, {"username": TEST_USER, "password": ""}],
)
def test_login_sin_campos_devuelve_422(client, data):
    assert client.post(TOKEN_URL, data=data).status_code == 422


def test_login_solo_acepta_post(client):
    assert client.get(TOKEN_URL).status_code == 405


def test_login_con_varios_usuarios(client):
    assert login(client, OTHER_USER, OTHER_PASSWORD).status_code == 200


def test_login_tiene_rate_limit_propio(make_client):
    client = make_client(login_rate_limit="3/minute")
    statuses = [login(client, TEST_USER, "mal").status_code for _ in range(4)]

    assert statuses == [401, 401, 401, 429]
    # El resto de la API no queda bloqueado por el límite del login.
    assert client.get("/health").status_code == 200


def test_logs_de_login_no_incluyen_la_contrasena(client, caplog):
    caplog.set_level(logging.INFO)
    login(client)
    login(client, TEST_USER, "contraseña-incorrecta-xyz")

    assert TEST_PASSWORD not in caplog.text
    assert "contraseña-incorrecta-xyz" not in caplog.text
    failed = [r for r in caplog.records if r.getMessage() == "login failed"]
    assert failed
    assert failed[0].attempted_user == TEST_USER


# --- Uso del token ---------------------------------------------------------


@pytest.mark.parametrize("path", ["/v1/productos", "/v1/productos/1", "/v1/clientes"])
def test_sin_token_devuelve_401(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_token_valido_devuelve_200(client, fake_db, auth):
    fake_db.total = 0
    assert client.get("/v1/productos", headers=auth).status_code == 200
    assert client.get("/v1/clientes", headers=auth).status_code == 200


@pytest.mark.parametrize(
    "token",
    [
        "abc",
        "Bearer",
        _token(secret="otro-secreto-distinto-al-del-servidor-000000"),
        _token(exp=datetime.now(timezone.utc) - timedelta(minutes=5)),
        _token(aud="otra-api"),
        _token(iss="otro-emisor"),
        _token(sub="no-existe"),
        _token(sub=INACTIVE_USER),
        _token(algorithm="HS512", secret=JWT_SECRET * 2),  # clave >= 64 bytes para HS512
    ],
    ids=[
        "basura",
        "vacio",
        "firma-incorrecta",
        "vencido",
        "audiencia",
        "emisor",
        "usuario-inexistente",
        "usuario-inactivo",
        "algoritmo",
    ],
)
def test_token_invalido_devuelve_401(client, token):
    response = client.get("/v1/productos", headers=bearer(token))
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_token_sin_firma_alg_none_es_rechazado(client):
    unsigned = jwt.encode(
        {"sub": TEST_USER, "iss": JWT_ISSUER, "aud": JWT_AUDIENCE, "exp": 9999999999, "iat": 0},
        key=None,
        algorithm="none",
    )
    assert client.get("/v1/productos", headers=bearer(unsigned)).status_code == 401


def test_esquema_distinto_de_bearer_es_rechazado(client, token):
    assert (
        client.get("/v1/productos", headers={"Authorization": f"Basic {token}"}).status_code == 401
    )
    assert client.get("/v1/productos", headers={"X-API-Key": token}).status_code == 401


# --- Cambios en el archivo de usuarios -------------------------------------


def _touch_later(path):
    """Asegura que el cambio de mtime se detecte aunque el FS tenga poca resolución."""
    later = time.time() + 5
    os.utime(path, (later, later))


def test_desactivar_usuario_invalida_sus_tokens(client, fake_db, auth, users_file, password_hashes):
    fake_db.total = 0
    assert client.get("/v1/productos", headers=auth).status_code == 200

    write_users(
        users_file,
        [{"username": TEST_USER, "password_hash": password_hashes[TEST_USER], "active": False}],
    )
    _touch_later(users_file)

    assert client.get("/v1/productos", headers=auth).status_code == 401
    assert login(client).status_code == 401


def test_usuario_nuevo_puede_loguearse_sin_reiniciar(client, users_file, password_hashes):
    assert login(client, "sistema-nuevo", TEST_PASSWORD).status_code == 401

    write_users(
        users_file,
        [{"username": "sistema-nuevo", "password_hash": password_hashes[TEST_USER]}],
    )
    _touch_later(users_file)

    assert login(client, "sistema-nuevo", TEST_PASSWORD).status_code == 200


def test_archivo_corrupto_en_caliente_conserva_usuarios(client, users_file):
    users_file.write_text("{ esto no es json", encoding="utf-8")
    _touch_later(users_file)
    assert login(client).status_code == 200


def test_archivo_de_usuarios_invalido_impide_arrancar(tmp_path):
    bad = tmp_path / "users.json"
    bad.write_text('{"users": [{"username": "x", "password_hash": "texto-plano"}]}')
    with pytest.raises(UsersFileError):
        create_app(make_settings(users_file=str(bad)))


def test_sin_archivo_de_usuarios_todo_devuelve_401(make_client, tmp_path):
    client = make_client(users_file=str(tmp_path / "no-existe.json"))
    assert login(client).status_code == 401


# --- Logs --------------------------------------------------------------------


def test_log_de_acceso_registra_usuario_y_no_el_token(client, fake_db, auth, token, caplog):
    caplog.set_level(logging.INFO, logger="api.access")
    client.get("/v1/productos", headers=auth)

    records = [r for r in caplog.records if r.name == "api.access"]
    assert records, "no se registró el acceso"
    record = records[-1]
    assert record.user == TEST_USER
    assert record.status == 200
    assert token not in str(record.__dict__)


def test_health_no_requiere_token(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
