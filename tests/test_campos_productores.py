"""Tests de /v1/campos-productores (vista IA_CAMPOS_PRODUCTORES).

Lo común a todas las vistas (lista blanca de orden, modelo, token, errores de base)
ya lo cubre tests/test_contratos.py."""

import pytest

URL = "/v1/campos-productores"

FILA = {
    "campo_codigo": 1,
    "campo_nombre": "TEXTO",
    "productor_codigo": "TEXTO",
    "productor_nombre": "TEXTO",
    "productor_cuit": "TEXTO",
}


def test_listado_formato_y_sql(client, fake_db, auth):
    fake_db.total = 1
    fake_db.rows = [FILA]

    response = client.get(URL, headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["data"][0]["campo_codigo"] == FILA["campo_codigo"]
    assert "FROM IA_CAMPOS_PRODUCTORES" in sql
    assert "ORDER BY CAMPO_CODIGO ASC" in sql
    assert binds["min_row"] == 0
    assert binds["max_row"] == 20


def test_filtros_viajan_como_binds(client, fake_db, auth):
    fake_db.total = 1
    malicioso = "X' OR '1'="
    response = client.get(
        URL, params={"productor_codigo": malicioso, "productor_cuit": malicioso}, headers=auth
    )
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert malicioso not in sql
    assert "TRIM(PRODUCTOR_CODIGO) = :productor_codigo" in sql
    assert binds["productor_codigo"] == malicioso
    assert "TRIM(PRODUCTOR_CUIT) = :productor_cuit" in sql
    assert binds["productor_cuit"] == malicioso


def test_detalle_devuelve_todas_las_filas(client, fake_db, auth):
    fake_db.rows = [FILA]
    response = client.get(f"{URL}/1", headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert "WHERE CAMPO_CODIGO = :item_id" in sql
    assert binds == {"item_id": 1}


def test_detalle_inexistente_404(client, fake_db, auth):
    fake_db.rows = []
    response = client.get(f"{URL}/999", headers=auth)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


@pytest.mark.parametrize("valor", ["0", "-1", "abc", "1.5"])
def test_id_invalido_422(client, fake_db, auth, valor):
    assert client.get(f"{URL}/{valor}", headers=auth).status_code == 422
    assert fake_db.calls == []
