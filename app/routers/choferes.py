"""Vista IA_CHOFERES.

Maestro de choferes.

Relevada el 11/11/2026 en la base de prueba (Oracle 11.2.0.4).
- CODIGO es texto (solo dígitos, sin relleno). 54810 filas, 54775 códigos: hay 35 filas
  repetidas idénticas, por eso el detalle devuelve una sola fila.
- PRO_EMPRESA_TRANSPORTE viene con espacios de relleno ("  42420"): filtros con TRIM.
- ACTIVO: "Si", "No" o "Ap".
- Datos personales: NOMBRE, CUIT, PRO_CARNET_CONDUCTOR y patentes.

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
    PRO_EMPRESA_TRANSPORTE VARCHAR2(10)
    ENT_NOMBRE VARCHAR2(50)
    PRO_CARNET_CONDUCTOR VARCHAR2(15)
    PRO_PATENTE_CAMION VARCHAR2(10)
    PRO_PATENTE_ACOPLADO VARCHAR2(10)
    TIPO_CAMION VARCHAR2(50)
    PRO_KILOS_MAXIMOS NUMBER(13)
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
    view="IA_CHOFERES",
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
        "PRO_EMPRESA_TRANSPORTE",
        "ENT_NOMBRE",
        "PRO_CARNET_CONDUCTOR",
        "PRO_PATENTE_CAMION",
        "PRO_PATENTE_ACOPLADO",
        "TIPO_CAMION",
        "PRO_KILOS_MAXIMOS",
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
        Filter("pro_empresa_transporte", "PRO_EMPRESA_TRANSPORTE", "=", trim=True),
        Filter("pro_patente_camion", "PRO_PATENTE_CAMION", "=", trim=True),
    ),
)


class Chofer(BaseModel):
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
    pro_empresa_transporte: str | None = None
    ent_nombre: str | None = None
    pro_carnet_conductor: str | None = None
    pro_patente_camion: str | None = None
    pro_patente_acoplado: str | None = None
    tipo_camion: str | None = None
    pro_kilos_maximos: int | None = None


MODEL = Chofer

router = APIRouter(prefix="/v1/choferes", tags=["choferes"], dependencies=[Depends(require_user)])


@router.get("", response_model=Page[Chofer])
def listar_choferes(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    cuit: Annotated[str | None, Query(min_length=1, max_length=14)] = None,
    comercial_codigo: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    zona: Annotated[str | None, Query(min_length=1, max_length=5)] = None,
    categoria: Annotated[int | None, Query(ge=0)] = None,
    activo: Annotated[
        str | None, Query(min_length=1, max_length=2, description="Si, No o Ap")
    ] = None,
    pro_empresa_transporte: Annotated[str | None, Query(min_length=1, max_length=10)] = None,
    pro_patente_camion: Annotated[str | None, Query(min_length=1, max_length=10)] = None,
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
            "pro_empresa_transporte": pro_empresa_transporte,
            "pro_patente_camion": pro_patente_camion,
        },
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}


@router.get("/{codigo}", response_model=Chofer)
def obtener_choferes(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    codigo: Annotated[str, Path(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")],
) -> dict[str, Any]:
    row = fetch_by_id(db, SPEC, settings.view_schema, codigo)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row
