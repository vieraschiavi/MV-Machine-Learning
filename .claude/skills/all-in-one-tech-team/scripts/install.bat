@echo off
REM Instalador automatico — all-in-one-tech-team (Claude Code, Windows)
setlocal
set SKILL_NAME=all-in-one-tech-team
set SRC=%~dp0..
set DEST=%USERPROFILE%\.claude\skills\%SKILL_NAME%

echo [1/4] Origen:  %SRC%
echo [2/4] Destino: %DEST%

if not exist "%SRC%\SKILL.md" (
  echo ERROR: no se encontro SKILL.md en %SRC% — abortando.
  exit /b 1
)

if not exist "%DEST%" mkdir "%DEST%"
copy /Y "%SRC%\SKILL.md" "%DEST%\" >nul
xcopy /E /I /Y "%SRC%\references" "%DEST%\references" >nul
xcopy /E /I /Y "%SRC%\scripts" "%DEST%\scripts" >nul
if exist "%SRC%\assets" xcopy /E /I /Y "%SRC%\assets" "%DEST%\assets" >nul

echo [3/4] Validando instalacion...
if not exist "%DEST%\SKILL.md" (
  echo ERROR: la copia fallo.
  exit /b 1
)
echo [4/4] OK — skill instalado en %DEST%
echo Probalo en Claude Code con: "activa el all-in-one para este proyecto"
endlocal
