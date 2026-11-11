# API de solo lectura sobre vistas Oracle

API REST (FastAPI) que publica vistas de una base **Oracle 11g** en modo solo lectura, con
autenticación con usuario y contraseña (tokens JWT), paginación, rate limiting y manejo de errores que no expone
detalles internos.

## Contenido

```
app/
  main.py          app (factory create_app), middlewares, handlers de error
  config.py        Settings desde variables de entorno / .env
  db.py            pool de conexiones python-oracledb (modo thick)
  security.py      verificación de contraseñas (bcrypt) y tokens JWT
  users.py         usuarios leídos de users.json (se relee al cambiar)
  query.py         construcción de SQL con bind variables y lista blanca de columnas
  params.py        paginación, rango de fechas, modelo Page
  middleware.py    request id, headers de seguridad, log de accesos
  ratelimit.py     límite de requests por IP
  logging_conf.py  logs JSON
  routers/         health, auth (login), campos (IA_CAMPOS), productos y clientes (ejemplos)
  routers/__init__.py  registro de las vistas publicadas (VIEW_MODULES)
tests/             pytest con la base de datos mockeada (test_contratos.py valida toda vista)
sql/setup.sql      usuario api_readonly, PROFILE y GRANTs (para el DBA)
scripts/           run_local.ps1, manage_users.py (usuarios), new_api.py (generar una API)
docs/              documentación del proyecto y guía para publicar vistas nuevas
postman/           colección de Postman (el environment local no se versiona)
run_local.bat      arranque local con doble clic
```

## Requisitos

- Python 3.10 o superior.
- **Java 8 o superior** (recomendado: Eclipse Temurin 17 JRE) y el **driver JDBC de Oracle
  `ojdbc8` 19.x**. La API se conecta por JDBC: el driver corre en una JVM embebida en el
  proceso de Python (JPype). No hace falta Oracle Instant Client.
  - `ojdbc8` 19.x soporta Oracle 11.2 en adelante y Java 8 en adelante.
  - Los Java 1.5 / 1.6 que vienen con los clientes Oracle 11.2 / 12.1 son demasiado viejos.
- Acceso de red desde esta máquina al listener de Oracle (normalmente el puerto 1521).

### Instalar Java y el driver JDBC en Windows

```powershell
winget install --id EclipseAdoptium.Temurin.17.JRE -e
New-Item -ItemType Directory -Force lib
Invoke-WebRequest https://repo1.maven.org/maven2/com/oracle/database/jdbc/ojdbc8/19.27.0.0/ojdbc8-19.27.0.0.jar -OutFile lib\ojdbc8-19.27.0.0.jar
```

Después indicar en el `.env` la carpeta del JRE en `JAVA_HOME` (por ejemplo
`C:\Program Files\Eclipse Adoptium\jre-17.0.21.9-hotspot`) y la ruta del `.jar` en
`JDBC_DRIVER_JAR`. El `.jar` no se versiona (`lib/*.jar` está en `.gitignore`).

### Alternativa: python-oracledb con Instant Client

Con `DB_DRIVER=oracledb` la API usa python-oracledb en modo *thick*, que con Oracle 11g
necesita **Oracle Instant Client 19** (Basic, x64) y el *Visual C++ Redistributable*. Los
clientes 11.2 / 12.1 instalados no sirven (`DPI-1050`). Indicar la carpeta en
`ORACLE_CLIENT_LIB_DIR`.

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt   # o requirements.txt sin herramientas de test
Copy-Item .env.example .env
```

Después editar `.env` con los valores reales (ver la tabla de abajo). Como mínimo:

1. Generar el secreto para firmar los tokens y ponerlo en `JWT_SECRET`:

   ```powershell
   .\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

2. Crear al menos un usuario (ver [Usuarios](#usuarios)).

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `ENV` | `development` | `development`, `test` o `production`. En `production` se desactivan `/docs`, `/redoc` y `/openapi.json`, y se agrega HSTS. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` o `ERROR`. |
| `DB_DRIVER` | `jdbc` | `jdbc` (driver JDBC ojdbc8 vía JVM embebida) u `oracledb` (python-oracledb + Instant Client). |
| `JDBC_DRIVER_JAR` | `lib/ojdbc8-19.27.0.0.jar` | Ruta al `.jar` del driver JDBC. |
| `JAVA_HOME` | del sistema | Carpeta del JRE/JDK 8+ que ejecuta el driver. |
| `DB_USER` | — | Usuario de solo lectura (`api_readonly`). |
| `DB_PASSWORD` | — | Contraseña de ese usuario. |
| `DB_JDBC_URL` | vacío | URL JDBC: `jdbc:oracle:thin:@host:1521:SID`, `@host:1521/servicio` o `@(DESCRIPTION=...)`. Sin usuario ni contraseña adentro. Obligatoria con `DB_DRIVER=jdbc`; con `oracledb` se convierte a su formato. |
| `DB_DSN` | vacío | Solo con `DB_DRIVER=oracledb`, en lugar de `DB_JDBC_URL`: `host:1521/servicio` o un alias de tnsnames. |
| `DB_POOL_MIN` / `DB_POOL_MAX` | `2` / `10` | Tamaño del pool de conexiones. |
| `DB_POOL_WAIT_TIMEOUT_MS` | `3000` | Espera máxima por una conexión libre del pool. |
| `DB_CALL_TIMEOUT_MS` | `5000` | Timeout de cada consulta (`conn.call_timeout`). |
| `ORACLE_CLIENT_LIB_DIR` | vacío | Solo con `DB_DRIVER=oracledb`: carpeta de Instant Client 19. |
| `VIEW_SCHEMA` | vacío | Esquema dueño de las vistas. Vacío si existen sinónimos. |
| `USERS_FILE` | `users.json` | Archivo con los usuarios de la API (usuario y hash bcrypt). |
| `JWT_SECRET` | — (obligatorio) | Secreto para firmar los tokens, mínimo 32 caracteres. Si cambia, todos los tokens emitidos dejan de valer. |
| `JWT_EXPIRE_MINUTES` | `30` | Duración de los tokens (1 a 1440). |
| `RATE_LIMIT` | `60/minute` | Límite por IP (formato `N/second`, `N/minute`, `N/hour`). |
| `LOGIN_RATE_LIMIT` | `10/minute` | Límite adicional por IP para `POST /v1/auth/token` (fuerza bruta). |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | `memory://` con un solo proceso; `redis://host:6379` con varios. |
| `CORS_ORIGINS` | vacío | Orígenes permitidos separados por coma. `*` se rechaza. Vacío = sin CORS. |

La aplicación no arranca si la configuración es inválida (por ejemplo, un `JWT_SECRET` corto,
CORS con `*`, un `users.json` mal formado o un `VIEW_SCHEMA` que no es un identificador válido).

## Usuarios

Los usuarios están en `users.json` (excluido de git), con la contraseña guardada como hash
bcrypt, nunca en texto plano. Se administran con:

```powershell
.\.venv\Scripts\python scripts\manage_users.py add sistema-a       # pide la contraseña (mín. 12 caracteres)
.\.venv\Scripts\python scripts\manage_users.py passwd sistema-a    # cambia la contraseña
.\.venv\Scripts\python scripts\manage_users.py disable sistema-a   # bloquea el usuario
.\.venv\Scripts\python scripts\manage_users.py enable sistema-a
.\.venv\Scripts\python scripts\manage_users.py remove sistema-a
.\.venv\Scripts\python scripts\manage_users.py list
```

La API relee el archivo cuando cambia, así que **no hace falta reiniciarla**. Al desactivar o
borrar un usuario, sus tokens vigentes dejan de valer en el acto. Cambiar la contraseña no
invalida los tokens ya emitidos; vencen solos según `JWT_EXPIRE_MINUTES`.

## Ejecución local

```powershell
run_local.bat                      # o doble clic en el archivo
run_local.bat --reload             # recarga automática al editar el código
```

Si PowerShell lo permite, también se puede usar `.\scripts\run_local.ps1`.

La API escucha solo en `http://127.0.0.1:8000`. En desarrollo la documentación interactiva
queda en `http://127.0.0.1:8000/docs`.

Si la base no está disponible, la API arranca igual: `/health` responde 503 y el pool se
crea en el primer request que logre conectar.

## Endpoints

| Método y ruta | Token | Descripción |
|---|---|---|
| `GET /health` | no | `{"status":"ok"}` (200) o `{"status":"unavailable"}` (503). Ejecuta `SELECT 1 FROM DUAL`. |
| `POST /v1/auth/token` | no | Login: recibe `username` y `password` y devuelve un token. |
| `GET /v1/campos` | sí | Listado paginado de `SYSADMIN.IA_CAMPOS`. Filtros: `productor_codigo`, `productor_cuit`, `codigo_postal`, `localidad`. Orden: `campo_codigo`, `campo_nombre`, `cpo_localidad`, `productor_codigo`, `productor_nombre`. |
| `GET /v1/campos/{campo_codigo}` | sí | Lista con todas las filas del campo (una por productor); 404 si no existe. |
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
| `GET /v1/productos` | sí | Listado paginado de `V_PRODUCTOS`. |
| `GET /v1/productos/{id}` | sí | Detalle por id; 404 si no existe. |
| `GET /v1/clientes` | sí | Listado paginado de `V_CLIENTES`. |
| `GET /v1/clientes/{id}` | sí | Detalle por id; 404 si no existe. |

### Autenticación

1. Pedir un token con usuario y contraseña, enviados como formulario
   (`application/x-www-form-urlencoded`, el flujo *password* de OAuth2):

   ```
   POST /v1/auth/token
   username=sistema-a&password=...
   ```

   Respuesta:

   ```json
   { "access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in": 1800 }
   ```

2. Enviar el token en cada request con el header `Authorization: Bearer <access_token>`.
3. Cuando vence (`expires_in` segundos), pedir otro.

En `/docs` (solo en desarrollo), el botón **Authorize** hace el login y prueba los endpoints
con el token.

### Listados

Parámetros:

- `page` (≥ 1, default 1) y `limit` (1 a 100, default 20).
- `categoria`: igualdad exacta.
- `fecha_desde` / `fecha_hasta`: formato `AAAA-MM-DD`, ambas inclusive.
- `sort`: columna de la lista blanca de cada vista. `order`: `asc` o `desc`.

Respuesta de un listado:

```json
{ "page": 1, "limit": 20, "total": 134, "data": [ { "id": 1, "nombre": "...", ... } ] }
```

Ejemplo con PowerShell:

```powershell
$login = Invoke-RestMethod -Method Post "http://127.0.0.1:8000/v1/auth/token" `
    -Body @{ username = "sistema-a"; password = (Read-Host "Contraseña") }
$h = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod "http://127.0.0.1:8000/v1/productos?page=1&limit=10&sort=precio&order=desc" -Headers $h
```

Errores:

- 401 `{"detail":"Unauthorized"}`: usuario o contraseña incorrectos, o falta el token, es
  inválido o venció. La respuesta es siempre la misma, para no revelar qué usuarios existen.
- 404 `{"detail":"Not found"}`: el registro no existe.
- 422: parámetros inválidos.
- 429 `{"detail":"Too many requests"}`: se superó el límite; incluye el header `Retry-After`.
- 500 `{"detail":"Internal server error","request_id":"..."}`: el detalle del error (incluidos
  los mensajes ORA-) queda solo en el log, asociado al mismo `request_id`. Ese id también se
  devuelve en el header `X-Request-ID` de todas las respuestas.

## Seguridad: decisiones de implementación

- **SQL**: todos los valores del usuario viajan como bind variables. En el texto SQL solo se
  interpolan identificadores definidos como constantes en `app/routers/*.py` y validados con
  una expresión regular. `sort` se traduce a una columna mediante una lista blanca fija.
- **Paginación en 11g**: `OFFSET ... FETCH` no existe en 11g, así que se usa el patrón
  `ROWNUM <= :max_row` / `rn__ > :min_row`, con `ORDER BY` determinístico (el id desempata).
- **Contraseñas**: se guardan como hash bcrypt (costo 12). Si el usuario no existe, igual se
  verifica contra un hash de relleno, para que la respuesta tarde lo mismo y no permita
  averiguar qué usuarios existen. El login tiene su propio límite por IP (`LOGIN_RATE_LIMIT`).
- **Tokens JWT**: se firman con HS256 y `JWT_SECRET`. Al validarlos se exigen la firma, el
  algoritmo (solo HS256; se rechazan `none` y cualquier otro), el vencimiento, el emisor y la
  audiencia. En cada request se comprueba además que el usuario siga existiendo y activo.
- **Rate limiting**: el límite es global por IP y cuenta todas las rutas juntas, incluida
  `/health`. Se implementa con la librería `limits`, que es el motor que usa slowapi por
  dentro. No se usa slowapi en sí porque su middleware (versión 0.1.10) no detecta las rutas
  en FastAPI 0.162 y deja pasar todos los requests sin limitar.
- **Headers**: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Cache-Control: no-store`, `Content-Security-Policy`, `Permissions-Policy` y, en producción,
  `Strict-Transport-Security`.
- **Logs**: se escriben en JSON a stdout. Cada acceso registra IP, método, ruta, status,
  duración y usuario. Nunca se registran contraseñas ni tokens. Los logins fallidos quedan
  registrados con el usuario que se intentó usar.
- **Conexión JDBC**: `PreparedStatement` con parámetros `?` (los binds `:nombre` se convierten
  antes de ejecutar), `setQueryTimeout`, timeout de lectura de red y conexiones `readOnly`.
- **Pool**: un único pool por proceso (propio, en `app/pool.py`, porque JDBC no trae uno),
  creado en el primer uso, con validación de conexiones ociosas y cerrado al apagar la API.
  La JVM arranca una sola vez por proceso (unos segundos en el primer request).

## Personalizar las vistas

`/v1/campos` publica la vista real `SYSADMIN.IA_CAMPOS` de la base de prueba. En esa vista
`CAMPO_CODIGO` se repite (un campo puede tener varios productores): la fila se identifica por
`(CAMPO_CODIGO, PRODUCTOR_CODIGO)`, que se usa como desempate del orden. Además varias columnas
vienen con espacios de relleno (`"    228"`): los filtros comparan con `TRIM(...)` y la
respuesta devuelve los valores sin esos espacios.

`V_PRODUCTOS` y `V_CLIENTES` son *placeholders*. Para publicar una vista real, seguir
**[docs/GUIA_NUEVA_API.md](docs/GUIA_NUEVA_API.md)**. En resumen:

```powershell
.venv\Scripts\python scripts\new_api.py ordenes_carga --view IA_ORDENES_CARGA --from-db `
    --id ORDEN_NUMERO --filter PRODUCTOR_CODIGO --trim --date-filter FECHA_EMISION
```

genera `app/routers/ordenes_carga.py` y `tests/test_ordenes_carga.py` y lo registra en
`VIEW_MODULES` (`app/routers/__init__.py`). Con `--from-db` lee las columnas del diccionario
de datos y detecta si el id se repite. Después hay que revisar el router (orden, filtros,
datos personales), agregar el `GRANT SELECT` en `sql/setup.sql` y los requests de Postman.

`tests/test_contratos.py` verifica automáticamente cada vista registrada: `SortField`
alineado con `SPEC.sort_columns`, modelo alineado con las columnas, token obligatorio,
formato del listado y errores de base sin `ORA-`.

Si una vista está en un esquema distinto de `VIEW_SCHEMA`, se indica en `ViewSpec(schema=...)`
(opción `--schema` del generador).

Los `NUMBER` con decimales se devuelven como `float` en JSON. Si se necesita precisión exacta
(por ejemplo, importes), conviene cambiar el modelo a `Decimal`, que se serializa como string.

Los códigos de texto (`CODIGO` de choferes, productores y empresas) se usan tal cual en la
URL del detalle: `/v1/productores/4904`. Los filtros de tipo Sí/No usan los valores de la
vista, que no son uniformes: `Si`/`No` en choferes, productores y empresas; `Sí`/`No` (con
acento) en plantas y regímenes. Cada parámetro lo indica en `/docs`.

## Base de datos

`sql/setup.sql` crea el PROFILE, el usuario `api_readonly` con `CREATE SESSION` y los
`GRANT SELECT` sobre las vistas. Lo tiene que revisar y ejecutar un DBA:

```
sqlplus / as sysdba @sql/setup.sql
```

El script pide la contraseña de forma interactiva (no queda en el archivo) y activa
`RESOURCE_LIMIT`, sin el cual 11g ignora los límites del PROFILE.

Notas sobre 11g:

- Las contraseñas distinguen mayúsculas y minúsculas (`SEC_CASE_SENSITIVE_LOGON`).
- Si al conectar con un driver 19 (ojdbc8 o Instant Client) aparece `ORA-28040` u `ORA-01017` con una contraseña
  correcta, puede que la cuenta solo tenga el verificador viejo (10G). Se soluciona
  regenerando la contraseña del usuario en la base.
- Oracle 11g está fuera de soporte y no recibe parches de seguridad. Conviene que solo el
  servidor de la API tenga acceso de red al listener.

## Tests y linter

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format --check .
```

Los tests no necesitan Oracle: reemplazan la capa de base de datos por un fake en memoria
(`tests/conftest.py`). Cubren login y tokens (válidos, vencidos, firma o algoritmo incorrectos, usuarios inactivos),
rate limit del login, paginación y límites (422), lista
blanca de orden, filtros como binds, 404 en detalle, que los errores de base no filtren
textos ORA-, rate limiting (429), headers de seguridad, CORS y docs desactivadas en
producción.

## Postman

En `postman/` está la colección `apis_server.postman_collection.json`. Para usarla:

1. **Import** de la colección y de un environment con las variables `baseUrl`, `username` y
   `password`. El environment local `postman/local.postman_environment.json` ya trae un
   usuario de prueba; no se versiona porque contiene la contraseña.
2. Seleccionar el environment arriba a la derecha.
3. Ejecutar cualquier request: la colección hace el login sola y guarda el token en
   `accessToken`. También se puede hacer a mano con *Autenticación → Login (obtener token)*.

## Despliegue (pendiente)

Por ahora el proyecto está preparado para correr en local. Para un servidor falta:

- Elegir el proxy inverso con HTTPS (IIS con URL Rewrite + ARR, Nginx o Apache), la
  redirección HTTP→HTTPS y, si corresponde, la lista blanca de IPs.
- Correr la API como servicio (NSSM o WinSW en Windows, systemd en Linux) con el mismo
  comando de `scripts/run_local.ps1`: uvicorn en `127.0.0.1:8000` y `--proxy-headers
  --forwarded-allow-ips 127.0.0.1`, para que el rate limiting vea la IP real del cliente.
- Poner `ENV=production` y configurar dominio y certificado TLS en el proxy.
