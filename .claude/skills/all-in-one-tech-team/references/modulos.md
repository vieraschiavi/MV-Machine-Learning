# Módulos operativos — All-in-One Tech Team

Leer SOLO las secciones de los módulos activados por el router. Cada módulo define: objetivo,
workflow, verificación (el gate) y equivalencia por entorno (Claude Code vs claude.ai).

---

## 1. Obsidian — Second Brain

**Objetivo:** conectar el código/proyecto con la base de conocimiento personal (vault markdown).
**Workflow:** localizar el vault (preguntar ruta si no está en contexto) → leer notas relevantes al
tema → crear/actualizar notas con frontmatter consistente (title, tags, fecha, links `[[wiki]]`) →
mantener un índice/MOC del proyecto.
**Gate:** la nota existe en disco, el frontmatter parsea, y los links `[[...]]` apuntan a notas
existentes (verificar con grep).
**Entornos:** Claude Code = filesystem directo. claude.ai = pedir export/upload del vault o
entregar las notas como archivos descargables.
**Deferencia:** si el usuario tiene un skill propio de vault/second brain, ese skill manda.

## 2. GitHub — Autopilot Reviews

**Objetivo:** revisar PRs y cambios de código más rápido, con hallazgos accionables.
**Workflow:** obtener el diff (gh CLI, git diff, o pegado) → revisar por capas: correctitud →
seguridad (inyección, secretos, paths) → performance (N+1, loops) → estilo/consistencia → tests
faltantes → emitir review con severidad (bloqueante/mayor/menor/nit) y línea exacta.
**Gate:** cada hallazgo cita archivo:línea y propone el fix concreto; cero hallazgos genéricos.
**Entornos:** Claude Code = `gh pr diff` / `git diff` reales. claude.ai = diff pegado o fetch del
PR público.

## 3. Notion — Self-Updating Wiki

**Objetivo:** convertir la actividad del proyecto en documentación siempre al día.
**Workflow:** leer el estado real (README, estructura, commits recientes) → generar/actualizar
páginas: overview, arquitectura, setup, changelog → si hay MCP de Notion, escribir directo; si no,
entregar markdown listo para pegar.
**Gate:** la doc refleja el código actual (spot-check: 3 afirmaciones de la doc verificadas contra
el repo).
**Entornos:** ambos; en claude.ai usar el conector Notion si está habilitado.

## 4. Playwright — QA Engineer

**Objetivo:** construir y correr tests de browser automatizados.
**Workflow:** identificar flujos críticos → escribir specs (playwright test, selectores robustos
por rol/testid, no por CSS frágil) → correr la suite → reportar pass/fail con traces.
**Gate:** salida real de `npx playwright test` pegada; si el entorno no tiene browser, entregar la
suite + config + comando exacto, marcado PARCIAL.
**Entornos:** Claude Code = ejecución real. claude.ai = generar suite standalone verificada en
sintaxis (node --check) + instrucciones.

## 5. Figma — Design-to-Code

**Objetivo:** convertir diseños en código frontend fiel.
**Workflow:** obtener el diseño (MCP Figma, export PNG, o descripción) → extraer tokens (colores,
tipografía, espaciado) → generar componentes (React/HTML según stack del proyecto) → renderizar y
comparar contra el diseño.
**Gate:** el componente compila/renderiza y el usuario (o captura) confirma fidelidad visual.
**Entornos:** claude.ai puede renderizar como artifact; Claude Code integra al repo real.

## 6. Supabase — Weekend SaaS

**Objetivo:** app funcional con database, auth y storage en tiempo récord.
**Workflow:** modelar schema (tablas, RLS policies) → auth (email/OAuth) → CRUD tipado → storage si
aplica → seeds de prueba → smoke test end-to-end.
**Gate:** signup + login + un CRUD completo probados contra la instancia (o contra Supabase local);
RLS verificada con un usuario sin permisos.
**Entornos:** requiere credenciales del usuario — pedirlas como variables de entorno, nunca
hardcodear.

## 7. Excel/CSV — Data Analyst

**Objetivo:** analizar datos y automatizar tareas de planilla.
**Workflow:** leer el archivo (openpyxl/pandas) → perfilar (tipos, nulos, duplicados, outliers) →
análisis pedido → output con formato consistente (respetar convenciones de formato del usuario si
las tiene definidas en otro skill).
**Gate:** re-abrir el archivo generado programáticamente y auditar: totales cuadran contra la
fuente, sin celdas rotas, formato aplicado.
**Entornos:** ambos (sandbox bash con Python).

## 8. Chrome — Web Automation

**Objetivo:** automatizar tareas de browser y debuggear sitios.
**Workflow:** definir la tarea (scraping, form-filling, debugging) → script (playwright/puppeteer
headless) → correr → entregar datos/capturas.
**Gate:** datos reales obtenidos o error de red/selector diagnosticado; nunca datos inventados.
**Entornos:** Claude Code o sandbox con headless; claude.ai sin browser = script standalone PARCIAL.
**Nota:** respetar robots.txt y términos del sitio; no automatizar login de terceros sin permiso.

## 9. Docker — DevOps Sidekick

**Objetivo:** containerizar y troubleshootear workflows.
**Workflow:** Dockerfile multi-stage mínimo → .dockerignore → compose si hay servicios → build →
diagnóstico de errores por capa.
**Gate:** `docker build` verde (o hadolint + análisis estático si no hay daemon, marcado PARCIAL).
**Entornos:** Claude Code con Docker = real; sandbox sin daemon = lint + dry-run.

## 10. Postgres/SQL — SQL Whisperer

**Objetivo:** explorar esquemas y generar queries correctas.
**Workflow:** mapear esquema (information_schema, FKs, índices) → entender la pregunta de negocio →
query con joins correctos y filtros obligatorios → EXPLAIN si performance importa.
**Gate:** query ejecutada contra la DB, o validada 100% contra el esquema real (columnas
existentes, joins por FK) si no hay conexión.
**Deferencia:** si el usuario tiene skills propios de SQL/joins/EDA, esos mandan; este módulo es el
genérico.

## 11. Slack — Team Assistant

**Objetivo:** soporte de coding dentro de las conversaciones del equipo.
**Workflow:** leer el hilo (MCP/Zapier o pegado) → responder la duda técnica con código verificado
→ resumir decisiones → formatear para Slack (bloques de código, threads).
**Gate:** el código sugerido corre en sandbox antes de enviarse; el resumen no inventa decisiones
que no están en el hilo.
**Entornos:** claude.ai con conector Slack/Zapier; Claude Code con MCP.

## 12. Vercel — Idea-to-Live-Site

**Objetivo:** de idea a sitio deployado con mínimo setup.
**Workflow:** generar la app (framework según pedido; default estático/Next) → build local →
deploy (MCP Vercel o CLI) → verificar URL viva.
**Gate:** build log verde + fetch de la URL de deploy devuelve 200. Sin deploy real = PARCIAL con
comandos exactos.
**Entornos:** claude.ai tiene MCP de Vercel (deploy directo); Claude Code usa `vercel` CLI.

## 13. Jupyter — Research Partner

**Objetivo:** analizar datos y testear ideas en notebooks.
**Workflow:** notebook con narrativa (markdown entre celdas) → datos → análisis/experimento →
conclusiones honestas (incluyendo resultados negativos).
**Gate:** `jupyter nbconvert --execute` corre el notebook end-to-end sin errores.
**Entornos:** ambos (sandbox tiene Python; instalar jupyter si falta).

## 14. AWS — Cloud Architect

**Objetivo:** diseñar y gestionar infraestructura cloud.
**Workflow:** requisitos (tráfico, presupuesto, compliance) → diagrama de arquitectura → IaC
(Terraform/CDK/CloudFormation) → estimación de costos → plan de deploy por etapas.
**Gate:** el IaC valida (`terraform validate`/`cdk synth`); costos estimados con números, no "barato".
**Entornos:** sin credenciales AWS = diseño + IaC validado localmente, marcado PARCIAL para apply.
**Seguridad:** jamás pedir/almacenar keys en texto plano; siempre roles/variables de entorno.

## 15. Terminal — 10x Developer

**Objetivo:** controlar flujos de desarrollo con lenguaje natural.
**Workflow:** traducir el pedido a comandos/scripts (bash/make/task runners) → correr en sandbox →
encadenar (build, test, lint, release) → dejar el flujo como script reusable en el repo.
**Gate:** script corrido con exit code 0 y salida pegada; comandos destructivos (rm -rf, force
push, drop) requieren confirmación explícita previa.
**Entornos:** ambos.
**Frontera con el módulo 18:** Terminal deja el flujo como script que se corre a mano; cuando el
pedido es que corra solo en cada push/PR, pasa al módulo 18 (el script de Terminal es el comando
que el job de CI invoca, así local y CI corren lo mismo).

## 16. Contenido Viral / Short-Form — Content Strategist

**Objetivo:** convertir una idea en un guion de video short-form *construido sobre las mecánicas que
correlacionan con viralidad* — no "a ver si pega", sino con cada palanca de retención auditada. El
formato ya es el dominante (Shorts ~200B vistas/día; TikTok ~95 min/usuario/día; Reels el mayor
reach). La distribución la decide cómo el algoritmo lee la **retención**, y la retención se juega en
los primeros ~3 segundos.

**Tesis (no negociable):** completion rate > largo. Un video de 45s con 70% de completación gana a
uno de 15s con 40%. La *intro retention* (% que pasa los 3s) es la señal madre; apuntar a 60-70%+.

**Workflow (5 palancas = las 5 letras de VIRAL):**
1. **Hook (0-3s, ~10-14 palabras habladas / primer frame visual).** Rotar 5-10 fórmulas probadas:
   Claim Contrario, Aviso de Error, Teaser de Lista, Open Loop, Identity Call, Confesión, Resultado
   Primero, Pregunta Directa, POV/Relatable. La especificidad es la palanca ("si sos analista de
   cobranzas y tu modelo scorea mal..." gana a "si trabajás en datos..."). Texto en pantalla para
   engancharlos con el sonido apagado.
2. **Retención/estructura.** Hook → valor en beats con *pattern interrupt* (corte cada ~2-3s, nuevo
   visual/dato), cero aire muerto, payoff adelantado, open loop sostenido hasta el final.
3. **Loop/Rewatch + Save.** Final que loopea al inicio o premia el re-watch; contenido "guardá esto"
   (numerado) dispara saves — señal fuerte, sobre todo en Reels.
4. **CTA.** Una sola acción explícita (seguir/comentar/guardar). En Shorts el CTA de suscripción
   puede ir dentro del hook.
5. **Distribución.** Audio en tendencia (descubrimiento en TikTok/Reels) + audio original para marca;
   Shorts se indexa por keyword → SEO en título/primera línea; el caption mueve el save rate en Reels.

**Fit por plataforma (no repostear igual en las tres):**
- **TikTok:** completion rate crudo + session depth + tendencias. Cadencia 3-5/sem.
- **Reels:** contenido original y prolijo + audio en tendencia + save rate + mayor reach (~30%). 4-7/sem.
- **Shorts:** SEO/keyword + funnel al long-form + CTA de suscripción en el hook + mayor engagement medio. 3-5/sem.
- **LinkedIn:** reach orgánico inusualmente alto para B2B, todavía temprano. 2-3/sem (útil para marca personal).
- **Cadencia:** consistencia > ráfagas. Primeros ~30 días casi a diario para que el algoritmo aprenda
  el nicho; después, el sweet spot de cada plataforma.

**Output (el entregable):** guion segundo a segundo — [0-3s: hook + texto en pantalla] · [cuerpo:
beats con cortes] · [cierre: loop + CTA] — más caption + hashtags + sugerencia de audio + nota de
primer frame/thumbnail. Vertical 9:16 desde la grabación.

**Gate — Score VIRAL 0-100 (auditar ANTES de entregar):**

| Letra | Palanca | Puntos | Qué se mide |
|---|---|---|---|
| **V** | Volada (Hook) | 0-30 | Hook ≤3s y ≤14 palabras, fórmula probada, primer frame/texto que frena el scroll |
| **I** | Inmersión (Retención) | 0-25 | Pattern interrupt ≤3s, cero aire muerto, open loop, payoff adelantado |
| **R** | Repetición (Loop+Save) | 0-15 | Final que loopea/premia rewatch; valor "guardable" |
| **A** | Acción (CTA) | 0-15 | Un solo CTA explícito, bien ubicado por plataforma |
| **L** | Lanzamiento (Distribución) | 0-15 | Audio, 9:16, caption/SEO en primera línea, fit por plataforma, plan de cadencia |

Semáforo: **Verde ≥85** (listo para grabar) · **Amarillo 70-84** (ajustar hook/estructura) ·
**Rojo <70** (rehacer). No se entrega por debajo de 85 sin decir explícitamente qué palanca falla y
por qué. Engancha con `output-qa-validator` si está.

**Honestidad (regla cero aplicada):** el score mide *adherencia a las mecánicas* que correlacionan con
virales, NO garantiza que el video explote. La viralidad es probabilística: el gate garantiza que el
video está bien construido, no el resultado. Prohibido prometer "esto se va a hacer viral".

**Entornos:** chat = guion + scorecard como artifact/markdown. Claude Code = lo mismo, integrable a un
repo/calendario de contenido.
**Deferencia (clave):** si el contenido es para las líneas de marca del usuario (marca personal,
producto, canal educativo), el skill de **generación de contenido de marca** manda para el batch; si la
pregunta es de *playbook de crecimiento / UGC 0→1000 usuarios*, manda el skill de **UGC/growth**. Este
módulo es el estratega *genérico por-video* + el scoring VIRAL; nunca pisa a esos especialistas.

---

## Combos frecuentes (pipelines pre-armados)

| Pedido | Pipeline | Gates encadenados |
|---|---|---|
| "MVP completo y online" | 6 Supabase → 5 Figma → 4 Playwright → 12 Vercel | CRUD ok → render ok → tests verdes → URL 200 |
| "Ordenar un repo heredado" | 15 Terminal → 2 GitHub → 9 Docker → 3 Notion | Build ok → review emitida → imagen ok → doc verificada |
| "Análisis reproducible" | 7 Excel → 13 Jupyter → 1 Obsidian | Números cuadran → notebook corre → nota linkeada |
| "Infra desde cero" | 14 AWS → 9 Docker → 12 Vercel/deploy → 3 Notion | IaC valida → build ok → 200 → doc al día |
| "Repo con CI/CD de punta a punta" | 15 Terminal → 4 Playwright → 18 CI/CD → 12 Vercel o 9 Docker → 3 Notion | Script local exit 0 → tests verdes → actionlint + cicd_check verdes → smoke 200 / imagen publicada → doc del pipeline al día |
| "Video que sí retiene" | 16 Contenido Viral → 7 Excel/13 Jupyter → 1 Obsidian | Score VIRAL ≥85 → calendario/tracking de retención → swipe file de hooks linkeado |

## 17. Proyecciones ML — Data Scientist honesto

**Objetivo:** que el número que se reporta a negocio sea el que se va a cumplir, no el que salió de
la ventana donde se eligió el modelo. Aplica a series de tiempo, scoring y cualquier target con
orden temporal.

**Workflow (4 chequeos, en orden):**

1. **Doble ventana.** Partir en TRAIN / SELECCIÓN / HOLDOUT CIEGO. Se elige modelo, hiperparámetros,
   pool, calibración y umbrales en SELECCIÓN; se mide UNA vez en HOLDOUT. Reportar ambos y la
   brecha: si es grande, la elección no generaliza y estás midiendo tu propia búsqueda.
2. **Combinar vs elegir.** Comparar en el holdout dos políticas: (A) campeón por serie, (B) promedio
   de un pool fijo. Con historia corta (menos de ~40 puntos) o quiebre de régimen, B suele ganar.
   El pool se arma por **estructura**, no por métrica: flujos → métodos de nivel con ventana corta;
   stocks → métodos de tendencia (los de nivel rezagan un stock).
3. **Auditoría de leakage.** Bloquear por REGLA toda columna que caiga en la ventana objetivo, y por
   EVIDENCIA toda feature con AUC univariada > 0,95. Pero **un AUC alto no prueba leakage**: si la
   validación es estructuralmente limpia y el AUC sigue alto, el problema es fácil. Verificar antes
   de acusar.
4. **Sesgo del monto.** Si se entrena sobre `log(y)`, al invertir con `exp()` se subestima 20-50%
   (Jensen). Corregir con smearing de Duan y luego con calibración de escala medida SOLO en los
   períodos de entrenamiento.

**Gate:** la métrica reportada sale de un tramo que no se usó para elegir nada, y se muestra junto
a la brecha selección→holdout y al skill score vs naive. Un solo número sin contexto no pasa.

**Scripts:** `scripts/backtest_doble_ventana.py` (panel de series: pool, doble ventana, skill score,
umbrales por percentiles del error) y `scripts/walkforward_origen.py` (scoring: un modelo por
período de origen, features solo de períodos anteriores, smearing + escala). Ambos con `--demo`.

**Detalle:** `references/proyecciones-validacion.md`, `proyecciones-calibracion.md`,
`proyecciones-diagnostico.md`.

**Entornos:** ambos. En claude.ai los scripts corren en el sandbox; con datasets grandes, submuestrear.

**Deferencia:** si el usuario tiene `ml-proyecciones-honestas`, `ml-validation-pipeline` o un skill
de forecasting propio instalado, ese skill manda y este módulo actúa solo como complemento.

**Antes de prometer precisión:** verificar skill score vs naive (si es ≤0 y el error es alto, la
serie es NO PROYECTABLE y hay que decirlo), el piso de ruido (si la volatilidad período a período es
10%, un error de 8-9% es el techo físico) y si hubo quiebre de régimen.

---

## 18. CI/CD — Release Engineer

**Objetivo:** que cada push y cada PR se validen solos, y que llegar a producción sea un proceso
repetible, auditable y reversible, sin pasos manuales. **CI/CD no reemplaza las pruebas ni las
buenas prácticas: las automatiza y las integra al flujo.** Si el repo no tiene tests, este módulo
lo dice primero y arma al menos un smoke test (con el módulo 4 si hay UI).

**Workflow (6 pasos, en orden):**

1. **Detectar stack y plataforma.** `package.json` → Node; `requirements.txt`/`pyproject.toml` →
   Python; `DESCRIPTION`/`renv.lock`/`app.R` → R/Shiny; `Dockerfile` → imagen. Plataforma por
   defecto GitHub Actions; si el repo usa GitLab CI o Azure DevOps, traducir la misma estructura
   (stages lint → test → build → deploy) a su sintaxis.
2. **Local primero.** Identificar (o crear con el módulo 15) los comandos exactos de lint, test y
   build, y correrlos local con exit 0. Lo que falla local va a fallar en CI: no se escribe YAML
   sobre comandos que no corren.
3. **CI** (`.github/workflows/ci.yml`, partir de `assets/cicd/ci-python.yml`, `ci-node.yml` o
   `ci-r.yml`): triggers `push` a main + `pull_request`; jobs lint → test → build encadenados con
   `needs`; `permissions: contents: read`; `concurrency` con `cancel-in-progress`; cache de
   dependencias; matriz de versiones solo si el proyecto la necesita.
4. **Gate de merge.** Branch protection de `main` con los checks del CI como requeridos y PR
   obligatorio. Se configura en Settings → Branches (o `gh api repos/OWNER/REPO/branches/main/protection`);
   sin permisos de admin queda como instrucción exacta, marcado PARCIAL.
5. **CD** (`.github/workflows/cd.yml`, partir de `cd-vercel.yml` o `cd-docker-ghcr.yml`): corre
   solo si el CI terminó verde en main (`workflow_run` + `conclusion == 'success'`) o con un tag
   `vX.Y.Z`; checkout del SHA exacto que pasó el CI; `environment: production` con aprobación
   manual si hay riesgo; secretos solo vía `secrets.*`; **smoke test** post-deploy (HTTP 200);
   **rollback** automático si el smoke falla (`vercel rollback`) o redeploy del tag anterior
   (imágenes versionadas por semver y SHA).
6. **Documentar** en el README: qué corre en cada evento, secretos requeridos, cómo hacer rollback.

**Gate (las tres, en orden):**
- (a) `actionlint` sobre todos los workflows sin errores.
- (b) `python scripts/cicd_check.py .github/workflows` en VERDE (exit 0): sin secretos en texto
  plano, sin tests con `continue-on-error`, sin `write-all`, actions con versión fija, sin
  inyección de `github.event.*` en `run`, sin `pull_request_target` que haga checkout del PR, sin
  deploy desde PR ni sin gate de CI, y con paso de tests.
- (c) Comandos de cada job corridos local con exit 0 y salida pegada, más un **control negativo**
  (romper un test a propósito → el paso de tests tiene que dar exit ≠ 0).
Completo = además un run remoto verde con link (`gh run watch` / pestaña Actions). Sin run remoto
(sin repo, sin push o sin secretos cargados) = **PARCIAL** con los comandos exactos para cerrarlo.

**Plantillas:** `assets/cicd/` — `ci-python.yml`, `ci-node.yml`, `ci-r.yml`, `cd-vercel.yml`,
`cd-docker-ghcr.yml`. Todas pasan actionlint y `cicd_check.py`. Son punto de partida: ajustar
versiones, rutas y comandos al proyecto, y volver a correr el gate.

**Seguridad (no negociable):** jamás pegar tokens en el YAML ni en el chat; para máxima
seguridad fijar actions de terceros por SHA completo; `pull_request_target` solo sin checkout del
código del PR; acciones destructivas (borrar environments, force push, desactivar branch
protection) solo con confirmación explícita.

**Entornos:** Claude Code = git, `gh` y push reales; se puede ver el run en vivo. claude.ai =
genera los workflows, corre actionlint + `cicd_check.py` + comandos locales en el sandbox; el push
y el run remoto quedan PARCIAL (o vía conector de GitHub si está habilitado). Deploys directos a
Vercel pueden verificarse con el conector de Vercel.

**Deferencia:** si el usuario tiene un skill propio de despliegue o de validación pre-entrega
(checklists de deploy, standalone), ese skill manda en su parte; este módulo arma y valida el
pipeline genérico.
