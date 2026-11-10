"""Vista V_PRODUCTOS (placeholder: ajustar nombre y columnas a la vista real)."""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.params import MAX_ID, Page, PageParams, date_range_filters, page_params
from app.query import Filter, SortOrder, ViewSpec, fetch_by_id, fetch_page
from app.security import require_user

SortField = Literal["id", "nombre", "categoria", "precio", "fecha_alta"]

SPEC = ViewSpec(
    view="V_PRODUCTOS",
    columns=("ID", "NOMBRE", "CATEGORIA", "PRECIO", "FECHA_ALTA"),
    id_column="ID",
    sort_columns={
        "id": "ID",
        "nombre": "NOMBRE",
        "categoria": "CATEGORIA",
        "precio": "PRECIO",
        "fecha_alta": "FECHA_ALTA",
    },
    filters=(
        Filter("categoria", "CATEGORIA", "="),
        Filter("fecha_desde", "FECHA_ALTA", ">="),
        Filter("fecha_hasta_excl", "FECHA_ALTA", "<"),
    ),
)


class Producto(BaseModel):
    id: int
    nombre: str
    categoria: str | None = None
    precio: float | None = None
    fecha_alta: datetime | None = None


MODEL = Producto

router = APIRouter(prefix="/v1/productos", tags=["productos"], dependencies=[Depends(require_user)])


@router.get("", response_model=Page[Producto])
def listar_productos(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    dates: Annotated[dict[str, Any], Depends(date_range_filters)],
    categoria: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    sort: SortField = "id",
    order: SortOrder = "asc",
) -> dict[str, Any]:
    total, rows = fetch_page(
        db,
        SPEC,
        settings.view_schema,
        {"categoria": categoria, **dates},
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}


@router.get("/{item_id}", response_model=Producto)
def obtener_producto(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    item_id: Annotated[int, Path(ge=1, le=MAX_ID)],
) -> dict[str, Any]:
    row = fetch_by_id(db, SPEC, settings.view_schema, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row
