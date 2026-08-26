# Datasets de ejemplo

Datos **sintéticos** que replican la estructura de casos reales de cobranzas,
sin ninguna cifra verdadera. Sirven para recorrer la plataforma completa.

| Archivo | Qué ejercita | Objetivo sugerido |
|---|---|---|
| `colocaciones_y_tasas.xlsx` | Serie mensual con el monto escrito como texto con puntos de miles (`391.311.281`): el ETL debe convertirlo sin corromperlo | `Tasa_Pct` (regresión) con `Periodo` como columna temporal |
| `cobranzas_panel.xlsx` | Panel mensual por **tramo de atraso** (`0-30`, `31-60`, …) y tipo de cliente, con 23 columnas; varias son componentes contables del total, así que la **auditoría de fuga** tiene trabajo de verdad | `TotalCobrado` (regresión, objetivo sesgado → smearing) |
| `gestiones_con_texto.csv` | Columna `NotaGestor` de texto libre: se vectoriza con TF-IDF y compite junto a las variables numéricas | `Pago30d` (clasificación binaria) |

`gestiones_con_texto.csv` lo produce [`generar_gestiones.py`](generar_gestiones.py),
que está acá para que se pueda auditar cómo se armó. La señal vive donde
viviría en la realidad: entrenando con el motor real, el AUC del holdout ciego
ronda **0,88** y las variables que más pesan son el contacto efectivo (≈18 %
de caída al permutar), los días de atraso (≈14 %) y las promesas cumplidas
(≈7 %). La nota del gestor entra al modelo como texto vectorizado y **aporta
poco** (≈1 %), que es justamente lo que se quiere mostrar: un texto que dijera
«confirma la transferencia» daría AUC 1,0 y no enseñaría nada, porque sería la
respuesta disfrazada de variable.

El panel lo produce [`generar_panel.py`](generar_panel.py). Está armado sobre
una cartera chica —el mes cierra alrededor de diez millones, no de
cuatrocientos— y agrupado por tramos de atraso en vez de estados internos:
así se lee sin conocer la nomenclatura de ninguna empresa y el gráfico queda
ordenado solo, de `0-30` a `+360`.

## Los mismos datos en inglés y en portugués

[`traducir.py`](traducir.py) escribe `gestiones_con_texto-en.csv`,
`gestiones_con_texto-pt.csv`, `cobranzas_panel-en.xlsx` y
`cobranzas_panel-pt.xlsx`. Existen por los videos del sitio: un KPI se llama
como la columna de la que sale, así que el video en inglés mostraba
`MontoACobrarVencido` mientras la voz hablaba en inglés — media pantalla
traducida no se lee como un producto internacional, se lee como una traducción
a medio hacer.

**Los números no se regeneran**: se toma el archivo en castellano y se le
cambian los nombres de columna, las categorías y las notas del gestor. Los tres
idiomas muestran exactamente las mismas cifras, y los tres videos se pueden
comparar cuadro a cuadro.

Con `cobranzas_panel.xlsx`, probá escribir el objetivo en el cartel:
*"cuánto voy a cobrar en total"* — y mirá qué bloquea y qué marca para revisar
la auditoría antes de entrenar.
