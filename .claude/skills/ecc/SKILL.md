---
name: ecc
description: >
  Layer ECC (github.com/affaan-m/ECC v2.2.0) instalado en MV Machine Learning: reglas de estilo, testing,
  seguridad, performance y patrones bajo .claude/rules/ecc/, más las skills de calidad
  (production-audit, security-review, tdd-workflow, e2e-testing, verification-loop,
  deployment-patterns, error-handling, coding-standards, repo-scan). ACTIVAR SIEMPRE que se pida
  "aplicá ECC", "reglas ECC", "auditá producción", "está listo para producción", "listo para
  vender", "puntaje 9/10 o 10/10", "qué rompe en prod", "auditoría de calidad", "gate de release",
  antes de abrir un PR de release, y al arrancar cualquier cambio no trivial en este repo para
  cargar el estándar que aplica al stack (python).
---

# ECC en MV Machine Learning

Layer operativo de [ECC](https://github.com/affaan-m/ECC) (MIT, v2.2.0) vendorizado en este repo.
En este entorno `/plugin` no existe, así que ECC vive como **skill + reglas versionadas**, no como
plug-in del marketplace. Eso lo hace reproducible: viaja con el repo y no depende de la máquina.

## Qué hay instalado

| Ruta | Contenido |
|---|---|
| `.claude/rules/ecc/common/` | Reglas transversales: coding-style, testing, security, performance, patterns, git-workflow, code-review, agents, hooks |
| `.claude/rules/ecc/{python}/` | Reglas del stack de este repo (pisan a las de `common` cuando chocan) |
| `.claude/skills/production-audit/` | Auditoría de listo-para-producción con evidencia local |
| `.claude/skills/security-review/` | Revisión de seguridad línea a línea |
| `.claude/skills/tdd-workflow/`, `e2e-testing/`, `verification-loop/` | Ciclo de test |
| `.claude/skills/deployment-patterns/`, `error-handling/`, `coding-standards/`, `repo-scan/` | Operación y estilo |
| `scripts/ecc-instalar.sh` | Reinstala/actualiza todo lo anterior desde upstream |

Precedencia: **regla de stack > regla común > costumbre del repo**, salvo que `CLAUDE.md` diga lo
contrario — el `CLAUDE.md` de este repo gana siempre, porque conoce el dominio.

## Cuándo leer qué

- Antes de escribir código → `common/coding-style.md` + la del stack.
- Antes de agregar tests → `common/testing.md` + la del stack.
- Antes de tocar auth, pagos, entrada de usuario o secretos → `common/security.md` + skill `security-review`.
- Antes de un PR → `common/code-review.md` y `common/git-workflow.md`.
- Antes de un release o de mostrarle el producto a un cliente → el gate de abajo.

## Gate de producción (el 9/10 o 10/10)

ECC puntúa 0-100. La equivalencia con la escala de 10 que usamos acá:

| ECC | Sobre 10 | Lectura | Qué hacer |
|---|---|---|---|
| 95-100 | **10/10** | Vendible sin asteriscos | Sale |
| 85-94 | **9/10** | Sin bloqueantes conocidos | Sale, con los pendientes anotados |
| 70-84 | 7-8/10 | Sale con salvedades aceptadas por el dueño | No mostrar como producto terminado |
| 50-69 | 5-6/10 | Riesgoso | Solo beta interna |
| 0-49 | ≤4/10 | Bloqueado | No sale |

**Topes duros** (aunque todo lo demás esté impecable):

- Tope 6/10 si falta auth/autorización sobre datos sensibles, si un webhook de pago no es
  idempotente, si una migración no se puede correr con seguridad, o si hay secretos expuestos en
  bundle, logs o archivos commiteados.
- Tope 8/10 si el gate del repo no está verde o si el camino crítico no se probó de punta a punta.

### Procedimiento

1. Correr el gate real del repo y **pegar la salida cruda**, no un resumen:
   ```bash
   ruff check backend
   pytest backend/tests -q
   python -c "import sys; sys.path.insert(0,'backend'); import app.main"
   ```
   CI también valida la sintaxis de todos los módulos y los diccionarios de idioma. El chequeo de import existe porque una suite verde no prueba que la app arranque.
2. Aplicar la skill `production-audit` sobre el checkout actual: superficie de release, cambios
   recientes, límites de runtime/auth/datos/jobs/deploy, CI, migraciones, variables de entorno,
   camino de rollback.
3. Aplicar `security-review` sobre el diff si toca seguridad.
4. Emitir el veredicto en una línea, y después `Bloqueantes` / `Arreglos de alto valor` /
   `Evidencia revisada` / `Evidencia faltante` / `Próxima acción`.

**Nunca** declarar un puntaje sin nombrar la evidencia que lo sostiene. CI en verde no es
listo-para-producción: es una de las entradas del puntaje.

## Actualizar ECC

```bash
./scripts/ecc-instalar.sh          # detecta el stack solo
./scripts/ecc-instalar.sh python  # forzando los stacks de este repo
```

Pisa `.claude/rules/ecc/` entero. No edites esos archivos a mano — si una regla no aplica acá,
anotá la excepción en la sección de abajo.

## Excepciones de este repo

_(vacío por ahora — agregá acá cualquier regla de ECC que este repo decida no seguir, con el
motivo)_
