@echo off
REM ---------------------------------------------------------------------------
REM MV AutoML Studio - arranque en Windows
REM Crea el entorno virtual si no existe, instala lo que falte y levanta la app.
REM ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
cd /d "%~dp0.."

set "PY="
for %%C in ("py -3.12" "py -3.11" "py -3" "python") do (
  if not defined PY (
    %%~C -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
    if !errorlevel! equ 0 set "PY=%%~C"
  )
)

if not defined PY (
  echo No se encontro Python 3.11 o superior.
  echo Instalalo desde https://www.python.org/downloads/ y volve a ejecutar.
  pause
  exit /b 1
)

echo Python detectado: %PY%

if not exist ".venv" (
  echo Creando el entorno virtual...
  %PY% -m venv .venv
)

call .venv\Scripts\activate.bat

python -c "import fastapi, pandas, sklearn, duckdb" >nul 2>&1
if errorlevel 1 (
  echo Instalando dependencias ^(la primera vez tarda unos minutos^)...
  python -m pip install --upgrade pip >nul
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Fallo la instalacion de dependencias.
    pause
    exit /b 1
  )
)

if "%MV_HOST%"=="" set "MV_HOST=127.0.0.1"
if "%MV_PORT%"=="" set "MV_PORT=8000"

echo.
echo   MV AutoML Studio
echo   http://%MV_HOST%:%MV_PORT%
echo   Ctrl+C para detener
echo.

start "" "http://%MV_HOST%:%MV_PORT%"
python -m uvicorn backend.app.main:app --host %MV_HOST% --port %MV_PORT%

pause
