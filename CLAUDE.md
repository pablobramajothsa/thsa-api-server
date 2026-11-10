# CLAUDE.md

API REST de **solo lectura** (FastAPI) que publica vistas de **Oracle 11.2.0.4** con login
usuario/contraseña → JWT. Idioma del proyecto: español (código, comentarios, docs, tests).
Documentación completa: `README.md`, `docs/DOCUMENTACION_PROYECTO.md`.

## Comandos

```powershell
.venv\Scripts\python -m pytest                # tests (no necesitan Oracle)
.venv\Scripts\ruff check .                    # lint
.venv\Scripts\ruff format --check .           # formato (line-length 100)
run_local.bat --reload                        # API en http://127.0.0.1:8000/docs
.venv\Scripts\python scripts\new_api.py --help  # generar una API nueva
```

En Bash (Git Bash) usar `./.venv/Scripts/python.exe` y exportar `PYTHONIOENCODING=utf-8`
(la ruta del proyecto tiene acentos y la consola es cp1252).

## Agregar una API (vista nueva)

Seguir `docs/GUIA_NUEVA_API.md`. Resumen:

1. `scripts/new_api.py <recurso> --view <VISTA> --from-db|--columns ... [--id --filter --trim --date-filter]`
   genera `app/routers/<recurso>.py` + `tests/test_<recurso>.py` y lo registra en
   `VIEW_MODULES` (`app/routers/__init__.py`).
2. Revisar el router: recortar `sort_columns`/`SortField`, filtros, `tiebreak_columns` si el
   id se repite, quitar datos personales.
3. `GRANT SELECT` en `sql/setup.sql`, requests en la colección de Postman, endpoint en README.

`tests/test_contratos.py` valida automáticamente todo módulo de `VIEW_MODULES`.

## Reglas de seguridad (no romper)

- **Nunca** interpolar valores del usuario en SQL. Solo identificadores constantes de
  `ViewSpec`/`Filter` (validados por regex en `app/query.py`); los valores van como binds.
- `sort` siempre por lista blanca (`SortField` ↔ `SPEC.sort_columns`).
- Todo router de vista: prefix `/v1/...` y `dependencies=[Depends(require_user)]`.
- Errores: el cliente recibe 500 genérico con `request_id`; el detalle (`ORA-`) solo al log.
  No devolver mensajes de excepción en respuestas.
- No loguear contraseñas, tokens ni `Settings` (usa `SecretStr`).
- Solo GET para datos; el único POST es el login.

## Arquitectura (lo no obvio)

- `create_app()` es factory (`uvicorn app.main:create_app --factory`); los tests le pasan
  `Settings` y una `FakeDatabase` (`tests/conftest.py`).
- Backend por `DB_DRIVER`: `jdbc` (default; JPype + `lib/ojdbc8-19.27.0.0.jar` + pool propio
  en `app/pool.py`) u `oracledb` (modo thick + Instant Client 19). 11g **no** soporta el modo
  thin de python-oracledb.
- Paginación 11g: `ROWNUM` (no existe `OFFSET/FETCH`). El orden siempre desempata por
  `SPEC.key_columns` para que sea determinístico.
- Interfaz `Database` (`app/db.py`): `fetch_all`, `fetch_one`, `scalar`, `close`. Binds con
  nombre `:x`; el backend JDBC los convierte a `?`.
- Esquema: `ViewSpec.schema` (por vista) > `VIEW_SCHEMA` (.env) > sinónimos.
- Columnas `CHAR`/padded: filtros con `Filter(..., trim=True)` y modelo con
  `ConfigDict(str_strip_whitespace=True)`.
- El JVM arranca una vez por proceso; pytest corre con `-p no:faulthandler` porque la JVM
  provoca "access violation" internas en Windows (inofensivas).

## Archivos que no se versionan

`.env`, `users.json`, `postman/*.postman_environment.json`, `lib/*.jar`. No leer ni copiar
sus valores a código, docs, tests o mensajes.
