# Guía: publicar una vista nueva como API

Cada API de este proyecto publica **una vista Oracle** en modo solo lectura, con dos
endpoints: listado paginado (`GET /v1/<recurso>`) y detalle por id (`GET /v1/<recurso>/{id}`).
Todo lo común (autenticación, paginación con `ROWNUM`, binds, lista blanca de orden,
errores sin `ORA-`, rate limit, logs) ya está resuelto: una API nueva es un archivo en
`app/routers/` más sus tests.

---

## 1. Antes de programar: relevar la vista

Preguntas a responder (con consultas de solo lectura, o con `--from-db`, que hace las dos
primeras solo):

| Pregunta | Por qué importa |
|---|---|
| ¿Qué columnas y tipos tiene? | Define el modelo Pydantic y los `max_length` de los filtros. |
| ¿La columna id es única? | Si se repite, el detalle devuelve una lista y el orden necesita `tiebreak_columns` (caso `IA_CAMPOS`). |
| ¿Hay columnas con espacios de relleno? (`"    228"`) | Los filtros tienen que comparar con `TRIM` (`--trim`). |
| ¿En qué esquema está? | Si no es el de `VIEW_SCHEMA`, indicarlo con `--schema`. |
| ¿Tiene datos personales? (CUIT, documento, email, teléfono) | Publicar solo lo que los consumidores necesitan. |
| ¿Por qué columnas van a filtrar y ordenar los consumidores? | Solo esas entran en `filters` y `sort_columns`. |

Consultas útiles:

```sql
-- Columnas y tipos
SELECT column_name, data_type, data_length, data_precision, data_scale
FROM all_tab_columns WHERE owner = 'SYSADMIN' AND table_name = 'IA_CAMPOS' ORDER BY column_id;

-- ¿El id es único?
SELECT COUNT(*), COUNT(DISTINCT campo_codigo) FROM sysadmin.ia_campos;

-- ¿Espacios de relleno?
SELECT COUNT(*) FROM sysadmin.ia_campos WHERE productor_codigo <> TRIM(productor_codigo);
```

---

## 2. Generar el router y los tests

`scripts/new_api.py` genera `app/routers/<recurso>.py` y `tests/test_<recurso>.py`, registra
el módulo en `app/routers/__init__.py` y formatea con ruff.

**Leyendo la vista desde la base** (usa la conexión del `.env`; solo lee el diccionario de
datos y hace un `COUNT` para ver si el id es único):

```powershell
.venv\Scripts\python scripts\new_api.py ordenes_carga --view IA_ORDENES_CARGA --from-db `
    --id ORDEN_NUMERO --filter PRODUCTOR_CODIGO --trim --date-filter FECHA_EMISION
```

**Sin base**, indicando las columnas a mano:

```powershell
.venv\Scripts\python scripts\new_api.py depositos --view V_DEPOSITOS --schema LOGISTICA `
    --columns "DEPOSITO_ID:NUMBER(6),NOMBRE:VARCHAR2(60),SUPERFICIE:NUMBER(12,2),ALTA:DATE" `
    --id DEPOSITO_ID --filter NOMBRE --date-filter ALTA
```

Con `--dry-run` muestra el router por pantalla sin escribir nada. `--help` lista todas las
opciones.

| Opción | Efecto |
|---|---|
| `recurso` | Nombre del módulo y de la URL (`ordenes_carga` → `/v1/ordenes-carga`). |
| `--view` | Vista Oracle. |
| `--schema` | Esquema propio de la vista (`ViewSpec.schema`); si no, se usa `VIEW_SCHEMA`. |
| `--from-db` / `--columns` | De dónde salen las columnas. |
| `--id` | Columna del detalle (entera). Default: la primera. |
| `--filter COL` | Filtro de igualdad (repetible). Columnas de texto o enteras. |
| `--trim` | Los filtros de texto comparan `TRIM(columna)`. |
| `--date-filter COL` | Agrega `fecha_desde` / `fecha_hasta` (inclusive) sobre una columna `DATE`. |
| `--detail-list` | El id se repite: el detalle devuelve una lista. Con `--from-db` se detecta solo. |
| `--model` | Nombre de la clase Pydantic (default: recurso en CamelCase). |

Mapeo de tipos que aplica el generador:

| Oracle | Python / JSON |
|---|---|
| `NUMBER(p)` / `NUMBER(p,0)` / `INTEGER` | `int` |
| `NUMBER(p,s)` con `s > 0` | `Decimal` (exacto; en JSON sale como string) |
| `NUMBER` sin precisión, `FLOAT`, `BINARY_DOUBLE` | `float` (revisar: puede convenir `int` o `Decimal`) |
| `DATE`, `TIMESTAMP` | `datetime` (el `DATE` de Oracle incluye la hora) |
| `VARCHAR2`, `CHAR`, `CLOB`, otros | `str` |

---

## 3. Revisar lo generado (obligatorio)

El generador arma una base correcta y segura, pero no conoce el negocio. Revisar en
`app/routers/<recurso>.py`:

1. **`sort_columns` y `SortField`**: el generador incluye todas las columnas. Dejar solo
   las que tenga sentido ordenar (ordenar por una columna sin índice en una vista grande es
   lento). Los dos tienen que coincidir (lo verifica un test).
2. **Filtros**: los que pidan los consumidores. Cada filtro del `SPEC` necesita su parámetro
   en `listar_<recurso>` y su entrada en el diccionario que se pasa a `fetch_page`.
3. **id repetido**: si el generador dejó un `TODO` en `tiebreak_columns`, completarlo con
   las columnas que identifican una fila (en `IA_CAMPOS`: `CAMPO_CODIGO, PRODUCTOR_CODIGO`).
   Sin eso la paginación no es estable.
4. **Datos personales**: quitar del `SPEC.columns` y del modelo lo que no haga falta.
5. **Campos obligatorios**: todo sale opcional (`| None = None`) salvo el id. Está bien así
   salvo que la vista garantice `NOT NULL`.
6. **Docstring**: dejar una descripción de la vista y lo que se relevó (como en `campos.py`).

Reglas que no se negocian (ver `app/query.py`):

- Nunca concatenar valores del usuario al SQL: todo filtro es un `Filter` → bind variable.
- Lo único que se interpola son identificadores constantes del `SPEC`, validados por regex.
- `sort` siempre pasa por la lista blanca `SortField` → `sort_columns`.
- Todo router de vista lleva `dependencies=[Depends(require_user)]`.

---

## 4. Tests

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check .
.venv\Scripts\ruff format --check .
```

- **`tests/test_contratos.py`** corre solo sobre todo módulo de `VIEW_MODULES`: que
  exponga `router`, `SPEC`, `SortField` y `MODEL`; que `SortField` coincida con
  `SPEC.sort_columns`; que el modelo coincida con las columnas; que los GET exijan token;
  que el listado responda con el formato paginado (esto valida que los filtros del router
  coincidan con los del `SPEC`); y que un error de base no filtre `ORA-` ni el nombre de la
  vista.
- **`tests/test_<recurso>.py`** (generado) cubre lo propio de la vista: SQL con la vista y
  el orden esperados, filtros como binds, detalle 200/404 e ids inválidos (422). Agregar acá
  los casos particulares (espacios de relleno, orden con desempate, etc.).

Los tests usan una base simulada (`FakeDatabase` en `tests/conftest.py`), no hace falta
Oracle.

---

## 5. Base de datos (DBA)

Agregar en `sql/setup.sql` el permiso sobre la vista nueva y pedirle al DBA que lo ejecute:

```sql
GRANT SELECT ON <ESQUEMA>.<VISTA> TO API_READONLY;
```

Si la vista lee tablas de otro esquema, el dueño de la vista necesita `SELECT ... WITH GRANT
OPTION` sobre esas tablas. Si se usan sinónimos en lugar de `VIEW_SCHEMA`, crear también el
sinónimo.

---

## 6. Probar de punta a punta

1. `run_local.bat --reload` y abrir `http://127.0.0.1:8000/docs` → **Authorize** → probar.
2. Agregar a `postman/apis_server.postman_collection.json` una carpeta con: listado,
   listado paginado y ordenado, cada filtro, detalle, detalle inexistente (404) y un `sort`
   fuera de la lista blanca (422). La colección ya hace el login sola.
3. Actualizar la tabla de endpoints del `README.md`.

---

## Checklist

- [ ] Vista relevada (tipos, unicidad del id, espacios de relleno, datos personales)
- [ ] `scripts/new_api.py ...` ejecutado
- [ ] Router revisado: orden, filtros, `tiebreak_columns`, columnas publicadas, docstring
- [ ] Tests propios de la vista agregados si hay casos particulares
- [ ] `pytest`, `ruff check` y `ruff format --check` sin errores
- [ ] `GRANT SELECT` agregado en `sql/setup.sql`
- [ ] Probado en `/docs` contra la base de prueba
- [ ] Requests agregados a la colección de Postman
- [ ] Endpoint agregado al `README.md`

---

## Hacerlo a mano (sin el generador)

1. Copiar `app/routers/productos.py` (id único) o `app/routers/campos.py` (id repetido) a
   `app/routers/<recurso>.py`.
2. Ajustar `SPEC` (vista, columnas en mayúsculas, id, `sort_columns`, filtros), `SortField`,
   el modelo Pydantic (campos = columnas en minúsculas) y `MODEL`.
3. Agregar el módulo al import y a `VIEW_MODULES` en `app/routers/__init__.py`.
4. Seguir desde el paso 3 de esta guía.
