# Despliegue — All-in-One Tech Team

Tres vías de instalación. El objetivo: cero pasos manuales más allá de correr un script o apretar
un botón.

## A. claude.ai / app (chat)

1. Descargar el paquete `all-in-one-tech-team.skill`.
2. Subirlo al chat → la tarjeta trae el botón **Save skill** → queda instalado en el perfil.
3. Verificar: en un chat nuevo, escribir "activá el all in one" — el skill debe cargar.

## B. Claude Code (automático, Linux/Mac)

```bash
bash scripts/install.sh
```

Qué hace: detecta `~/.claude/skills/` (la crea si no existe) → copia `SKILL.md`, `references/`,
`scripts/` y `assets/` (plantillas CI/CD) → valida que `SKILL.md` quedó legible → imprime OK con la ruta final. Es idempotente: re-correrlo
actualiza el skill en el lugar.

## C. Claude Code (automático, Windows)

```bat
scripts\install.bat
```

Mismo comportamiento que el .sh, usando `%USERPROFILE%\.claude\skills`.

## Verificación post-instalación (las 2 plataformas)

Correr estos 4 prompts y confirmar que dispara / no dispara:

1. "activá el all-in-one para este proyecto" → DEBE disparar.
2. "convertite en mi full tech team: código, tests y deploy" → DEBE disparar.
3. "armame el pipeline CI/CD para este repo" → DEBE disparar (módulo 18).
4. "¿cuánto es 15% de 2.400?" → NO debe disparar.

Chequeo extra del módulo 18 (Claude Code): `python ~/.claude/skills/all-in-one-tech-team/scripts/cicd_check.py --demo`
→ debe terminar en `AUTOTEST: OK`. Requiere PyYAML; actionlint es opcional pero recomendado
(sin él, el gate queda PARCIAL).

## D. Gate local pre-commit (opcional, ciclo Coder→QA→Executor)

Para que el linter + tests + `cicd_check.py` corran automáticamente antes de cada commit del
repo del usuario (no solo cuando Claude los corre a mano):

```bash
bash scripts/pre_commit_hook.sh --install   # instala en .git/hooks/pre-commit del repo actual
```

Verificación: `bash scripts/pre_commit_hook.sh --demo` → debe terminar en `AUTOTEST: OK` (repo
sano da VERDE, repo con lint roto y un test que falla da ROJO). Herramienta faltante (ruff/eslint/
lintr no instalados) queda como `OMITIDO`, no como éxito falso — instalarla con el comando que el
propio hook imprime.

## Actualización

Reemplazar la carpeta con la versión nueva y re-correr el script (o re-subir el `.skill`). El
`name` no cambia entre versiones para no duplicar la entrada.

## Desinstalación

- Claude Code: borrar `~/.claude/skills/all-in-one-tech-team/`.
- claude.ai: Settings → Capabilities/Skills → eliminar el skill.

## Registro en router maestro (si el usuario tiene uno)

Agregar la fila a la tabla de enrutamiento del router, con estas keywords sugeridas:

```
| `all-in-one-tech-team` | Equipo técnico completo (18 módulos: repo, QA, deploy, docs, data, infra, contenido viral, proyecciones ML, CI/CD) | "all in one", "tech team", "full tech team", "equipo técnico completo", "estrategia de video viral", "guion viral", "hook para mi video", "por qué no retiene", "scoreá el video", "proyectar", "backtest honesto", "CI/CD", "pipeline de CI", "GitHub Actions", "integración continua", "deploy automático", orquestar repo+tests+deploy, módulo suelto sin skill específico | Alta — generalista; deferir SIEMPRE al skill específico si existe (contenido de marca, UGC/growth, vault, forecasting, checklists de deploy) |
```
