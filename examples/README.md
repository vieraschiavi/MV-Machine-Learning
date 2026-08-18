# Datasets de ejemplo

Datos **sintéticos** que replican la estructura de casos reales de cobranzas,
sin ninguna cifra verdadera. Sirven para recorrer la plataforma completa.

| Archivo | Qué ejercita | Objetivo sugerido |
|---|---|---|
| `colocaciones_y_tasas.xlsx` | Serie mensual con el monto escrito como texto con puntos de miles (`391.311.281`): el ETL debe convertirlo sin corromperlo | `Tasa_Pct` (regresión) con `Periodo` como columna temporal |
| `cobranzas_panel.xlsx` | Panel por estado y mes con 23 columnas; varias son componentes contables del total, así que la **auditoría de fuga** tiene trabajo de verdad | `TotalCobrado` (regresión, objetivo sesgado → smearing) |
| `gestiones_con_texto.csv` | Columna `NotaGestor` de texto libre: se vectoriza con TF-IDF y compite junto a las variables numéricas | `Pago30d` (clasificación binaria) |

`gestiones_con_texto.csv` lo produce [`generar_gestiones.py`](generar_gestiones.py),
que está acá para que se pueda auditar cómo se armó. La señal vive donde
viviría en la realidad —atraso, monto, contacto efectivo, historial de
promesas y canal—, y la nota del gestor **aporta sin contener la respuesta**:
entrenando sobre él, el AUC del holdout ciego ronda 0,88, y si se excluye el
texto baja apenas. Un ejemplo cuyo texto dijera «confirma la transferencia»
daría AUC 1,0 y no enseñaría nada: eso es fuga, no una variable.

Con `cobranzas_panel.xlsx`, probá escribir el objetivo en el cartel:
*"cuánto voy a cobrar en total"* — y mirá qué bloquea y qué marca para revisar
la auditoría antes de entrenar.
