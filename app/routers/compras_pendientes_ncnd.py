"""Vista IA_COMPRAS_PENDIENTES_NCND.

Renglones de compras pendientes de notas de crédito / débito.

Relevada el 11/11/2026 en la base de prueba (Oracle 11.2.0.4).
- Clave única (HCA_CODIGO, HCA_SUCURSAL, HCA_NUMERO, HCA_RENGLON): 2 filas.
- Sin endpoint de detalle: un comprobante se consulta filtrando hca_codigo,
  hca_sucursal y hca_numero (devuelve todos sus renglones).
- HCV_ENTIDAD (proveedor) y HCA_ENTIDAD vienen con espacios de relleno: filtros con TRIM.
- Varias columnas son VARCHAR2(0) (siempre nulas) o estaban vacías; se publican igual
  para respetar la definición de la vista.

Estructura relevada:
    HCA_COMPRA_VENTA VARCHAR2(1)
    HCA_CODIGO VARCHAR2(2)
    HCA_SUCURSAL NUMBER(5)
    HCA_NUMERO NUMBER(10)
    HCA_FECHA DATE
    HCA_RENGLON NUMBER(5)
    HCA_CODIGO1 VARCHAR2(6)
    HCA_SUCURSAL1 NUMBER(4)
    HCA_NUMERO1 NUMBER(10)
    HCA_FECHA1 DATE
    XARTICULO VARCHAR2(20)
    HCA_ARTICULO VARCHAR2(20)
    HCA_CANTIDAD NUMBER(9,2)
    CANTIDAD_PENDIENTE NUMBER
    HCA_PRECIO_UNITARIO NUMBER
    IMPORTE NUMBER
    ART_DESCRIPCION VARCHAR2(60)
    COMPROBANTE VARCHAR2(14)
    HCV_TIPO_ENTIDAD NUMBER(2)
    HCV_ENTIDAD VARCHAR2(60)
    ENT_NOMBRE VARCHAR2(50)
    HCV_NOMBRE_CUENTA VARCHAR2(50)
    HCV_COMENTARIOS VARCHAR2(2000)
    HCA_FECHA_DE_ENTREGA DATE
    HCV_CODIGO_POSTAL_ENTREGA NUMBER(5)
    HCV_SUFIJO_POSTAL_ENTREGA VARCHAR2(1)
    LOCALIDAD_ENTREGA VARCHAR2(50)
    HCV_LUGAR_ENTREGA VARCHAR2(50)
    HCA_PARTIDA VARCHAR2(50)
    HCA_TIPO_ENTIDAD NUMBER(2)
    HCA_ENTIDAD VARCHAR2(20)
    HCA_DEPOSITO NUMBER(5)
    HCA_FECHA_VENCIMIENTO DATE
    HCV_CODIGO_VENDEDOR VARCHAR2(20)
    NOMBRE_VENDEDOR VARCHAR2(50)
    HCV_CONDICION_COMPRA VARCHAR2(5)
    COC_DESCRIPCION VARCHAR2(50)
    HCU_FECHA_VENCIMIENTO DATE
    ENT_ZONA VARCHAR2(5)
    HCV_CAMPO NUMBER(7)
    CAM_DESCRIPCION VARCHAR2(50)
    X_CAMPO VARCHAR2(0)
    X_CAMPO_DESCRIPCION VARCHAR2(0)
    HCV_ESPECIE VARCHAR2(4)
    HCV_COSECHA VARCHAR2(4)
    X_DEPOSITO VARCHAR2(0)
    X_DEPOSITO_DESCRIPCION VARCHAR2(0)
    HCV_MONEDA_ORIGINAL VARCHAR2(1)
    UNIDADES_ORIGEN NUMBER
    HCV_TIPO_ENTIDAD_TRANSPORTISTA NUMBER(2)
    HCV_TRANSPORTISTA VARCHAR2(20)
    HCV_NOMBRE_TRANSPORTISTA VARCHAR2(50)
    HCV_TIPO_ENTIDAD_EMP_TRANSPORT NUMBER(2)
    HCV_EMP_TRANSPORTE VARCHAR2(20)
    HCV_NOMBRE_EMP_TRANSPORTE VARCHAR2(50)
    HCV_DOMICILIO_EMP_TRANSPORTE VARCHAR2(200)
    HCV_CODIGO_POSTAL_EMP_TRANSPOR NUMBER(5)
    HCV_SUFIJO_POSTAL_EMP_TRANSPOR VARCHAR2(1)
    HCV_CUIT_EMP_TRANSPORTE VARCHAR2(20)
    UNIDADES_PENDIENTES NUMBER
    COMP_AMBOS VARCHAR2(0)
    ART_PRINCIPIO_ACTIVO VARCHAR2(3)
    CONDICION_COMPRA_ORIGEN VARCHAR2(5)
    DSC_CONDICION_COMPRA_ORIGEN VARCHAR2(50)
    FECHA_VENCIMIENTO_ORIGEN DATE
    HCV_BLOQUEADO_REMITIR VARCHAR2(2)
    HCV_CONTROL_CREDITICIO VARCHAR2(4000)
    HCA_TARIFA_FLETE NUMBER(12,4)
    HCA_TARIFA_DESCARGA NUMBER(9,4)
    HCA_TARIFA_SERVICIO NUMBER(9,4)
    ROOT_COMPRA_VENTA VARCHAR2(0)
    ROOT_CODIGO_COMP_CV VARCHAR2(0)
    ROOT_SUCURSAL VARCHAR2(0)
    ROOT_NUMERO VARCHAR2(0)
    ROOT_FECHA VARCHAR2(0)
    HCV_PATENTE_CAMION VARCHAR2(10)
    HCV_PATENTE_ACOPLADO VARCHAR2(10)
    HCV_LIQUIDA_VIAJE VARCHAR2(0)
    HCV_NO_CALCULA_FLETE VARCHAR2(0)
    HCV_SEGUN_FLETE_ARTICULOS VARCHAR2(0)
    HCV_NUMERO_DOCUMENTO_FISCAL VARCHAR2(14)
    DESC_CONDICION_FLETE VARCHAR2(15)
    HCV_SUCURSAL_EMISORA VARCHAR2(10)
    CUIT_TRANSPORTISTA VARCHAR2(14)
    DESCIPCION_RUBRO VARCHAR2(93)
    DESCIPCION_SUBRUBRO VARCHAR2(93)
    HCA_PRECIO_INTERNO NUMBER(14,4)
    HCV_COD_ENTIDAD_CTA_Y_ORDEN VARCHAR2(20)
    PROVEEDOR_CYO VARCHAR2(50)
    TC NUMBER(11,4)
    REMITOS_SF VARCHAR2(0)
    NOMBRE_PRODUCTOR_PARTIDA VARCHAR2(50)
    ART_CATEGORIA_TOXICOLOGICA VARCHAR2(17)
    PRESENTACION_VTA VARCHAR2(0)
    DSC_PRESENTACION_VTA VARCHAR2(0)
    HCA_LISTA_PRECIO NUMBER(3)
    HCV_CIRCUITO_CV VARCHAR2(0)
    HCV_CV_HCV_GENERADO VARCHAR2(0)
    HCV_COD_HCV_GENERADO VARCHAR2(6)
    HCV_DEPOSITO_TRANSFERENCIA VARCHAR2(0)
    ROOT_NRO_COMP_EXT VARCHAR2(0)
    ART_UNIDAD_MEDIDA VARCHAR2(0)
    UMD_DESCRIPCION VARCHAR2(0)
    HCC_CENTRO_COSTO VARCHAR2(30)
    HCC_IMPORTE NUMBER(13,2)
    HCC_UNIDADES NUMBER(13,4)
    HCV_TIPO_OPERACION VARCHAR2(6)
    HCA_CUENTA_CONTABLE VARCHAR2(30)
    HCV_EJERCICIO VARCHAR2(10)
    HCA_EJERCICIO VARCHAR2(10)
    HCA_OBSERVACION_ARTICULO VARCHAR2(1024)
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.params import Page, PageParams, date_range_filters, page_params
from app.query import Filter, SortOrder, ViewSpec, fetch_page
from app.security import require_user

SortField = Literal["hca_codigo", "hca_fecha", "hca_numero", "ent_nombre", "hcu_fecha_vencimiento"]

SPEC = ViewSpec(
    view="IA_COMPRAS_PENDIENTES_NCND",
    columns=(
        "HCA_COMPRA_VENTA",
        "HCA_CODIGO",
        "HCA_SUCURSAL",
        "HCA_NUMERO",
        "HCA_FECHA",
        "HCA_RENGLON",
        "HCA_CODIGO1",
        "HCA_SUCURSAL1",
        "HCA_NUMERO1",
        "HCA_FECHA1",
        "XARTICULO",
        "HCA_ARTICULO",
        "HCA_CANTIDAD",
        "CANTIDAD_PENDIENTE",
        "HCA_PRECIO_UNITARIO",
        "IMPORTE",
        "ART_DESCRIPCION",
        "COMPROBANTE",
        "HCV_TIPO_ENTIDAD",
        "HCV_ENTIDAD",
        "ENT_NOMBRE",
        "HCV_NOMBRE_CUENTA",
        "HCV_COMENTARIOS",
        "HCA_FECHA_DE_ENTREGA",
        "HCV_CODIGO_POSTAL_ENTREGA",
        "HCV_SUFIJO_POSTAL_ENTREGA",
        "LOCALIDAD_ENTREGA",
        "HCV_LUGAR_ENTREGA",
        "HCA_PARTIDA",
        "HCA_TIPO_ENTIDAD",
        "HCA_ENTIDAD",
        "HCA_DEPOSITO",
        "HCA_FECHA_VENCIMIENTO",
        "HCV_CODIGO_VENDEDOR",
        "NOMBRE_VENDEDOR",
        "HCV_CONDICION_COMPRA",
        "COC_DESCRIPCION",
        "HCU_FECHA_VENCIMIENTO",
        "ENT_ZONA",
        "HCV_CAMPO",
        "CAM_DESCRIPCION",
        "X_CAMPO",
        "X_CAMPO_DESCRIPCION",
        "HCV_ESPECIE",
        "HCV_COSECHA",
        "X_DEPOSITO",
        "X_DEPOSITO_DESCRIPCION",
        "HCV_MONEDA_ORIGINAL",
        "UNIDADES_ORIGEN",
        "HCV_TIPO_ENTIDAD_TRANSPORTISTA",
        "HCV_TRANSPORTISTA",
        "HCV_NOMBRE_TRANSPORTISTA",
        "HCV_TIPO_ENTIDAD_EMP_TRANSPORT",
        "HCV_EMP_TRANSPORTE",
        "HCV_NOMBRE_EMP_TRANSPORTE",
        "HCV_DOMICILIO_EMP_TRANSPORTE",
        "HCV_CODIGO_POSTAL_EMP_TRANSPOR",
        "HCV_SUFIJO_POSTAL_EMP_TRANSPOR",
        "HCV_CUIT_EMP_TRANSPORTE",
        "UNIDADES_PENDIENTES",
        "COMP_AMBOS",
        "ART_PRINCIPIO_ACTIVO",
        "CONDICION_COMPRA_ORIGEN",
        "DSC_CONDICION_COMPRA_ORIGEN",
        "FECHA_VENCIMIENTO_ORIGEN",
        "HCV_BLOQUEADO_REMITIR",
        "HCV_CONTROL_CREDITICIO",
        "HCA_TARIFA_FLETE",
        "HCA_TARIFA_DESCARGA",
        "HCA_TARIFA_SERVICIO",
        "ROOT_COMPRA_VENTA",
        "ROOT_CODIGO_COMP_CV",
        "ROOT_SUCURSAL",
        "ROOT_NUMERO",
        "ROOT_FECHA",
        "HCV_PATENTE_CAMION",
        "HCV_PATENTE_ACOPLADO",
        "HCV_LIQUIDA_VIAJE",
        "HCV_NO_CALCULA_FLETE",
        "HCV_SEGUN_FLETE_ARTICULOS",
        "HCV_NUMERO_DOCUMENTO_FISCAL",
        "DESC_CONDICION_FLETE",
        "HCV_SUCURSAL_EMISORA",
        "CUIT_TRANSPORTISTA",
        "DESCIPCION_RUBRO",
        "DESCIPCION_SUBRUBRO",
        "HCA_PRECIO_INTERNO",
        "HCV_COD_ENTIDAD_CTA_Y_ORDEN",
        "PROVEEDOR_CYO",
        "TC",
        "REMITOS_SF",
        "NOMBRE_PRODUCTOR_PARTIDA",
        "ART_CATEGORIA_TOXICOLOGICA",
        "PRESENTACION_VTA",
        "DSC_PRESENTACION_VTA",
        "HCA_LISTA_PRECIO",
        "HCV_CIRCUITO_CV",
        "HCV_CV_HCV_GENERADO",
        "HCV_COD_HCV_GENERADO",
        "HCV_DEPOSITO_TRANSFERENCIA",
        "ROOT_NRO_COMP_EXT",
        "ART_UNIDAD_MEDIDA",
        "UMD_DESCRIPCION",
        "HCC_CENTRO_COSTO",
        "HCC_IMPORTE",
        "HCC_UNIDADES",
        "HCV_TIPO_OPERACION",
        "HCA_CUENTA_CONTABLE",
        "HCV_EJERCICIO",
        "HCA_EJERCICIO",
        "HCA_OBSERVACION_ARTICULO",
    ),
    id_column="HCA_CODIGO",
    tiebreak_columns=(
        "HCA_CODIGO",
        "HCA_SUCURSAL",
        "HCA_NUMERO",
        "HCA_RENGLON",
    ),
    sort_columns={
        "hca_codigo": "HCA_CODIGO",
        "hca_fecha": "HCA_FECHA",
        "hca_numero": "HCA_NUMERO",
        "ent_nombre": "ENT_NOMBRE",
        "hcu_fecha_vencimiento": "HCU_FECHA_VENCIMIENTO",
    },
    filters=(
        Filter("hca_codigo", "HCA_CODIGO", "=", trim=True),
        Filter("hca_sucursal", "HCA_SUCURSAL", "="),
        Filter("hca_numero", "HCA_NUMERO", "="),
        Filter("hcv_entidad", "HCV_ENTIDAD", "=", trim=True),
        Filter("hca_articulo", "HCA_ARTICULO", "=", trim=True),
        Filter("fecha_desde", "HCA_FECHA", ">="),
        Filter("fecha_hasta_excl", "HCA_FECHA", "<"),
    ),
)


class CompraPendienteNcnd(BaseModel):
    # Quita los espacios de relleno que pueda traer la vista.
    model_config = ConfigDict(str_strip_whitespace=True)

    hca_compra_venta: str | None = None
    hca_codigo: str
    hca_sucursal: int | None = None
    hca_numero: int | None = None
    hca_fecha: datetime | None = None
    hca_renglon: int | None = None
    hca_codigo1: str | None = None
    hca_sucursal1: int | None = None
    hca_numero1: int | None = None
    hca_fecha1: datetime | None = None
    xarticulo: str | None = None
    hca_articulo: str | None = None
    hca_cantidad: float | None = None
    cantidad_pendiente: float | None = None
    hca_precio_unitario: float | None = None
    importe: float | None = None
    art_descripcion: str | None = None
    comprobante: str | None = None
    hcv_tipo_entidad: int | None = None
    hcv_entidad: str | None = None
    ent_nombre: str | None = None
    hcv_nombre_cuenta: str | None = None
    hcv_comentarios: str | None = None
    hca_fecha_de_entrega: datetime | None = None
    hcv_codigo_postal_entrega: int | None = None
    hcv_sufijo_postal_entrega: str | None = None
    localidad_entrega: str | None = None
    hcv_lugar_entrega: str | None = None
    hca_partida: str | None = None
    hca_tipo_entidad: int | None = None
    hca_entidad: str | None = None
    hca_deposito: int | None = None
    hca_fecha_vencimiento: datetime | None = None
    hcv_codigo_vendedor: str | None = None
    nombre_vendedor: str | None = None
    hcv_condicion_compra: str | None = None
    coc_descripcion: str | None = None
    hcu_fecha_vencimiento: datetime | None = None
    ent_zona: str | None = None
    hcv_campo: int | None = None
    cam_descripcion: str | None = None
    x_campo: str | None = None
    x_campo_descripcion: str | None = None
    hcv_especie: str | None = None
    hcv_cosecha: str | None = None
    x_deposito: str | None = None
    x_deposito_descripcion: str | None = None
    hcv_moneda_original: str | None = None
    unidades_origen: float | None = None
    hcv_tipo_entidad_transportista: int | None = None
    hcv_transportista: str | None = None
    hcv_nombre_transportista: str | None = None
    hcv_tipo_entidad_emp_transport: int | None = None
    hcv_emp_transporte: str | None = None
    hcv_nombre_emp_transporte: str | None = None
    hcv_domicilio_emp_transporte: str | None = None
    hcv_codigo_postal_emp_transpor: int | None = None
    hcv_sufijo_postal_emp_transpor: str | None = None
    hcv_cuit_emp_transporte: str | None = None
    unidades_pendientes: float | None = None
    comp_ambos: str | None = None
    art_principio_activo: str | None = None
    condicion_compra_origen: str | None = None
    dsc_condicion_compra_origen: str | None = None
    fecha_vencimiento_origen: datetime | None = None
    hcv_bloqueado_remitir: str | None = None
    hcv_control_crediticio: str | None = None
    hca_tarifa_flete: float | None = None
    hca_tarifa_descarga: float | None = None
    hca_tarifa_servicio: float | None = None
    root_compra_venta: str | None = None
    root_codigo_comp_cv: str | None = None
    root_sucursal: str | None = None
    root_numero: str | None = None
    root_fecha: str | None = None
    hcv_patente_camion: str | None = None
    hcv_patente_acoplado: str | None = None
    hcv_liquida_viaje: str | None = None
    hcv_no_calcula_flete: str | None = None
    hcv_segun_flete_articulos: str | None = None
    hcv_numero_documento_fiscal: str | None = None
    desc_condicion_flete: str | None = None
    hcv_sucursal_emisora: str | None = None
    cuit_transportista: str | None = None
    descipcion_rubro: str | None = None
    descipcion_subrubro: str | None = None
    hca_precio_interno: float | None = None
    hcv_cod_entidad_cta_y_orden: str | None = None
    proveedor_cyo: str | None = None
    tc: float | None = None
    remitos_sf: str | None = None
    nombre_productor_partida: str | None = None
    art_categoria_toxicologica: str | None = None
    presentacion_vta: str | None = None
    dsc_presentacion_vta: str | None = None
    hca_lista_precio: int | None = None
    hcv_circuito_cv: str | None = None
    hcv_cv_hcv_generado: str | None = None
    hcv_cod_hcv_generado: str | None = None
    hcv_deposito_transferencia: str | None = None
    root_nro_comp_ext: str | None = None
    art_unidad_medida: str | None = None
    umd_descripcion: str | None = None
    hcc_centro_costo: str | None = None
    hcc_importe: float | None = None
    hcc_unidades: float | None = None
    hcv_tipo_operacion: str | None = None
    hca_cuenta_contable: str | None = None
    hcv_ejercicio: str | None = None
    hca_ejercicio: str | None = None
    hca_observacion_articulo: str | None = None


MODEL = CompraPendienteNcnd

router = APIRouter(
    prefix="/v1/compras-pendientes-ncnd",
    tags=["compras_pendientes_ncnd"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_model=Page[CompraPendienteNcnd])
def listar_compras_pendientes_ncnd(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    dates: Annotated[dict[str, Any], Depends(date_range_filters)],
    hca_codigo: Annotated[str | None, Query(min_length=1, max_length=2)] = None,
    hca_sucursal: Annotated[int | None, Query(ge=0)] = None,
    hca_numero: Annotated[int | None, Query(ge=0)] = None,
    hcv_entidad: Annotated[
        str | None, Query(min_length=1, max_length=60, description="Código del proveedor")
    ] = None,
    hca_articulo: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    sort: SortField = "hca_codigo",
    order: SortOrder = "asc",
) -> dict[str, Any]:
    total, rows = fetch_page(
        db,
        SPEC,
        settings.view_schema,
        {
            "hca_codigo": hca_codigo,
            "hca_sucursal": hca_sucursal,
            "hca_numero": hca_numero,
            "hcv_entidad": hcv_entidad,
            "hca_articulo": hca_articulo,
            **dates,
        },
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}
