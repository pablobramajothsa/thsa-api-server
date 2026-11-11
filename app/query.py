"""Construcción de SQL para las vistas publicadas (compatible con Oracle 11g).

Regla de seguridad: todo valor que viene del usuario viaja como bind variable.
Lo único que se interpola en el texto SQL son identificadores definidos como constantes
en el código (ViewSpec / Filter), validados con una expresión regular al definirse, y el
esquema de configuración (validado en Settings). El ordenamiento elegido por el usuario
se traduce a una columna mediante una lista blanca fija.

Paginación: 11g no soporta OFFSET/FETCH, se usa el patrón con ROWNUM.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from app.db import Database, Row

_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_$#]{0,29}$")
_BIND_NAME = re.compile(r"^[a-z][a-z0-9_]{0,29}$")
_OPERATORS = frozenset({"=", "<", "<=", ">", ">="})
_DIRECTIONS = {"asc": "ASC", "desc": "DESC"}

SortOrder = Literal["asc", "desc"]


def _identifier(name: str) -> str:
    if not _IDENTIFIER.fullmatch(name):
        raise ValueError(f"invalid SQL identifier: {name!r}")
    return name


@dataclass(frozen=True)
class Filter:
    """Filtro opcional: `<column> <op> :<param>` (o `TRIM(<column>) ...` si trim=True,
    para columnas que la vista devuelve con espacios de relleno)."""

    param: str
    column: str
    op: str
    trim: bool = False

    def __post_init__(self) -> None:
        _identifier(self.column)
        if not _BIND_NAME.fullmatch(self.param):
            raise ValueError(f"invalid bind name: {self.param!r}")
        if self.op not in _OPERATORS:
            raise ValueError(f"invalid operator: {self.op!r}")


@dataclass(frozen=True)
class ViewSpec:
    view: str
    columns: tuple[str, ...]
    id_column: str
    sort_columns: Mapping[str, str]  # nombre público -> columna
    filters: tuple[Filter, ...] = field(default_factory=tuple)
    # Columnas que juntas identifican una fila; se usan como desempate del ORDER BY.
    # Por defecto, solo id_column (cuando el id es único).
    tiebreak_columns: tuple[str, ...] = ()
    # Esquema propio de esta vista. Si es None se usa VIEW_SCHEMA (o los sinónimos).
    schema: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.view)
        if self.schema is not None:
            _identifier(self.schema)
        for column in self.columns:
            _identifier(column)
        if self.id_column not in self.columns:
            raise ValueError("id_column must be one of the columns")
        for column in self.sort_columns.values():
            if column not in self.columns:
                raise ValueError(f"sort column {column!r} is not a view column")
        for column in self.tiebreak_columns:
            if column not in self.columns:
                raise ValueError(f"tiebreak column {column!r} is not a view column")

    @property
    def key_columns(self) -> tuple[str, ...]:
        return self.tiebreak_columns or (self.id_column,)

    def source(self, schema: str | None) -> str:
        schema = self.schema or schema
        return f"{_identifier(schema)}.{self.view}" if schema else self.view


def _where(spec: ViewSpec, filters: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    known = {f.param for f in spec.filters}
    unknown = set(filters) - known
    if unknown:
        raise ValueError(f"unknown filters: {sorted(unknown)}")

    clauses: list[str] = []
    binds: dict[str, Any] = {}
    for f in spec.filters:
        value = filters.get(f.param)
        if value is None:
            continue
        target = f"TRIM({f.column})" if f.trim else f.column
        clauses.append(f"{target} {f.op} :{f.param}")
        binds[f.param] = value.strip() if f.trim and isinstance(value, str) else value
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, binds


def _order_by(spec: ViewSpec, sort: str, order: SortOrder) -> str:
    column = spec.sort_columns[sort]
    direction = _DIRECTIONS[order]
    # Desempate por las columnas clave para que el orden sea determinístico.
    parts = [f"{column} {direction}"]
    parts += [f"{key} ASC" for key in spec.key_columns if key != column]
    return ", ".join(parts)


def build_count_sql(
    spec: ViewSpec, schema: str | None, filters: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    where, binds = _where(spec, filters)
    sql = f"SELECT COUNT(*) FROM {spec.source(schema)}{where}"  # noqa: S608 - solo identificadores constantes
    return sql, binds


def build_page_sql(
    spec: ViewSpec,
    schema: str | None,
    filters: Mapping[str, Any],
    *,
    sort: str,
    order: SortOrder,
    page: int,
    limit: int,
) -> tuple[str, dict[str, Any]]:
    where, binds = _where(spec, filters)
    columns = ", ".join(spec.columns)
    inner = (
        f"SELECT {columns} FROM {spec.source(schema)}{where} "  # noqa: S608 - solo identificadores constantes
        f"ORDER BY {_order_by(spec, sort, order)}"
    )
    sql = (
        f"SELECT {columns} FROM ("  # noqa: S608 - solo identificadores constantes
        f"SELECT q.*, ROWNUM AS rn__ FROM ({inner}) q WHERE ROWNUM <= :max_row"
        f") WHERE rn__ > :min_row ORDER BY rn__"
    )
    binds["max_row"] = page * limit
    binds["min_row"] = (page - 1) * limit
    return sql, binds


def build_detail_sql(
    spec: ViewSpec, schema: str | None, item_id: int | str
) -> tuple[str, dict[str, Any]]:
    columns = ", ".join(spec.columns)
    order_by = ", ".join(f"{key} ASC" for key in spec.key_columns)
    sql = (
        f"SELECT {columns} FROM {spec.source(schema)} "  # noqa: S608 - solo identificadores constantes
        f"WHERE {spec.id_column} = :item_id ORDER BY {order_by}"
    )
    return sql, {"item_id": item_id}


def fetch_page(
    db: Database,
    spec: ViewSpec,
    schema: str | None,
    filters: Mapping[str, Any],
    *,
    sort: str,
    order: SortOrder,
    page: int,
    limit: int,
) -> tuple[int, list[Row]]:
    count_sql, count_binds = build_count_sql(spec, schema, filters)
    total = int(db.scalar(count_sql, count_binds) or 0)
    if total == 0 or (page - 1) * limit >= total:
        return total, []
    page_sql, page_binds = build_page_sql(
        spec, schema, filters, sort=sort, order=order, page=page, limit=limit
    )
    return total, db.fetch_all(page_sql, page_binds)


def fetch_by_id(db: Database, spec: ViewSpec, schema: str | None, item_id: int | str) -> Row | None:
    sql, binds = build_detail_sql(spec, schema, item_id)
    return db.fetch_one(sql, binds)


def fetch_all_by_id(
    db: Database, spec: ViewSpec, schema: str | None, item_id: int | str
) -> list[Row]:
    """Para vistas donde el id se repite (p. ej. un campo con varios productores)."""
    sql, binds = build_detail_sql(spec, schema, item_id)
    return db.fetch_all(sql, binds)
