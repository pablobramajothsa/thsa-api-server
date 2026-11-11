"""Tests de /v1/impuestos-regimenes (vista IA_IMPUESTOS_REGIMENES).

Lo común a todas las vistas (lista blanca de orden, modelo, token, errores de base)
ya lo cubre tests/test_contratos.py."""

import pytest

URL = "/v1/impuestos-regimenes"

FILA = {
    "rgi_codigo_regimen": 1,
    "rgi_descripcion": "TEXTO",
    "rgi_descripcion_reducida": "TEXTO",
    "rgi_codigo_impuesto": 10,
    "rgi_tipo_operacion": "TEXTO",
    "rgi_provincia": "TEX",
    "rgi_codigo_importe_iva": 10,
    "rgi_habilitado": "TE",
    "rgi_calcula_siempre": "TE",
    "rgi_talonario": 10,
    "rgi_regimen_afip": 10,
    "rgi_calcula_segun_articulo": "TE",
    "rgi_base_para_calculo": "T",
    "rgi_impuesto_interno": "TE",
    "rgi_fecha_a_usar": "T",
    "rgi_numero_agente_retencion": "TEXTO",
    "rgi_pide_periodos": "TE",
    "rgi_calculo_por_comprobante": "TE",
    "rgi_permite_negativos": "TE",
    "rgi_retiene_sobre_total": "TE",
    "rgi_calculo_no_proporcional": "TE",
    "rgi_ret_ent_cta_y_orden": "TE",
}


def test_listado_formato_y_sql(client, fake_db, auth):
    fake_db.total = 1
    fake_db.rows = [FILA]

    response = client.get(URL, headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["data"][0]["rgi_codigo_regimen"] == FILA["rgi_codigo_regimen"]
    assert "FROM IA_IMPUESTOS_REGIMENES" in sql
    assert "ORDER BY RGI_CODIGO_REGIMEN ASC" in sql
    assert binds["min_row"] == 0
    assert binds["max_row"] == 20


def test_filtros_viajan_como_binds(client, fake_db, auth):
    fake_db.total = 1
    malicioso = "X'"
    response = client.get(
        URL,
        params={
            "rgi_codigo_impuesto": 5,
            "rgi_tipo_operacion": malicioso,
            "rgi_provincia": malicioso,
            "rgi_habilitado": malicioso,
        },
        headers=auth,
    )
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert malicioso not in sql
    assert "RGI_CODIGO_IMPUESTO = :rgi_codigo_impuesto" in sql
    assert binds["rgi_codigo_impuesto"] == 5
    assert "RGI_TIPO_OPERACION = :rgi_tipo_operacion" in sql
    assert binds["rgi_tipo_operacion"] == malicioso
    assert "RGI_PROVINCIA = :rgi_provincia" in sql
    assert binds["rgi_provincia"] == malicioso
    assert "RGI_HABILITADO = :rgi_habilitado" in sql
    assert binds["rgi_habilitado"] == malicioso


def test_detalle_existente(client, fake_db, auth):
    fake_db.detail = FILA
    response = client.get(f"{URL}/1", headers=auth)
    sql, binds = fake_db.last("one")

    assert response.status_code == 200, response.text
    assert response.json()["rgi_codigo_regimen"] == 1
    assert "WHERE RGI_CODIGO_REGIMEN = :item_id" in sql
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
