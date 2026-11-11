"""Tests de /v1/catac (vista IA_CATAC).

Lo común a todas las vistas (lista blanca de orden, modelo, token, errores de base)
ya lo cubre tests/test_contratos.py."""

from datetime import datetime

URL = "/v1/catac"

FILA = {
    "tarifa_codigo": 1,
    "tarifa_nombre": "TEXTO",
    "fecha_vigencia_desde": datetime(2024, 1, 15, 10, 30),
    "kilometros": 10,
    "tarifa_por_tn": 1.5,
    "segunda_tarifa": 1.5,
}


def test_listado_formato_y_sql(client, fake_db, auth):
    fake_db.total = 1
    fake_db.rows = [FILA]

    response = client.get(URL, headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["data"][0]["tarifa_codigo"] == FILA["tarifa_codigo"]
    assert "FROM IA_CATAC" in sql
    assert "ORDER BY TARIFA_CODIGO ASC" in sql
    assert binds["min_row"] == 0
    assert binds["max_row"] == 20


def test_filtros_viajan_como_binds(client, fake_db, auth):
    fake_db.total = 1
    malicioso = "X' OR '1'='1"
    response = client.get(URL, params={"tarifa_codigo": 5, "kilometros": 5}, headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert malicioso not in sql
    assert "TARIFA_CODIGO = :tarifa_codigo" in sql
    assert binds["tarifa_codigo"] == 5
    assert "KILOMETROS = :kilometros" in sql
    assert binds["kilometros"] == 5


def test_rango_de_fechas(client, fake_db, auth):
    fake_db.total = 1
    response = client.get(
        URL, params={"fecha_desde": "2024-01-01", "fecha_hasta": "2024-01-31"}, headers=auth
    )
    sql, _ = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert "FECHA_VIGENCIA_DESDE >= :fecha_desde" in sql
    assert "FECHA_VIGENCIA_DESDE < :fecha_hasta_excl" in sql


def test_no_hay_detalle(client, fake_db, auth):
    assert client.get(f"{URL}/1", headers=auth).status_code == 404
    assert fake_db.calls == []
