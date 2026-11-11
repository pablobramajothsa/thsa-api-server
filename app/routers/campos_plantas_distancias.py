"""Vista IA_CAMPOS_PLANTAS_DISTANCIAS.

Distancias de cada campo a las plantas: kilómetros según el formulario 1116A y
según el transportista.

Relevada el 11/11/2026 en la base de prueba (Oracle 11.2.0.4).
- 45076 filas, 14603 campos. Ninguna combinación de columnas es única: hay filas
  repetidas idénticas (37722 distintas) y 30183 filas sin planta (PLANTA_CODIGO nulo).
  El orden desempata por todas las columnas, así que solo empatan filas idénticas.
- El detalle por campo devuelve una lista (hasta 42 filas por campo).
- PLANTA_NOMBRE trae espacios de relleno: la respuesta los quita.

Estructura relevada:
    CAMPO_CODIGO NUMBER(7)
    PLANTA_CODIGO NUMBER(5)
    PLANTA_NOMBRE VARCHAR2(50)
    KMS_1116A NUMBER(7,2)
    KMS_TRANSPORTISTA NUMBER(7,2)
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

SortField = Literal["campo_codigo", "planta_codigo", "planta_nombre"]

SPEC = ViewSpec(
    view="IA_CAMPOS_PLANTAS_DISTANCIAS",
    columns=(
        "CAMPO_CODIGO",
        "PLANTA_CODIGO",
        "PLANTA_NOMBRE",
        "KMS_1116A",
        "KMS_TRANSPORTISTA",
    ),
    id_column="CAMPO_CODIGO",
    tiebreak_columns=(
        "CAMPO_CODIGO",
        "PLANTA_CODIGO",
        "KMS_1116A",
        "KMS_TRANSPORTISTA",
    ),
    sort_columns={
        "campo_codigo": "CAMPO_CODIGO",
        "planta_codigo": "PLANTA_CODIGO",
        "planta_nombre": "PLANTA_NOMBRE",
    },
    filters=(Filter("planta_codigo", "PLANTA_CODIGO", "="),),
)


class CampoPlantaDistancia(BaseModel):
    # Quita los espacios de relleno que pueda traer la vista.
    model_config = ConfigDict(str_strip_whitespace=True)

    campo_codigo: int
    planta_codigo: int | None = None
    planta_nombre: str | None = None
    kms_1116a: float | None = None
    kms_transportista: float | None = None


MODEL = CampoPlantaDistancia

router = APIRouter(
    prefix="/v1/campos-plantas-distancias",
    tags=["campos_plantas_distancias"],
    dependencies=[Depends(require_user)],
)


@router.get("", response_model=Page[CampoPlantaDistancia])
def listar_campos_plantas_distancias(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    planta_codigo: Annotated[int | None, Query(ge=0)] = None,
    sort: SortField = "campo_codigo",
    order: SortOrder = "asc",
) -> dict[str, Any]:
    total, rows = fetch_page(
        db,
        SPEC,
        settings.view_schema,
        {"planta_codigo": planta_codigo},
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}


@router.get("/{campo_codigo}", response_model=list[CampoPlantaDistancia])
def obtener_campos_plantas_distancias(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    campo_codigo: Annotated[int, Path(ge=1, le=MAX_CAMPO_CODIGO)],
) -> list[dict[str, Any]]:
    """Todas las filas con ese id. 404 si no existe."""
    rows = fetch_all_by_id(db, SPEC, settings.view_schema, campo_codigo)
    if not rows:
        raise HTTPException(status_code=404, detail="Not found")
    return rows
