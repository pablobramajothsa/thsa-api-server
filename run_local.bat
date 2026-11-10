@echo off
REM Ejecuta la API en local, escuchando solo en 127.0.0.1:8000.
REM Uso:  run_local.bat            (normal)
REM       run_local.bat --reload   (recarga automatica al editar codigo)
REM Se puede ejecutar con doble clic o desde cualquier carpeta.

setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual .venv
    echo Crealo con:
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements-dev.txt
    pause
    exit /b 1
)

if not exist ".env" (
    echo [AVISO] No existe el archivo .env: copia .env.example a .env y completalo.
    echo         Sin claves configuradas, todos los requests a /v1 devuelven 401.
    echo.
)

echo Iniciando API en http://127.0.0.1:8000  ^(docs: http://127.0.0.1:8000/docs^)
echo Ctrl+C para detener.
echo.

set "UVICORN_ARGS=--factory --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header --no-access-log"
".venv\Scripts\python.exe" -m uvicorn app.main:create_app %UVICORN_ARGS% %*

if errorlevel 1 pause
endlocal
