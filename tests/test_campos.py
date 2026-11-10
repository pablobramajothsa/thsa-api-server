from typing import get_args

import pytest

from app.routers import campos

FILA = {
    "campo_codigo": 100009,
    "campo_nombre": "LA ESPERANZA",
    "domicilio": "RUTA 5 KM 300",
    "codigo_postal": "6000",
    "cpo_localidad": "JUNIN",
    "kilometros": None,
    "productor_codigo": "P001",
    "productor_nombre": "PRODUCTOR UNO",
    "productor_cuit": "20-00000000-0",
}


def test_listado_formato_y_orden_deterministico(make_client, fake_db, auth):
    client = make_client(view_schema="sysadmin")
    fake_db.total = 1
    fake_db.rows = [FILA]

    response = client.get("/v1/campos", headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["data"][0] == FILA
    assert "FROM SYSADMIN.IA_CAMPOS" in sql
    assert "ORDER BY CAMPO_CODIGO ASC, PRODUCTOR_CODIGO ASC" in sql
    assert binds["min_row"] == 0
    assert binds["max_row"] == 20


def test_orden_por_nombre_desempata_por_clave_compuesta(client, fake_db, auth):
    fake_db.total = 1
    client.get("/v1/campos?sort=productor_nombre&order=desc", headers=auth)
    sql, _ = fake_db.last("all")
    assert "ORDER BY PRODUCTOR_NOMBRE DESC, CAMPO_CODIGO ASC, PRODUCTOR_CODIGO ASC" in sql


def test_filtros_como_binds(client, fake_db, auth):
    fake_db.total = 1
    malicioso = "1' OR '1'='1"
    response = client.get(
        "/v1/campos",
        params={"productor_codigo": "P001", "localidad": malicioso, "codigo_postal": "6000"},
        headers=auth,
    )
    sql, binds = fake_db.last("all")

    assert response.status_code == 200
    assert malicioso not in sql
    assert "TRIM(PRODUCTOR_CODIGO) = :productor_codigo" in sql
    assert "TRIM(CPO_LOCALIDAD) = :localidad" in sql
    assert "TRIM(CODIGO_POSTAL) = :codigo_postal" in sql
    assert binds["localidad"] == malicioso
    assert "productor_cuit" not in binds


@pytest.mark.parametrize(
    "query",
    ["sort=domicilio", "sort=productor_cuit", "productor_codigo=" + "x" * 11, "limit=500"],
)
def test_parametros_invalidos_422(client, fake_db, auth, query):
    assert client.get(f"/v1/campos?{query}", headers=auth).status_code == 422
    assert fake_db.calls == []


def test_espacios_de_relleno_se_quitan_en_filtro_y_respuesta(client, fake_db, auth):
    fake_db.total = 1
    fake_db.rows = [{**FILA, "productor_codigo": "    228", "codigo_postal": "   6000"}]
    response = client.get("/v1/campos", params={"productor_codigo": " 228 "}, headers=auth)
    _, binds = fake_db.last("all")

    assert binds["productor_codigo"] == "228"
    assert response.json()["data"][0]["productor_codigo"] == "228"
    assert response.json()["data"][0]["codigo_postal"] == "6000"


def test_detalle_devuelve_todas_las_filas_del_campo(client, fake_db, auth):
    fake_db.rows = [FILA, {**FILA, "productor_codigo": "P002", "productor_nombre": "DOS"}]
    response = client.get("/v1/campos/100009", headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200
    assert [r["productor_codigo"] for r in response.json()] == ["P001", "P002"]
    assert "WHERE CAMPO_CODIGO = :item_id ORDER BY CAMPO_CODIGO ASC, PRODUCTOR_CODIGO ASC" in sql
    assert binds == {"item_id": 100009}


def test_detalle_inexistente_404(client, fake_db, auth):
    fake_db.rows = []
    response = client.get("/v1/campos/999999", headers=auth)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


@pytest.mark.parametrize("campo", ["0", "10000000", "abc"])
def test_detalle_codigo_invalido_422(client, fake_db, auth, campo):
    assert client.get(f"/v1/campos/{campo}", headers=auth).status_code == 422
    assert fake_db.calls == []


def test_requiere_token(client):
    assert client.get("/v1/campos").status_code == 401
    assert client.get("/v1/campos/100009").status_code == 401


def test_lista_blanca_de_orden_coincide_con_la_vista():
    assert set(get_args(campos.SortField)) == set(campos.SPEC.sort_columns)
