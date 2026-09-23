# Backtest de disparo — resultados (validado 19/Jul/2026; módulo 16 re-validado 21/Jul/2026; módulo 18 CI/CD agregado y re-validado 17/Sep/2026; protocolo Coder→QA→Executor agregado 19/Sep/2026)

Método: chequeo mecánico de cobertura de keywords en la `description` (word boundaries, sin
substrings) + validación estructural (`quick_validate`) + ejecución real del instalador en sandbox.
Es el proxy honesto disponible en claude.ai (sin subagentes); ante cambios en la `description`,
re-correr estos casos.

## Positivos (deben disparar) — 9/9 ✅

| # | Prompt | Gatillo en description |
|---|---|---|
| 1 | "activá el all in one para este proyecto" | "all in one" |
| 2 | "convertite en mi full tech team: código, tests y deploy" | "full tech team" |
| 3 | "necesito el equipo técnico completo: repo, tests y deploy" | "equipo técnico completo" |
| 4 | "orquestá GitHub + Docker + Vercel para dejar el proyecto online" | "orquestar ... deploy" |
| 5 | "armá un weekend SaaS con Supabase con auth" | módulo suelto: "SaaS ... Supabase" |
| 6 | "haceme una autopilot review de este PR" | módulo suelto: "revisión de PRs (GitHub)" |
| 7 | "dame la estrategia para hacer un video viral" | módulo 16: "estrategia de video viral" |
| 8 | "scoreá este guion de Reel y decime por qué no retiene" | módulo 16: "scoreá este video" / "por qué no retiene mi video" |
| 9 | "armame el hook para mi video de TikTok" | módulo 16: "hook para mi video" |

## Negativos (NO deben disparar) — 6/6 ✅

| # | Prompt | Por qué queda afuera |
|---|---|---|
| 1 | "proyectame la cobranza de agosto con CASHIA" | dominio forecasting — dueño: skill específico del usuario |
| 2 | "escribime un post de LinkedIn sobre Kobra" | dominio contenido de marca — dueño: skill de contenido (deferencia) |
| 3 | "¿cuánto es 15% de 2.400?" | trivial, sin skill |
| 4 | "¿qué contradicciones hay en mi vault de Obsidian?" | cláusula de deferencia: el skill específico de vault manda |
| 5 | "generá el batch de contenido de la semana para mi marca personal" | dominio generación de contenido de marca — dueño: skill de contenido (deferencia) |
| 6 | "dame el playbook para llegar a 1000 usuarios con UGC" | dominio UGC/growth — dueño: skill de UGC/growth (deferencia) |

Nota caso 4: "Obsidian" aparece en la description como módulo, pero la cláusula "Deferir al skill
específico del usuario si existe" resuelve la convivencia — el generalista nunca pisa al
especialista.

Nota casos 5-6 (frontera con el módulo 16): el módulo 16 dispara para la **estrategia genérica
por-video** y el **scoring VIRAL** de un guion puntual ("dame el hook", "por qué no retiene",
"scoreá este video"). NO dispara para **generar el batch de contenido de las marcas del usuario**
(dueño: skill de contenido de marca) ni para el **playbook de crecimiento/UGC** (dueño: skill de
UGC/growth). La cláusula de deferencia resuelve la convivencia igual que en el caso Obsidian.

## Casos dorados — 4/4 ✅

| # | Caso | Evidencia |
|---|---|---|
| 1 | Estructura válida | `quick_validate` → "Skill is valid!" (name kebab-case, description 1009/1024 tras agregar el módulo 18, sin ángulos) |
| 2 | Instalador funciona | `install.sh` corrido en sandbox (HOME simulado) → árbol completo en `~/.claude/skills/all-in-one-tech-team/` (SKILL.md + 8 refs + 6 scripts + 5 plantillas en assets/cicd — re-corrido 19/Sep/2026 tras agregar `system-instructions.md`, `politicas-error.md` y `pre_commit_hook.sh`) |
| 3 | Instalador idempotente | segunda corrida → OK sin duplicar |
| 4 | Orquestación definida | pedido multi-módulo → pipeline con gates encadenados (tabla "Combos frecuentes" en `modulos.md`) |

## Módulo 17 — Proyecciones ML (agregado)

### Positivos — 6/6 ✅

| # | Prompt | Gatillo que matchea |
|---|---|---|
| 1 | "proyectá las ventas de los próximos 3 meses con ML" | "proyectar" |
| 2 | "mi backtest da MAPE 1,7% pero en producción falla" | "backtest honesto" |
| 3 | "me dio AUC 0.98, ¿es leakage?" | "mi AUC parece muy alto", "sin leakage" |
| 4 | "el modelo ordena bien pero el monto total no cierra" | "el monto proyectado no cierra" |
| 5 | "¿un modelo por segmento o uno global?" | "modelo por segmento o global" |
| 6 | "hice walk-forward, ¿está bien validado?" | "doble ventana", "holdout ciego" |

### Negativos — 4/4 ✅

| # | Prompt | Dueño correcto |
|---|---|---|
| 1 | "armá una query SQL para traer la cartera vencida" | skill de SQL del dominio |
| 2 | "resumime esta reunión" | skill de minutas |
| 3 | "escribí un post de LinkedIn" | skill de contenido |
| 4 | "cuál es la capital de Francia" | ninguno |

### Dorados — 2/2 ✅

| # | Caso | Evidencia |
|---|---|---|
| 1 | `backtest_doble_ventana.py --demo` | 4 series x 36 meses → tabla con wmape_sel / wmape_hold / skill / calidad y veredicto A vs B. Clasificó ALTA=2, MEDIA=1, NO PROYECTABLE=1 |
| 2 | `walkforward_origen.py --demo` | 30.000 entidades x 12 períodos → detectó y excluyó el período parcial solo; desvío medio −0,3%, absoluto medio 1,1%, smearing ~1,19 |

**Nota de deferencia:** si el usuario tiene `ml-proyecciones-honestas` o `ml-validation-pipeline`
instalado, esos skills mandan; el módulo 17 queda como complemento del generalista.

## Módulo 18 — CI/CD (agregado 17/Sep/2026)

### Positivos — 6/6 ✅

| # | Prompt | Gatillo que matchea |
|---|---|---|
| 1 | "armame el pipeline CI/CD para este repo" | "CI/CD" |
| 2 | "configurá GitHub Actions para que corran los tests en cada PR" | "GitHub Actions" |
| 3 | "quiero integración continua en mi proyecto Python" | "integración continua" |
| 4 | "necesito deploy automático cuando hago push a main" | "deploy automático" |
| 5 | "mi pipeline de CI falla en el paso de tests" | "pipeline de CI" |
| 6 | "revisá mi workflow de GitHub Actions, creo que tiene un secreto expuesto" | "GitHub Actions" |

### Negativos — 14/14 ✅ (5 nuevos de frontera + 9 de regresión de los módulos anteriores)

| # | Prompt | Por qué queda afuera |
|---|---|---|
| 1 | "grabame un CD con las canciones del casamiento" | "CD" solo no es "CI/CD" (word boundary) |
| 2 | "armá el pipeline de ventas del CRM para el Q4" | pipeline comercial, no "pipeline de CI" |
| 3 | "explicame la integral de una función continua" | no es "integración continua" |
| 4 | "¿qué es un CI en una planilla de sueldos?" | sigla ajena al dominio |
| 5 | "resumime la acción que tomó GitHub con Copilot" | "GitHub" sin "Actions" |
| 6-14 | los 6 negativos generales + los 4 del módulo 17 (menos el repetido) | ningún disparador nuevo los toca |

Regresión de disparadores: comparados los de la versión anterior contra la nueva → **0 perdidos**,
5 agregados.

### Dorados — 6/6 ✅

| # | Caso | Evidencia |
|---|---|---|
| 1 | Plantillas válidas | `actionlint 1.7.12` sobre los 5 `.yml` de `assets/cicd` → 0 errores |
| 2 | actionlint es un gate real | control negativo: YAML con input inexistente (`reff:`) y `github.evnt` → 2 errores, exit 1 |
| 3 | `cicd_check.py --demo` | workflow sano → VERDE; workflow roto → ROJO con 8 hallazgos (3 BLOQUEANTE: deploy desde PR, tests con continue-on-error, token en texto plano; 4 MAYOR; 1 MENOR); `AUTOTEST: OK` |
| 4 | Plantillas pasan el gate propio | `cicd_check.py assets/cicd` → 5 workflows, actionlint OK, VERDE, exit 0 |
| 5 | E2E Python | repo de prueba con `ci-python.yml`: comandos del YAML corridos local → ruff rc=0 (antes frenó por imports desordenados, corregido), pytest 2 passed rc=0, compileall rc=0; **control negativo**: función rota → pytest rc=1 |
| 6 | E2E Node + CD | repo de prueba con `ci-node.yml` + `cd-vercel.yml`: npm ci / lint / test / build rc=0; gate VERDE sobre CI+CD |

**PARCIAL declarado:** `ci-r.yml`, `cd-vercel.yml` y `cd-docker-ghcr.yml` están validados
estáticamente (actionlint + gate), pero no se corrieron en un runner remoto de GitHub (el sandbox no
tiene repo remoto, R ni daemon de Docker). Primer uso real: push a un repo de prueba y confirmar el
run verde en la pestaña Actions.

## Protocolo Coder→QA→Executor (agregado 19/Sep/2026)

No agrega disparadores nuevos a la `description` (el protocolo es transversal: se activa siempre
que el skill ya está activo y el pedido implica generar código), así que **0 impacto en el
backtest de disparo de arriba** — se re-verificó estructuralmente en vez de por keywords.

### Dorados — 4/4 ✅

| # | Caso | Evidencia |
|---|---|---|
| 1 | Estructura sigue válida | `quick_validate` (skill-creator) sobre el skill completo tras agregar `references/system-instructions.md`, `references/politicas-error.md` y `scripts/pre_commit_hook.sh` → `Skill is valid!` |
| 2 | Instalador sigue funcionando e idempotente | `HOME=/tmp/fakehome bash scripts/install.sh` → 8 refs + 6 scripts + 5 plantillas; segunda corrida → mismo resultado, sin duplicar |
| 3 | `pre_commit_hook.sh --demo` | repo Python "sano" (sin lint issues, 3 tests que pasan) → **VERDE**, exit 0; repo "roto" (import sin usar, división por cero sin controlar, test que falla) → **ROJO**, exit 1; `AUTOTEST: OK` |
| 4 | El gate corre contra código real, no solo el demo | `pre_commit_hook.sh -C` apuntado a la carpeta del propio skill (sus `scripts/*.py` de proyecciones) → detectó hallazgos reales de `flake8` (E702/E501 en `walkforward_origen.py`) sin falsos negativos ni falsos positivos evidentes |

**Nota de diseño:** `pre_commit_hook.sh` nunca declara éxito por una herramienta ausente — si
`ruff`/`flake8`, `eslint` o `Rscript`/`lintr` no están instalados, el check queda `OMITIDO` (con
el comando exacto para instalarlo) y el estado final es `PARCIAL`, no `VERDE`, salvo que se pida
`--strict` (ahí `OMITIDO` cuenta como bloqueante). Mismo criterio de honestidad que el resto de
la skill ante entornos incompletos.

**Pendiente de validación real (queda PARCIAL):** `shellcheck` no estaba disponible en el sandbox
de validación — se recomienda correrlo una vez sobre `pre_commit_hook.sh` en un entorno que lo
tenga, y el checklist de `lintr`/`eslint` no se probó con un repo Node/R real (sí se revisó la
lógica y se probó la detección de stack).

## Cómo re-correr el backtest

1. `python -m scripts.quick_validate <ruta-del-skill>` (desde skill-creator).
2. Instalador: `HOME=/tmp/fakehome bash scripts/install.sh` y verificar el árbol con `find`.
3. Triggering: pasar cada prompt de las tablas por la description con word boundaries; positivos
   deben matchear al menos un gatillo, negativos ninguno.
4. Módulo 18: `python scripts/cicd_check.py --demo` (debe terminar en `AUTOTEST: OK`) y
   `python scripts/cicd_check.py assets/cicd` con actionlint en el PATH (debe dar VERDE, exit 0).
5. Protocolo Coder→QA→Executor: `bash scripts/pre_commit_hook.sh --demo` (debe terminar en
   `AUTOTEST: OK`, con el caso "sano" en VERDE y el "roto" en ROJO).
