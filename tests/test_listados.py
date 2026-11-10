from datetime import date, datetime
from typing import get_args

import pytest

from app.routers import clientes, productos

PRODUCTO = {
    "id": 7,
    "nombre": "Tornillo",
    "categoria": "FERRETERIA",
    "precio": 12.5,
    "fecha_alta": datetime(2024, 1, 15, 10, 30),
}


def test_formato_de_respuesta(client, fake_db, auth):
    fake_db.total = 1
    fake_db.rows = [PRODUCTO]
    response = client.get("/v1/productos", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"page", "limit", "total", "data"}
    assert body["page"] == 1
    assert body["limit"] == 20
    assert body["total"] == 1
    assert body["data"][0]["nombre"] == "Tornillo"
    assert all(key == key.lower() for key in body["data"][0])


def test_paginacion_por_defecto_usa_rownum(client, fake_db, auth):
    fake_db.total = 100
    client.get("/v1/productos", headers=auth)
    sql, binds = fake_db.last("all")

    assert "ROWNUM <= :max_row" in sql
    assert "rn__ > :min_row" in sql
    assert "OFFSET" not in sql  # no existe en Oracle 11g
    assert binds["min_row"] == 0
    assert binds["max_row"] == 20


def test_paginacion_pagina_3_limite_10(client, fake_db, auth):
    fake_db.total = 100
    response = client.get("/v1/productos?page=3&limit=10", headers=auth)
    _, binds = fake_db.last("all")

    assert response.json()["page"] == 3
    assert binds["min_row"] == 20
    assert binds["max_row"] == 30


def test_pagina_fuera_de_rango_no_consulta_filas(client, fake_db, auth):
    fake_db.total = 5
    response = client.get("/v1/productos?page=2&limit=10", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert all(kind != "all" for kind, _, _ in fake_db.calls)


@pytest.mark.parametrize(
    "query",
    ["page=0", "page=-1", "page=abc", "limit=0", "limit=101", "limit=-5", "page=1000001"],
)
def test_paginacion_invalida_devuelve_422(client, auth, query):
    response = client.get(f"/v1/productos?{query}", headers=auth)
    assert response.status_code == 422


def test_limite_maximo_permitido(client, fake_db, auth):
    fake_db.total = 500
    response = client.get("/v1/productos?limit=100", headers=auth)
    assert response.status_code == 200
    assert fake_db.last("all")[1]["max_row"] == 100


def test_orden_por_defecto_es_deterministico(client, fake_db, auth):
    fake_db.total = 1
    client.get("/v1/productos", headers=auth)
    sql, _ = fake_db.last("all")
    assert "ORDER BY ID ASC" in sql


def test_orden_por_columna_de_lista_blanca(client, fake_db, auth):
    fake_db.total = 1
    response = client.get("/v1/productos?sort=precio&order=desc", headers=auth)
    sql, _ = fake_db.last("all")

    assert response.status_code == 200
    assert "ORDER BY PRECIO DESC, ID ASC" in sql


@pytest.mark.parametrize("sort", ["password", "ID; DROP TABLE x", "1", "nombre desc"])
def test_orden_fuera_de_lista_blanca_devuelve_422(client, fake_db, auth, sort):
    response = client.get("/v1/productos", params={"sort": sort}, headers=auth)
    assert response.status_code == 422
    assert fake_db.calls == []


def test_orden_direccion_invalida_devuelve_422(client, auth):
    response = client.get("/v1/productos?order=sideways", headers=auth)
    assert response.status_code == 422


def test_filtros_viajan_como_binds(client, fake_db, auth):
    fake_db.total = 1
    malicioso = "X' OR '1'='1"
    response = client.get(
        "/v1/productos",
        params={"categoria": malicioso, "fecha_desde": "2024-01-01", "fecha_hasta": "2024-01-31"},
        headers=auth,
    )
    sql, binds = fake_db.last("all")
    count_sql, count_binds = fake_db.last("scalar")

    assert response.status_code == 200
    assert malicioso not in sql
    assert malicioso not in count_sql
    assert "CATEGORIA = :categoria" in sql
    assert "FECHA_ALTA >= :fecha_desde" in sql
    assert "FECHA_ALTA < :fecha_hasta_excl" in sql
    assert binds["categoria"] == malicioso
    assert binds["fecha_desde"] == date(2024, 1, 1)
    # fecha_hasta es inclusiva: se compara contra el día siguiente.
    assert binds["fecha_hasta_excl"] == date(2024, 2, 1)
    assert count_binds == {k: v for k, v in binds.items() if k not in ("min_row", "max_row")}


def test_sin_filtros_no_hay_where_ni_binds_extra(client, fake_db, auth):
    fake_db.total = 1
    client.get("/v1/productos", headers=auth)
    count_sql, count_binds = fake_db.last("scalar")

    assert "WHERE" not in count_sql
    assert count_binds == {}


def test_rango_de_fechas_invertido_devuelve_422(client, fake_db, auth):
    response = client.get(
        "/v1/productos?fecha_desde=2024-02-01&fecha_hasta=2024-01-01", headers=auth
    )
    assert response.status_code == 422
    assert fake_db.calls == []


def test_fecha_invalida_devuelve_422(client, auth):
    response = client.get("/v1/productos?fecha_desde=31-01-2024", headers=auth)
    assert response.status_code == 422


def test_esquema_configurado_califica_la_vista(make_client, fake_db, auth):
    client = make_client(view_schema="app_owner")
    fake_db.total = 1
    client.get("/v1/productos", headers=auth)
    assert "FROM APP_OWNER.V_PRODUCTOS" in fake_db.last("all")[0]


def test_listado_clientes(client, fake_db, auth):
    fake_db.total = 1
    fake_db.rows = [{"id": 1, "razon_social": "ACME SA", "categoria": "A", "fecha_alta": None}]
    response = client.get("/v1/clientes?sort=razon_social", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"][0]["razon_social"] == "ACME SA"
    assert "FROM V_CLIENTES" in fake_db.last("all")[0]
    assert "ORDER BY RAZON_SOCIAL ASC, ID ASC" in fake_db.last("all")[0]


@pytest.mark.parametrize("module", [productos, clientes])
def test_lista_blanca_de_orden_coincide_con_la_vista(module):
    assert set(get_args(module.SortField)) == set(module.SPEC.sort_columns)


def test_esquema_propio_de_la_vista_tiene_prioridad():
    from app.query import ViewSpec

    spec = ViewSpec(view="V_X", columns=("ID",), id_column="ID", sort_columns={}, schema="OTRO")
    assert spec.source("app_owner") == "OTRO.V_X"
    assert ViewSpec(view="V_X", columns=("ID",), id_column="ID", sort_columns={}).source(
        "APP_OWNER"
    ) == ("APP_OWNER.V_X")


def test_esquema_propio_invalido_falla_al_definirse():
    from app.query import ViewSpec

    with pytest.raises(ValueError, match="identifier"):
        ViewSpec(view="V_X", columns=("ID",), id_column="ID", sort_columns={}, schema="A; DROP")
