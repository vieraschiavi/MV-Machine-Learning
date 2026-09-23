# Políticas de manejo de errores — All-in-One Tech Team

Estándar de oro para cómo el código de cualquier módulo (Python/Node/R) captura excepciones. Lo
audita el rol QA de `system-instructions.md`, y en parte lo automatiza
`scripts/pre_commit_hook.sh`.

## Principio general

Distinguir dos clases de error y no tratarlas igual:

- **Error esperable del dominio** (dato faltante, denominador cero, fila mal formada, timeout de
  red, credencial vencida): se captura, se reporta con contexto accionable y — cuando el proceso
  es un batch — se sigue procesando el resto, salvo que el error sea global (no hay conexión a la
  base, falta un archivo de config).
- **Error de programación** (bug real): no se enmascara con un `except` genérico. Se deja
  propagar o se loguea con el traceback completo para poder arreglarlo — nunca se "traga" en
  silencio.

## Regla de oro contra las excepciones no controladas

**Prohibido:** `except:` (bare) en Python, `catch {}` vacío en Node/TS, `tryCatch(..., error =
function(e) NULL)` sin loguear en R. Todo bloque de captura tiene que:

1. Capturar el tipo específico de excepción cuando se puede anticipar (no `Exception` genérica
   salvo en el borde externo del programa).
2. Loguear con contexto suficiente para reproducir: qué input, qué paso del pipeline, timestamp.
3. Decidir explícitamente si sigue, reintenta o aborta — nunca dejarlo implícito.

## Caso concreto: divisiones (proyecciones, ratios, variaciones %)

Toda división del dominio de negocio de este skill (variación % real vs. proyectado,
`%Cobrado_Vencido`, ratio cuotas atrasadas/monto a cobrar, penalty rate, etc.) valida el
denominador **antes** de dividir:

- `denominador == 0` o `None`/`NA`/`NaN` → devolver `None`/`NA` explícito + flag
  `"no_calculable": true`. Nunca `Inf`/`-Inf`/`NaN` silencioso, y nunca un traceback que corte el
  script completo por una sola fila.

```python
import math

def variacion_pct(real, proyectado):
    """Variación % real vs. proyectado. None ('no_calculable') si no se puede dividir."""
    if proyectado in (0, None):
        return None
    if isinstance(proyectado, float) and math.isnan(proyectado):
        return None
    return (real - proyectado) / proyectado * 100
```

## Estándar por lenguaje

### Python

- `try/except <ExcepcionEspecifica>` — nunca `except:` bare.
- Excepciones propias (`class DatosVacioError(ValueError): ...`) cuando el mensaje genérico no
  alcanza para debuggear.
- `logging` (no `print`) para errores y warnings, incluyendo el input que disparó el error.
- Scripts CLI: `sys.exit(code)` con códigos distintos por tipo de falla — `0` ok, `1`
  hallazgos/fallo de negocio, `2` error de uso/argumentos (mismo patrón que `cicd_check.py` de
  este skill).
- `.get(clave, default)` en vez de acceso directo a dict/columna que puede no existir; validar
  índice antes de indexar listas/arrays.

### Node / JS / TS

- `try/catch` con `Error` (o subclases) descriptivas — nunca `catch (e) {}` vacío.
- `async/await` siempre con manejo de rechazo: `try/catch` alrededor del `await`, o `.catch()`
  explícito si se usa la promesa directamente.
- `process.exitCode = N` en vez de `process.exit(N)` abrupto cuando hay streams/conexiones
  pendientes de cerrar.
- Validar `undefined`/`null`/`NaN` antes de operar, en especial en cálculos financieros.

### R / Shiny

- `tryCatch(expr, warning = ..., error = ..., finally = ...)` — nunca silenciar `error` sin
  loguear.
- Conexiones SQL: reusar el patrón de retry/timeout ya definido en el contexto del proyecto;
  nunca dejar una conexión colgada sin `on.exit()`.
- Shiny: `validate(need(...))` para inputs de usuario en vez de dejar que un cálculo con `NULL`
  tire abajo la sesión completa; `shiny::showNotification(type = "error")` para mostrar el error
  sin crashear la app.

## Checklist que corre el QA antes de declarar el código listo

- [ ] ¿Hay algún `except:` bare, `catch {}` vacío o `tryCatch` que trague el error sin loguear?
- [ ] ¿Hay alguna división sin chequeo previo de denominador `0`/`NA`?
- [ ] ¿Hay acceso a índice/clave/columna sin validar que existe?
- [ ] ¿Los mensajes de error incluyen contexto suficiente para reproducir (input, paso,
      timestamp)?
- [ ] En un batch (miles de clientes/filas), ¿un solo registro roto tira abajo todo el proceso, o
      se loguea y se sigue?

Cada ítem con hallazgo se reporta en formato `archivo:línea — qué está mal — fix propuesto`
(mismo formato que el módulo 2, GitHub Autopilot Reviews).

## Automatización

- `scripts/pre_commit_hook.sh` corre linter + tests localmente antes de cada commit. No
  reemplaza este checklist semántico de manejo de errores, que sigue siendo criterio del QA.
- `scripts/cicd_check.py` (módulo 18) es el gate equivalente para el pipeline remoto.
