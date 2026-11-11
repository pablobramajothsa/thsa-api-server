# API de solo lectura sobre vistas Oracle — Documentación del proyecto

Estado al 06/11/2026. Este documento resume qué se construyó, cómo está armado, qué
decisiones se tomaron (y por qué), cómo se verificó y qué queda pendiente.

> Este documento no contiene usuarios ni contraseñas. Las credenciales viven solo en
> archivos locales que no se versionan (`.env`, `users.json` y el environment de Postman).

---

## 1. Resumen

| Tema | Estado |
|---|---|
| API REST de solo lectura con FastAPI | Funcionando en local |
| Base de datos | Oracle **11.2.0.4** (base de prueba), conexión por **JDBC** |
| Vista publicada con datos reales | `SYSADMIN.IA_CAMPOS` → `/v1/campos` |
| Autenticación | Usuario y contraseña → **token JWT** (Bearer) |
| Tests | **148 tests** con pytest, todos pasan; `ruff check` sin observaciones |
| Prueba de punta a punta | Colección de Postman ejecutada contra la base de prueba: todo OK |
| Despliegue en servidor | **Pendiente** (hoy corre solo en local) |
| Control de versiones | Repositorio Git inicializado, **sin commits todavía** |

---

## 2. Arquitectura

```
Cliente (Postman, sistemas)
        │  HTTPS (pendiente: proxy inverso)
        ▼
uvicorn 127.0.0.1:8000
        │
        ▼
FastAPI ── middlewares: request id + headers de seguridad + log de accesos
        │              CORS (orígenes configurados)
        │              rate limit por IP (global + login)
        ├── /health                  (sin autenticación)
        ├── /v1/auth/token           (login → JWT)
        └── /v1/campos, /v1/...      (requieren Bearer token)
                │
                ▼
        app/query.py  ── arma SQL con identificadores fijos + bind variables
                │
                ▼
        Backend de base de datos (DB_DRIVER)
          ├── jdbc (por defecto): JVM embebida (JPype) + driver ojdbc8 19.27 + pool propio
          └── oracledb: python-oracledb modo thick + Instant Client 19 (alternativa)
                │
                ▼
        Oracle 11.2.0.4
```

### Estructura de carpetas

```
app/
  main.py          factory create_app(): middlewares, handlers de error, routers
  config.py        Settings (pydantic-settings) desde variables de entorno / .env
  jdbc.py          conversión de URL JDBC -> formato python-oracledb
  db.py            interfaz Database, DatabaseError y backend python-oracledb
  db_jdbc.py       backend JDBC (JPype + ojdbc8)
  pool.py          pool de conexiones genérico (usado por JDBC)
  query.py         construcción de SQL (paginación ROWNUM, filtros, orden)
  params.py        parámetros de paginación y fechas, modelo Page
  security.py      bcrypt + emisión/validación de tokens JWT
  users.py         usuarios desde users.json (se relee al cambiar)
  middleware.py    request id, headers de seguridad, log de accesos
  ratelimit.py     rate limiting por IP
  logging_conf.py  logs en JSON
  routers/
    __init__.py    registro de vistas publicadas (VIEW_MODULES)
    health.py      GET /health
    auth.py        POST /v1/auth/token
    campos.py      vista real SYSADMIN.IA_CAMPOS
    productos.py   ejemplo (placeholder V_PRODUCTOS)
    clientes.py    ejemplo (placeholder V_CLIENTES)
tests/             tests con base de datos simulada (salvo conversión de tipos con JVM real);
                   test_contratos.py valida toda vista registrada
sql/setup.sql      usuario de solo lectura, PROFILE y GRANTs (para el DBA)
scripts/
  manage_users.py  alta, baja y cambio de contraseña de usuarios de la API
  new_api.py       genera router + tests de una vista nueva (ver GUIA_NUEVA_API.md)
  run_local.ps1    arranque local (PowerShell)
postman/           colección de Postman (+ environment local, no versionado)
lib/               driver ojdbc8 (no versionado)
docs/              esta documentación y GUIA_NUEVA_API.md
run_local.bat      arranque local con doble clic
```

---

## 3. Stack y versiones

| Componente | Versión |
|---|---|
| Python | 3.13 (compatible con 3.10+) |
| FastAPI | 0.162.0 |
| uvicorn | 0.54.0 |
| pydantic-settings | 2.16.2 |
| limits (rate limiting) | 5.8.0 |
| PyJWT | 2.15.1 |
| bcrypt | 5.0.0 |
| python-multipart | 0.0.33 |
| JPype1 | 1.7.1 |
| python-oracledb (backend alternativo) | 26.1.0 |
| Java | Eclipse Temurin 17 JRE (17.0.21) |
| Driver JDBC | ojdbc8 19.27.0.0 (Maven Central, SHA1 verificado) |
| Tests / lint | pytest 9.2.0, httpx 0.28.1, ruff 0.17.4 |
| Git | 2.56 (instalado en esta sesión, a nivel de usuario) |

---

## 4. Endpoints

| Método y ruta | Token | Descripción |
|---|---|---|
| `GET /health` | no | `{"status":"ok"}` (200) o `{"status":"unavailable"}` (503). Ejecuta `SELECT 1 FROM DUAL`. No expone detalles. |
| `POST /v1/auth/token` | no | Login. Body `x-www-form-urlencoded` con `username` y `password`. Devuelve `access_token`, `token_type`, `expires_in`. |
| `GET /v1/campos` | sí | Listado paginado de `SYSADMIN.IA_CAMPOS`. |
| `GET /v1/campos/{campo_codigo}` | sí | Todas las filas del campo (una por productor). 404 si no existe. |
| `GET /v1/campos-plantas-distancias`, `/{campo_codigo}` | sí | `IA_CAMPOS_PLANTAS_DISTANCIAS`: kms de cada campo a cada planta. Filtro: `planta_codigo`. Detalle: lista. |
| `GET /v1/campos-productores`, `/{campo_codigo}` | sí | `IA_CAMPOS_PRODUCTORES`. Filtros: `productor_codigo`, `productor_cuit`. Detalle: lista (una fila por productor). |
| `GET /v1/catac` | sí | `IA_CATAC`: tarifas por tonelada. Filtros: `tarifa_codigo`, `kilometros`, `fecha_desde`/`fecha_hasta` (vigencia). Sin detalle. |
| `GET /v1/choferes`, `/{codigo}` | sí | `IA_CHOFERES`. Filtros: `cuit`, `comercial_codigo`, `zona`, `categoria`, `activo`, `pro_empresa_transporte`, `pro_patente_camion`. |
| `GET /v1/choferes-activos`, `/{codigo}` | sí | `IA_CHOFERES_ACTIVOS`. Mismos filtros que choferes. |
| `GET /v1/choferes-no-activos`, `/{codigo}` | sí | `IA_CHOFERES_NO_ACTIVOS`. Mismos filtros que choferes. |
| `GET /v1/compras-pendientes-facturas` | sí | `IA_COMPRAS_PENDIENTES_FACTURAS`. Filtros: `hca_codigo`, `hca_sucursal`, `hca_numero`, `hcv_entidad`, `hca_articulo`, `fecha_desde`/`fecha_hasta`. Sin detalle. |
| `GET /v1/compras-pendientes-ncnd` | sí | `IA_COMPRAS_PENDIENTES_NCND`. Mismos filtros que facturas. Sin detalle. |
| `GET /v1/empresas-transporte`, `/{codigo}` | sí | `IA_EMPRESA_TRANSPORTE`. Filtros: `cuit`, `comercial_codigo`, `zona`, `categoria`, `activo`. |
| `GET /v1/impuestos-regimenes`, `/{rgi_codigo_regimen}` | sí | `IA_IMPUESTOS_REGIMENES`. Filtros: `rgi_codigo_impuesto`, `rgi_tipo_operacion`, `rgi_provincia`, `rgi_habilitado`. |
| `GET /v1/plantas`, `/{pla_planta}` | sí | `IA_PLANTAS`. Filtros: `pla_inactivo`, `pla_codigo_postal`. |
| `GET /v1/productores`, `/{codigo}` | sí | `IA_PRODUCTORES`. Filtros: `cuit`, `comercial_codigo`, `zona`, `categoria`, `activo`. |
| `GET /v1/productos`, `/v1/productos/{id}` | sí | Ejemplo sobre `V_PRODUCTOS` (no existe en la base de prueba → 500). |
| `GET /v1/clientes`, `/v1/clientes/{id}` | sí | Ejemplo sobre `V_CLIENTES` (no existe en la base de prueba → 500). |

En desarrollo, la documentación interactiva está en `http://127.0.0.1:8000/docs`; el botón
**Authorize** permite hacer login y probar con el token. En producción `/docs`, `/redoc` y
`/openapi.json` quedan desactivados.

### Parámetros de `/v1/campos`

| Parámetro | Detalle |
|---|---|
| `page` | ≥ 1, default 1 |
| `limit` | 1 a 100, default 20 |
| `productor_codigo` | igualdad exacta (se ignoran espacios de relleno) |
| `productor_cuit` | igualdad exacta |
| `codigo_postal` | igualdad exacta |
| `localidad` | igualdad exacta sobre `CPO_LOCALIDAD` |
| `sort` | `campo_codigo` (default), `campo_nombre`, `cpo_localidad`, `productor_codigo`, `productor_nombre` |
| `order` | `asc` (default) o `desc` |

Formato de respuesta de los listados:

```json
{ "page": 1, "limit": 20, "total": 4334, "data": [ { "campo_codigo": 100449, "...": "..." } ] }
```

### Códigos de error

| Código | Cuándo |
|---|---|
| 401 `{"detail":"Unauthorized"}` | Login inválido, o token ausente, inválido, vencido o de un usuario desactivado. Siempre la misma respuesta. |
| 404 `{"detail":"Not found"}` | El registro no existe. |
| 405 | Método incorrecto (por ejemplo, `GET` al login). |
| 422 | Parámetros inválidos (paginación, `sort` fuera de la lista blanca, fechas, ids). |
| 429 `{"detail":"Too many requests"}` | Se superó el límite; incluye `Retry-After`. |
| 500 `{"detail":"Internal server error","request_id":"..."}` | Error interno o de base. El detalle (incluidos `ORA-xxxxx`) va solo al log con el mismo `request_id`. |

Todas las respuestas llevan el header `X-Request-ID`.

---

## 5. La vista `SYSADMIN.IA_CAMPOS`

Relevada con consultas de solo lectura sobre el diccionario de datos.

| Columna | Tipo | Observación |
|---|---|---|
| `CAMPO_CODIGO` | NUMBER(7) | **Se repite**: 4334 filas, 4311 códigos distintos. |
| `CAMPO_NOMBRE` | VARCHAR2(50) | |
| `DOMICILIO` | VARCHAR2(79) | |
| `CODIGO_POSTAL` | VARCHAR2(42) | 3802 filas con espacios de relleno. |
| `CPO_LOCALIDAD` | VARCHAR2(50) | |
| `KILOMETROS` | VARCHAR2(0) | Siempre vacía. |
| `PRODUCTOR_CODIGO` | VARCHAR2(10) | **Todas** las filas con espacios de relleno a la izquierda (ej. `"    228"`). |
| `PRODUCTOR_NOMBRE` | VARCHAR2(50) | |
| `PRODUCTOR_CUIT` | VARCHAR2(14) | Puede ser un dato personal (CUIT de persona física). |
| `URL` | VARCHAR2(2083) | Agregada el 10/11/2026. Al agregarla, vacía en las 4334 filas. Se publica como `url` (texto, puede ser `null`); no se ordena ni se filtra por ella. |

Decisiones derivadas:

- **Clave real `(CAMPO_CODIGO, PRODUCTOR_CODIGO)`**: verificado que es única (4334
  combinaciones = 4334 filas). Un campo puede tener varios productores, por eso el detalle
  devuelve una lista, y el orden de los listados desempata por esas dos columnas para que la
  paginación sea estable.
- **Espacios de relleno**: los filtros comparan contra `TRIM(columna)` y el valor recibido
  también se recorta; la respuesta JSON devuelve los textos sin esos espacios.

---

## 5.1 Vistas publicadas el 11/11/2026

Relevadas con consultas de solo lectura en la base de prueba (estructura, filas, claves,
espacios de relleno) y probadas de punta a punta con la app conectada por JDBC: listado,
cada orden permitido, cada filtro con un valor real, paginación y detalle.

| Vista → endpoint | Filas | Clave / detalle | Observaciones |
|---|---|---|---|
| `IA_CAMPOS_PLANTAS_DISTANCIAS` → `/v1/campos-plantas-distancias` | 45076 | Sin clave única. Detalle por `campo_codigo` → lista. | 30183 filas sin planta y filas repetidas idénticas (37722 distintas). |
| `IA_CAMPOS_PRODUCTORES` → `/v1/campos-productores` | 4334 | (`CAMPO_CODIGO`, `PRODUCTOR_CODIGO`). Detalle → lista. | `PRODUCTOR_CODIGO` con relleno (TRIM). |
| `IA_CATAC` → `/v1/catac` | 134510 | (`TARIFA_CODIGO`, `FECHA_VIGENCIA_DESDE`, `KILOMETROS`). Sin detalle. | Hasta 2400 filas por tarifa: se consulta con filtros. `SEGUNDA_TARIFA` vacía. |
| `IA_CHOFERES` → `/v1/choferes` | 54810 | `CODIGO` (texto). Detalle → una fila. | 35 filas repetidas idénticas. Datos personales (nombre, CUIT, carnet, patentes). |
| `IA_CHOFERES_ACTIVOS` → `/v1/choferes-activos` | 54810 | Igual que choferes. | **Devuelve lo mismo que `IA_CHOFERES`**, incluidos 12567 con `ACTIVO = 'No'`. |
| `IA_CHOFERES_NO_ACTIVOS` → `/v1/choferes-no-activos` | 0 | Igual que choferes. | **Vacía**, aunque hay 12567 choferes con `ACTIVO = 'No'`. |
| `IA_COMPRAS_PENDIENTES_FACTURAS` → `/v1/compras-pendientes-facturas` | 34 | (`HCA_CODIGO`, `HCA_SUCURSAL`, `HCA_NUMERO`, `HCA_RENGLON`). Sin detalle: filtrar por comprobante. | **Lenta: ~4 s por consulta** (cada request hace 2). Muchas columnas siempre nulas. |
| `IA_COMPRAS_PENDIENTES_NCND` → `/v1/compras-pendientes-ncnd` | 2 | Igual que facturas. | **Lenta: ~4 s por consulta.** |
| `IA_EMPRESA_TRANSPORTE` → `/v1/empresas-transporte` | 23407 | `CODIGO` (texto, único). | |
| `IA_IMPUESTOS_REGIMENES` → `/v1/impuestos-regimenes` | 263 | `RGI_CODIGO_REGIMEN` (único). | Valores con acento (`Sí`, `Retención`). |
| `IA_PLANTAS` → `/v1/plantas` | 68 | `PLA_PLANTA` (único). | `PLA_INACTIVO` = `Sí` (con acento) / `No`. |
| `IA_PRODUCTORES` → `/v1/productores` | 16927 | `CODIGO` (texto, único). | Coincide con el `PRODUCTOR_CODIGO` de `IA_CAMPOS` ya recortado. |

Criterios comunes:

- Se publican todas las columnas de cada vista, con los nombres en minúsculas.
- Los textos se devuelven sin espacios de relleno; los filtros sobre columnas que los traen
  comparan con `TRIM`.
- Las filas repetidas idénticas no rompen la paginación: el orden desempata por la clave (o
  por todas las columnas), así que solo empatan filas iguales.
- El detalle de los códigos de texto acepta letras y números (`/v1/choferes/125613`).
- Las notas de cada vista están en el docstring de su router (`app/routers/<recurso>.py`).

---

## 6. Conexión a la base de datos

### Base de prueba

- Oracle Database 11g Release 11.2.0.4.0 (64 bit).
- Host `192.168.16.248`, puerto `1521`, SID `BASE`.
- URL configurada: `jdbc:oracle:thin:@192.168.16.248:1521:BASE`.
- Usuario y contraseña: solo en el `.env` local.

### Por qué JDBC

Oracle 11g **no es compatible con el modo thin** de python-oracledb (requiere 12.1+). Las
alternativas eran:

1. python-oracledb en modo *thick* → requiere **Instant Client 19** (los clientes 11.2 y 12.1
   instalados en la máquina no sirven: `DPI-1050`).
2. **Driver JDBC de Oracle** ejecutado desde Python → no requiere Instant Client.

Se eligió **JDBC**. Se mantiene python-oracledb como alternativa configurable
(`DB_DRIVER=oracledb`).

### Cómo funciona el backend JDBC (`app/db_jdbc.py`)

- La JVM (Java 17) se inicia **una vez por proceso** con JPype, en el primer request
  (~3–4 s). Los requests siguientes tardan menos de un segundo.
- Se usa `DriverManager` con el driver `ojdbc8` 19.27 (soporta Oracle 11.2 y Java 8+).
- Las consultas usan **`PreparedStatement`** con parámetros `?`: los binds con nombre
  (`:nombre`) que arma `app/query.py` se convierten a posicionales antes de ejecutar.
- **Timeouts**: `setQueryTimeout` (desde `DB_CALL_TIMEOUT_MS`), timeout de conexión de 10 s
  y timeout de lectura de red del driver.
- Conexiones en modo **solo lectura** (`setReadOnly(true)`).
- **Pool propio** (`app/pool.py`), porque JDBC no trae uno: mínimo y máximo configurables,
  espera con timeout cuando no hay conexiones libres, validación (`isValid`) de conexiones
  ociosas y descarte de conexiones caídas.
- Conversión de tipos: `BigDecimal` → `int` o `Decimal`, `Timestamp` → `datetime`,
  `Date` → `date`, `String` → `str`, `CLOB` → `str`.
- Cualquier error Java/Oracle se convierte en `DatabaseError`; el cliente recibe el 500
  genérico y el detalle queda en el log.

### URL JDBC soportadas (`app/jdbc.py`)

- `jdbc:oracle:thin:@host:puerto:SID`
- `jdbc:oracle:thin:@host:puerto/servicio` y `@//host:puerto/servicio`
- `jdbc:oracle:thin:@(DESCRIPTION=...)`

Se rechazan URLs con usuario o contraseña embebidos: las credenciales van en `DB_USER` y
`DB_PASSWORD`.

---

## 7. Seguridad

| Requisito | Implementación |
|---|---|
| SQL sin concatenar datos del usuario | Solo se interpolan identificadores constantes (validados por regex); todos los valores van como bind variables / parámetros `?`. `sort` se traduce mediante una lista blanca fija. |
| Paginación compatible con 11g | `ROWNUM <= :max_row` / `rn__ > :min_row` (11g no tiene `OFFSET … FETCH`), con `ORDER BY` determinístico. |
| Autenticación | Usuario y contraseña → JWT HS256 firmado con `JWT_SECRET` (mínimo 32 caracteres), vencimiento configurable (30 min por defecto). Se validan firma, algoritmo (se rechaza `none`), vencimiento, emisor y audiencia. |
| Almacenamiento de contraseñas | Hash **bcrypt** (costo 12) en `users.json`; nunca texto plano. |
| No revelar usuarios existentes | Mismo 401 y mismo tiempo de respuesta para usuario inexistente o contraseña incorrecta. |
| Revocación | Desactivar o borrar un usuario invalida sus tokens en el acto (se verifica en cada request). |
| Rate limiting | 60 requests/minuto por IP (global) y 10 logins/minuto por IP. Configurables. |
| Timeout por consulta | `DB_CALL_TIMEOUT_MS` (5000 ms por defecto). |
| Errores sin detalles | Handler global: respuesta genérica con `request_id`; `ORA-xxxxx` solo en el log. |
| Documentación en producción | `/docs`, `/redoc` y `/openapi.json` desactivados con `ENV=production`. |
| CORS | Solo orígenes de `CORS_ORIGINS`; se rechaza `*`. Métodos GET y POST. |
| Headers de seguridad | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store`, `Content-Security-Policy`, `Permissions-Policy` y HSTS en producción. |
| Logs | JSON estructurado: IP, método, ruta, status, duración, usuario y request id. Nunca contraseñas ni tokens. Los logins fallidos registran el usuario intentado. |
| Secretos fuera del repo | `.env`, `users.json`, environment de Postman y `lib/*.jar` en `.gitignore`. La configuración no muestra secretos en errores de validación. |
| Pool de conexiones | Un pool por proceso; no se abre una conexión por request. |

---

## 8. Configuración (`.env`)

Plantilla con valores ficticios: `.env.example`.

| Variable | Default | Descripción |
|---|---|---|
| `ENV` | `development` | `development`, `test` o `production`. |
| `LOG_LEVEL` | `INFO` | Nivel de log. |
| `DB_DRIVER` | `jdbc` | `jdbc` u `oracledb`. |
| `JDBC_DRIVER_JAR` | `lib/ojdbc8-19.27.0.0.jar` | Ruta al driver JDBC. |
| `JAVA_HOME` | del sistema | Carpeta del JRE 8+. |
| `DB_USER` / `DB_PASSWORD` | — | Credenciales de la base. |
| `DB_JDBC_URL` | — | URL JDBC (obligatoria con `jdbc`). |
| `DB_DSN` | — | Solo con `oracledb`, en lugar de la URL JDBC. |
| `DB_POOL_MIN` / `DB_POOL_MAX` | `2` / `10` | Tamaño del pool. |
| `DB_POOL_WAIT_TIMEOUT_MS` | `3000` | Espera máxima por una conexión libre. |
| `DB_CALL_TIMEOUT_MS` | `5000` | Timeout por consulta. |
| `ORACLE_CLIENT_LIB_DIR` | — | Solo con `oracledb`: carpeta de Instant Client 19. |
| `VIEW_SCHEMA` | — | Esquema dueño de las vistas (`SYSADMIN` en la base de prueba). |
| `USERS_FILE` | `users.json` | Archivo de usuarios de la API. |
| `JWT_SECRET` | — (obligatorio) | Secreto para firmar tokens. |
| `JWT_EXPIRE_MINUTES` | `30` | Duración de los tokens. |
| `RATE_LIMIT` | `60/minute` | Límite global por IP. |
| `LOGIN_RATE_LIMIT` | `10/minute` | Límite del login por IP. |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | `redis://...` si hay varios procesos. |
| `CORS_ORIGINS` | — | Orígenes permitidos, separados por coma. |

La API no arranca si la configuración es inválida (secreto corto, CORS con `*`, URL JDBC mal
formada, `users.json` corrupto, etc.).

---

## 9. Operación

### Arrancar en local

```
run_local.bat              (o doble clic)
run_local.bat --reload     (recarga al editar código)
```

Escucha solo en `http://127.0.0.1:8000`. Cambios en `.env` requieren reiniciar
(Ctrl+C y volver a abrir); `--reload` solo detecta cambios de código.

### Administrar usuarios de la API

```
.venv\Scripts\python scripts\manage_users.py add <usuario>
.venv\Scripts\python scripts\manage_users.py passwd <usuario>
.venv\Scripts\python scripts\manage_users.py disable <usuario>
.venv\Scripts\python scripts\manage_users.py enable <usuario>
.venv\Scripts\python scripts\manage_users.py remove <usuario>
.venv\Scripts\python scripts\manage_users.py list
```

La contraseña se pide de forma interactiva (mínimo 12 caracteres). La API relee el archivo
sola; no hace falta reiniciar.

### Postman

1. Importar `postman/apis_server.postman_collection.json` y un environment con las variables
   `baseUrl`, `username` y `password` (el environment local ya existe, pero no se versiona).
2. Seleccionar el environment.
3. Ejecutar cualquier request: la colección hace el login automáticamente y guarda el token.

Para un request armado a mano: `POST {{baseUrl}}/v1/auth/token`, pestaña *Body* →
`x-www-form-urlencoded` con `username` y `password`; luego *Authorization* → *Bearer Token*.

### Tests y lint

```
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check .
.venv\Scripts\ruff format --check .
```

---

## 10. Verificación realizada

| Prueba | Resultado |
|---|---|
| Suite de tests (148): autenticación, JWT, rate limit, paginación, filtros, lista blanca, 404/422, errores sin `ORA-`, headers, CORS, docs en producción, URL JDBC, pool, conversión de tipos con JVM real | Todos pasan |
| `ruff check` / `ruff format --check` | Sin observaciones |
| SQL generado por la API ejecutado con sqlplus contra la base de prueba (conteo, páginas, orden, detalle, filtros) | Correcto en 11.2.0.4 |
| Backend JDBC contra la base de prueba (ping, filtros, paginación, detalle, error de tabla inexistente) | Correcto |
| Colección de Postman completa contra la API conectada por JDBC | Todos los requests con el resultado esperado; `/health` = ok, `/v1/campos` con datos reales |
| Búsqueda de contraseñas en los logs | No aparecen |

---

## 11. Historial de decisiones y problemas resueltos

| Tema | Qué pasó | Resolución |
|---|---|---|
| Versión de Oracle | El pedido original asumía modo thin; la base es 11g. | Se descartó el modo thin; paginación con `ROWNUM`. |
| slowapi | Su middleware (0.1.10) no detecta las rutas en FastAPI 0.162: no limitaba nada (lo detectaron los tests). | Rate limiting propio con `limits`, el motor que usa slowapi. |
| Clientes Oracle instalados | La máquina tiene clientes 11.2 y 12.1; python-oracledb 26 exige 19+ (`DPI-1050`). | Primero Instant Client 19 como requisito; luego se cambió a JDBC. |
| Autenticación | Se empezó con API keys (`X-API-Key`). | Reemplazado por usuario y contraseña con JWT, a pedido; usuarios en archivo aparte. |
| URL JDBC | Se pidió configurar la conexión con URL JDBC. | `DB_JDBC_URL` con conversión a DSN. |
| Driver JDBC | Se pidió conexión realmente por JDBC. | Java 17 + ojdbc8 19.27 + JPype, con pool propio. |
| `CAMPO_CODIGO` repetido | 23 códigos con más de un productor. | Clave compuesta para orden y detalle como lista. |
| Espacios de relleno | `PRODUCTOR_CODIGO` y otros vienen como `"    228"`; el filtro no encontraba nada. | `TRIM` en filtros y recorte en la respuesta. |
| `run_local.bat` | Error `"rver-header"` al modificar el .bat mientras corría. | Comando en una sola línea y fines de línea CRLF. |
| 401 en Postman | El servidor había arrancado antes de crear el `.env`. | Reiniciar tras cambiar `.env`. |
| 405 en el login | El request se enviaba como GET. | Usar POST. |

---

## 12. Pendientes y recomendaciones

### Para dejarlo listo en un servidor

1. **Despliegue**: elegir proxy inverso con HTTPS (IIS con URL Rewrite + ARR, Nginx o
   Apache), redirección HTTP→HTTPS, dominio, certificado TLS y, si corresponde, lista blanca
   de IPs. Correr la API como servicio (NSSM/WinSW en Windows, systemd en Linux) con uvicorn
   en `127.0.0.1:8000` y `--proxy-headers --forwarded-allow-ips 127.0.0.1`.
2. **`ENV=production`** en el servidor.
3. **Usuario de base de solo lectura**: hoy la API se conecta con el usuario dueño del
   esquema de la base de prueba, que tiene más permisos de los necesarios. Pedir al DBA que
   ejecute `sql/setup.sql` (usuario con `CREATE SESSION` y `SELECT` solo sobre las vistas,
   más un PROFILE con límites), con `DEFINE owner_schema = SYSADMIN`. El script ya tiene
   los GRANTs de las 13 vistas `IA_*` publicadas.
4. **Rotar credenciales** que se compartieron durante el desarrollo (la contraseña de la base
   de prueba y la del usuario de Postman) antes de cualquier uso fuera de pruebas.

### Del código

5. **Endpoints de ejemplo**: `/v1/productos` y `/v1/clientes` apuntan a vistas que no
   existen; conviene quitarlos o reemplazarlos por vistas reales.
6. **`PRODUCTOR_CUIT`**: evaluar si los consumidores lo necesitan; si no, quitarlo de la
   respuesta por ser potencialmente un dato personal.
7. **Varios procesos**: con más de un worker, usar Redis para el rate limiting
   (`RATE_LIMIT_STORAGE_URI`) y ajustar `SESSIONS_PER_USER` del PROFILE (cada proceso tiene
   su pool y su JVM).

### De las vistas (para quien las mantiene)

8. **`IA_CHOFERES_ACTIVOS` / `IA_CHOFERES_NO_ACTIVOS`**: la primera devuelve todos los
   choferes (también los inactivos) y la segunda está vacía. Revisar sus definiciones.
9. **Compras pendientes**: `IA_COMPRAS_PENDIENTES_FACTURAS` y `IA_COMPRAS_PENDIENTES_NCND`
   tardan ~4 s por consulta con muy pocas filas, cerca del timeout de 5 s
   (`DB_CALL_TIMEOUT_MS`). Conviene optimizar las vistas; si no, subir el timeout.
10. **Filas repetidas**: `IA_CHOFERES` (35) e `IA_CAMPOS_PLANTAS_DISTANCIAS` (7354) tienen
    filas idénticas repetidas, probablemente por un join. La API las tolera, pero los
    consumidores las ven en los listados.

### Nuevas APIs (10/11/2026)

Se preparó el proyecto para publicar más vistas:

- Registro central `VIEW_MODULES` en `app/routers/__init__.py` (antes, `include_router` a
  mano en `main.py`).
- `tests/test_contratos.py`: tests que se aplican solos a toda vista registrada.
- `scripts/new_api.py`: generador de router + tests (con `--from-db` lee la vista del
  diccionario de datos; probado contra `SYSADMIN.IA_CAMPOS`).
- `ViewSpec.schema`: esquema por vista, para publicar vistas fuera de `VIEW_SCHEMA`.
- Guía paso a paso: `docs/GUIA_NUEVA_API.md`. Contexto para asistentes de IA: `CLAUDE.md`.

### Repositorio

11. **Git**: hecho. Repositorio en GitHub (`pablobramajothsa/thsa-api-server`, privado).
