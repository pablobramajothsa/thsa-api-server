"""Parámetros comunes de los listados y modelo de respuesta paginada."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Any, Generic, TypeVar

from fastapi import HTTPException, Query, status
from pydantic import BaseModel

MAX_PAGE = 100_000
MAX_LIMIT = 100
DEFAULT_LIMIT = 20
MAX_ID = 10**18

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    page: int
    limit: int
    total: int
    data: list[T]


@dataclass(frozen=True)
class PageParams:
    page: int
    limit: int


def page_params(
    page: Annotated[int, Query(ge=1, le=MAX_PAGE, description="Número de página (desde 1)")] = 1,
    limit: Annotated[
        int, Query(ge=1, le=MAX_LIMIT, description="Registros por página (1 a 100)")
    ] = DEFAULT_LIMIT,
) -> PageParams:
    return PageParams(page=page, limit=limit)


def date_range_filters(
    fecha_desde: Annotated[date | None, Query(description="Fecha mínima (inclusive)")] = None,
    fecha_hasta: Annotated[date | None, Query(description="Fecha máxima (inclusive)")] = None,
) -> dict[str, Any]:
    """Devuelve los binds del rango; fecha_hasta se convierte a 'menor que el día siguiente'
    para incluir todo el día aunque la columna DATE tenga hora."""
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="fecha_desde must be less than or equal to fecha_hasta",
        )
    return {
        "fecha_desde": fecha_desde,
        "fecha_hasta_excl": fecha_hasta + timedelta(days=1) if fecha_hasta else None,
    }
