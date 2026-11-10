# Ejecuta la API en local, escuchando solo en 127.0.0.1:8000.
# Uso:  .\scripts\run_local.ps1            (normal)
#       .\scripts\run_local.ps1 --reload   (recarga automática al editar código)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

& .\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory `
    --host 127.0.0.1 --port 8000 `
    --proxy-headers --forwarded-allow-ips 127.0.0.1 `
    --no-server-header --no-access-log @args
