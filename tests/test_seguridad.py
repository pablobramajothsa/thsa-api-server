import pytest
from pydantic import ValidationError

from tests.conftest import JWT_SECRET, make_settings


def test_rate_limit_responde_429(make_client, fake_db, auth):
    client = make_client(rate_limit="3/minute")
    fake_db.total = 0

    statuses = [client.get("/v1/productos", headers=auth).status_code for _ in range(4)]

    assert statuses == [200, 200, 200, 429]
    last = client.get("/v1/productos", headers=auth)
    assert last.json() == {"detail": "Too many requests"}
    assert 1 <= int(last.headers["Retry-After"]) <= 60
    # La respuesta 429 también lleva request id y headers de seguridad.
    assert "X-Request-ID" in last.headers
    assert last.headers["X-Content-Type-Options"] == "nosniff"


def test_rate_limit_es_global_por_ip(make_client, auth):
    client = make_client(rate_limit="2/minute")
    assert client.get("/v1/productos", headers=auth).status_code == 200
    assert client.get("/v1/clientes", headers=auth).status_code == 200
    assert client.get("/health").status_code == 429


def test_rate_limit_aplica_aunque_falte_el_token(make_client):
    client = make_client(rate_limit="2/minute")
    statuses = [client.get("/v1/productos").status_code for _ in range(3)]
    assert statuses == [401, 401, 429]


def test_headers_de_seguridad(client, auth):
    response = client.get("/v1/productos", headers=auth)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert len(response.headers["X-Request-ID"]) == 32


def test_hsts_solo_en_produccion(make_client, auth):
    assert "Strict-Transport-Security" not in make_client().get("/health").headers
    assert "Strict-Transport-Security" in make_client(env="production").get("/health").headers


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_desactivadas_en_produccion(make_client, path):
    assert make_client(env="production").get(path).status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/openapi.json"])
def test_docs_activas_en_desarrollo(make_client, path):
    assert make_client(env="development").get(path).status_code == 200


def test_cors_permite_solo_origenes_configurados(client, auth):
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    denied = client.get("/health", headers={"Origin": "https://malicioso.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_cors_preflight_solo_get(client):
    response = client.options(
        "/v1/productos",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "DELETE",
        },
    )
    assert response.status_code == 400


@pytest.mark.parametrize("origins", ["*", "http://localhost:3000,*", "https://*.example.com"])
def test_cors_rechaza_comodin(origins):
    with pytest.raises(ValidationError):
        make_settings(cors_origins=origins)


@pytest.mark.parametrize("secret", ["", "corto", "x" * 31])
def test_jwt_secret_obligatorio_y_largo(secret):
    with pytest.raises(ValidationError):
        make_settings(jwt_secret=secret)


def test_view_schema_debe_ser_identificador():
    with pytest.raises(ValidationError):
        make_settings(view_schema="APP; DROP USER x")


def test_settings_no_exponen_secretos():
    settings = make_settings(db_password="super-secreta")
    assert "super-secreta" not in repr(settings)
    assert JWT_SECRET not in repr(settings)
