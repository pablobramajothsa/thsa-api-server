"""Tests de /v1/compras-pendientes-ncnd (vista IA_COMPRAS_PENDIENTES_NCND).

Lo común a todas las vistas (lista blanca de orden, modelo, token, errores de base)
ya lo cubre tests/test_contratos.py."""

from datetime import datetime

URL = "/v1/compras-pendientes-ncnd"

FILA = {
    "hca_compra_venta": "T",
    "hca_codigo": "12",
    "hca_sucursal": 10,
    "hca_numero": 10,
    "hca_fecha": datetime(2024, 1, 15, 10, 30),
    "hca_renglon": 10,
    "hca_codigo1": "TEXTO",
    "hca_sucursal1": 10,
    "hca_numero1": 10,
    "hca_fecha1": datetime(2024, 1, 15, 10, 30),
    "xarticulo": "TEXTO",
    "hca_articulo": "TEXTO",
    "hca_cantidad": 1.5,
    "cantidad_pendiente": 1.5,
    "hca_precio_unitario": 1.5,
    "importe": 1.5,
    "art_descripcion": "TEXTO",
    "comprobante": "TEXTO",
    "hcv_tipo_entidad": 10,
    "hcv_entidad": "TEXTO",
    "ent_nombre": "TEXTO",
    "hcv_nombre_cuenta": "TEXTO",
    "hcv_comentarios": "TEXTO",
    "hca_fecha_de_entrega": datetime(2024, 1, 15, 10, 30),
    "hcv_codigo_postal_entrega": 10,
    "hcv_sufijo_postal_entrega": "T",
    "localidad_entrega": "TEXTO",
    "hcv_lugar_entrega": "TEXTO",
    "hca_partida": "TEXTO",
    "hca_tipo_entidad": 10,
    "hca_entidad": "TEXTO",
    "hca_deposito": 10,
    "hca_fecha_vencimiento": datetime(2024, 1, 15, 10, 30),
    "hcv_codigo_vendedor": "TEXTO",
    "nombre_vendedor": "TEXTO",
    "hcv_condicion_compra": "TEXTO",
    "coc_descripcion": "TEXTO",
    "hcu_fecha_vencimiento": datetime(2024, 1, 15, 10, 30),
    "ent_zona": "TEXTO",
    "hcv_campo": 10,
    "cam_descripcion": "TEXTO",
    "x_campo": "TEXTO",
    "x_campo_descripcion": "TEXTO",
    "hcv_especie": "TEXT",
    "hcv_cosecha": "TEXT",
    "x_deposito": "TEXTO",
    "x_deposito_descripcion": "TEXTO",
    "hcv_moneda_original": "T",
    "unidades_origen": 1.5,
    "hcv_tipo_entidad_transportista": 10,
    "hcv_transportista": "TEXTO",
    "hcv_nombre_transportista": "TEXTO",
    "hcv_tipo_entidad_emp_transport": 10,
    "hcv_emp_transporte": "TEXTO",
    "hcv_nombre_emp_transporte": "TEXTO",
    "hcv_domicilio_emp_transporte": "TEXTO",
    "hcv_codigo_postal_emp_transpor": 10,
    "hcv_sufijo_postal_emp_transpor": "T",
    "hcv_cuit_emp_transporte": "TEXTO",
    "unidades_pendientes": 1.5,
    "comp_ambos": "TEXTO",
    "art_principio_activo": "TEX",
    "condicion_compra_origen": "TEXTO",
    "dsc_condicion_compra_origen": "TEXTO",
    "fecha_vencimiento_origen": datetime(2024, 1, 15, 10, 30),
    "hcv_bloqueado_remitir": "TE",
    "hcv_control_crediticio": "TEXTO",
    "hca_tarifa_flete": 1.5,
    "hca_tarifa_descarga": 1.5,
    "hca_tarifa_servicio": 1.5,
    "root_compra_venta": "TEXTO",
    "root_codigo_comp_cv": "TEXTO",
    "root_sucursal": "TEXTO",
    "root_numero": "TEXTO",
    "root_fecha": "TEXTO",
    "hcv_patente_camion": "TEXTO",
    "hcv_patente_acoplado": "TEXTO",
    "hcv_liquida_viaje": "TEXTO",
    "hcv_no_calcula_flete": "TEXTO",
    "hcv_segun_flete_articulos": "TEXTO",
    "hcv_numero_documento_fiscal": "TEXTO",
    "desc_condicion_flete": "TEXTO",
    "hcv_sucursal_emisora": "TEXTO",
    "cuit_transportista": "TEXTO",
    "descipcion_rubro": "TEXTO",
    "descipcion_subrubro": "TEXTO",
    "hca_precio_interno": 1.5,
    "hcv_cod_entidad_cta_y_orden": "TEXTO",
    "proveedor_cyo": "TEXTO",
    "tc": 1.5,
    "remitos_sf": "TEXTO",
    "nombre_productor_partida": "TEXTO",
    "art_categoria_toxicologica": "TEXTO",
    "presentacion_vta": "TEXTO",
    "dsc_presentacion_vta": "TEXTO",
    "hca_lista_precio": 10,
    "hcv_circuito_cv": "TEXTO",
    "hcv_cv_hcv_generado": "TEXTO",
    "hcv_cod_hcv_generado": "TEXTO",
    "hcv_deposito_transferencia": "TEXTO",
    "root_nro_comp_ext": "TEXTO",
    "art_unidad_medida": "TEXTO",
    "umd_descripcion": "TEXTO",
    "hcc_centro_costo": "TEXTO",
    "hcc_importe": 1.5,
    "hcc_unidades": 1.5,
    "hcv_tipo_operacion": "TEXTO",
    "hca_cuenta_contable": "TEXTO",
    "hcv_ejercicio": "TEXTO",
    "hca_ejercicio": "TEXTO",
    "hca_observacion_articulo": "TEXTO",
}


def test_listado_formato_y_sql(client, fake_db, auth):
    fake_db.total = 1
    fake_db.rows = [FILA]

    response = client.get(URL, headers=auth)
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["data"][0]["hca_codigo"] == FILA["hca_codigo"]
    assert "FROM IA_COMPRAS_PENDIENTES_NCND" in sql
    assert "ORDER BY HCA_CODIGO ASC" in sql
    assert binds["min_row"] == 0
    assert binds["max_row"] == 20


def test_filtros_viajan_como_binds(client, fake_db, auth):
    fake_db.total = 1
    malicioso = "X'"
    response = client.get(
        URL,
        params={
            "hca_codigo": malicioso,
            "hca_sucursal": 5,
            "hca_numero": 5,
            "hcv_entidad": malicioso,
            "hca_articulo": malicioso,
        },
        headers=auth,
    )
    sql, binds = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert malicioso not in sql
    assert "TRIM(HCA_CODIGO) = :hca_codigo" in sql
    assert binds["hca_codigo"] == malicioso
    assert "HCA_SUCURSAL = :hca_sucursal" in sql
    assert binds["hca_sucursal"] == 5
    assert "HCA_NUMERO = :hca_numero" in sql
    assert binds["hca_numero"] == 5
    assert "TRIM(HCV_ENTIDAD) = :hcv_entidad" in sql
    assert binds["hcv_entidad"] == malicioso
    assert "TRIM(HCA_ARTICULO) = :hca_articulo" in sql
    assert binds["hca_articulo"] == malicioso


def test_rango_de_fechas(client, fake_db, auth):
    fake_db.total = 1
    response = client.get(
        URL, params={"fecha_desde": "2024-01-01", "fecha_hasta": "2024-01-31"}, headers=auth
    )
    sql, _ = fake_db.last("all")

    assert response.status_code == 200, response.text
    assert "HCA_FECHA >= :fecha_desde" in sql
    assert "HCA_FECHA < :fecha_hasta_excl" in sql


def test_no_hay_detalle(client, fake_db, auth):
    assert client.get(f"{URL}/1", headers=auth).status_code == 404
    assert fake_db.calls == []
