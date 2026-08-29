# MV AutoML Studio — Gate de producción ECC

> Puntaje bajo la rúbrica de `.claude/skills/ecc/SKILL.md` (ECC v2.2.0,
> skill `production-audit`). **Evidencia ejecutada o no cuenta.**

**Veredicto: 88/100 → 9/10. Sin bloqueantes. Los tres gates del job de CI
corren verdes acá, incluido el chequeo de import que existe porque una suite
verde no prueba que la app arranque.**

## Evidencia ejecutada

| Verificación | Comando | Resultado |
|---|---|---|
| Linter | `ruff check backend` | ✅ `All checks passed!` |
| Suite | `pytest backend/tests -q` | ✅ **348 tests, 0 fallas** |
| La app importa | `import app.main` | ✅ `VERSION: 1.0.0` |
| Health check | `/api/health` | ✅ presente |
| Secretos versionados | `git ls-files \| grep -E '\.env$\|\.pem\|\.keystore'` | ✅ ninguno |

El chequeo de import es el que más vale de los tres: una suite puede estar
entera en verde con la aplicación rota al arrancar, porque los tests importan
módulos sueltos y no el entrypoint. Acá está cubierto.

## Por qué 9 y no 10

Ningún tope duro aplica. Lo que falta:

1. **Warnings ruidosos en la suite.** `test_automl.py` levanta
   `PendingDeprecationWarning` de SHAP (`set_over`/`set_under` se deprecan) y
   dos `RuntimeWarning: invalid value encountered in divide` de numpy. El de
   numpy no es cosmético: una división por desvío estándar cero significa una
   columna constante entrando al cálculo de correlación. Hoy no rompe nada,
   pero es el tipo de `NaN` silencioso que después aparece en una explicación
   SHAP mostrada al cliente. Vale la pena mirarlo.
2. **Sin E2E.** Hay `frontend/` y `web/` y nada recorre la pantalla.
3. **Sin humo post-deploy.** `vercel.json` publica el producto y nada verifica
   que la URL responda después del deploy.

## Arreglos de alto valor

1. Rastrear el `invalid value encountered in divide` de
   `test_shap_nombra_la_categoria_no_el_codigo_interno`: si es una columna
   constante, filtrarla antes del cálculo en vez de dejar que produzca `NaN`.
2. Fijar la versión de SHAP o migrar a `cmap.with_extremes(...)` antes de que
   la deprecación se vuelva error.

## Próxima acción

Antes de cada push: `ruff check backend && pytest backend/tests -q`, y el
chequeo de import.
