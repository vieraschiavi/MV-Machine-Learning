@echo off
setlocal enabledelayedexpansion
title MV AutoML Studio - bajar el instalador OWNER
REM (c) 2026 Martin Viera. Software propietario.
REM
REM Baja la compilacion OWNER (la version completa, con la licencia de dueno
REM adentro) usando tu licencia. No hace falta cuenta de GitHub ni token: el
REM sitio verifica la firma y devuelve un enlace temporal.
REM
REM Sin acentos a proposito: la consola de Windows los rompe segun la pagina
REM de codigos que tenga puesta cada equipo.

set "SITIO=https://mv-automl-studio.vercel.app"
set "LICFILE=%~dp0mi-licencia.txt"
set "DESTINO=%~dp0MV-AutoML-Studio-Owner-Setup.exe"

echo.
echo  ============================================
echo   INSTALADOR OWNER - VERSION COMPLETA
echo  ============================================
echo.

REM --- la licencia: del archivo de al lado, o se pide una vez ---
set "LIC="
if exist "%LICFILE%" (
  set /p LIC=<"%LICFILE%"
  echo  Licencia leida de mi-licencia.txt
)
if not defined LIC (
  echo  Pega tu licencia de dueno. Se emite en %SITIO%/panel,
  echo  seccion "Emitir licencia", nivel Owner, sin vencimiento.
  echo.
  set /p LIC=  Licencia: 
  if not defined LIC (
    echo.
    echo  [ERROR] No escribiste ninguna licencia.
    goto :fin
  )
  >"%LICFILE%" echo !LIC!
  echo  Guardada en mi-licencia.txt: la proxima vez no te la pide.
)

REM --- Windows 10 y posteriores traen curl.exe ---
where curl.exe >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [ERROR] No encuentro curl.exe. Viene con Windows 10 y posteriores.
  echo          Alternativa: abri esta direccion en el navegador
  echo          %SITIO%/api/descargar?lic=!LIC!
  goto :fin
)

echo.
echo  Bajando desde %SITIO% ...
echo  Son unos 375 MB: puede tardar varios minutos.
echo.
curl.exe -L --fail --progress-bar -o "%DESTINO%" "%SITIO%/api/descargar?lic=!LIC!"
if errorlevel 1 (
  echo.
  echo  [ERROR] La descarga no salio. Las causas posibles, en orden:
  echo    1. La licencia no es de nivel Owner, no es valida o vencio.
  echo    2. El sitio todavia no tiene cargadas MV_LICENSE_PUBLIC_KEY
  echo       y GITHUB_TOKEN. Mira %SITIO%/api/estado
  echo    3. Todavia no se compilo ningun instalador Owner:
  echo       GitHub - Actions - "Escritorio Windows" - Run workflow.
  if exist "%DESTINO%" del "%DESTINO%"
  goto :fin
)

echo.
echo  [OK] Listo: %DESTINO%
echo.
echo  Doble clic para instalar. Arranca con todas las funciones abiertas:
echo  no hay que activar nada.

:fin
echo.
pause
