"""Vista IA_IMPUESTOS_REGIMENES.

Regímenes de impuestos (retenciones y percepciones).

Relevada el 11/11/2026 en la base de prueba (Oracle 11.2.0.4).
- RGI_CODIGO_REGIMEN es único: 263 filas.
- Los valores llevan acento: RGI_HABILITADO "Sí" / "No", RGI_TIPO_OPERACION
  "Retención" / "Percepción".

Estructura relevada:
    RGI_CODIGO_REGIMEN NUMBER(5)
    RGI_DESCRIPCION VARCHAR2(50)
    RGI_DESCRIPCION_REDUCIDA VARCHAR2(10)
    RGI_CODIGO_IMPUESTO NUMBER(5)
    RGI_TIPO_OPERACION VARCHAR2(20)
    RGI_PROVINCIA VARCHAR2(3)
    RGI_CODIGO_IMPORTE_IVA NUMBER(3)
    RGI_HABILITADO VARCHAR2(2)
    RGI_CALCULA_SIEMPRE VARCHAR2(2)
    RGI_TALONARIO NUMBER(5)
    RGI_REGIMEN_AFIP NUMBER(7)
    RGI_CALCULA_SEGUN_ARTICULO VARCHAR2(2)
    RGI_BASE_PARA_CALCULO VARCHAR2(1)
    RGI_IMPUESTO_INTERNO VARCHAR2(2)
    RGI_FECHA_A_USAR VARCHAR2(1)
    RGI_NUMERO_AGENTE_RETENCION VARCHAR2(20)
    RGI_PIDE_PERIODOS VARCHAR2(2)
    RGI_CALCULO_POR_COMPROBANTE VARCHAR2(2)
    RGI_PERMITE_NEGATIVOS VARCHAR2(2)
    RGI_RETIENE_SOBRE_TOTAL VARCHAR2(2)
    RGI_CALCULO_NO_PROPORCIONAL VARCHAR2(2)
    RGI_RET_ENT_CTA_Y_ORDEN VARCHAR2(2)
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.params import Page, PageParams, page_params
from app.query import Filter, SortOrder, ViewSpec, fetch_by_id, fetch_page
from app.security import require_user

MAX_RGI_CODIGO_REGIMEN = 99_999  # NUMBER(5)

SortField = Literal["rgi_codigo_regimen", "rgi_descripcion", "rgi_codigo_impuesto"]

SPEC = ViewSpec(
    view="IA_IMPUESTOS_REGIMENES",
    columns=(
        "RGI_CODIGO_REGIMEN",
        "RGI_DESCRIPCION",
        "RGI_DESCRIPCION_REDUCIDA",
        "RGI_CODIGO_IMPUESTO",
        "RGI_TIPO_OPERACION",
        "RGI_PROVINCIA",
        "RGI_CODIGO_IMPORTE_IVA",
        "RGI_HABILITADO",
        "RGI_CALCULA_SIEMPRE",
        "RGI_TALONARIO",
        "RGI_REGIMEN_AFIP",
        "RGI_CALCULA_SEGUN_ARTICULO",
        "RGI_BASE_PARA_CALCULO",
        "RGI_IMPUESTO_INTERNO",
        "RGI_FECHA_A_USAR",
        "RGI_NUMERO_AGENTE_RETENCION",
        "RGI_PIDE_PERIODOS",
        "RGI_CALCULO_POR_COMPROBANTE",
        "RGI_PERMITE_NEGATIVOS",
        "RGI_RETIENE_SOBRE_TOTAL",
        "RGI_CALCULO_NO_PROPORCIONAL",
        "RGI_RET_ENT_CTA_Y_ORDEN",
    ),
    id_column="RGI_CODIGO_REGIMEN",
    sort_columns={
        "rgi_codigo_regimen": "RGI_CODIGO_REGIMEN",
        "rgi_descripcion": "RGI_DESCRIPCION",
        "rgi_codigo_impuesto": "RGI_CODIGO_IMPUESTO",
    },
    filters=(
        Filter("rgi_codigo_impuesto", "RGI_CODIGO_IMPUESTO", "="),
        Filter("rgi_tipo_operacion", "RGI_TIPO_OPERACION", "="),
        Filter("rgi_provincia", "RGI_PROVINCIA", "="),
        Filter("rgi_habilitado", "RGI_HABILITADO", "="),
    ),
)


class ImpuestoRegimen(BaseModel):
    # Quita los espacios de relleno que pueda traer la vista.
    model_config = ConfigDict(str_strip_whitespace=True)

    rgi_codigo_regimen: int
    rgi_descripcion: str | None = None
    rgi_descripcion_reducida: str | None = None
    rgi_codigo_impuesto: int | None = None
    rgi_tipo_operacion: str | None = None
    rgi_provincia: str | None = None
    rgi_codigo_importe_iva: int | None = None
    rgi_habilitado: str | None = None
    rgi_calcula_siempre: str | None = None
    rgi_talonario: int | None = None
    rgi_regimen_afip: int | None = None
    rgi_calcula_segun_articulo: str | None = None
    rgi_base_para_calculo: str | None = None
    rgi_impuesto_interno: str | None = None
    rgi_fecha_a_usar: str | None = None
    rgi_numero_agente_retencion: str | None = None
    rgi_pide_periodos: str | None = None
    rgi_calculo_por_comprobante: str | None = None
    rgi_permite_negativos: str | None = None
    rgi_retiene_sobre_total: str | None = None
    rgi_calculo_no_proporcional: str | None = None
    rgi_ret_ent_cta_y_orden: str | None = None


MODEL = ImpuestoRegimen

router = APIRouter(
    prefix="/v1/impuestos-regimenes",
    tags=["impuestos_regimenes"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_model=Page[ImpuestoRegimen])
def listar_impuestos_regimenes(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    rgi_codigo_impuesto: Annotated[int | None, Query(ge=0)] = None,
    rgi_tipo_operacion: Annotated[
        str | None, Query(min_length=1, max_length=20, description="Retención o Percepción")
    ] = None,
    rgi_provincia: Annotated[str | None, Query(min_length=1, max_length=3)] = None,
    rgi_habilitado: Annotated[
        str | None, Query(min_length=1, max_length=2, description="Sí (con acento) o No")
    ] = None,
    sort: SortField = "rgi_codigo_regimen",
    order: SortOrder = "asc",
) -> dict[str, Any]:
    total, rows = fetch_page(
        db,
        SPEC,
        settings.view_schema,
        {
            "rgi_codigo_impuesto": rgi_codigo_impuesto,
            "rgi_tipo_operacion": rgi_tipo_operacion,
            "rgi_provincia": rgi_provincia,
            "rgi_habilitado": rgi_habilitado,
        },
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}


@router.get("/{rgi_codigo_regimen}", response_model=ImpuestoRegimen)
def obtener_impuestos_regimenes(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    rgi_codigo_regimen: Annotated[int, Path(ge=1, le=MAX_RGI_CODIGO_REGIMEN)],
) -> dict[str, Any]:
    row = fetch_by_id(db, SPEC, settings.view_schema, rgi_codigo_regimen)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row
