# Instalación en el servidor de testing

| Dato | Valor |
|---|---|
| Servidor | `192.168.16.39` (`TH-SRV-PPRD.THSA.LOCAL`), Windows con IIS 10 en los puertos 80/443 |
| Puerto de la API | **8001** (el 8000 lo usa la Calculadora de Huella de Carbono) |
| URL | `http://192.168.16.39:8001` (docs: `http://192.168.16.39:8001/docs`) |
| Carpeta sugerida | `C:\apps\thsa-api-server` |
| Servicio de Windows | `ThsaApiServer`, con NSSM, arranque automático, cuenta `LocalService` |
| Logs | `C:\apps\thsa-api-server\logs\api.log` (JSON, rota cada 10 MB) |

La instalación la hace un **administrador del servidor por Escritorio Remoto**: desde otro
equipo no se puede, porque WinRM pide permisos de administrador.

> HTTP sin cifrar: alcanza para testing en la red interna, pero el usuario, la contraseña y
> los tokens viajan en texto plano. Para producción, publicar detrás de IIS con HTTPS
> (ver "Despliegue" en el README).

---

## Instalación en un paso (recomendada)

`deploy/instalar_todo.ps1` hace toda la instalación. Es PowerShell (no Python) porque el
servidor todavía no tiene Python: lo instala el propio script.

1. Copiar `deploy\instalar_todo.ps1` al servidor (por Escritorio Remoto se puede copiar y
   pegar el archivo), por ejemplo a `C:\instaladores\instalar_todo.ps1`.
2. Abrir PowerShell con **Ejecutar como administrador** y ejecutar:

   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\instaladores\instalar_todo.ps1
   ```

El script:

1. instala Python 3.13, Java 17, Git y NSSM si faltan (descarga de los sitios oficiales);
2. clona el repositorio en `C:\apps\thsa-api-server` (pide iniciar sesión en GitHub) o hace
   `git pull` si ya está;
3. crea el `.env`: **pide usuario y clave de Oracle** y completa el resto (`ENV=test`,
   `JAVA_HOME`, base `192.168.16.248:1521:BASE`, esquema `SYSADMIN`, `JWT_SECRET` nuevo).
   El `.env` queda legible solo por administradores y la cuenta del servicio;
4. ejecuta `deploy\instalar_servidor.ps1` (dependencias, driver, prueba de Oracle, servicio,
   firewall y `/health`);
5. si no hay usuarios de la API, **pide nombre y clave** del primero.

Se puede volver a ejecutar sin problemas: saltea lo que ya está hecho y no pisa el `.env`.
Opciones: `-Simular` (muestra qué haría, sin tocar nada), `-Carpeta`, `-Puerto`,
`-JdbcUrl`, `-Esquema`.

Las secciones siguientes son el mismo proceso **paso a paso**, por si se prefiere hacerlo a
mano o hay que diagnosticar un problema.

---

## 1. Requisitos (una sola vez)

En una consola de PowerShell **como administrador**. Si el servidor no tiene `winget`,
bajar los mismos instaladores de las páginas oficiales.

```powershell
# Python 3.13 para TODOS los usuarios (la cuenta del servicio tiene que poder leerlo)
winget install -e --id Python.Python.3.13 --scope machine

# Java 17 (JRE) para el driver JDBC
winget install -e --id EclipseAdoptium.Temurin.17.JRE

# Git
winget install -e --id Git.Git
```

**NSSM** (administra el servicio): descargar NSSM 2.24 de <https://nssm.cc/download>,
descomprimir y copiar `win64\nssm.exe` a `C:\nssm\nssm.exe`.

**Sin `winget`** (habitual en Windows Server): este bloque baja los instaladores oficiales y
los instala sin ventanas, NSSM incluido. Java queda en una ruta fija, que es la que va en
`JAVA_HOME`.

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'
$tmp = "C:\instaladores"; New-Item -ItemType Directory -Force $tmp | Out-Null

# Python 3.13 para todos los usuarios, con el PATH
Invoke-WebRequest https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe -OutFile "$tmp\python.exe" -UseBasicParsing
Start-Process "$tmp\python.exe" -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 Include_test=0' -Wait

# Java 17 (JRE Temurin) en C:\Program Files\Eclipse Adoptium\jre-17
Invoke-WebRequest "https://api.adoptium.net/v3/installer/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse?project=jdk" -OutFile "$tmp\java.msi" -UseBasicParsing
Start-Process msiexec.exe -ArgumentList "/i `"$tmp\java.msi`" /quiet ADDLOCAL=FeatureMain,FeatureEnvironment,FeatureJavaHome INSTALLDIR=`"C:\Program Files\Eclipse Adoptium\jre-17`"" -Wait

# Git (última versión de Git for Windows)
$git = (Invoke-RestMethod https://api.github.com/repos/git-for-windows/git/releases/latest).assets | Where-Object name -match '^Git-[\d.]+-64-bit\.exe$' | Select-Object -First 1
Invoke-WebRequest $git.browser_download_url -OutFile "$tmp\git.exe" -UseBasicParsing
Start-Process "$tmp\git.exe" -ArgumentList '/VERYSILENT /NORESTART /NOCANCEL /SP- /SUPPRESSMSGBOXES' -Wait

# NSSM 2.24 en C:\nssm\nssm.exe
Invoke-WebRequest https://nssm.cc/release/nssm-2.24.zip -OutFile "$tmp\nssm.zip" -UseBasicParsing
Expand-Archive "$tmp\nssm.zip" "$tmp\nssm" -Force
New-Item -ItemType Directory -Force C:\nssm | Out-Null
Copy-Item "$tmp\nssm\nssm-2.24\win64\nssm.exe" C:\nssm\nssm.exe -Force
```

Si el servidor no tiene salida a internet, bajar esos mismos archivos en otra PC, copiarlos a
`C:\instaladores` del servidor y ejecutar solo las líneas `Start-Process` / `Copy-Item`.

Cerrar y volver a abrir la consola para que tome el `PATH` nuevo, y comprobar:

```powershell
python --version; java -version; git --version; Test-Path C:\nssm\nssm.exe
```

## 2. Bajar el código

```powershell
git clone https://github.com/pablobramajothsa/thsa-api-server.git C:\apps\thsa-api-server
cd C:\apps\thsa-api-server
```

El repositorio es privado: Git pide iniciar sesión en GitHub. En un servidor compartido
conviene **no dejar una sesión personal**: crear en GitHub un *fine-grained token* de solo
lectura (permiso *Contents: Read-only*, solo para este repositorio y con vencimiento) y
usarlo como contraseña.

## 3. Configurar `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

Valores para el servidor de testing:

| Variable | Valor |
|---|---|
| `ENV` | `test` (deja `/docs` activo; `production` lo apaga) |
| `DB_DRIVER` | `jdbc` |
| `JAVA_HOME` | carpeta del JRE: `C:\Program Files\Eclipse Adoptium\jre-17` si se usó el bloque sin `winget`; con `winget`, `C:\Program Files\Eclipse Adoptium\jre-17.0.x-hotspot` |
| `DB_JDBC_URL` | `jdbc:oracle:thin:@192.168.16.248:1521:BASE` |
| `DB_USER` / `DB_PASSWORD` | usuario de la base (idealmente `api_readonly`, ver `sql/setup.sql`) |
| `VIEW_SCHEMA` | `SYSADMIN` |
| `JWT_SECRET` | **uno nuevo** para este servidor (no reutilizar el de otra máquina) |
| `CORS_ORIGINS` | orígenes web que consumen la API desde el navegador, o vacío |

Generar el `JWT_SECRET` (después de instalar Python):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 4. Instalar

Primero una verificación (no instala nada; prueba Python, Java y la conexión a Oracle):

```powershell
powershell -ExecutionPolicy Bypass -File deploy\instalar_servidor.ps1 -SoloVerificar
```

La primera vez va a avisar que falta el driver JDBC: lo descarga el instalador. Después:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\instalar_servidor.ps1
```

El instalador:

1. verifica los requisitos y el `.env`;
2. crea `.venv` e instala `requirements.txt`;
3. descarga `ojdbc8-19.27.0.0.jar` de Maven Central y verifica su SHA-1;
4. prueba la conexión a Oracle desde el servidor;
5. crea (o actualiza) el servicio `ThsaApiServer` con NSSM: uvicorn en `0.0.0.0:8001`,
   arranque automático, reinicio si se cae, logs con rotación, cuenta `LocalService` con
   lectura sobre la carpeta y escritura solo en `logs\`;
6. abre el puerto 8001 en el firewall (perfiles Dominio y Privado);
7. arranca el servicio y comprueba `GET /health`.

Opciones: `-Puerto 8002`, `-Cuenta LocalSystem` (si `LocalService` tuviera problemas de
permisos), `-Nssm <ruta a nssm.exe>`.

## 5. Crear los usuarios de la API

```powershell
.venv\Scripts\python scripts\manage_users.py add sistema-testing
```

No hace falta reiniciar: la API relee `users.json` sola.

## 6. Probar desde otra PC

- `http://192.168.16.39:8001/health` → `{"status":"ok"}`
- `http://192.168.16.39:8001/docs` → **Authorize** con el usuario creado.
- Postman: un environment con `baseUrl = http://192.168.16.39:8001` y el usuario creado.

---

## Operación

| Tarea | Comando (como administrador, en `C:\apps\thsa-api-server`) |
|---|---|
| Estado | `Get-Service ThsaApiServer` |
| Reiniciar | `C:\nssm\nssm.exe restart ThsaApiServer` (necesario tras cambiar `.env`) |
| Ver logs | `Get-Content logs\api.log -Tail 50 -Wait` |
| Actualizar a la última versión | `powershell -ExecutionPolicy Bypass -File deploy\actualizar_servidor.ps1` |
| Usuarios | `.venv\Scripts\python scripts\manage_users.py list` / `add` / `disable` / `passwd` |
| Desinstalar | `C:\nssm\nssm.exe remove ThsaApiServer confirm` y `Remove-NetFirewallRule -DisplayName "THSA API Server (TCP 8001)"` |

`actualizar_servidor.ps1` hace `git pull`, actualiza dependencias, reinicia el servicio y
comprueba `/health`. No toca `.env`, `users.json` ni la configuración del servicio; si
cambia algo de eso, volver a correr `instalar_servidor.ps1`.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| `/health` → `unavailable` (503) | El servidor no llega a Oracle (`192.168.16.248:1521`), o usuario/clave incorrectos. Ver `logs\api.log`. |
| El servicio arranca y se detiene | Revisar `logs\api.log`. Si es un error de permisos, reinstalar con `-Cuenta LocalSystem`. |
| Desde otra PC no conecta, pero en el servidor sí | Firewall: la regla abre solo los perfiles Dominio y Privado. |
| 401 en todo | No hay usuarios en `users.json`, o el token es de otro servidor (`JWT_SECRET` distinto). |
| Primer request lento (~4 s) | Normal: la JVM arranca con el primer acceso a la base. |
