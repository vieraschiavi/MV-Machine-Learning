@echo off
setlocal enabledelayedexpansion
title MV AutoML Studio - activar edicion OWNER
REM (c) 2026 Martin Viera. Software propietario.
REM
REM Convierte una instalacion que ya tenes en edicion OWNER, sin bajar de nuevo
REM el instalador. Escribe la licencia en la carpeta de datos del programa; al
REM reabrirlo, arranca en nivel Owner.
REM
REM NO hace falta para el instalador owner: ese ya viene con la licencia y la
REM clave que la valida adentro, y arranca en Owner solo. Esto es para el otro
REM caso: convertir una instalacion de CLIENTE que ya tengas.
REM
REM La licencia es un token firmado con Ed25519: escribir el archivo a mano no
REM sirve, el programa verifica la firma contra la clave publica que lleva
REM embebida (backend/app/core/licensing.py).
REM
REM Escrito con etiquetas y sin bloques anidados a proposito. Un parentesis
REM suelto adentro de un if - por ejemplo en un mensaje entre comillas - le
REM cierra el bloque a cmd.exe antes de tiempo y el resto del script se
REM ejecuta como comandos sueltos. Asi no hay bloques que romper.

REM --- la licencia de este build; la rellena el CI ---
set "LIC_EMBEBIDA="

set "LICFILE=%~dp0mi-licencia.txt"
set "DATOS=%APPDATA%\MV AutoML Studio\data"
set "LIC="

echo.
echo  ============================================
echo   ACTIVAR EDICION OWNER
echo  ============================================
echo.

if defined LIC_EMBEBIDA goto :embebida
if exist "%LICFILE%" goto :del_archivo
goto :pedir

:embebida
set "LIC=!LIC_EMBEBIDA!"
echo  Licencia de dueno incluida en este activador.
goto :controlar

:del_archivo
set /p LIC=<"%LICFILE%"
echo  Licencia leida de mi-licencia.txt
if not defined LIC goto :pedir
goto :controlar

:pedir
echo  Este activador vino sin licencia adentro.
echo.
echo  Bajate el del release - se llama Activador OWNER y esta al lado del
echo  instalador owner - y no te pide nada.
echo.
echo  O pega la tuya aca. Se emite en tu sitio, en /panel, seccion
echo  Emitir licencia, nivel Owner, sin vencimiento.
echo.
set /p LIC=  Licencia: 
if not defined LIC goto :sin_licencia
>"%LICFILE%" echo !LIC!
goto :controlar

:sin_licencia
echo.
echo  [ERROR] No escribiste ninguna licencia.
goto :fin

:controlar
REM Un control barato antes de escribir: las licencias empiezan con MVAS.
echo !LIC! | findstr /b /c:"MVAS." >nul
if errorlevel 1 goto :no_parece

if exist "%DATOS%" goto :escribir
echo  [AVISO] No encuentro la carpeta de datos del programa:
echo          %DATOS%
echo          Se crea igual: si todavia no instalaste, la licencia queda
echo          esperando y el programa la toma la primera vez que arranque.
mkdir "%DATOS%" 2>nul

:escribir
>"%DATOS%\license.key" echo !LIC!
if errorlevel 1 goto :no_pude

echo.
echo  [OK] Licencia escrita en:
echo       %DATOS%\license.key
echo.
echo  Cerra el programa si lo tenes abierto y volve a abrirlo. Arriba a la
echo  derecha tiene que decir Owner.
echo.
echo  Para volver atras: Desactivar-OWNER.bat
goto :fin

:no_parece
echo.
echo  [ERROR] Eso no parece una licencia: tienen que empezar con MVAS.
echo          Revisa que la hayas copiado entera, sin cortar el final.
goto :fin

:no_pude
echo.
echo  [ERROR] No pude escribir en %DATOS%
goto :fin

:fin
echo.
pause
