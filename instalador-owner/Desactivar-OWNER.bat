@echo off
setlocal
title MV AutoML Studio - volver a la edicion normal
REM (c) 2026 Martin Viera. Software propietario.
REM
REM Borra la licencia activada en este equipo. No toca los datasets, los
REM modelos ni los informes: solo el archivo de licencia.

set "DATOS=%APPDATA%\MV AutoML Studio\data"

echo.
echo  Borrando la licencia activada en este equipo...
if exist "%DATOS%\license.key" (
  del "%DATOS%\license.key"
  echo  [OK] Listo. Al reabrir, el programa vuelve a como estaba.
) else (
  echo  No habia ninguna licencia activada en %DATOS%
)
echo.
echo  Tus datasets, modelos e informes siguen donde estaban.
echo.
pause
