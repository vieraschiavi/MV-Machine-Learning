# Calibración de montos — corregir el sesgo de predecir en log

Leer cuando el modelo ordena bien pero el monto agregado no cierra, o cuando el desvío
real-vs-predicho es sistemático (siempre del mismo signo).

## Por qué aparece el sesgo

Entrenar sobre `log1p(y)` es habitual (el monto es asimétrico y de cola larga). El problema es
la vuelta: `expm1(pred_log)` estima la **mediana** condicional, no la media. Por Jensen:

```
exp(E[log Y])  <  E[Y]
```

El resultado subestima siempre. Magnitud típica: 20% a 50%. No se corrige con más árboles ni
con más features: es un sesgo de la transformación.

## Corrección 1 — Smearing de Duan (1983)

```python
ylog  = np.log1p(np.clip(y, 0, None))
reg.fit(X, ylog)
resid = ylog - reg.predict(X)
smear = float(np.mean(np.exp(resid)))      # típicamente 1,15 - 1,30
pred  = np.expm1(reg.predict(X_new)).clip(0) * smear
```

No asume normalidad de los residuos, a diferencia de la corrección `exp(sigma²/2)`.

## Corrección 2 — Calibración de escala agregada

El smearing corrige el sesgo de la transformación, no el sesgo de nivel del modelo. Para eso:

```python
# medido SOLO en los períodos de entrenamiento, nunca en el objetivo
escala = suma(real_en_entrenamiento) / suma(predicho_en_entrenamiento)
escala = np.clip(escala, 0.5, 3.0)         # cota de seguridad
pred_final = pred * escala
```

El clip evita que un período de entrenamiento anómalo dispare el factor. Si la escala se va
sistemáticamente fuera de [0.7, 1.4], el problema es el modelo, no la calibración.

## Verificación

Reportar ambos factores junto con el desvío por período:

```
período | smearing | escala | real | predicho | desvío %
```

Criterio: desvío por período dentro de ±20%, y desvío medio cerca de 0. Si el desvío medio es
cercano a 0 pero los individuales son grandes y de signo alternado, el sesgo está corregido y
lo que queda es varianza — eso es lo esperable.

## Dónde NO aplicarlo

- Si el modelo predice directamente en la escala original (sin log), no hace falta smearing.
- Si el objetivo es la mediana condicional (no la media), `expm1` sin corregir es lo correcto.
- Nunca calibrar la escala contra el período que se está prediciendo: eso es leakage.
