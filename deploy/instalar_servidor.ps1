<#
.SYNOPSIS
    Instala (o reinstala) la API como servicio de Windows con NSSM.

.DESCRIPTION
    Ejecutar en el servidor, como administrador, desde la carpeta del proyecto clonado:

        powershell -ExecutionPolicy Bypass -File deploy\instalar_servidor.ps1

    Pasos (todos se pueden repetir sin romper nada):
      1. Verifica Python 3.10+, Java (via JAVA_HOME del .env), NSSM, .env y users.json.
      2. Crea .venv e instala requirements.txt.
      3. Descarga el driver ojdbc8 de Maven Central si falta (verifica el SHA-1).
      4. Valida la configuracion y prueba la conexion a Oracle (SELECT 1 FROM DUAL).
      5. Crea o actualiza el servicio, abre el puerto en el firewall y arranca la API.
      6. Verifica GET /health.

    Con -SoloVerificar hace solo los pasos 1 y 4 (no instala ni toca el sistema).
    Ver docs/INSTALACION_SERVIDOR.md.

    Los mensajes van sin acentos a proposito: PowerShell 5.1 lee los .ps1 sin BOM como ANSI.
#>
[CmdletBinding()]
param(
    [int]$Puerto = 8001,
    [string]$Servicio = "ThsaApiServer",
    [string]$Nssm = "",
    # LocalService: cuenta con pocos privilegios (recomendado). LocalSystem si hubiera
    # problemas de permisos.
    [ValidateSet("LocalService", "LocalSystem")]
    [string]$Cuenta = "LocalService",
    [switch]$SoloVerificar
)

# Continue: los ejecutables (pip, python, java) escriben avisos en stderr y PowerShell 5.1
# los convertiria en errores. Cada paso verifica $LASTEXITCODE o usa -ErrorAction Stop.
$ErrorActionPreference = "Continue"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$OjdbcVersion = "19.27.0.0"
$OjdbcUrl = "https://repo1.maven.org/maven2/com/oracle/database/jdbc/ojdbc8/$OjdbcVersion/ojdbc8-$OjdbcVersion.jar"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$LogDir = Join-Path $Root "logs"

function Paso([string]$texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Ok([string]$texto) { Write-Host "    [OK] $texto" -ForegroundColor Green }
function Aviso([string]$texto) { Write-Host "    [AVISO] $texto" -ForegroundColor Yellow }
function Falla([string]$texto) { Write-Host "    [ERROR] $texto" -ForegroundColor Red; exit 1 }

function Invoke-Python([string]$exe, [string]$codigo) {
    # Ejecuta codigo Python en la raiz del proyecto y devuelve (exitcode, salida).
    $env:PYTHONIOENCODING = "utf-8"
    $out = & $exe -c $codigo 2>&1 | ForEach-Object { "$_" } | Where-Object { $_ -notmatch '^\{"ts"' }
    return @($LASTEXITCODE, ($out -join "`n"))
}

# --- 1. Requisitos ---------------------------------------------------------------

Paso "Verificando requisitos"

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if ($esAdmin) { Ok "Ejecutando como administrador" }
elseif ($SoloVerificar) { Aviso "No es administrador (para instalar hace falta)" }
else { Falla "Ejecutar PowerShell como administrador" }

# Python: py launcher o python del PATH, 3.10 o superior.
$python = $null
foreach ($cand in @(@("py", "-3"), @("python"))) {
    $cmd = Get-Command $cand[0] -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $args_ = @($cand | Select-Object -Skip 1)
    $ver = & $cmd.Source @args_ -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and $ver -and [version]$ver -ge [version]"3.10") {
        $exe = & $cmd.Source @args_ -c "import sys; print(sys.executable)"
        $python = $exe.Trim()
        break
    }
}
if (-not $python) { Falla "No se encontro Python 3.10+ (instalarlo 'para todos los usuarios')" }
Ok "Python: $python"
if ($python -like "*\AppData\*" -and $Cuenta -eq "LocalService") {
    Aviso "Python esta instalado para un solo usuario; la cuenta LocalService puede no poder leerlo. Reinstalar 'para todos los usuarios' o usar -Cuenta LocalSystem"
}

if (-not (Test-Path ".env")) {
    Falla "Falta .env: copiar .env.example a .env y completarlo (ver docs/INSTALACION_SERVIDOR.md)"
}
Ok ".env encontrado"

if (-not (Test-Path "users.json")) {
    Aviso "Falta users.json: sin usuarios, todos los requests a /v1 devuelven 401. Crear uno con: .venv\Scripts\python scripts\manage_users.py add <usuario>"
} else {
    Ok "users.json encontrado"
}

if (-not $SoloVerificar) {
    if (-not $Nssm) {
        $c = Get-Command nssm -ErrorAction SilentlyContinue
        if ($c) { $Nssm = $c.Source }
        elseif (Test-Path "C:\nssm\nssm.exe") { $Nssm = "C:\nssm\nssm.exe" }
    }
    if (-not $Nssm -or -not (Test-Path $Nssm)) {
        Falla "No se encontro nssm.exe. Copiar win64\nssm.exe de NSSM 2.24 (https://nssm.cc/download) a C:\nssm\nssm.exe o indicar -Nssm <ruta>"
    }
    Ok "NSSM: $Nssm"
}

# --- 2. Entorno virtual -----------------------------------------------------------

if (-not $SoloVerificar) {
    Paso "Entorno virtual e instalacion de dependencias"
    if (-not (Test-Path $VenvPython)) {
        & $python -m venv .venv
        if ($LASTEXITCODE -ne 0) { Falla "No se pudo crear .venv" }
        Ok ".venv creado"
    } else {
        Ok ".venv ya existe"
    }
    & $VenvPython -m pip install --disable-pip-version-check -q --upgrade pip
    & $VenvPython -m pip install --disable-pip-version-check -q -r requirements.txt
    if ($LASTEXITCODE -ne 0) { Falla "Fallo pip install -r requirements.txt" }
    Ok "Dependencias instaladas"
}
$py = if (Test-Path $VenvPython) { $VenvPython } else { $python }

# --- 3. Driver JDBC ---------------------------------------------------------------

$r = Invoke-Python $py "from app.config import Settings; print(Settings().jdbc_driver_jar)"
$jar = if ($r[0] -eq 0) { $r[1].Trim() } else { "lib\ojdbc8-$OjdbcVersion.jar" }
$jarPath = if ([IO.Path]::IsPathRooted($jar)) { $jar } else { Join-Path $Root $jar }
if (-not (Test-Path $jarPath)) {
    if ($SoloVerificar) {
        Aviso "Falta el driver JDBC: $jarPath (el instalador lo descarga)"
    } else {
        Paso "Descargando el driver JDBC ojdbc8 $OjdbcVersion (Maven Central)"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        New-Item -ItemType Directory -Force (Split-Path $jarPath -Parent) | Out-Null
        $tmp = "$jarPath.descarga"
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $OjdbcUrl -OutFile $tmp -ErrorAction Stop
            $esperado = (Invoke-WebRequest -UseBasicParsing -Uri "$OjdbcUrl.sha1" -ErrorAction Stop).Content
        } catch { Falla "No se pudo descargar el driver: $($_.Exception.Message). Copiarlo a mano a $jarPath" }
        if ($esperado -is [byte[]]) { $esperado = [Text.Encoding]::ASCII.GetString($esperado) }
        $esperado = $esperado.Trim().Split(" ")[0].ToLower()
        $real = (Get-FileHash -Algorithm SHA1 $tmp).Hash.ToLower()
        if ($real -ne $esperado) { Remove-Item $tmp; Falla "SHA-1 del driver no coincide ($real <> $esperado)" }
        Move-Item -Force $tmp $jarPath
        Ok "Driver descargado y verificado: $jarPath"
    }
} else {
    Ok "Driver JDBC: $jarPath"
}

# --- 4. Configuracion y conexion a Oracle -------------------------------------------

Paso "Validando .env y probando la conexion a Oracle"
$codigo = @"
import sys
from app.config import Settings
try:
    s = Settings()
except Exception as exc:
    print('CONFIG_INVALIDA', exc)
    sys.exit(2)
print('ENV', s.env, 'DRIVER', s.db_driver, 'SCHEMA', s.view_schema)
if s.db_driver == 'jdbc':
    from app.db_jdbc import JdbcDatabase, find_jvm
    print('JVM', find_jvm(s.java_home))
    db = JdbcDatabase(s)
else:
    from app.db import OracleDatabase
    db = OracleDatabase(s)
try:
    print('PING', db.scalar('SELECT 1 FROM DUAL', {}))
except Exception as exc:
    print('SIN_CONEXION', exc)
    sys.exit(3)
finally:
    db.close()
"@
$r = Invoke-Python $py $codigo
$r[1] -split "`n" | ForEach-Object { if ($_.Trim()) { Write-Host "    $_" } }
switch ($r[0]) {
    0 { Ok "Configuracion valida y Oracle responde" }
    2 { Falla "El .env tiene valores invalidos (ver el mensaje de arriba)" }
    3 { Falla "No se pudo conectar a Oracle desde este servidor (red, usuario/clave o JAVA_HOME)" }
    default { Falla "No se pudo validar la configuracion (codigo $($r[0]))" }
}

if ($SoloVerificar) {
    Write-Host ""
    Write-Host "Verificacion terminada. Para instalar, ejecutar sin -SoloVerificar." -ForegroundColor Green
    exit 0
}

# --- 5. Servicio -------------------------------------------------------------------

Paso "Configurando el servicio $Servicio (puerto $Puerto)"

$enUso = Get-NetTCPConnection -State Listen -LocalPort $Puerto -ErrorAction SilentlyContinue
$existe = Get-Service -Name $Servicio -ErrorAction SilentlyContinue
if ($existe -and $existe.Status -ne "Stopped") {
    & $Nssm stop $Servicio | Out-Null
    Start-Sleep -Seconds 3
    $enUso = Get-NetTCPConnection -State Listen -LocalPort $Puerto -ErrorAction SilentlyContinue
}
if ($enUso) {
    $proc = (Get-Process -Id ($enUso | Select-Object -First 1).OwningProcess).ProcessName
    Falla "El puerto $Puerto ya esta en uso por '$proc'. Elegir otro con -Puerto"
}

New-Item -ItemType Directory -Force $LogDir | Out-Null
$appArgs = "-m uvicorn app.main:create_app --factory --host 0.0.0.0 --port $Puerto --no-server-header --no-access-log"

if (-not $existe) {
    & $Nssm install $Servicio $VenvPython | Out-Null
    if ($LASTEXITCODE -ne 0) { Falla "nssm install fallo" }
    Ok "Servicio creado"
} else {
    & $Nssm set $Servicio Application $VenvPython | Out-Null
    Ok "Servicio existente: se actualiza"
}
$config = @(
    @("AppParameters", $appArgs),
    @("AppDirectory", $Root),
    @("DisplayName", "THSA API Server (vistas Oracle)"),
    @("Description", "API REST de solo lectura sobre vistas Oracle. Puerto $Puerto. Carpeta $Root"),
    @("Start", "SERVICE_AUTO_START"),
    @("AppStdout", (Join-Path $LogDir "api.log")),
    @("AppStderr", (Join-Path $LogDir "api.log")),
    @("AppRotateFiles", "1"),
    @("AppRotateOnline", "1"),
    @("AppRotateBytes", "10485760"),
    @("AppExit", "Default", "Restart"),
    @("AppRestartDelay", "5000"),
    @("AppStopMethodConsole", "10000")
)
foreach ($c in $config) {
    & $Nssm set $Servicio @c | Out-Null
    if ($LASTEXITCODE -ne 0) { Falla "nssm set $($c[0]) fallo" }
}
& $Nssm set $Servicio AppEnvironmentExtra "PYTHONIOENCODING=utf-8" | Out-Null

if ($Cuenta -eq "LocalService") {
    # '""': PowerShell 5.1 descarta los argumentos vacios; asi nssm recibe la clave vacia.
    & $Nssm set $Servicio ObjectName "NT AUTHORITY\LocalService" '""' | Out-Null
    if ($LASTEXITCODE -ne 0) { Falla "No se pudo asignar la cuenta LocalService (probar -Cuenta LocalSystem)" }
    # S-1-5-19 = LOCAL SERVICE: lectura del proyecto, escritura solo en logs.
    icacls $Root /grant "*S-1-5-19:(OI)(CI)RX" /Q | Out-Null
    icacls $LogDir /grant "*S-1-5-19:(OI)(CI)M" /Q | Out-Null
    Ok "Cuenta del servicio: LocalService (permisos de lectura en $Root, escritura en logs)"
} else {
    & $Nssm set $Servicio ObjectName "LocalSystem" | Out-Null
    Aviso "Cuenta del servicio: LocalSystem (tiene todos los privilegios del equipo)"
}

$regla = "THSA API Server (TCP $Puerto)"
if (-not (Get-NetFirewallRule -DisplayName $regla -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $regla -Direction Inbound -Protocol TCP -LocalPort $Puerto `
        -Action Allow -Profile Domain, Private -ErrorAction Stop | Out-Null
    Ok "Regla de firewall creada: $regla (perfiles Dominio y Privado)"
} else {
    Ok "Regla de firewall ya existe: $regla"
}

# --- 6. Arranque y verificacion -------------------------------------------------------

Paso "Iniciando el servicio y verificando /health"
& $Nssm start $Servicio | Out-Null
$salud = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $salud = Invoke-RestMethod -Uri "http://127.0.0.1:$Puerto/health" -TimeoutSec 10 -ErrorAction Stop
        break
    } catch { }
}
if ($salud -and $salud.status -eq "ok") {
    Ok "La API responde: http://127.0.0.1:$Puerto/health -> ok"
} else {
    Aviso "La API no respondio /health = ok en 60 s. Revisar $LogDir\api.log y 'Get-Service $Servicio'"
    exit 1
}

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } | Select-Object -First 1).IPAddress
Write-Host ""
Write-Host "Instalacion terminada." -ForegroundColor Green
Write-Host "  API:     http://${ip}:$Puerto"
Write-Host "  Docs:    http://${ip}:$Puerto/docs   (solo si ENV no es production)"
Write-Host "  Logs:    $LogDir\api.log"
Write-Host "  Usuarios: .venv\Scripts\python scripts\manage_users.py add <usuario>  (no requiere reiniciar)"
Write-Host "  Actualizar: powershell -ExecutionPolicy Bypass -File deploy\actualizar_servidor.ps1"
