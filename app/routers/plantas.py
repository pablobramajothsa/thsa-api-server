"""Vista IA_PLANTAS.

Plantas.

Relevada el 11/11/2026 en la base de prueba (Oracle 11.2.0.4).
- PLA_PLANTA es único: 68 filas.
- PLA_INACTIVO: "Sí" (con acento) o "No".
- Incluye domicilio, teléfonos y email de cada planta.

Estructura relevada:
    PLA_PLANTA NUMBER(5)
    PLA_DESCRIPCION VARCHAR2(50)
    PLA_DOM_CALLE VARCHAR2(50)
    PLA_DOM_NUMERO VARCHAR2(7)
    PLA_DOM_PISO VARCHAR2(5)
    PLA_DOM_DEPTO VARCHAR2(5)
    PLA_CODIGO_POSTAL NUMBER(5)
    PLA_SUFIJO_POSTAL VARCHAR2(1)
    PLA_TELEFONOS VARCHAR2(30)
    PLA_FAX VARCHAR2(30)
    PLA_E_MAIL VARCHAR2(40)
    PLA_DELEGACION_SAGPYA VARCHAR2(3)
    PLA_CAPACIDAD NUMBER(13)
    PLA_TALONARIO_1116A NUMBER(5)
    PLA_TALONARIO_1116B NUMBER(5)
    PLA_TALONARIO_1116C NUMBER(5)
    PLA_TALONARIO_INT_1116A NUMBER(5)
    PLA_TALONARIO_INT_1116B NUMBER(5)
    PLA_TALONARIO_INT_1116C NUMBER(5)
    PLA_PLANTA_C14 NUMBER(5)
    PLA_NUMERO_ONCCA NUMBER(6)
    PLA_PLANTA_AGRUPACION NUMBER(5)
    PLA_SUCURSAL_OPERA VARCHAR2(10)
    PLA_TALONARIO_1116RT NUMBER(5)
    PLA_TALONARIO_INT_1116RT NUMBER(5)
    PLA_TALONARIO_CARTAS_PORTE NUMBER(5)
    PLA_TALONARIO_1116A_PP NUMBER(5)
    PLA_TALONARIO_INT_1116A_PP NUMBER(5)
    PLA_TALONARIO_1116BC_PP NUMBER(5)
    PLA_TALONARIO_INT_1116BC_PP NUMBER(5)
    PLA_LUGAR_DESCARGA VARCHAR2(3)
    PLA_PUERTO VARCHAR2(2)
    PLA_ENTREGADOR VARCHAR2(10)
    PLA_DESTINATARIO VARCHAR2(10)
    PLA_DESTINO VARCHAR2(5)
    PLA_PUNTO_INGRESO NUMBER(4)
    PLA_INACTIVO VARCHAR2(2)
    PLA_MUNICIPIO VARCHAR2(3)
    PLA_ESPECIE_EXCLUSIVA VARCHAR2(4)
    PLA_DIFERENCIAL_FLETE NUMBER(9,4)
    PLA_DESTINO_CONTROL_FLETE VARCHAR2(5)
    PLA_PLANTA_DIRECTO VARCHAR2(2)
    PLA_TERCEROS VARCHAR2(2)
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.params import Page, PageParams, page_params
from app.query import Filter, SortOrder, ViewSpec, fetch_by_id, fetch_page
from app.security import require_user

MAX_PLA_PLANTA = 99_999  # NUMBER(5)

SortField = Literal["pla_planta", "pla_descripcion", "pla_codigo_postal"]

SPEC = ViewSpec(
    view="IA_PLANTAS",
    columns=(
        "PLA_PLANTA",
        "PLA_DESCRIPCION",
        "PLA_DOM_CALLE",
        "PLA_DOM_NUMERO",
        "PLA_DOM_PISO",
        "PLA_DOM_DEPTO",
        "PLA_CODIGO_POSTAL",
        "PLA_SUFIJO_POSTAL",
        "PLA_TELEFONOS",
        "PLA_FAX",
        "PLA_E_MAIL",
        "PLA_DELEGACION_SAGPYA",
        "PLA_CAPACIDAD",
        "PLA_TALONARIO_1116A",
        "PLA_TALONARIO_1116B",
        "PLA_TALONARIO_1116C",
        "PLA_TALONARIO_INT_1116A",
        "PLA_TALONARIO_INT_1116B",
        "PLA_TALONARIO_INT_1116C",
        "PLA_PLANTA_C14",
        "PLA_NUMERO_ONCCA",
        "PLA_PLANTA_AGRUPACION",
        "PLA_SUCURSAL_OPERA",
        "PLA_TALONARIO_1116RT",
        "PLA_TALONARIO_INT_1116RT",
        "PLA_TALONARIO_CARTAS_PORTE",
        "PLA_TALONARIO_1116A_PP",
        "PLA_TALONARIO_INT_1116A_PP",
        "PLA_TALONARIO_1116BC_PP",
        "PLA_TALONARIO_INT_1116BC_PP",
        "PLA_LUGAR_DESCARGA",
        "PLA_PUERTO",
        "PLA_ENTREGADOR",
        "PLA_DESTINATARIO",
        "PLA_DESTINO",
        "PLA_PUNTO_INGRESO",
        "PLA_INACTIVO",
        "PLA_MUNICIPIO",
        "PLA_ESPECIE_EXCLUSIVA",
        "PLA_DIFERENCIAL_FLETE",
        "PLA_DESTINO_CONTROL_FLETE",
        "PLA_PLANTA_DIRECTO",
        "PLA_TERCEROS",
    ),
    id_column="PLA_PLANTA",
    sort_columns={
        "pla_planta": "PLA_PLANTA",
        "pla_descripcion": "PLA_DESCRIPCION",
        "pla_codigo_postal": "PLA_CODIGO_POSTAL",
    },
    filters=(
        Filter("pla_inactivo", "PLA_INACTIVO", "="),
        Filter("pla_codigo_postal", "PLA_CODIGO_POSTAL", "="),
    ),
)


class Planta(BaseModel):
    # Quita los espacios de relleno que pueda traer la vista.
    model_config = ConfigDict(str_strip_whitespace=True)

    pla_planta: int
    pla_descripcion: str | None = None
    pla_dom_calle: str | None = None
    pla_dom_numero: str | None = None
    pla_dom_piso: str | None = None
    pla_dom_depto: str | None = None
    pla_codigo_postal: int | None = None
    pla_sufijo_postal: str | None = None
    pla_telefonos: str | None = None
    pla_fax: str | None = None
    pla_e_mail: str | None = None
    pla_delegacion_sagpya: str | None = None
    pla_capacidad: int | None = None
    pla_talonario_1116a: int | None = None
    pla_talonario_1116b: int | None = None
    pla_talonario_1116c: int | None = None
    pla_talonario_int_1116a: int | None = None
    pla_talonario_int_1116b: int | None = None
    pla_talonario_int_1116c: int | None = None
    pla_planta_c14: int | None = None
    pla_numero_oncca: int | None = None
    pla_planta_agrupacion: int | None = None
    pla_sucursal_opera: str | None = None
    pla_talonario_1116rt: int | None = None
    pla_talonario_int_1116rt: int | None = None
    pla_talonario_cartas_porte: int | None = None
    pla_talonario_1116a_pp: int | None = None
    pla_talonario_int_1116a_pp: int | None = None
    pla_talonario_1116bc_pp: int | None = None
    pla_talonario_int_1116bc_pp: int | None = None
    pla_lugar_descarga: str | None = None
    pla_puerto: str | None = None
    pla_entregador: str | None = None
    pla_destinatario: str | None = None
    pla_destino: str | None = None
    pla_punto_ingreso: int | None = None
    pla_inactivo: str | None = None
    pla_municipio: str | None = None
    pla_especie_exclusiva: str | None = None
    pla_diferencial_flete: float | None = None
    pla_destino_control_flete: str | None = None
    pla_planta_directo: str | None = None
    pla_terceros: str | None = None


MODEL = Planta

router = APIRouter(prefix="/v1/plantas", tags=["plantas"], dependencies=[Depends(require_user)])


@router.get("", response_model=Page[Planta])
def listar_plantas(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    pla_inactivo: Annotated[
        str | None, Query(min_length=1, max_length=2, description="Sí (con acento) o No")
    ] = None,
    pla_codigo_postal: Annotated[int | None, Query(ge=0)] = None,
    sort: SortField = "pla_planta",
    order: SortOrder = "asc",
) -> dict[str, Any]:
    total, rows = fetch_page(
        db,
        SPEC,
        settings.view_schema,
        {"pla_inactivo": pla_inactivo, "pla_codigo_postal": pla_codigo_postal},
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}


@router.get("/{pla_planta}", response_model=Planta)
def obtener_plantas(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    pla_planta: Annotated[int, Path(ge=1, le=MAX_PLA_PLANTA)],
) -> dict[str, Any]:
    row = fetch_by_id(db, SPEC, settings.view_schema, pla_planta)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row
