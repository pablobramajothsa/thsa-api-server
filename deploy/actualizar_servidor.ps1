<#
.SYNOPSIS
    Actualiza la API en el servidor: git pull, dependencias y reinicio del servicio.

.DESCRIPTION
    Ejecutar como administrador desde la carpeta del proyecto:

        powershell -ExecutionPolicy Bypass -File deploy\actualizar_servidor.ps1

    No toca .env, users.json, el driver ni la configuracion del servicio. Si cambia algo de
    eso, volver a ejecutar deploy\instalar_servidor.ps1.
    Mensajes sin acentos a proposito (PowerShell 5.1 lee los .ps1 sin BOM como ANSI).
#>
[CmdletBinding()]
param(
    [int]$Puerto = 8001,
    [string]$Servicio = "ThsaApiServer",
    [string]$Nssm = ""
)

$ErrorActionPreference = "Continue"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

function Paso([string]$texto) { Write-Host ""; Write-Host "==> $texto" -ForegroundColor Cyan }
function Ok([string]$texto) { Write-Host "    [OK] $texto" -ForegroundColor Green }
function Falla([string]$texto) { Write-Host "    [ERROR] $texto" -ForegroundColor Red; exit 1 }

if (-not $Nssm) {
    $c = Get-Command nssm -ErrorAction SilentlyContinue
    $Nssm = if ($c) { $c.Source } else { "C:\nssm\nssm.exe" }
}
if (-not (Test-Path $Nssm)) { Falla "No se encontro nssm.exe (indicar -Nssm <ruta>)" }
if (-not (Get-Service -Name $Servicio -ErrorAction SilentlyContinue)) {
    Falla "No existe el servicio ${Servicio}: ejecutar primero deploy\instalar_servidor.ps1"
}

Paso "Descargando la ultima version (git pull)"
$antes = (git rev-parse --short HEAD).Trim()
git pull --ff-only
if ($LASTEXITCODE -ne 0) { Falla "git pull fallo (cambios locales en el servidor?). Revisar con 'git status'" }
$despues = (git rev-parse --short HEAD).Trim()
if ($antes -eq $despues) { Ok "Ya estaba en la ultima version ($despues)" }
else { Ok "Actualizado de $antes a $despues"; git log --oneline "$antes..$despues" | ForEach-Object { Write-Host "      $_" } }

Paso "Instalando dependencias"
& $VenvPython -m pip install --disable-pip-version-check -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Falla "Fallo pip install -r requirements.txt" }
Ok "Dependencias al dia"

Paso "Reiniciando el servicio $Servicio"
& $Nssm restart $Servicio | Out-Null
$salud = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $salud = Invoke-RestMethod -Uri "http://127.0.0.1:$Puerto/health" -TimeoutSec 10 -ErrorAction Stop
        break
    } catch { }
}
if ($salud -and $salud.status -eq "ok") { Ok "La API responde /health -> ok (version $despues)" }
else { Falla "La API no respondio /health = ok en 60 s. Revisar logs\api.log" }
