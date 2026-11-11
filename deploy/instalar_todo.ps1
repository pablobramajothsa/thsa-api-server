<#
.SYNOPSIS
    Instalacion completa de la API en un servidor Windows, en un solo paso.

.DESCRIPTION
    Copiar este archivo al servidor (por ejemplo a C:\instaladores) y ejecutar en una
    consola de PowerShell abierta COMO ADMINISTRADOR:

        powershell -ExecutionPolicy Bypass -File C:\instaladores\instalar_todo.ps1

    Hace, saltando lo que ya este hecho (se puede ejecutar varias veces):
      1. Instala Python 3.13, Java 17 (Temurin JRE), Git y NSSM si faltan.
      2. Clona el repositorio en -Carpeta (o hace git pull si ya existe).
      3. Crea el .env: pide usuario y clave de Oracle; el resto lo completa solo
         (ENV=test, JAVA_HOME detectado, JWT_SECRET generado).
      4. Ejecuta deploy\instalar_servidor.ps1 (venv, driver, prueba de Oracle, servicio,
         firewall, /health).
      5. Si no hay usuarios de la API, crea el primero (pide nombre y clave).

    Con -Simular solo muestra que haria, sin instalar ni cambiar nada.

    Mensajes sin acentos a proposito: PowerShell 5.1 lee los .ps1 sin BOM como ANSI.
#>
[CmdletBinding()]
param(
    [string]$Carpeta = "C:\apps\thsa-api-server",
    [string]$Repo = "https://github.com/pablobramajothsa/thsa-api-server.git",
    [int]$Puerto = 8001,
    [string]$JdbcUrl = "jdbc:oracle:thin:@192.168.16.248:1521:BASE",
    [string]$Esquema = "SYSADMIN",
    [switch]$Simular
)

$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

$Descargas = "C:\instaladores"
$PythonUrl = "https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe"
$JavaUrl = "https://api.adoptium.net/v3/installer/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse?project=jdk"
$JavaDir = "C:\Program Files\Eclipse Adoptium\jre-17"
$NssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
$NssmExe = "C:\nssm\nssm.exe"

function Paso([string]$t) { Write-Host ""; Write-Host "==> $t" -ForegroundColor Cyan }
function Ok([string]$t) { Write-Host "    [OK] $t" -ForegroundColor Green }
function Info([string]$t) { Write-Host "    $t" }
function Aviso([string]$t) { Write-Host "    [AVISO] $t" -ForegroundColor Yellow }
function Falla([string]$t) {
    Write-Host "    [ERROR] $t" -ForegroundColor Red
    Write-Host ""
    Write-Host "La instalacion se detuvo. Corregir lo indicado y volver a ejecutar este script." -ForegroundColor Red
    exit 1
}

function Actualizar-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
        [Environment]::GetEnvironmentVariable("Path", "User")
}

function Descargar([string]$url, [string]$destino) {
    New-Item -ItemType Directory -Force $Descargas | Out-Null
    Info "Descargando $url"
    try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $destino -ErrorAction Stop }
    catch {
        Falla ("No se pudo descargar ($($_.Exception.Message)). Si el servidor no tiene internet, " +
            "bajar el archivo en otra PC y copiarlo a $destino")
    }
}

function Buscar-Python {
    foreach ($p in @("C:\Program Files\Python313\python.exe", "C:\Program Files\Python312\python.exe",
            "C:\Program Files\Python311\python.exe", "C:\Program Files\Python310\python.exe")) {
        if (Test-Path $p) { return $p }
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $exe = & $py.Source -3 -c "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { return "$exe".Trim() }
    }
    return $null
}

function Buscar-JavaHome {
    $candidatos = @($JavaDir)
    if (Test-Path "C:\Program Files\Eclipse Adoptium") {
        $candidatos += Get-ChildItem "C:\Program Files\Eclipse Adoptium" -Directory |
            Where-Object { $_.Name -match '^(jre|jdk)-(1[7-9]|2\d)' } | Sort-Object Name -Descending |
            ForEach-Object { $_.FullName }
    }
    if ($env:JAVA_HOME) { $candidatos += $env:JAVA_HOME }
    foreach ($c in $candidatos) {
        if ($c -and (Test-Path (Join-Path $c "bin\server\jvm.dll"))) { return $c }
    }
    return $null
}

function Valor-Env([string]$v) {
    # Comillas simples si hace falta (python-dotenv las toma literales).
    if ($v -match '^[A-Za-z0-9_.:/@\\-]*$') { return $v }
    if ($v -notmatch "'") { return "'$v'" }
    return '"' + ($v -replace '\\', '\\' -replace '"', '\"') + '"'
}

function Leer-Clave([string]$texto) {
    $seguro = Read-Host $texto -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($seguro)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

Write-Host "Instalacion de THSA API Server" -ForegroundColor Cyan
Write-Host "  Carpeta: $Carpeta   Puerto: $Puerto   Repo: $Repo"
if ($Simular) { Write-Host "  MODO SIMULACION: no se instala ni se modifica nada" -ForegroundColor Yellow }

$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin -and -not $Simular) { Falla "Abrir PowerShell con 'Ejecutar como administrador'" }

# --- 1. Programas ---------------------------------------------------------------------

Paso "1/5 Programas necesarios"
Actualizar-Path

$python = Buscar-Python
if ($python) { Ok "Python: $python" }
elseif ($Simular) { Info "Se instalaria Python 3.13 (para todos los usuarios)" }
else {
    Descargar $PythonUrl "$Descargas\python-3.13.7-amd64.exe"
    Info "Instalando Python 3.13 (1-2 minutos)..."
    $p = Start-Process "$Descargas\python-3.13.7-amd64.exe" -Wait -PassThru `
        -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 Include_test=0"
    Actualizar-Path
    $python = Buscar-Python
    if (-not $python) { Falla "La instalacion de Python fallo (codigo $($p.ExitCode))" }
    Ok "Python instalado: $python"
}

$javaHome = Buscar-JavaHome
if ($javaHome) { Ok "Java: $javaHome" }
elseif ($Simular) { Info "Se instalaria Java 17 (Temurin JRE) en $JavaDir" }
else {
    Descargar $JavaUrl "$Descargas\temurin-17-jre.msi"
    Info "Instalando Java 17..."
    $p = Start-Process msiexec.exe -Wait -PassThru -ArgumentList ("/i `"$Descargas\temurin-17-jre.msi`" /quiet " +
        "ADDLOCAL=FeatureMain,FeatureEnvironment,FeatureJavaHome INSTALLDIR=`"$JavaDir`"")
    $javaHome = Buscar-JavaHome
    if (-not $javaHome) { Falla "La instalacion de Java fallo (codigo $($p.ExitCode))" }
    Ok "Java instalado: $javaHome"
}

$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) { Ok "Git: $($git.Source)" }
elseif ($Simular) { Info "Se instalaria Git (ultima version de Git for Windows)" }
else {
    try {
        $rel = Invoke-RestMethod "https://api.github.com/repos/git-for-windows/git/releases/latest" -ErrorAction Stop
        $asset = $rel.assets | Where-Object name -match '^Git-[\d.]+-64-bit\.exe$' | Select-Object -First 1
    } catch { Falla "No se pudo consultar la ultima version de Git: $($_.Exception.Message)" }
    Descargar $asset.browser_download_url "$Descargas\$($asset.name)"
    Info "Instalando Git..."
    $p = Start-Process "$Descargas\$($asset.name)" -Wait -PassThru `
        -ArgumentList "/VERYSILENT /NORESTART /NOCANCEL /SP- /SUPPRESSMSGBOXES"
    Actualizar-Path
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { Falla "La instalacion de Git fallo (codigo $($p.ExitCode))" }
    Ok "Git instalado: $($git.Source)"
}

if (Test-Path $NssmExe) { Ok "NSSM: $NssmExe" }
elseif ($Simular) { Info "Se instalaria NSSM 2.24 en $NssmExe" }
else {
    Descargar $NssmUrl "$Descargas\nssm-2.24.zip"
    Expand-Archive "$Descargas\nssm-2.24.zip" "$Descargas\nssm" -Force
    New-Item -ItemType Directory -Force (Split-Path $NssmExe) | Out-Null
    Copy-Item "$Descargas\nssm\nssm-2.24\win64\nssm.exe" $NssmExe -Force
    if (-not (Test-Path $NssmExe)) { Falla "No se pudo copiar nssm.exe" }
    Ok "NSSM instalado: $NssmExe"
}

# --- 2. Codigo ------------------------------------------------------------------------

Paso "2/5 Codigo"
if (Test-Path (Join-Path $Carpeta ".git")) {
    if ($Simular) { Info "Se haria git pull en $Carpeta" }
    else {
        Push-Location $Carpeta
        git pull --ff-only
        $rc = $LASTEXITCODE
        Pop-Location
        if ($rc -ne 0) { Falla "git pull fallo en $Carpeta (revisar 'git status')" }
        Ok "Repositorio actualizado en $Carpeta"
    }
} elseif ((Test-Path $Carpeta) -and (Get-ChildItem $Carpeta -Force | Select-Object -First 1)) {
    Falla "$Carpeta existe y no esta vacia, pero no es un repositorio git. Usar otra con -Carpeta"
} elseif ($Simular) {
    Info "Se clonaria $Repo en $Carpeta"
} else {
    Info "Clonando $Repo"
    Info "El repositorio es privado: si se abre una ventana de GitHub, iniciar sesion."
    Info "(Recomendado: un token 'fine-grained' de solo lectura para este repositorio.)"
    New-Item -ItemType Directory -Force (Split-Path $Carpeta) | Out-Null
    git clone $Repo $Carpeta
    if ($LASTEXITCODE -ne 0) { Falla "git clone fallo (credenciales de GitHub o acceso a internet)" }
    Ok "Repositorio clonado en $Carpeta"
}

# --- 3. .env ----------------------------------------------------------------------------

Paso "3/5 Configuracion (.env)"
$envFile = Join-Path $Carpeta ".env"
if (Test-Path $envFile) {
    Ok ".env ya existe: no se modifica (editarlo a mano si hace falta)"
} elseif ($Simular) {
    Info "Se crearia .env a partir de .env.example (pidiendo usuario y clave de Oracle)"
} else {
    $ejemplo = Join-Path $Carpeta ".env.example"
    if (-not (Test-Path $ejemplo)) { Falla "No se encontro $ejemplo" }
    Write-Host ""
    Write-Host "    Datos de la base Oracle ($JdbcUrl, esquema $Esquema):" -ForegroundColor White
    $dbUser = Read-Host "    Usuario de Oracle"
    if (-not $dbUser) { Falla "El usuario de Oracle es obligatorio" }
    $dbPass = Leer-Clave "    Clave de Oracle (no se muestra)"
    if (-not $dbPass) { Falla "La clave de Oracle es obligatoria" }
    $cors = Read-Host "    Origenes CORS separados por coma (Enter = ninguno)"
    $jwt = & $python -c "import secrets; print(secrets.token_urlsafe(48))"
    if ($LASTEXITCODE -ne 0 -or -not $jwt) { Falla "No se pudo generar JWT_SECRET con Python" }

    $valores = [ordered]@{
        "ENV" = "test"
        "LOG_LEVEL" = "INFO"
        "DB_DRIVER" = "jdbc"
        "JDBC_DRIVER_JAR" = "lib/ojdbc8-19.27.0.0.jar"
        "JAVA_HOME" = $javaHome
        "DB_USER" = $dbUser
        "DB_PASSWORD" = $dbPass
        "DB_JDBC_URL" = $JdbcUrl
        "DB_DSN" = ""
        "ORACLE_CLIENT_LIB_DIR" = ""
        "VIEW_SCHEMA" = $Esquema
        "USERS_FILE" = "users.json"
        "JWT_SECRET" = "$jwt".Trim()
        "CORS_ORIGINS" = $cors
    }
    $lineas = foreach ($linea in Get-Content $ejemplo -Encoding UTF8) {
        if ($linea -match '^([A-Z_]+)=') {
            $k = $Matches[1]
            if ($valores.Contains($k)) { "$k=$(Valor-Env $valores[$k])" } else { $linea }
        } else { $linea }
    }
    $lineas = @("# Generado por deploy\instalar_todo.ps1 el $(Get-Date -Format 'dd/MM/yyyy HH:mm')") + $lineas
    [IO.File]::WriteAllLines($envFile, [string[]]$lineas, (New-Object Text.UTF8Encoding($false)))
    $dbPass = $null
    # Solo administradores, SYSTEM y la cuenta del servicio (LOCAL SERVICE) pueden leerlo.
    icacls $envFile /inheritance:r /grant:r "*S-1-5-32-544:(F)" "*S-1-5-18:(F)" "*S-1-5-19:(R)" /Q | Out-Null
    Ok ".env creado (ENV=test, JAVA_HOME=$javaHome, JWT_SECRET generado)"
}

# --- 4. Servicio ------------------------------------------------------------------------

Paso "4/5 Instalacion del servicio"
$instalador = Join-Path $Carpeta "deploy\instalar_servidor.ps1"
if ($Simular) {
    Info "Se ejecutaria $instalador -Puerto $Puerto -Nssm $NssmExe"
} else {
    if (-not (Test-Path $instalador)) { Falla "No se encontro $instalador" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $instalador -Puerto $Puerto -Nssm $NssmExe
    if ($LASTEXITCODE -ne 0) { Falla "deploy\instalar_servidor.ps1 no termino bien (ver mensajes de arriba)" }
}

# --- 5. Usuario de la API -----------------------------------------------------------------

Paso "5/5 Usuarios de la API"
$usersFile = Join-Path $Carpeta "users.json"
$hayUsuarios = (Test-Path $usersFile) -and ((Get-Content $usersFile -Raw) -match '"username"')
if ($hayUsuarios) {
    Ok "Ya hay usuarios en users.json"
} elseif ($Simular) {
    Info "Se pediria nombre y clave para crear el primer usuario de la API"
} else {
    $nombre = Read-Host "    Nombre del primer usuario de la API (Enter = sistema-testing)"
    if (-not $nombre) { $nombre = "sistema-testing" }
    Info "Ahora se pide la clave del usuario (minimo 12 caracteres, dos veces)."
    Push-Location $Carpeta
    & (Join-Path $Carpeta ".venv\Scripts\python.exe") scripts\manage_users.py add $nombre
    $rc = $LASTEXITCODE
    Pop-Location
    if ($rc -ne 0) { Aviso "No se creo el usuario. Crearlo despues con: .venv\Scripts\python scripts\manage_users.py add <usuario>" }
    else { Ok "Usuario '$nombre' creado (la API lo toma sin reiniciar)" }
}

Write-Host ""
if ($Simular) {
    Write-Host "Simulacion terminada. Para instalar, ejecutar sin -Simular." -ForegroundColor Green
} else {
    Write-Host "Listo. Probar desde otra PC: http://192.168.16.39:$Puerto/health y /docs" -ForegroundColor Green
    Write-Host "Para actualizar en el futuro: ejecutar este mismo script, o deploy\actualizar_servidor.ps1"
}
