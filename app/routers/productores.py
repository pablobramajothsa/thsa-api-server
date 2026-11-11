"""Vista IA_PRODUCTORES.

Maestro de productores.

Relevada el 11/11/2026 en la base de prueba (Oracle 11.2.0.4).
- CODIGO es texto (solo dígitos, sin relleno) y único: 16927 filas. En IA_CAMPOS el
  código del productor viene con relleno; la API lo devuelve recortado, así que coinciden.
- ACTIVO: "Si" o "No".
- Datos personales: NOMBRE y CUIT.

Estructura relevada:
    CODIGO VARCHAR2(20)
    NOMBRE VARCHAR2(50)
    CUIT VARCHAR2(14)
    COMERCIAL_CODIGO VARCHAR2(20)
    COMERCIAL_NOMBRE VARCHAR2(50)
    ZONA VARCHAR2(5)
    ZONA_DESCRIPCION VARCHAR2(50)
    CATEGORIA NUMBER(3)
    CATEGORIA_NOMBRE VARCHAR2(50)
    ACTIVO CHAR(2)
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.params import Page, PageParams, page_params
from app.query import Filter, SortOrder, ViewSpec, fetch_by_id, fetch_page
from app.security import require_user

SortField = Literal["codigo", "nombre", "zona", "categoria"]

SPEC = ViewSpec(
    view="IA_PRODUCTORES",
    columns=(
        "CODIGO",
        "NOMBRE",
        "CUIT",
        "COMERCIAL_CODIGO",
        "COMERCIAL_NOMBRE",
        "ZONA",
        "ZONA_DESCRIPCION",
        "CATEGORIA",
        "CATEGORIA_NOMBRE",
        "ACTIVO",
    ),
    id_column="CODIGO",
    sort_columns={
        "codigo": "CODIGO",
        "nombre": "NOMBRE",
        "zona": "ZONA",
        "categoria": "CATEGORIA",
    },
    filters=(
        Filter("cuit", "CUIT", "=", trim=True),
        Filter("comercial_codigo", "COMERCIAL_CODIGO", "=", trim=True),
        Filter("zona", "ZONA", "=", trim=True),
        Filter("categoria", "CATEGORIA", "="),
        Filter("activo", "ACTIVO", "=", trim=True),
    ),
)


class Productor(BaseModel):
    # Quita los espacios de relleno que pueda traer la vista.
    model_config = ConfigDict(str_strip_whitespace=True)

    codigo: str
    nombre: str | None = None
    cuit: str | None = None
    comercial_codigo: str | None = None
    comercial_nombre: str | None = None
    zona: str | None = None
    zona_descripcion: str | None = None
    categoria: int | None = None
    categoria_nombre: str | None = None
    activo: str | None = None


MODEL = Productor

router = APIRouter(
    prefix="/v1/productores", tags=["productores"], dependencies=[Depends(require_user)]
)


@router.get("", response_model=Page[Productor])
def listar_productores(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    cuit: Annotated[str | None, Query(min_length=1, max_length=14)] = None,
    comercial_codigo: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    zona: Annotated[str | None, Query(min_length=1, max_length=5)] = None,
    categoria: Annotated[int | None, Query(ge=0)] = None,
    activo: Annotated[str | None, Query(min_length=1, max_length=2, description="Si o No")] = None,
    sort: SortField = "codigo",
    order: SortOrder = "asc",
) -> dict[str, Any]:
    total, rows = fetch_page(
        db,
        SPEC,
        settings.view_schema,
        {
            "cuit": cuit,
            "comercial_codigo": comercial_codigo,
            "zona": zona,
            "categoria": categoria,
            "activo": activo,
        },
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}


@router.get("/{codigo}", response_model=Productor)
def obtener_productores(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    codigo: Annotated[str, Path(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")],
) -> dict[str, Any]:
    row = fetch_by_id(db, SPEC, settings.view_schema, codigo)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row
