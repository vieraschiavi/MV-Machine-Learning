# Procedencia de este skill

Copia del skill personal `all-in-one-tech-team` (18 módulos), activado a nivel
proyecto para que cargue en cualquier sesión de Claude Code que abra este repo.
Se mantiene en su origen, no acá: para actualizarlo, volver a copiar la carpeta
entera desde el skill personal.

## Único cambio respecto del original

`scripts/cicd_check.py`, fixture `WF_ROTO` de la demo: el token de GitHub de
ejemplo se arma en tiempo de ejecución (`"ghp_" + "…"`) en vez de estar escrito
entero. Escrito entero, el escaneo de secretos de GitHub lo toma por uno real y
puede bloquear el push del repositorio. La demo lo sigue detectando igual
(`secreto-en-texto-plano`); verificado con `python scripts/cicd_check.py --demo`.

**Al actualizar la copia, repetir este cambio.**

## Instalarlo para todos tus proyectos (Windows)

Desde la carpeta que contiene `all-in-one-tech-team`:

    xcopy /E /I /Y all-in-one-tech-team "%USERPROFILE%\.claude\skills\all-in-one-tech-team"
