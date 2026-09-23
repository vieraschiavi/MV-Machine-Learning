# Diagnóstico de series — ¿esto se puede proyectar?

Leer ANTES de prometer precisión, y cuando el error no baje por más que se pruebe.

## 1. Skill score vs naive

```python
skill = (1 - wmape_modelo / wmape_naive) * 100
```

- `skill > 20`  → el modelo aporta valor real
- `0 < skill ≤ 20` → aporta poco; evaluar si compensa la complejidad
- `skill ≤ 0`  → **NO PROYECTABLE**. Usar el método más conservador y decirlo.

Clasificación sugerida por error: ALTA ≤ 8%, MEDIA ≤ 15%, BAJA ≤ 30%, NO PROYECTABLE > 30%.

## 2. Piso de ruido irreducible

```python
vol = serie.pct_change().std() * 100
```

Si la volatilidad período a período es del 10%, un error del 8-9% ya está en el piso. Ningún
modelo baja de ahí sin variables externas (gestión, campañas, dotación, calendario). Comunicarlo
antes de que lo pregunten, no después de fallar.

## 3. Quiebre de régimen

```python
mitad = len(serie) // 2
vol_1 = serie[:mitad].pct_change().std() * 100
vol_2 = serie[mitad:].pct_change().std() * 100
nivel_1, nivel_2 = serie[:mitad].mean(), serie[mitad:].mean()
```

Si la volatilidad se duplica o el nivel cambia mucho, la historia larga miente:

- Acortar la ventana de entrenamiento (los métodos de nivel corto pasan a ganar).
- Preferir combinación sobre selección — la selección es especialmente frágil tras un quiebre.
- Documentar el quiebre en el output. Un error alto tras un quiebre no es culpa del modelo,
  pero hay que explicar por qué.

## 4. Segmentar o no segmentar

Un modelo por segmento **rara vez** gana contra un modelo global que recibe el segmento como
feature: los árboles ya capturan la interacción. Condiciones mínimas para que la segmentación
valga:

- ≥ 2.000 filas y ≥ 200 eventos positivos por segmento
- heterogeneidad real de la relación X→y entre segmentos
- y sobre todo: que **gane en el holdout**, no en la ventana de selección

Probar global y segmentado en el mismo holdout, y aceptar la segmentación solo si supera un
umbral de mejora explícito. Si no lo supera, el global gana por simplicidad.

## 5. Coherencia jerárquica

Si hay total y desagregado, reconciliar para que cierren:

```python
total_conciliado = 0.5 * suma_hijos + 0.5 * total_directo   # MinTrace simplificado
factor = total_conciliado / suma_hijos
hijos  = hijos * factor                                      # cierre exacto
```

Verificar en el output que la suma del desagregado iguale al total con desvío 0,000%.
