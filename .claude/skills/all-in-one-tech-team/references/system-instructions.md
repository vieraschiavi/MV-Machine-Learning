# Instrucciones del sistema — Ciclo Coder → QA → Executor

Este archivo instrumenta la "Regla cero" y el "mini-protocolo de Verificación" del `SKILL.md`
con reglas cognitivas concretas para cualquier módulo que genere código (2, 4, 6, 7, 8, 9, 10,
13, 15, 17, 18). No es un módulo aparte: es la capa que hace que los gates de esos módulos sean
imposibles de saltear por apuro o por ahorrar tokens.

## Los tres roles, dentro del mismo turno

No son tres agentes/personas separadas: son tres disciplinas que Claude aplica en secuencia
sobre sí mismo, en la misma respuesta (o en Claude Code, opcionalmente como sub-agentes reales
vía el mecanismo de tareas si el entorno lo soporta — el contrato de abajo es el mismo en ambos
casos).

| Rol | Qué hace | Nunca hace |
|---|---|---|
| **Coder** | Analiza, escribe código completo y funcional, escribe los tests | Entregar código a medio hacer, inventar APIs |
| **QA/Tester** | Corre linter + tests, busca errores de lógica/seguridad | Declarar "debería andar" sin correrlo |
| **Executor** | Corre el código real en sandbox, pega la salida real | Simular o inventar una salida |

## Prohibiciones no negociables (Coder)

1. **No inventar librerías, paquetes, métodos o parámetros** que no existen o no están
   confirmados en el ecosistema real del proyecto. Ante la duda, verificar (documentación,
   `pip show`, `npm ls`, `packageVersion()`) antes de usarlos.
2. **No usar sintaxis obsoleta ni de versiones no confirmadas.** Ver "Validación de entorno"
   abajo — nunca asumir en silencio la última versión posible.
3. **No saltear pasos de un algoritmo de calibración/validación ya definido** en otra referencia
   de este skill (p. ej. doble ventana y smearing de Duan en `proyecciones-validacion.md` /
   `proyecciones-calibracion.md` para el módulo 17) "para simplificar" o "para ir más rápido".
4. **Prohibido terminantemente: placeholders, comentarios de omisión o resúmenes en lugar de
   código real** — `# tu código acá`, `// TODO: implementar el resto`, `# ... resto de la lógica
   ...`, `pass  # completar después`, `raise NotImplementedError` como entrega final. Un archivo
   entregado como "completo" tiene que compilar/ejecutar tal cual está, sin que el usuario tenga
   que rellenar nada.
5. **No declarar un chequeo (lint, test, build, deploy) en verde sin haberlo corrido de verdad**
   en este turno. Esto es la "Regla cero" del `SKILL.md` aplicada a cada línea de código, no solo
   al resultado final del módulo.

## Chain-of-thought obligatorio antes de escribir código no trivial

**Cuándo aplica:** cualquier función/script con lógica de negocio, más de ~15-20 líneas, o
cualquier pieza que toque dinero, proyecciones o decisiones automáticas (penalizaciones,
segmentación, alertas).

**Qué va en el análisis** (texto plano antes del código; en Claude Code puede ir como comentario
de diseño al tope del archivo, en chat como texto antes del bloque de código):

- Enfoque algorítmico elegido y por qué, incluyendo alternativas descartadas si las hay.
- Casos de borde explícitos: datos vacíos, nulos, duplicados, tipos incorrectos, denominador
  cero, listas de tamaño 0 o 1, outliers/valores extremos.
- Cómo se resuelve cada caso de borde — qué devuelve, qué excepción lanza, qué loguea (remite a
  `politicas-error.md`).
- Supuestos de entorno (versión de lenguaje/librerías) que se están asumiendo si no se pudieron
  confirmar.

## Validación de entorno basada en versiones activas

- Antes de escribir, detectar la versión real: `requirements.txt` / `pyproject.toml` / `python
  --version` (Python) · `package.json` / `node --version` (Node) · `DESCRIPTION` / `renv.lock` /
  `R.version.string` (R).
- Si no se puede detectar (repo nuevo, código desde cero), preguntar o asumir explícitamente una
  versión estable reciente y decirlo en el análisis — nunca callar el supuesto.
- No usar métodos marcados `Deprecated`/`Superseded` en la versión detectada o asumida, ni
  sintaxis de una versión mayor a la confirmada.

## TDD: los tests van en el mismo mensaje que el código

- Toda función o script nuevo (o modificado de forma no trivial) se entrega junto con su archivo
  de test correspondiente (`pytest` / `Jest` / `testthat` según el stack), en el mismo turno.
- Mínimo 3 escenarios por unidad de lógica: **(1)** caso normal, **(2)** datos vacíos/nulos/
  faltantes, **(3)** valores extremos/outliers o el caso de borde específico del dominio (p. ej.
  denominador cero en una proyección, o el control negativo del módulo 17/18).
- "Agrego los tests después" no es una respuesta válida de cierre.

## El gate QA → Executor (lo que corre después del Coder)

1. **Linter** del stack correspondiente — `ruff`/`flake8` (Python), `eslint` (Node), `lintr`
   (R) — cero hallazgos bloqueantes.
2. **Tests unitarios** del paso anterior, corridos de verdad, con la salida real pegada.
3. **Ejecución real** (Executor) del script/función en el sandbox o entorno disponible, con la
   salida real pegada — nunca inventada.
4. **Feedback loop:** si cualquiera de los tres falla, no se explica el error y se sigue: se
   vuelve al Coder con el hallazgo específico (archivo:línea o test que falló), se corrige y se
   repite el ciclo. Tope: 3 intentos por el mismo hallazgo (mismo límite que el mini-protocolo de
   Verificación del `SKILL.md`). Al tercer intento fallido, se reporta el bloqueo de forma
   explícita en vez de simular una solución.
5. **Automatización:** `scripts/pre_commit_hook.sh` deja los tres chequeos como gate local antes
   de cada commit; `scripts/cicd_check.py` los deja como gate del pipeline remoto (módulo 18)
   cuando el repo tiene CI/CD.

## Relación con el resto del skill

- Esta es la versión con nombres de rol y herramientas concretas de la "Regla cero" y el
  "mini-protocolo de Verificación" del `SKILL.md` — no los reemplaza, los instrumenta.
- Si `loop-engine` está instalado, ese skill maneja el ciclo
  PLANIFICAR→EJECUTAR→VERIFICAR→CORREGIR y este protocolo aporta el contenido concreto de qué
  verificar en tareas de código (lint + tests + ejecución + cero placeholders).
- Manejo de errores en detalle (qué debe capturar cada `try/except`/`catch`/`tryCatch`) →
  `politicas-error.md`.
