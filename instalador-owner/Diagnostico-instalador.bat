@echo off
setlocal enabledelayedexpansion
title MV AutoML Studio - por que no arranca el instalador
REM (c) 2026 Martin Viera. Software propietario.
REM
REM Para el caso peor: doble clic al instalador y no pasa NADA. Ni ventana, ni
REM cartel, ni error. Ese sintoma tiene varias causas que se ven igual desde
REM afuera, y sin datos hay que adivinar. Esto las separa.
REM
REM No instala nada por su cuenta: mide, informa, y recien al final ofrece
REM lanzar el instalador salteando la comprobacion interna de integridad.
REM
REM Sin acentos y con etiquetas en vez de bloques anidados, a proposito: la
REM consola de Windows rompe los acentos segun la pagina de codigos, y un
REM parentesis suelto adentro de un bloque se lo cierra a cmd.exe antes de
REM tiempo.

set "SETUP=%~dp0MV-AutoML-Studio-Owner-Setup.exe"
if exist "%SETUP%" goto :tengo
set "SETUP=%~dp0MV-AutoML-Studio-Setup.exe"
if exist "%SETUP%" goto :tengo

echo.
echo  No encuentro ningun instalador al lado de este archivo.
echo  Dejalos juntos en la misma carpeta.
echo.
pause
exit /b 1

:tengo
echo.
echo  ============================================
echo   DIAGNOSTICO DEL INSTALADOR
echo  ============================================
echo.
echo  Archivo: %SETUP%
echo.

REM --- 1. Tamano -------------------------------------------------------------
REM Una descarga cortada es la causa mas comun de "no hace nada": el .exe
REM existe, pesa menos de lo que deberia, y Windows no lo puede ejecutar.
for %%A in ("%SETUP%") do set "BYTES=%%~zA"
set /a MB=!BYTES! / 1048576
echo  [1] Tamano: !MB! MB  ^(!BYTES! bytes^)
if !MB! LSS 300 goto :corto
echo      Parece completo. El instalador owner ronda los 354 MB.
goto :espacio

:corto
echo      [PROBLEMA] Esta cortado. Tiene que rondar los 354 MB.
echo      La descarga se interrumpio. Bajalo de nuevo y verifica el
echo      SHA-256 contra el que figura en el release.
echo.
goto :fin

REM --- 2. Espacio en la carpeta temporal --------------------------------------
:espacio
echo.
echo  [2] Carpeta temporal: %TEMP%
for /f "tokens=3" %%B in ('dir /-c "%TEMP%" 2^>nul ^| findstr /c:"bytes libres"') do set "LIBRE=%%B"
if not defined LIBRE goto :sin_medida
set /a LIBREMB=!LIBRE! / 1048576
echo      Libre: !LIBREMB! MB
if !LIBREMB! LSS 900 echo      [AVISO] Con menos de 900 MB la extraccion puede fallar.
goto :bloqueo

:sin_medida
echo      No pude medir el espacio libre. Sigo igual.

REM --- 3. Marca de archivo bajado de internet ---------------------------------
:bloqueo
echo.
echo  [3] Marca de "bajado de internet"
if exist "%SETUP%:Zone.Identifier" goto :bloqueado
echo      No la tiene. Windows no deberia bloquearlo por eso.
goto :ofrecer

:bloqueado
echo      La tiene. Windows puede estar bloqueandolo en silencio.
echo      Lo desbloqueo ahora...
powershell -NoProfile -Command "Unblock-File -LiteralPath '%SETUP%'" 2>nul
if exist "%SETUP%:Zone.Identifier" goto :no_desbloqueo
echo      [OK] Desbloqueado. Proba el doble clic de nuevo antes de seguir.
goto :ofrecer

:no_desbloqueo
echo      No pude quitarla. Hacelo a mano: clic derecho sobre el
echo      instalador, Propiedades, y abajo tildar Desbloquear.

REM --- 4. Lanzarlo salteando la comprobacion de integridad --------------------
:ofrecer
echo.
echo  [4] Ultima prueba
echo.
echo      Lo lanzo con /NCRC, que saltea la comprobacion interna de
echo      integridad. Si el archivo esta apenas danado, con esto abre igual
echo      y ya sabemos que el problema era la descarga.
echo.
set "R="
set /p R=  Lanzarlo ahora? (S/N):
if /i not "!R!"=="S" goto :fin

echo.
echo  Lanzando...
start /wait "" "%SETUP%" /NCRC
echo  El instalador termino con el codigo: !errorlevel!
echo.
echo  Codigo 0 = termino bien.
echo  Codigo 1 = lo cancelaste o se cancelo solo.
echo  Codigo 2 = el archivo esta danado: bajalo de nuevo.
echo.
echo  Si tampoco abrio nada, usa la version portable (.zip): no pasa por
echo  el instalador, se descomprime donde quieras y se ejecuta.

:fin
echo.
pause
