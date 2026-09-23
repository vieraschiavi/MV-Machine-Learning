# Protocolo de validación — doble ventana y walk-forward por origen

Leer cuando haya que montar la validación desde cero, o cuando el usuario pregunte si su
backtest es honesto.

## A. Series de tiempo — doble ventana con ventanas expansivas

```
N ventanas de walk-forward (h=1, refit en cada paso)
  primeras N_sel  -> ventana de SELECCIÓN
  últimas N-N_sel -> HOLDOUT CIEGO
```

Regla práctica: `N ≈ 40-50%` del histórico, `N_sel ≈ 2/3 de N`. Con 36 puntos: 18 ventanas,
12 de selección y 6 de holdout.

```python
objetivos = fechas[-n_windows:]
f_sel, f_hold = objetivos[:n_seleccion], objetivos[n_seleccion:]
# en cada objetivo f: el modelo ve SOLO y[fechas < f]
```

Nunca `train_test_split` aleatorio ni `KFold` estratificado sobre datos con orden temporal.

## B. Scoring de entidades — walk-forward por período de origen

Cuando el dataset viene "pivoteado" (una fila por entidad, columnas M1..M12 con el
comportamiento de cada período), el protocolo correcto es **un modelo por período predicho**:

```
para predecir el período Mk:
    features    = SOLO M(k+1) .. M(k+V)     # V = ventana de observación
    entrenamiento = SOLO orígenes j > k     # modelos ajustados con info previa a Mk
```

Ejemplo con V=7 y orígenes disponibles j ∈ {1,2,3,4}:

| Predice | Entrena con | Features |
|---|---|---|
| M3 | j=4 | M5..M11 |
| M2 | j=3,4 | M4..M10 |
| M1 | j=2,3,4 | M3..M9 |
| M0 (futuro) | j=1..4 | M2..M8 |

Ningún dato de Mk ni posterior entra al modelo que predice Mk. Esto hace el leakage
**estructuralmente imposible**, que es más fuerte que auditarlo.

### Anclar los períodos a fechas reales

Antes de reportar nada, verificar a qué mes calendario corresponde cada slot Mk. Si hay una
fuente independiente (un reporte de negocio con los totales mensuales), cruzar los agregados
y confirmar por correlación de forma. Un anclaje mal hecho invalida toda la lectura.

Marcar y **excluir** los períodos parciales: se detectan porque su tasa de evento o su total
cae muy por debajo del resto (p. ej. 13% cuando el resto está en 27%).

## C. Qué se congela y cuándo

| Decisión | Se toma en | Se mide en |
|---|---|---|
| Modelo / pool | SELECCIÓN | HOLDOUT |
| Hiperparámetros | SELECCIÓN | HOLDOUT |
| Calibración (isotónica/Platt) | SELECCIÓN | HOLDOUT |
| Umbral de decisión | SELECCIÓN | HOLDOUT |
| Factor de escala del monto | períodos de ENTRENAMIENTO | período objetivo |

Si una decisión se toma mirando el holdout, el holdout dejó de ser ciego y hay que abrir uno nuevo.
