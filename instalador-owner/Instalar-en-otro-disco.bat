@echo off
setlocal enabledelayedexpansion
title Instalar MV AutoML Studio en otro disco

REM ---------------------------------------------------------------------
REM  Para que la instalacion no dependa del disco C:
REM
REM  El instalador (NSIS) descomprime su paquete interno en %TEMP% antes de
REM  copiarlo al destino. %TEMP% vive en el disco del sistema, asi que aunque
REM  elijas instalar en D: el pico de espacio lo sufre C:. Cuando no entra,
REM  falla con "error escribiendo al archivo ...\app-64.7z", que no menciona
REM  el espacio por ningun lado.
REM
REM  Este script mueve el %TEMP% al disco que le digas y recien ahi lanza el
REM  instalador. Adentro del instalador, elegi tambien la carpeta de destino
REM  en ese mismo disco.
REM ---------------------------------------------------------------------

echo.
echo  ============================================
echo   INSTALAR SIN USAR EL DISCO C:
echo  ============================================
echo.

set "SETUP=%~dp0MV-AutoML-Studio-Owner-Setup.exe"
if exist "%SETUP%" goto :tengo_setup
set "SETUP=%~dp0MV-AutoML-Studio-Setup.exe"
if exist "%SETUP%" goto :tengo_setup

echo  No encuentro el instalador al lado de este archivo.
echo.
echo  Dejalos juntos en la misma carpeta: este .bat y el
echo  MV-AutoML-Studio-Owner-Setup.exe que bajaste del release.
echo.
pause
exit /b 1

:tengo_setup
echo  Instalador: %SETUP%
echo.
echo  En que disco queres que trabaje? Escribi solo la letra.
echo  Tiene que tener unos 3 GB libres.
echo.
set "DISCO="
set /p DISCO=  Disco (por ejemplo D):

if not defined DISCO goto :sin_disco
set "DISCO=%DISCO:~0,1%"
if not exist "%DISCO%:\" goto :no_existe

set "TRABAJO=%DISCO%:\mv-instalacion-temporal"
mkdir "%TRABAJO%" 2>nul
if not exist "%TRABAJO%" goto :no_escribe

set "TEMP=%TRABAJO%"
set "TMP=%TRABAJO%"

echo.
echo  Espacio temporal: %TRABAJO%
echo.
echo  Arranca el instalador. Cuando te pregunte la carpeta de
echo  instalacion, elegi una en %DISCO%: tambien.
echo.
"%SETUP%"

echo.
echo  Limpiando el espacio temporal...
rmdir /s /q "%TRABAJO%" 2>nul
echo  Listo.
echo.
pause
exit /b 0

:sin_disco
echo.
echo  No escribiste ninguna letra. No hice nada.
echo.
pause
exit /b 1

:no_existe
echo.
echo  El disco %DISCO%: no existe en esta maquina.
echo.
pause
exit /b 1

:no_escribe
echo.
echo  No puedo crear carpetas en %DISCO%:. Proba con otro disco,
echo  o revisa los permisos de escritura.
echo.
pause
exit /b 1
