@echo off
setlocal enabledelayedexpansion
title MV AutoML Studio - bajar el instalador OWNER
REM (c) 2026 Martin Viera. Software propietario.
REM
REM Baja la compilacion OWNER - la version completa, con la licencia adentro -
REM pidiendosela al sitio con tu licencia de dueno. No hace falta cuenta de
REM GitHub ni token: el sitio verifica la firma y devuelve un enlace temporal.
REM
REM Camino mas corto que este: GitHub, pestana Actions, workflow Escritorio
REM Windows, y abajo de la ejecucion, en Artifacts, esta el instalador. Ese no
REM necesita ni licencia ni que el sitio este configurado.
REM
REM Sin acentos y con etiquetas en vez de bloques anidados, a proposito: la
REM consola de Windows rompe los acentos segun la pagina de codigos, y un
REM parentesis suelto adentro de un bloque se lo cierra a cmd.exe antes de
REM tiempo.

set "SITIO=https://mv-automl-studio.vercel.app"
set "LICFILE=%~dp0mi-licencia.txt"
set "DESTINO=%~dp0MV-AutoML-Studio-Owner-Setup.exe"
set "LIC="

echo.
echo  ============================================
echo   INSTALADOR OWNER - VERSION COMPLETA
echo  ============================================
echo.

if exist "%LICFILE%" goto :del_archivo
goto :pedir

:del_archivo
set /p LIC=<"%LICFILE%"
echo  Licencia leida de mi-licencia.txt
if not defined LIC goto :pedir
goto :buscar_curl

:pedir
echo  Pega tu licencia de dueno. Se emite en %SITIO%/panel,
echo  seccion Emitir licencia, nivel Owner, sin vencimiento.
echo.
set /p LIC=  Licencia: 
if not defined LIC goto :sin_licencia
>"%LICFILE%" echo !LIC!
echo  Guardada en mi-licencia.txt: la proxima vez no te la pide.
goto :buscar_curl

:sin_licencia
echo.
echo  [ERROR] No escribiste ninguna licencia.
goto :fin

:buscar_curl
REM Windows 10 y posteriores traen curl.exe
where curl.exe >nul 2>&1
if errorlevel 1 goto :sin_curl

echo.
echo  Bajando desde %SITIO% ...
echo  Son unos 375 MB: puede tardar varios minutos.
echo.
curl.exe -L --fail --progress-bar -o "%DESTINO%" "%SITIO%/api/descargar?lic=!LIC!"
if errorlevel 1 goto :fallo

echo.
echo  [OK] Listo: %DESTINO%
echo.
echo  Doble clic para instalar. Arranca con todas las funciones abiertas:
echo  no hay que activar nada.
goto :fin

:sin_curl
echo.
echo  [ERROR] No encuentro curl.exe. Viene con Windows 10 y posteriores.
echo          Alternativa: abri esta direccion en el navegador
echo          %SITIO%/api/descargar?lic=!LIC!
goto :fin

:fallo
echo.
echo  [ERROR] La descarga no salio. Las causas posibles, en orden:
echo    1. La licencia no es de nivel Owner, no es valida o vencio.
echo    2. El sitio todavia no tiene cargadas MV_LICENSE_PUBLIC_KEY
echo       y GITHUB_TOKEN. Mira %SITIO%/api/estado
echo    3. Todavia no se compilo ningun instalador Owner:
echo       GitHub, Actions, Escritorio Windows, Run workflow.
echo.
echo  Mientras tanto, el instalador esta en Actions: abri la ultima
echo  ejecucion de Escritorio Windows y bajalo de Artifacts.
if exist "%DESTINO%" del "%DESTINO%"
goto :fin

:fin
echo.
pause
