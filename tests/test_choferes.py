"""Tests de /v1/choferes (vista IA_CHOFERES).

Lo común a todas las vistas (lista blanca de orden, modelo, token, errores de base)
ya lo cubre tests/test_contratos.py."""

import pytest

URL = "/v1/choferes"

FILA = {
    "codigo": "123",
    "nombre": "TEXTO",
    "cuit": "TEXTO",
    "comercial_codigo": "TEXTO",
    "comercial_nombre": "TEXTO",
    "zona": "TEXTO",
    "zona_descripcion": "TEXTO",
    "categoria": 10,
    "categoria_nombre": "TEXTO",
    "activo": "TE",
    "pro_empresa_transporte": "TEXTO",
    "ent_nombre": "TEXTO",
    "pro_carnet_conductor": "TEXTO",
    "pro_patente_camion": "TEXTO",
    "pro_patente_acoplado": "TEXTO",
    "tipo_camion": "TEXTO",
    "pro_kilos_maximos": 10,
}


def test_listado_formato_y_sql(client, fake_db, auth):
    fake_db.total = 1
    fake_db.rows = [FILA]

    response = client.get(URL, headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["data"][0]["codigo"] == FILA["codigo"]
    assert "FROM IA_CHOFERES" in sql
    assert "ORDER BY CODIGO ASC" in sql
    assert binds["min_row"] == 0
    assert binds["max_row"] == 20


def test_filtros_viajan_como_binds(client, fake_db, auth):
    fake_db.total = 1
    malicioso = "X'"
    response = client.get(
        URL,
        params={
            "cuit": malicioso,
            "comercial_codigo": malicioso,
            "zona": malicioso,
            "categoria": 5,
            "activo": malicioso,
            "pro_empresa_transporte": malicioso,
            "pro_patente_camion": malicioso,
        },
        headers=auth,
    )
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert malicioso not in sql
    assert "TRIM(CUIT) = :cuit" in sql
    assert binds["cuit"] == malicioso
    assert "TRIM(COMERCIAL_CODIGO) = :comercial_codigo" in sql
    assert binds["comercial_codigo"] == malicioso
    assert "TRIM(ZONA) = :zona" in sql
    assert binds["zona"] == malicioso
    assert "CATEGORIA = :categoria" in sql
    assert binds["categoria"] == 5
    assert "TRIM(ACTIVO) = :activo" in sql
    assert binds["activo"] == malicioso
    assert "TRIM(PRO_EMPRESA_TRANSPORTE) = :pro_empresa_transporte" in sql
    assert binds["pro_empresa_transporte"] == malicioso
    assert "TRIM(PRO_PATENTE_CAMION) = :pro_patente_camion" in sql
    assert binds["pro_patente_camion"] == malicioso


def test_detalle_existente(client, fake_db, auth):
    fake_db.detail = FILA
    response = client.get(f"{URL}/123", headers=auth)
    sql, binds = fake_db.last("one")

    assert response.status_code == 200, response.text
    assert response.json()["codigo"] == "123"
    assert "WHERE CODIGO = :item_id" in sql
    assert binds == {"item_id": "123"}


def test_detalle_inexistente_404(client, fake_db, auth):
    fake_db.detail = None
    response = client.get(f"{URL}/999", headers=auth)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


@pytest.mark.parametrize("valor", ["xxxxxxxxxxxxxxxxxxxxx", "a b", "1;DROP", "1%27"])
def test_id_invalido_422(client, fake_db, auth, valor):
    assert client.get(f"{URL}/{valor}", headers=auth).status_code == 422
    assert fake_db.calls == []
