"""Vista IA_CATAC.

Tarifas CATAC: precio por tonelada según kilómetros y fecha de vigencia.

Relevada el 11/11/2026 en la base de prueba (Oracle 11.2.0.4).
- Clave única (TARIFA_CODIGO, FECHA_VIGENCIA_DESDE, KILOMETROS): 134510 filas, 159
  tarifas, vigencias de 2006 a 2023.
- Sin endpoint de detalle: una tarifa tiene hasta 2400 filas. Se consulta con filtros
  (tarifa_codigo, kilometros, fecha_desde / fecha_hasta sobre FECHA_VIGENCIA_DESDE).
- SEGUNDA_TARIFA estaba vacía en todas las filas.

Estructura relevada:
    TARIFA_CODIGO NUMBER(3)
    TARIFA_NOMBRE VARCHAR2(50)
    FECHA_VIGENCIA_DESDE DATE
    KILOMETROS NUMBER(5)
    TARIFA_POR_TN NUMBER
    SEGUNDA_TARIFA NUMBER(9,4)
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

SortField = Literal["tarifa_codigo", "tarifa_nombre", "fecha_vigencia_desde", "kilometros"]

SPEC = ViewSpec(
    view="IA_CATAC",
    columns=(
        "TARIFA_CODIGO",
        "TARIFA_NOMBRE",
        "FECHA_VIGENCIA_DESDE",
        "KILOMETROS",
        "TARIFA_POR_TN",
        "SEGUNDA_TARIFA",
    ),
    id_column="TARIFA_CODIGO",
    tiebreak_columns=(
        "TARIFA_CODIGO",
        "FECHA_VIGENCIA_DESDE",
        "KILOMETROS",
    ),
    sort_columns={
        "tarifa_codigo": "TARIFA_CODIGO",
        "tarifa_nombre": "TARIFA_NOMBRE",
        "fecha_vigencia_desde": "FECHA_VIGENCIA_DESDE",
        "kilometros": "KILOMETROS",
    },
    filters=(
        Filter("tarifa_codigo", "TARIFA_CODIGO", "="),
        Filter("kilometros", "KILOMETROS", "="),
        Filter("fecha_desde", "FECHA_VIGENCIA_DESDE", ">="),
        Filter("fecha_hasta_excl", "FECHA_VIGENCIA_DESDE", "<"),
    ),
)


class TarifaCatac(BaseModel):
    # Quita los espacios de relleno que pueda traer la vista.
    model_config = ConfigDict(str_strip_whitespace=True)

    tarifa_codigo: int
    tarifa_nombre: str | None = None
    fecha_vigencia_desde: datetime | None = None
    kilometros: int | None = None
    tarifa_por_tn: float | None = None
    segunda_tarifa: float | None = None


MODEL = TarifaCatac

router = APIRouter(prefix="/v1/catac", tags=["catac"], dependencies=[Depends(require_user)])


@router.get("", response_model=Page[TarifaCatac])
def listar_catac(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    dates: Annotated[dict[str, Any], Depends(date_range_filters)],
    tarifa_codigo: Annotated[int | None, Query(ge=0)] = None,
    kilometros: Annotated[int | None, Query(ge=0)] = None,
    sort: SortField = "tarifa_codigo",
    order: SortOrder = "asc",
) -> dict[str, Any]:
    total, rows = fetch_page(
        db,
        SPEC,
        settings.view_schema,
        {"tarifa_codigo": tarifa_codigo, "kilometros": kilometros, **dates},
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}
