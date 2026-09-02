@echo off
setlocal enabledelayedexpansion
title MV AutoML Studio - activar edicion OWNER
REM (c) 2026 Martin Viera. Software propietario.
REM
REM Convierte una instalacion que ya tenes en edicion OWNER, sin bajar de nuevo
REM los 375 MB del instalador. Escribe la licencia en la carpeta de datos del
REM programa; al reabrirlo, arranca en nivel Owner.
REM
REM La licencia es un token firmado con Ed25519: escribir el archivo a mano no
REM sirve de nada, el programa verifica la firma contra la clave publica que
REM lleva embebida (backend/app/core/licensing.py).
REM
REM El que se baja del release viene con la licencia YA ADENTRO (la pone el paso
REM "Activador OWNER" del workflow, firmada con el par de ese mismo build): se
REM abre con doble clic y no pregunta nada. La copia que vive en el repositorio
REM tiene el hueco vacio a proposito, porque una licencia fija ahi dejaria de
REM valer apenas cambien las claves.

REM --- la licencia de este build; la rellena el CI ---
set "LIC_EMBEBIDA="

set "LICFILE=%~dp0mi-licencia.txt"
set "DATOS=%APPDATA%\MV AutoML Studio\data"

echo.
echo  ============================================
echo   ACTIVAR EDICION OWNER
echo  ============================================
echo.

set "LIC="
if defined LIC_EMBEBIDA (
  set "LIC=!LIC_EMBEBIDA!"
  echo  Licencia de dueno incluida en este activador.
)
if not defined LIC if exist "%LICFILE%" (
  set /p LIC=<"%LICFILE%"
  echo  Licencia leida de mi-licencia.txt
)
if not defined LIC (
  echo  Este activador vino sin licencia adentro. Bajate el del release
  echo  ("Activador OWNER", al lado del instalador owner) y no te pide nada,
  echo  o pega la tuya aca: se emite en tu sitio, /panel, seccion
  echo  "Emitir licencia", nivel Owner, sin vencimiento.
  echo.
  set /p LIC=  Licencia: 
  if not defined LIC (
    echo.
    echo  [ERROR] No escribiste ninguna licencia.
    goto :fin
  )
  >"%LICFILE%" echo !LIC!
)

REM Un control barato antes de escribir: las licencias empiezan con MVAS.
echo !LIC! | findstr /b /c:"MVAS." >nul
if errorlevel 1 (
  echo.
  echo  [ERROR] Eso no parece una licencia: tienen que empezar con MVAS.
  echo          Revisa que la hayas copiado entera, sin cortar el final.
  goto :fin
)

if not exist "%DATOS%" (
  echo  [AVISO] No encuentro la carpeta de datos del programa:
  echo          %DATOS%
  echo          Se crea igual: si todavia no instalaste, la licencia queda
  echo          esperando y el programa la toma la primera vez que arranque.
  mkdir "%DATOS%" 2>nul
)

>"%DATOS%\license.key" echo !LIC!
if errorlevel 1 (
  echo  [ERROR] No pude escribir en %DATOS%
  goto :fin
)

echo.
echo  [OK] Licencia escrita en:
echo       %DATOS%\license.key
echo.
echo  Cerra el programa si lo tenes abierto y volve a abrirlo. Arriba a la
echo  derecha tiene que decir Owner.
echo.
echo  Para volver atras: Desactivar-OWNER.bat

:fin
echo.
pause
