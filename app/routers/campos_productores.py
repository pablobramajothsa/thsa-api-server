"""Vista IA_CAMPOS_PRODUCTORES.

Relación campo - productor (las columnas de campo y productor de IA_CAMPOS).

Relevada el 11/11/2026 en la base de prueba (Oracle 11.2.0.4).
- Clave única (CAMPO_CODIGO, PRODUCTOR_CODIGO): 4334 filas, 4311 campos. Un campo puede
  tener varios productores, por eso el detalle devuelve una lista.
- PRODUCTOR_CODIGO viene con espacios de relleno ("   4904"): los filtros comparan con
  TRIM y la respuesta devuelve el código recortado.
- PRODUCTOR_CUIT puede ser un dato personal (CUIT de persona física).

Estructura relevada:
    CAMPO_CODIGO NUMBER(7)
    CAMPO_NOMBRE VARCHAR2(50)
    PRODUCTOR_CODIGO VARCHAR2(10)
    PRODUCTOR_NOMBRE VARCHAR2(50)
    PRODUCTOR_CUIT VARCHAR2(14)
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.params import Page, PageParams, page_params
from app.query import Filter, SortOrder, ViewSpec, fetch_all_by_id, fetch_page
from app.security import require_user

MAX_CAMPO_CODIGO = 9_999_999  # NUMBER(7)

SortField = Literal["campo_codigo", "campo_nombre", "productor_codigo", "productor_nombre"]

SPEC = ViewSpec(
    view="IA_CAMPOS_PRODUCTORES",
    columns=(
        "CAMPO_CODIGO",
        "CAMPO_NOMBRE",
        "PRODUCTOR_CODIGO",
        "PRODUCTOR_NOMBRE",
        "PRODUCTOR_CUIT",
    ),
    id_column="CAMPO_CODIGO",
    tiebreak_columns=(
        "CAMPO_CODIGO",
        "PRODUCTOR_CODIGO",
    ),
    sort_columns={
        "campo_codigo": "CAMPO_CODIGO",
        "campo_nombre": "CAMPO_NOMBRE",
        "productor_codigo": "PRODUCTOR_CODIGO",
        "productor_nombre": "PRODUCTOR_NOMBRE",
    },
    filters=(
        Filter("productor_codigo", "PRODUCTOR_CODIGO", "=", trim=True),
        Filter("productor_cuit", "PRODUCTOR_CUIT", "=", trim=True),
    ),
)


class CampoProductor(BaseModel):
    # Quita los espacios de relleno que pueda traer la vista.
    model_config = ConfigDict(str_strip_whitespace=True)

    campo_codigo: int
    campo_nombre: str | None = None
    productor_codigo: str | None = None
    productor_nombre: str | None = None
    productor_cuit: str | None = None


MODEL = CampoProductor

router = APIRouter(
    prefix="/v1/campos-productores",
    tags=["campos_productores"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_model=Page[CampoProductor])
def listar_campos_productores(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    productor_codigo: Annotated[str | None, Query(min_length=1, max_length=10)] = None,
    productor_cuit: Annotated[str | None, Query(min_length=1, max_length=14)] = None,
    sort: SortField = "campo_codigo",
    order: SortOrder = "asc",
) -> dict[str, Any]:
    total, rows = fetch_page(
        db,
        SPEC,
        settings.view_schema,
        {"productor_codigo": productor_codigo, "productor_cuit": productor_cuit},
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}


@router.get("/{campo_codigo}", response_model=list[CampoProductor])
def obtener_campos_productores(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    campo_codigo: Annotated[int, Path(ge=1, le=MAX_CAMPO_CODIGO)],
) -> list[dict[str, Any]]:
    """Todas las filas con ese id. 404 si no existe."""
    rows = fetch_all_by_id(db, SPEC, settings.view_schema, campo_codigo)
    if not rows:
        raise HTTPException(status_code=404, detail="Not found")
    return rows
