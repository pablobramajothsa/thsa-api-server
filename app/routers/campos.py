"""Vista SYSADMIN.IA_CAMPOS (base de prueba, Oracle 11.2.0.4).

Estructura relevada:
    CAMPO_CODIGO NUMBER(7), CAMPO_NOMBRE VARCHAR2(50), DOMICILIO VARCHAR2(79),
    CODIGO_POSTAL VARCHAR2(42), CPO_LOCALIDAD VARCHAR2(50), KILOMETROS VARCHAR2(0),
    PRODUCTOR_CODIGO VARCHAR2(10), PRODUCTOR_NOMBRE VARCHAR2(50), PRODUCTOR_CUIT VARCHAR2(14),
    URL VARCHAR2(2083) (agregada el 10/11/2026; puede venir vacía)

CAMPO_CODIGO no es único: un campo puede estar asociado a varios productores. La fila se
identifica por (CAMPO_CODIGO, PRODUCTOR_CODIGO), que se usa como desempate del orden. Por
eso el detalle devuelve una lista (una fila por productor).

Nota: PRODUCTOR_CUIT puede ser un dato personal (CUIT de persona física).
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

SortField = Literal[
    "campo_codigo", "campo_nombre", "cpo_localidad", "productor_codigo", "productor_nombre"
]

SPEC = ViewSpec(
    view="IA_CAMPOS",
    columns=(
        "CAMPO_CODIGO",
        "CAMPO_NOMBRE",
        "DOMICILIO",
        "CODIGO_POSTAL",
        "CPO_LOCALIDAD",
        "KILOMETROS",
        "PRODUCTOR_CODIGO",
        "PRODUCTOR_NOMBRE",
        "PRODUCTOR_CUIT",
        "URL",
    ),
    id_column="CAMPO_CODIGO",
    tiebreak_columns=("CAMPO_CODIGO", "PRODUCTOR_CODIGO"),
    sort_columns={
        "campo_codigo": "CAMPO_CODIGO",
        "campo_nombre": "CAMPO_NOMBRE",
        "cpo_localidad": "CPO_LOCALIDAD",
        "productor_codigo": "PRODUCTOR_CODIGO",
        "productor_nombre": "PRODUCTOR_NOMBRE",
    },
    filters=(
        # La vista devuelve estos campos con espacios de relleno ("    228"): se compara con TRIM.
        Filter("productor_codigo", "PRODUCTOR_CODIGO", "=", trim=True),
        Filter("productor_cuit", "PRODUCTOR_CUIT", "=", trim=True),
        Filter("codigo_postal", "CODIGO_POSTAL", "=", trim=True),
        Filter("localidad", "CPO_LOCALIDAD", "=", trim=True),
    ),
)


class Campo(BaseModel):
    # Quita los espacios de relleno que trae la vista (p. ej. PRODUCTOR_CODIGO = "    228").
    model_config = ConfigDict(str_strip_whitespace=True)

    campo_codigo: int
    campo_nombre: str | None = None
    domicilio: str | None = None
    codigo_postal: str | None = None
    cpo_localidad: str | None = None
    kilometros: str | None = None
    productor_codigo: str | None = None
    productor_nombre: str | None = None
    productor_cuit: str | None = None
    url: str | None = None


MODEL = Campo

router = APIRouter(prefix="/v1/campos", tags=["campos"], dependencies=[Depends(require_user)])


@router.get("", response_model=Page[Campo])
def listar_campos(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    paging: Annotated[PageParams, Depends(page_params)],
    productor_codigo: Annotated[str | None, Query(min_length=1, max_length=10)] = None,
    productor_cuit: Annotated[str | None, Query(min_length=1, max_length=14)] = None,
    codigo_postal: Annotated[str | None, Query(min_length=1, max_length=42)] = None,
    localidad: Annotated[
        str | None, Query(min_length=1, max_length=50, description="CPO_LOCALIDAD exacta")
    ] = None,
    sort: SortField = "campo_codigo",
    order: SortOrder = "asc",
) -> dict[str, Any]:
    total, rows = fetch_page(
        db,
        SPEC,
        settings.view_schema,
        {
            "productor_codigo": productor_codigo,
            "productor_cuit": productor_cuit,
            "codigo_postal": codigo_postal,
            "localidad": localidad,
        },
        sort=sort,
        order=order,
        page=paging.page,
        limit=paging.limit,
    )
    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}


@router.get("/{campo_codigo}", response_model=list[Campo])
def obtener_campo(
    db: Annotated[Database, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    campo_codigo: Annotated[int, Path(ge=1, le=MAX_CAMPO_CODIGO)],
) -> list[dict[str, Any]]:
    """Todas las filas del campo (una por productor asociado). 404 si no existe."""
    rows = fetch_all_by_id(db, SPEC, settings.view_schema, campo_codigo)
    if not rows:
        raise HTTPException(status_code=404, detail="Not found")
    return rows
