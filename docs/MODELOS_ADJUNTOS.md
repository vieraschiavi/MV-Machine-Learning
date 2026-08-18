# Qué se tomó de los cinco scripts adjuntos

Los archivos `ProbPago_v12_AutoML.py`, `probpago_core.py`,
`ProbPago_v13_WalkForward.py`, `proyeccion.py` y `run_v50.py` son motores de
producción atados a un dataset concreto (la cartera de CASH S.A., con columnas
`Pago_M1..M12`, `Monto_M1..M12`, `Estado`, `SubEstado`, `ScoreCash`). No se
pueden ejecutar sobre "cualquier dataset", que es lo que pide esta plataforma.

Lo que sí es reutilizable —y es lo valioso— son las **decisiones metodológicas**
que esos scripts documentan en sus propios comentarios. Cada una se generalizó y
quedó incorporada al motor. Esta tabla dice qué se tomó, de dónde y adónde fue.

| Del script adjunto | Qué resuelve | Dónde vive ahora |
|---|---|---|
| `probpago_core.auditar_leakage` — bloquea columnas por regla y por evidencia (AUC univariada > 0,95) **antes** de entrenar | Un AUC de 0,97 en una cartera de cobranzas es la firma de una columna que contiene la respuesta | `backend/app/core/etl.py::audit_leakage` — generalizado a los tres tipos de tarea (AUC para binaria, η² para regresión, V de Cramér para categóricas) y a nombres derivados del objetivo. Se ejecuta como paso del ETL y bloquea la columna antes de modelar |
| `ProbPago_v12` — **validación de doble ventana**: una ventana elige el modelo, otra ciega reporta el número que va a gerencia | La ventana con la que se elige el modelo siempre se ve mejor de lo que el modelo es | `backend/app/core/automl.py::split_indices` y `train` — partición en tres: entrenamiento, selección y holdout ciego. La brecha entre selección y holdout se informa como "degradación" en pantalla y en el Excel |
| `run_v50` — **combinar en vez de coronar un campeón**, con la evidencia de que elegir el mejor por serie daba 3,98 % en selección y 11,67 % en holdout, mientras que combinar daba 5,49 % y 8,71 % | Con historia corta o quiebre de régimen, el ganador de un semestre no es el del siguiente | `backend/app/core/automl.py` — se arma el promedio de los tres mejores y **se lo compara contra el mejor individual en el holdout**. No se asume que combinar gana: se mide y se reporta cuál sostuvo mejor |
| `ProbPago_v13.fit_regresor_monto` — **corrección de smearing de Duan (1983)** sobre la regresión en logaritmo | `exp(E[log Y])` subestima `E[Y]` por la desigualdad de Jensen; sin el factor, el monto predicho queda 20-30 % por debajo del real | `backend/app/core/automl.py::TargetTransform` — se activa sola cuando el objetivo es positivo y sesgado (asimetría > 1,5), y el factor se muestra en el informe |
| `ProbPago_v13.escala_agregada` — factor real/predicho medido **sólo en los meses de entrenamiento**, nunca en el mes que se predice | Corrige el sesgo del total agregado sin introducir fuga | El diagnóstico de regresión reporta `total real vs total predicho` y el desvío porcentual sobre el holdout; el sesgo agregado (`bias`) es una métrica de primer nivel con semáforo a ±5 % |
| `ProbPago_v13.features_origen` — features construidas **sólo con meses anteriores** al que se predice | Entrenar con el futuro para predecir el pasado infla todas las métricas | `backend/app/core/automl.py` — al declarar una columna temporal, las tres ventanas son consecutivas en el tiempo (walk-forward). El ETL además deriva año, mes, día y semana de cualquier fecha |
| `ProbPago_v13` — calibración isotónica sobre la ventana de validación | Una probabilidad que no se puede leer como probabilidad no sirve para decidir | `backend/app/core/automl.py` — se ajusta isotónica en la ventana de selección **y se aplica sólo si mejora el ECE**, medido |
| `ProbPago_v12/v13` — Excel corporativo: encabezados `#1E3A8A`, semáforos verde/ámbar/rojo, montos con separador de miles, hoja de resumen ejecutivo + backtest + listado | Es el formato aprobado y conocido por el negocio | `backend/app/core/exporter.py` — mismo formato y misma paleta, con ocho hojas: Resumen Ejecutivo, Comparativa de Modelos, Análisis de Variables, Diagnóstico Holdout, Calidad de Datos, Análisis Estadístico, Plan de ETL y Datos |
| `ProbPago_v13` — escritura del listado por filas (`ws.append`) en vez de celda por celda | Con 245.000 filas, celda por celda agota la memoria del proceso | `exporter.py` usa `xlsxwriter` en modo *constant memory*: las filas van a disco a medida que se generan |
| `ProbPago_v12.metricas_clf` — AUC, PR-AUC, KS, Brier, ECE, precisión, recall al **umbral que reproduce la tasa base** (no 0,5) | Con 25 % de positivos, el umbral 0,5 no dice nada | `backend/app/core/metrics.py` — el umbral por defecto es el cuantil que reproduce la tasa base observada |
| `run_v50` — reconciliación jerárquica y pools por tipo de métrica (flujo vs stock) | Específico de proyección de series agregadas por estado | **No se incorporó.** Depende de una jerarquía de negocio (Total → Estado → Tipo de cliente) que no existe en un dataset arbitrario. Queda como candidato para un módulo de series de tiempo |
| `proyeccion.py` — orquestador de dos pasos para no sostener tres modelos en RAM | El problema de memoria era del script, no del método | Resuelto por diseño: el entrenamiento corre como trabajo en segundo plano con progreso observable, y el scoring se aplica por bloques |

## Lo que no se copió, y por qué

* **El anclaje temporal `M1=mar-2026 … M12=abr-2025`** y la exclusión del mes
  parcial son propios de ese dataset. La plataforma no puede adivinar que la
  columna 12 de un CSV cualquiera es un mes incompleto. Lo que sí hace es
  detectar y reportar columnas anómalas en el perfil de calidad.
* **Las bandas de acción** (`URGENTE`, `ARREGLO S/QUITA`, `ARREGLO C/QUITA`,
  `NO PRIORIZAR`) son reglas de negocio de cobranzas. La plataforma entrega la
  probabilidad calibrada y la concentración por decil, que es la materia prima
  con la que esas bandas se arman.
* **El horizonte 60/90/180 días** vía `1-(1-p)^ratio` supone un objetivo de
  "al menos un evento en la ventana". No generaliza a regresión ni a multiclase.

## Conclusión

Los scripts sirven, pero no como código: sirven como **especificación de un
protocolo de validación honesto**, y eso es exactamente lo que se implementó.
El aporte concreto de los cinco archivos a este proyecto es la disciplina de
doble ventana, la auditoría de fuga previa al entrenamiento, la corrección de
smearing y el formato de salida aprobado.
