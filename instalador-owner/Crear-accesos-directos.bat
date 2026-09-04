@echo off
setlocal
title Crear accesos directos de MV AutoML Studio

REM ---------------------------------------------------------------------
REM  La copia portable no instala nada, asi que nadie le crea el icono.
REM  Este script deja el acceso directo en el Escritorio y en el Menu de
REM  inicio, apuntando al ejecutable que este al lado suyo.
REM
REM  Si moves la carpeta del programa, volve a ejecutarlo: el acceso
REM  guarda la ruta de donde estaba.
REM
REM  La ruta se pasa por variable de entorno y no dentro del comando de
REM  PowerShell: asi no hay que anidar comillas, que es de donde salen
REM  los errores cuando la carpeta tiene espacios (y "MV AutoML Studio"
REM  los tiene).
REM ---------------------------------------------------------------------

set "MVEXE=%~dp0MV AutoML Studio.exe"
set "MVDIR=%~dp0"

if not exist "%MVEXE%" goto :no_exe

echo.
echo  Creando accesos directos...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$sh = New-Object -ComObject WScript.Shell; foreach ($carpeta in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) { $lnk = $sh.CreateShortcut((Join-Path $carpeta 'MV AutoML Studio.lnk')); $lnk.TargetPath = $env:MVEXE; $lnk.WorkingDirectory = $env:MVDIR; $lnk.IconLocation = $env:MVEXE; $lnk.Description = 'MV AutoML Studio'; $lnk.Save(); Write-Host ('  listo: ' + $carpeta) }"

if errorlevel 1 goto :fallo

echo.
echo  Ya tenes el icono en el Escritorio y en el Menu de inicio.
echo.
if not defined MV_SIN_PAUSA pause
exit /b 0

:no_exe
echo.
echo  No encuentro "MV AutoML Studio.exe" al lado de este archivo.
echo.
echo  Este script tiene que quedar en la misma carpeta que el programa,
echo  que es donde lo deja el .zip. Si lo moviste, devolvelo ahi.
echo.
if not defined MV_SIN_PAUSA pause
exit /b 1

:fallo
echo.
echo  No pude crear los accesos directos.
echo.
echo  Suele ser el antivirus bloqueando PowerShell. Podes hacerlo a mano:
echo  boton derecho sobre "MV AutoML Studio.exe", Enviar a, Escritorio.
echo.
if not defined MV_SIN_PAUSA pause
exit /b 1
