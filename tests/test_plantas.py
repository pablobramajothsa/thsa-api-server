"""Tests de /v1/plantas (vista IA_PLANTAS).

Lo común a todas las vistas (lista blanca de orden, modelo, token, errores de base)
ya lo cubre tests/test_contratos.py."""

import pytest

URL = "/v1/plantas"

FILA = {
    "pla_planta": 1,
    "pla_descripcion": "TEXTO",
    "pla_dom_calle": "TEXTO",
    "pla_dom_numero": "TEXTO",
    "pla_dom_piso": "TEXTO",
    "pla_dom_depto": "TEXTO",
    "pla_codigo_postal": 10,
    "pla_sufijo_postal": "T",
    "pla_telefonos": "TEXTO",
    "pla_fax": "TEXTO",
    "pla_e_mail": "TEXTO",
    "pla_delegacion_sagpya": "TEX",
    "pla_capacidad": 10,
    "pla_talonario_1116a": 10,
    "pla_talonario_1116b": 10,
    "pla_talonario_1116c": 10,
    "pla_talonario_int_1116a": 10,
    "pla_talonario_int_1116b": 10,
    "pla_talonario_int_1116c": 10,
    "pla_planta_c14": 10,
    "pla_numero_oncca": 10,
    "pla_planta_agrupacion": 10,
    "pla_sucursal_opera": "TEXTO",
    "pla_talonario_1116rt": 10,
    "pla_talonario_int_1116rt": 10,
    "pla_talonario_cartas_porte": 10,
    "pla_talonario_1116a_pp": 10,
    "pla_talonario_int_1116a_pp": 10,
    "pla_talonario_1116bc_pp": 10,
    "pla_talonario_int_1116bc_pp": 10,
    "pla_lugar_descarga": "TEX",
    "pla_puerto": "TE",
    "pla_entregador": "TEXTO",
    "pla_destinatario": "TEXTO",
    "pla_destino": "TEXTO",
    "pla_punto_ingreso": 10,
    "pla_inactivo": "TE",
    "pla_municipio": "TEX",
    "pla_especie_exclusiva": "TEXT",
    "pla_diferencial_flete": 1.5,
    "pla_destino_control_flete": "TEXTO",
    "pla_planta_directo": "TE",
    "pla_terceros": "TE",
}


def test_listado_formato_y_sql(client, fake_db, auth):
    fake_db.total = 1
    fake_db.rows = [FILA]

    response = client.get(URL, headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["data"][0]["pla_planta"] == FILA["pla_planta"]
    assert "FROM IA_PLANTAS" in sql
    assert "ORDER BY PLA_PLANTA ASC" in sql
    assert binds["min_row"] == 0
    assert binds["max_row"] == 20


def test_filtros_viajan_como_binds(client, fake_db, auth):
    fake_db.total = 1
    malicioso = "X'"
    response = client.get(
        URL, params={"pla_inactivo": malicioso, "pla_codigo_postal": 5}, headers=auth
    )
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert malicioso not in sql
    assert "PLA_INACTIVO = :pla_inactivo" in sql
    assert binds["pla_inactivo"] == malicioso
    assert "PLA_CODIGO_POSTAL = :pla_codigo_postal" in sql
    assert binds["pla_codigo_postal"] == 5


def test_detalle_existente(client, fake_db, auth):
    fake_db.detail = FILA
    response = client.get(f"{URL}/1", headers=auth)
    sql, binds = fake_db.last("one")

    assert response.status_code == 200, response.text
    assert response.json()["pla_planta"] == 1
    assert "WHERE PLA_PLANTA = :item_id" in sql
    assert binds == {"item_id": 1}


def test_detalle_inexistente_404(client, fake_db, auth):
    fake_db.detail = None
    response = client.get(f"{URL}/999", headers=auth)
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


@pytest.mark.parametrize("valor", ["0", "-1", "abc", "1.5"])
def test_id_invalido_422(client, fake_db, auth, valor):
    assert client.get(f"{URL}/{valor}", headers=auth).status_code == 422
    assert fake_db.calls == []
