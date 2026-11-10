"""Genera una API nueva (router + tests) para publicar una vista Oracle.

Uso (desde la carpeta del proyecto):

    # Leyendo la estructura de la vista desde la base (usa la conexión del .env):
    .venv\\Scripts\\python scripts\\new_api.py ordenes_carga --view IA_ORDENES_CARGA --from-db \\
        --id ORDEN_NUMERO --filter PRODUCTOR_CODIGO --date-filter FECHA_EMISION

    # Sin base, indicando las columnas a mano (NOMBRE:TIPO, tipos Oracle):
    .venv\\Scripts\\python scripts\\new_api.py depositos --view V_DEPOSITOS \\
        --columns "DEPOSITO_ID:NUMBER(6),NOMBRE:VARCHAR2(60),ALTA:DATE" --filter NOMBRE

Opciones:
    --view NOMBRE         vista Oracle (obligatoria)
    --schema ESQUEMA      esquema propio de la vista (si no, VIEW_SCHEMA del .env)
    --from-db             leer columnas de ALL_TAB_COLUMNS y verificar si el id es único
    --columns LISTA       columnas a mano: "COL:NUMBER(7),COL2:VARCHAR2(50),COL3:DATE"
    --id COLUMNA          columna id del detalle (default: la primera)
    --filter COLUMNA      filtro de igualdad (repetible)
    --trim                comparar los filtros de texto con TRIM (columnas con espacios de relleno)
    --date-filter COLUMNA rango fecha_desde / fecha_hasta sobre esa columna DATE
    --detail-list         el id se repite: el detalle devuelve una lista (con --from-db se detecta)
    --model NOMBRE        nombre de la clase Pydantic (default: recurso en CamelCase)
    --dry-run             mostrar el router por pantalla sin escribir nada
    --no-register         no agregar el módulo a app/routers/__init__.py
    --force               sobrescribir archivos existentes

Genera app/routers/<recurso>.py y tests/test_<recurso>.py, registra el módulo en
VIEW_MODULES y formatea con ruff. Después revisar el router generado (ver
docs/GUIA_NUEVA_API.md): lista de orden, filtros y columnas con datos personales.
"""

import argparse
import keyword
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel  # noqa: E402

from app.query import _BIND_NAME, _IDENTIFIER  # noqa: E402

ROUTERS_DIR = ROOT / "app" / "routers"
TESTS_DIR = ROOT / "tests"
REGISTRY = ROUTERS_DIR / "__init__.py"

_RESOURCE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_COLUMN_SPEC = re.compile(
    r"^\s*(?P<name>[A-Za-z][A-Za-z0-9_$#]*)\s*:\s*(?P<type>[A-Za-z0-9_ ]+?)"
    r"\s*(?:\(\s*(?P<p>\d+)\s*(?:,\s*(?P<s>-?\d+)\s*)?\))?\s*$"
)
_RESERVED_BINDS = {"max_row", "min_row", "item_id", "fecha_desde", "fecha_hasta_excl"}
_STRING_TYPES = {"VARCHAR2", "VARCHAR", "NVARCHAR2", "CHAR", "NCHAR", "CLOB", "NCLOB", "LONG"}
_LOB_TYPES = {"CLOB", "NCLOB", "BLOB", "LONG", "RAW", "LONG RAW"}

DICTIONARY_SQL = (
    "SELECT column_name, data_type, data_length, data_precision, data_scale "
    "FROM all_tab_columns WHERE owner = :owner AND table_name = :view ORDER BY column_id"
)


class ScaffoldError(Exception):
    pass


# --- Columnas -----------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    name: str
    oracle_type: str
    length: int | None = None
    precision: int | None = None
    scale: int | None = None

    @property
    def field(self) -> str:
        return self.name.lower()

    @property
    def base_type(self) -> str:
        return self.oracle_type.split("(")[0].upper()

    @property
    def is_string(self) -> bool:
        return self.base_type in _STRING_TYPES

    @property
    def sortable(self) -> bool:
        return self.base_type not in _LOB_TYPES

    def py_type(self, is_id: bool) -> str:
        t = self.base_type
        if t == "NUMBER":
            if is_id or self.scale == 0:
                return "int"
            if self.scale is not None and self.scale > 0:
                return "Decimal"  # exacto; en JSON se serializa como string
            return "float"  # NUMBER sin precisión: revisar si conviene int o Decimal
        if t in ("INTEGER", "SMALLINT"):
            return "int"
        if t in ("FLOAT", "BINARY_FLOAT", "BINARY_DOUBLE"):
            return "float"
        if t == "DATE" or t.startswith("TIMESTAMP"):
            return "datetime"  # DATE de Oracle incluye la hora
        return "str"

    def describe(self) -> str:
        if self.base_type == "NUMBER" and self.precision is not None:
            size = f"({self.precision},{self.scale})" if self.scale else f"({self.precision})"
        elif self.is_string and self.length is not None and self.base_type not in _LOB_TYPES:
            size = f"({self.length})"
        else:
            size = ""
        return f"{self.name} {self.base_type}{size}"


def parse_columns(text: str) -> list[Column]:
    columns = []
    for part in re.split(r",(?![^()]*\))", text):  # las comas de NUMBER(12,2) no separan
        match = _COLUMN_SPEC.fullmatch(part)
        if not match:
            raise ScaffoldError(f"columna inválida: {part.strip()!r} (formato NOMBRE:TIPO(n))")
        oracle_type = " ".join(match["type"].upper().split())
        p = int(match["p"]) if match["p"] else None
        s = int(match["s"]) if match["s"] else None
        name = match["name"].upper()
        if oracle_type == "NUMBER":
            # NUMBER(p) tiene escala 0; NUMBER sin precisión no tiene ni precisión ni escala.
            scale = (s or 0) if p is not None else None
            columns.append(Column(name, oracle_type, None, p, scale))
        else:
            columns.append(Column(name, oracle_type, p))
    return columns


def open_db():
    """Conexión con la configuración del .env (solo lee el diccionario y hace un conteo)."""
    import os

    os.chdir(ROOT)  # el .env y el .jar se buscan con rutas relativas a la raíz
    from app.config import Settings
    from app.db import OracleDatabase
    from app.db_jdbc import JdbcDatabase

    settings = Settings()
    db = JdbcDatabase(settings) if settings.db_driver == "jdbc" else OracleDatabase(settings)
    return db, settings


def columns_from_db(db, view: str, owner: str) -> list[Column]:
    rows = db.fetch_all(DICTIONARY_SQL, {"owner": owner, "view": view})
    if not rows:
        raise ScaffoldError(
            f"no se encontró {owner}.{view} en ALL_TAB_COLUMNS "
            "(¿nombre o esquema incorrecto, o falta el GRANT SELECT?)"
        )
    columns = [
        Column(
            r["column_name"],
            r["data_type"],
            r["data_length"],
            r["data_precision"],
            r["data_scale"],
        )
        for r in rows
    ]
    return columns


def id_counts(db, view: str, owner: str, id_column: str) -> tuple[int, int] | None:
    """(filas, valores distintos del id)."""
    for name in (view, owner, id_column):
        if not _IDENTIFIER.fullmatch(name):
            raise ScaffoldError(f"identificador inválido: {name!r}")
    sql = (
        f"SELECT COUNT(*) AS total, COUNT(DISTINCT {id_column}) AS distintos "  # noqa: S608
        f"FROM {owner}.{view}"
    )
    try:
        row = db.fetch_one(sql, {})
    except Exception as exc:
        print(f"[AVISO] no se pudo verificar si {id_column} es único: {exc}")
        return None
    return (int(row["total"]), int(row["distintos"])) if row else None


# --- Generación ---------------------------------------------------------------


@dataclass
class Plan:
    resource: str
    model: str
    view: str
    schema: str | None
    columns: list[Column]
    id_column: Column
    filters: list[Column]
    trim: bool
    date_filter: Column | None
    detail_list: bool

    @property
    def prefix(self) -> str:
        return "/v1/" + self.resource.replace("_", "-")

    @property
    def path_param(self) -> str:
        return "item_id" if self.id_column.field == "id" else self.id_column.field

    @property
    def source(self) -> str:
        return f"{self.schema}.{self.view}" if self.schema else self.view

    @property
    def sort_fields(self) -> list[Column]:
        return [c for c in self.columns if c.sortable]

    def max_id(self) -> tuple[str, str]:
        """(nombre de la constante, expresión)."""
        p = self.id_column.precision
        if self.id_column.base_type == "NUMBER" and p and self.id_column.scale == 0 and p < 18:
            name = f"MAX_{self.id_column.name}"
            return name, f"{10**p - 1:_}  # NUMBER({p})"
        return "MAX_ID", ""


def _camel(resource: str) -> str:
    return "".join(part.capitalize() for part in resource.split("_"))


def validate(plan: Plan) -> None:
    if not _IDENTIFIER.fullmatch(plan.view):
        raise ScaffoldError(f"nombre de vista inválido: {plan.view!r}")
    if plan.schema and not _IDENTIFIER.fullmatch(plan.schema):
        raise ScaffoldError(f"esquema inválido: {plan.schema!r}")
    names = [c.name for c in plan.columns]
    if len(names) != len(set(names)):
        raise ScaffoldError("hay columnas repetidas")
    reserved = set(dir(BaseModel))
    for column in plan.columns:
        if not _IDENTIFIER.fullmatch(column.name):
            raise ScaffoldError(f"columna con nombre no soportado: {column.name!r}")
        if keyword.iskeyword(column.field) or column.field in reserved:
            raise ScaffoldError(
                f"la columna {column.name} choca con un nombre reservado de Python/Pydantic; "
                "pedir un alias en la vista"
            )
    for column in plan.filters:
        if not _BIND_NAME.fullmatch(column.field) or column.field in _RESERVED_BINDS:
            raise ScaffoldError(f"la columna {column.name} no se puede usar como filtro")
        if not (column.is_string or column.py_type(False) == "int"):
            raise ScaffoldError(
                f"--filter {column.name}: solo columnas de texto o enteras "
                "(para fechas usar --date-filter)"
            )
    if plan.date_filter and plan.date_filter.py_type(False) != "datetime":
        raise ScaffoldError(f"--date-filter {plan.date_filter.name} no es una columna DATE")
    if plan.id_column.py_type(True) != "int":
        raise ScaffoldError(
            f"la columna id {plan.id_column.name} no es numérica: el generador solo soporta "
            "ids enteros (adaptar el router a mano)"
        )


def _filter_param(column: Column) -> str:
    if column.py_type(False) == "int":
        annotation = "int | None"
        query = "Query(ge=0)"
    elif column.is_string:
        annotation = "str | None"
        max_len = f", max_length={column.length}" if column.length else ""
        query = f"Query(min_length=1{max_len})"
    else:
        annotation = f"{column.py_type(False)} | None"
        query = "Query()"
    return f"    {column.field}: Annotated[{annotation}, {query}] = None,"


def render_router(plan: Plan) -> str:
    types = {c.py_type(c is plan.id_column) for c in plan.columns}
    has_str = any(c.is_string for c in plan.columns)
    max_name, max_expr = plan.max_id()
    fetch_detail = "fetch_all_by_id" if plan.detail_list else "fetch_by_id"

    std_imports = []
    if "datetime" in types:
        std_imports.append("from datetime import datetime")
    if "Decimal" in types:
        std_imports.append("from decimal import Decimal")
    std_imports.append("from typing import Annotated, Any, Literal")

    fastapi_names = ["APIRouter", "Depends", "HTTPException", "Path"]
    if plan.filters:
        fastapi_names.append("Query")
    pydantic_names = ["BaseModel"] + (["ConfigDict"] if has_str else [])
    params_names = ["Page", "PageParams", "page_params"]
    if plan.date_filter:
        params_names.append("date_range_filters")
    if max_name == "MAX_ID":
        params_names.append("MAX_ID")
    query_names = ["SortOrder", "ViewSpec", fetch_detail, "fetch_page"]
    if plan.filters or plan.date_filter:
        query_names.insert(0, "Filter")

    structure = "\n".join(f"    {c.describe()}" for c in plan.columns)
    out: list[str] = [
        f'"""Vista {plan.source}.',
        "",
        f"Generado con scripts/new_api.py el {date.today():%d/%m/%Y}. Revisar antes de publicar:",
        "- sort_columns / SortField: dejar solo las columnas por las que tenga sentido ordenar.",
        "- Filtros: agregar o quitar según lo que necesiten los consumidores.",
        "- Datos personales (CUIT, documento, email, teléfono): quitar las columnas innecesarias.",
        "",
        "Estructura relevada:",
        structure,
        '"""',
        "",
        *std_imports,
        "",
        f"from fastapi import {', '.join(fastapi_names)}",
        f"from pydantic import {', '.join(pydantic_names)}",
        "",
        "from app.config import Settings, get_settings",
        "from app.db import Database, get_db",
        f"from app.params import {', '.join(params_names)}",
        f"from app.query import {', '.join(query_names)}",
        "from app.security import require_user",
        "",
    ]
    if max_name != "MAX_ID":
        out += [f"{max_name} = {max_expr}", ""]
    out += [
        "SortField = Literal[" + ", ".join(f'"{c.field}"' for c in plan.sort_fields) + "]",
        "",
        "SPEC = ViewSpec(",
        f'    view="{plan.view}",',
    ]
    if plan.schema:
        out.append(f'    schema="{plan.schema}",')
    out.append("    columns=(")
    out += [f'        "{c.name}",' for c in plan.columns]
    out += [
        "    ),",
        f'    id_column="{plan.id_column.name}",',
    ]
    if plan.detail_list:
        out.append(
            "    # TODO: el id se repite; completar con las columnas que identifican una fila."
        )
        out.append(f'    tiebreak_columns=("{plan.id_column.name}",),')
    out.append("    sort_columns={")
    out += [f'        "{c.field}": "{c.name}",' for c in plan.sort_fields]
    out.append("    },")
    if plan.filters or plan.date_filter:
        out.append("    filters=(")
        for c in plan.filters:
            trim = ", trim=True" if plan.trim and c.is_string else ""
            out.append(f'        Filter("{c.field}", "{c.name}", "="{trim}),')
        if plan.date_filter:
            d = plan.date_filter.name
            out.append(f'        Filter("fecha_desde", "{d}", ">="),')
            out.append(f'        Filter("fecha_hasta_excl", "{d}", "<"),')
        out.append("    ),")
    out += [")", "", ""]

    out.append(f"class {plan.model}(BaseModel):")
    if has_str:
        out += [
            "    # Quita los espacios de relleno que pueda traer la vista.",
            "    model_config = ConfigDict(str_strip_whitespace=True)",
            "",
        ]
    for c in plan.columns:
        t = c.py_type(c is plan.id_column)
        optional = "" if c is plan.id_column else " | None = None"
        out.append(f"    {c.field}: {t}{optional}")
    out += [
        "",
        "",
        f"MODEL = {plan.model}",
        "",
        "router = APIRouter(",
        f'    prefix="{plan.prefix}", tags=["{plan.resource}"], '
        "dependencies=[Depends(require_user)]",
        ")",
        "",
        "",
        f'@router.get("", response_model=Page[{plan.model}])',
        f"def listar_{plan.resource}(",
        "    db: Annotated[Database, Depends(get_db)],",
        "    settings: Annotated[Settings, Depends(get_settings)],",
        "    paging: Annotated[PageParams, Depends(page_params)],",
    ]
    if plan.date_filter:
        out.append("    dates: Annotated[dict[str, Any], Depends(date_range_filters)],")
    out += [_filter_param(c) for c in plan.filters]
    out += [
        f'    sort: SortField = "{plan.id_column.field}",',
        '    order: SortOrder = "asc",',
        ") -> dict[str, Any]:",
    ]
    filter_items = [f'"{c.field}": {c.field}' for c in plan.filters]
    if plan.date_filter:
        filter_items.append("**dates")
    out += [
        "    total, rows = fetch_page(",
        "        db,",
        "        SPEC,",
        "        settings.view_schema,",
        f"        {{{', '.join(filter_items)}}},",
        "        sort=sort,",
        "        order=order,",
        "        page=paging.page,",
        "        limit=paging.limit,",
        "    )",
        '    return {"page": paging.page, "limit": paging.limit, "total": total, "data": rows}',
        "",
        "",
    ]
    p = plan.path_param
    if plan.detail_list:
        out += [
            f'@router.get("/{{{p}}}", response_model=list[{plan.model}])',
            f"def obtener_{plan.resource}(",
            "    db: Annotated[Database, Depends(get_db)],",
            "    settings: Annotated[Settings, Depends(get_settings)],",
            f"    {p}: Annotated[int, Path(ge=1, le={max_name})],",
            ") -> list[dict[str, Any]]:",
            '    """Todas las filas con ese id. 404 si no existe."""',
            f"    rows = fetch_all_by_id(db, SPEC, settings.view_schema, {p})",
            "    if not rows:",
            '        raise HTTPException(status_code=404, detail="Not found")',
            "    return rows",
        ]
    else:
        out += [
            f'@router.get("/{{{p}}}", response_model={plan.model})',
            f"def obtener_{plan.resource}(",
            "    db: Annotated[Database, Depends(get_db)],",
            "    settings: Annotated[Settings, Depends(get_settings)],",
            f"    {p}: Annotated[int, Path(ge=1, le={max_name})],",
            ") -> dict[str, Any]:",
            f"    row = fetch_by_id(db, SPEC, settings.view_schema, {p})",
            "    if row is None:",
            '        raise HTTPException(status_code=404, detail="Not found")',
            "    return row",
        ]
    return "\n".join(out) + "\n"


def _sample(column: Column, is_id: bool) -> str:
    t = column.py_type(is_id)
    if t == "int":
        return "1" if is_id else "10"
    if t == "float":
        return "1.5"
    if t == "Decimal":
        return 'Decimal("12.50")'
    if t == "datetime":
        return "datetime(2024, 1, 15, 10, 30)"
    max_len = column.length or 5
    return repr("TEXTO"[:max_len] or "T")


def render_test(plan: Plan) -> str:
    types = {c.py_type(c is plan.id_column) for c in plan.columns}
    order_by = f"ORDER BY {plan.id_column.name} ASC"
    std_imports = []
    if "datetime" in types:
        std_imports.append("from datetime import datetime")
    if "Decimal" in types:
        std_imports.append("from decimal import Decimal")
    out = [
        f'"""Tests de {plan.prefix} (vista {plan.source}).',
        "",
        "Lo común a todas las vistas (lista blanca de orden, modelo, token, errores de base)",
        'ya lo cubre tests/test_contratos.py."""',
        "",
        *std_imports,
        "",
        "import pytest",
        "",
        f'URL = "{plan.prefix}"',
        "",
        "FILA = {",
    ]
    out += [f'    "{c.field}": {_sample(c, c is plan.id_column)},' for c in plan.columns]
    out += [
        "}",
        "",
        "",
        "def test_listado_formato_y_sql(client, fake_db, auth):",
        "    fake_db.total = 1",
        "    fake_db.rows = [FILA]",
        "",
        "    response = client.get(URL, headers=auth)",
        '    sql, binds = fake_db.last("all")',
        "",
        "    assert response.status_code == 200, response.text",
        '    assert response.json()["total"] == 1',
        f'    assert response.json()["data"][0]["{plan.id_column.field}"] == '
        f'FILA["{plan.id_column.field}"]',
        f'    assert "FROM {plan.source}" in sql',
        f'    assert "{order_by}" in sql',
        '    assert binds["min_row"] == 0',
        '    assert binds["max_row"] == 20',
        "",
    ]
    if plan.filters:
        params, asserts = [], []
        for c in plan.filters:
            value = "5" if c.py_type(False) == "int" else "malicioso"
            params.append(f'"{c.field}": {value}')
            target = f"TRIM({c.name})" if plan.trim and c.is_string else c.name
            asserts.append(f'    assert "{target} = :{c.field}" in sql')
            asserts.append(f'    assert binds["{c.field}"] == {value}')
        # El valor de prueba no puede superar el max_length del filtro de texto más corto.
        lengths = [c.length for c in plan.filters if c.is_string and c.length]
        malicious = "X' OR '1'='1"[: min(lengths, default=12)]
        out += [
            "",
            "def test_filtros_viajan_como_binds(client, fake_db, auth):",
            "    fake_db.total = 1",
            f"    malicioso = {malicious!r}",
            f"    response = client.get(URL, params={{{', '.join(params)}}}, headers=auth)",
            '    sql, binds = fake_db.last("all")',
            "",
            "    assert response.status_code == 200, response.text",
            "    assert malicioso not in sql",
            *asserts,
            "",
        ]
    if plan.date_filter:
        d = plan.date_filter.name
        out += [
            "",
            "def test_rango_de_fechas(client, fake_db, auth):",
            "    fake_db.total = 1",
            "    response = client.get(",
            '        URL, params={"fecha_desde": "2024-01-01", "fecha_hasta": "2024-01-31"}, '
            "headers=auth",
            "    )",
            '    sql, _ = fake_db.last("all")',
            "",
            "    assert response.status_code == 200, response.text",
            f'    assert "{d} >= :fecha_desde" in sql',
            f'    assert "{d} < :fecha_hasta_excl" in sql',
            "",
        ]
    id_value = _sample(plan.id_column, True)
    if plan.detail_list:
        out += [
            "",
            "def test_detalle_devuelve_todas_las_filas(client, fake_db, auth):",
            "    fake_db.rows = [FILA]",
            f'    response = client.get(f"{{URL}}/{id_value}", headers=auth)',
            '    sql, binds = fake_db.last("all")',
            "",
            "    assert response.status_code == 200, response.text",
            "    assert len(response.json()) == 1",
            f'    assert "WHERE {plan.id_column.name} = :item_id" in sql',
            f'    assert binds == {{"item_id": {id_value}}}',
            "",
            "",
            "def test_detalle_inexistente_404(client, fake_db, auth):",
            "    fake_db.rows = []",
            '    response = client.get(f"{URL}/999", headers=auth)',
            "    assert response.status_code == 404",
            '    assert response.json() == {"detail": "Not found"}',
            "",
        ]
    else:
        out += [
            "",
            "def test_detalle_existente(client, fake_db, auth):",
            "    fake_db.detail = FILA",
            f'    response = client.get(f"{{URL}}/{id_value}", headers=auth)',
            '    sql, binds = fake_db.last("one")',
            "",
            "    assert response.status_code == 200, response.text",
            f'    assert response.json()["{plan.id_column.field}"] == {id_value}',
            f'    assert "WHERE {plan.id_column.name} = :item_id" in sql',
            f'    assert binds == {{"item_id": {id_value}}}',
            "",
            "",
            "def test_detalle_inexistente_404(client, fake_db, auth):",
            "    fake_db.detail = None",
            '    response = client.get(f"{URL}/999", headers=auth)',
            "    assert response.status_code == 404",
            '    assert response.json() == {"detail": "Not found"}',
            "",
        ]
    out += [
        "",
        '@pytest.mark.parametrize("valor", ["0", "-1", "abc", "1.5"])',
        "def test_id_invalido_422(client, fake_db, auth, valor):",
        '    assert client.get(f"{URL}/{valor}", headers=auth).status_code == 422',
        "    assert fake_db.calls == []",
    ]
    return "\n".join(out) + "\n"


def register(resource: str) -> bool:
    text = REGISTRY.read_text(encoding="utf-8")
    import_match = re.search(r"^from app\.routers import ([^\n(]+)$", text, re.MULTILINE)
    modules_match = re.search(
        r"(VIEW_MODULES: tuple\[ModuleType, \.\.\.\] = \(\n)(.*?)(\n\))", text, re.DOTALL
    )
    if not import_match or not modules_match:
        return False
    names = {n.strip() for n in import_match[1].split(",")} | {resource}
    text = text.replace(import_match[0], "from app.routers import " + ", ".join(sorted(names)))
    modules_match = re.search(
        r"(VIEW_MODULES: tuple\[ModuleType, \.\.\.\] = \(\n)(.*?)(\n\))", text, re.DOTALL
    )
    if modules_match is None:
        return False
    body = modules_match[2]
    if not re.search(rf"^\s*{resource},\s*$", body, re.MULTILINE):
        body = body.rstrip() + f"\n    {resource},"
        text = text[: modules_match.start(2)] + body + text[modules_match.end(2) :]
    REGISTRY.write_text(text, encoding="utf-8")
    return True


def ruff(paths: list[Path]) -> None:
    exe = Path(sys.executable).with_name("ruff.exe" if sys.platform == "win32" else "ruff")
    cmd = [str(exe)] if exe.exists() else [sys.executable, "-m", "ruff"]
    files = [str(p) for p in paths]
    try:
        subprocess.run([*cmd, "check", "--fix", "--quiet", *files], check=False)  # noqa: S603
        subprocess.run([*cmd, "format", "--quiet", *files], check=False)  # noqa: S603
    except OSError:
        print("[AVISO] no se encontró ruff: formatear a mano con 'ruff format'")


# --- CLI ----------------------------------------------------------------------


def build_plan(args: argparse.Namespace) -> Plan:
    if not _RESOURCE.fullmatch(args.resource):
        raise ScaffoldError("recurso: minúsculas, números y _ (p. ej. ordenes_carga)")
    view = args.view.upper()
    schema = args.schema.upper() if args.schema else None
    if not args.from_db and not args.columns:
        raise ScaffoldError("indicar --from-db o --columns")
    if not args.from_db:
        return _plan(args, view, schema, parse_columns(args.columns), None, None)
    db, settings = open_db()
    owner = (schema or settings.view_schema or settings.db_user).upper()
    try:
        return _plan(args, view, schema, columns_from_db(db, view, owner), db, owner)
    finally:
        db.close()


def _plan(args, view, schema, columns, db, owner) -> Plan:

    by_name = {c.name: c for c in columns}

    def pick(name: str) -> Column:
        column = by_name.get(name.upper())
        if column is None:
            raise ScaffoldError(f"la columna {name.upper()} no está en la vista")
        return column

    id_column = pick(args.id) if args.id else columns[0]
    detail_list = args.detail_list
    if db is not None and not detail_list:
        counts = id_counts(db, view, owner, id_column.name)
        if counts:
            total, distinct = counts
            print(f"{view}: {total} filas, {distinct} valores distintos de {id_column.name}")
            if total != distinct:
                print(f"[AVISO] {id_column.name} se repite: el detalle devolverá una lista.")
                detail_list = True
    return Plan(
        resource=args.resource,
        model=args.model or _camel(args.resource),
        view=view,
        schema=schema,
        columns=columns,
        id_column=id_column,
        filters=[pick(name) for name in args.filter],
        trim=args.trim,
        date_filter=pick(args.date_filter) if args.date_filter else None,
        detail_list=detail_list,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera una API nueva sobre una vista Oracle")
    parser.add_argument("resource", help="nombre del recurso (módulo y URL), p. ej. ordenes_carga")
    parser.add_argument("--view", required=True)
    parser.add_argument("--schema")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--from-db", action="store_true")
    source.add_argument("--columns")
    parser.add_argument("--id")
    parser.add_argument("--filter", action="append", default=[])
    parser.add_argument("--trim", action="store_true")
    parser.add_argument("--date-filter")
    parser.add_argument("--detail-list", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-register", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    try:
        plan = build_plan(args)
        validate(plan)
    except ScaffoldError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    router_src, test_src = render_router(plan), render_test(plan)
    if args.dry_run:
        print(router_src)
        return 0

    router_path = ROUTERS_DIR / f"{plan.resource}.py"
    test_path = TESTS_DIR / f"test_{plan.resource}.py"
    existing = [p for p in (router_path, test_path) if p.exists()]
    if existing and not args.force:
        names = ", ".join(str(p.relative_to(ROOT)) for p in existing)
        print(f"[ERROR] ya existe: {names} (usar --force para sobrescribir)", file=sys.stderr)
        return 1

    router_path.write_text(router_src, encoding="utf-8")
    test_path.write_text(test_src, encoding="utf-8")
    touched = [router_path, test_path]
    registered = False
    if not args.no_register:
        registered = register(plan.resource)
        if registered:
            touched.append(REGISTRY)
    ruff(touched)

    print(f"Creado  {router_path.relative_to(ROOT)}")
    print(f"Creado  {test_path.relative_to(ROOT)}")
    if registered:
        print(f"Registrado en {REGISTRY.relative_to(ROOT)} (VIEW_MODULES)")
    elif not args.no_register:
        print(f"[AVISO] agregar '{plan.resource}' a VIEW_MODULES en {REGISTRY.relative_to(ROOT)}")
    grant_owner = plan.schema or "&&owner_schema"
    print("\nPasos siguientes (docs/GUIA_NUEVA_API.md):")
    print(f"  1. Revisar {router_path.relative_to(ROOT)}: orden, filtros y datos personales.")
    print("  2. Correr los tests:  .venv\\Scripts\\python -m pytest")
    print(f"  3. GRANT para el DBA:  GRANT SELECT ON {grant_owner}.{plan.view} TO &&api_user;")
    print(f"  4. Agregar los requests de {plan.prefix} a la colección de Postman.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
