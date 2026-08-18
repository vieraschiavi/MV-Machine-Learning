# MV AutoML Studio

**De cualquier dataset a un modelo validado, sin escribir código.**

Traés un Excel, un CSV o una consulta contra tu servidor SQL; la plataforma
perfila los datos, propone y ejecuta el ETL, entrena y compara modelos para la
variable objetivo que le digas en tus palabras, y devuelve el informe en Excel.
Interfaz en **español, inglés y portugués**, con lectura en voz alta de los
resultados.

---

## Arranque

```bash
git clone https://github.com/vieraschiavi/mv-machine-learning.git
cd mv-machine-learning
./scripts/run.sh            # Windows: scripts\run.bat
```

Se abre en `http://127.0.0.1:8000`. La primera corrida crea el entorno virtual e
instala las dependencias; las siguientes arrancan en segundos.

Manual, si preferís controlar el entorno:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --port 8000
```

Requiere Python 3.11 o superior. No hace falta Node ni compilar nada: la
interfaz son módulos ES nativos.

---

## Qué hace

### 1. Datos, sin límite de tamaño

* **Archivos**: CSV, TXT, TSV, Excel (`xlsx`, `xlsm`, `xls`, `ods`), Parquet y
  JSON. **No hay tope de filas ni de megas**: el archivo se sube por streaming,
  se convierte a Parquet por bloques y se consulta con DuckDB fuera de memoria.
  El límite es el disco, no la RAM.
* **Servidores SQL**: SQL Server, PostgreSQL, MySQL/MariaDB, SQLite, DuckDB y
  cualquier otro motor vía URL de SQLAlchemy (Oracle, Snowflake, BigQuery,
  Redshift…). Explorás esquemas y tablas, escribís el `SELECT`, ves la vista
  previa y extraés. **El conector es de sólo lectura**: cualquier sentencia que
  escriba se rechaza antes de salir.
* El encoding, el separador y el símbolo decimal se detectan solos, y se
  detectan bien: un archivo con montos `$ 1.711,20` no se parte por la coma.

### 2. ETL automático, explicado y auditable

La plataforma analiza el dataset real y **propone un plan**, paso por paso, con
el motivo de cada uno:

* columnas constantes, identificadores y columnas casi vacías (un monto
  entero único **no** es un identificador: la clave es entera *y densa*);
* texto que en realidad es numérico (`$ 1.234,56` → `1234.56`, con la convención
  decimal deducida de la forma de los valores);
* texto que en realidad es fecha, del que se derivan año, mes, día, día de
  semana y semana;
* faltantes: imputación con marca de qué valor faltaba;
* categorías raras agrupadas, filas duplicadas, valores atípicos;
* **auditoría de fuga de información**: columnas que contienen la respuesta se
  bloquean *antes* de entrenar, no después de ver un AUC sospechoso.

Nada se ejecuta hasta que lo aprobás. Podés desactivar cualquier paso. El plan
se compila a **una sola sentencia SQL que la interfaz te muestra**.

### 2 bis. Texto libre como feature

Una columna de observaciones o comentarios se detecta sola, se vectoriza con
TF-IDF + SVD **ajustado únicamente sobre la ventana de entrenamiento**, y sus
componentes compiten junto a las variables numéricas y categóricas del mismo
modelo. El ETL la declara y la protege. A diferencia de dashAI, el texto no es
una tarea aparte: convive con el resto de la tabla.

### 2 ter. Workspaces aislados con catálogo SQLite

Cada workspace separa datasets, modelos, conexiones, exportaciones e historial
de trabajos; se cambia desde la barra superior y viaja en cada request
(`X-Workspace`). Un catálogo **SQLite** por workspace indexa los artefactos y
persiste el historial de trabajos entre reinicios; si se pierde, se
reconstruye solo desde el disco.

### 3. Decís qué querés predecir, en tus palabras

Escribís *"si el cliente va a pagar en los próximos 30 días"* y la plataforma
identifica la columna objetivo, detecta si el problema es de clasificación
binaria, multiclase o regresión, y te muestra cómo se relaciona cada variable
con el objetivo. Funciona **con o sin IA configurada**: sin clave usa una
heurística propia que entiende los tres idiomas.

### 4. AutoML con validación honesta

Compiten **15 familias registradas** — LightGBM, XGBoost, CatBoost,
HistGradientBoosting, Random Forest, Extra Trees, Gradient Boosting clásico,
AdaBoost, árbol de decisión, lineal, Elastic Net, SGD, KNN, MLP y Naive
Bayes — con búsqueda de hiperparámetros (Optuna) sujeta a un presupuesto de
tiempo que fijás vos. El catálogo es **extensible al estilo de dashAI**:
cada familia es un archivo en `backend/app/core/zoo/` y agregar un modelo no
toca el motor; toda familia registrada hereda el protocolo de validación, la
calibración y la comparación contra la combinación. Además:

* **depuración automática de features**, aceptada sólo si no empeora la métrica;
* **calibración isotónica**, aplicada sólo si mejora el error de calibración;
* **combinación vs mejor individual**, comparados y reportados los dos;
* **regresión sesgada**: se modela en logaritmo con corrección de smearing de
  Duan, para que el total predicho cierre contra el total real.

El protocolo es de tres ventanas:

```
ENTRENAMIENTO → ajusta      SELECCIÓN → elige      HOLDOUT CIEGO → reporta
```

El holdout no participa de ninguna decisión. **El número que se reporta es el del
holdout**, porque reportar la ventana con la que se eligió el modelo siempre da
mejor de lo que el modelo realmente es. La diferencia entre las dos se muestra
como *degradación*, y si es grande la plataforma lo dice.

Con una columna temporal declarada, las tres ventanas son consecutivas en el
tiempo: nunca se entrena con el futuro para predecir el pasado.

### 5. Resultados que se pueden leer

Métricas con su explicación en lenguaje llano, comparativa de todos los modelos,
concentración por decil, lift, captura acumulada, curva ROC, curva de
calibración, matriz de confusión, real contra predicho, residuos. Y el análisis
de variables por tres vías: importancia nativa, **caída de la métrica al
permutar sobre el holdout** y SHAP con la dirección del efecto.

### 6. Motor de IA a elección

ChatGPT (OpenAI), Claude (Anthropic), Grok (xAI), Gemini (Google), Copilot
(GitHub Models) o cualquier servicio compatible con OpenAI (Azure, OpenRouter,
Ollama, LM Studio). Para cada uno:

* **Actualizar** trae el catálogo real de modelos desde el proveedor;
* elegís el modelo de la lista;
* **Verificar** hace una llamada de verdad y confirma clave, modelo y red.

La clave se guarda sólo en tu equipo, con permisos restringidos, y nunca vuelve
al navegador. **La IA es opcional**: sin ninguna clave, el ETL, el AutoML y la
exportación funcionan completos; sólo se pierde la interpretación en lenguaje
natural.

### 7. Exportación

* **Excel corporativo** de ocho hojas: Resumen Ejecutivo, Comparativa de
  Modelos, Análisis de Variables, Diagnóstico Holdout, Calidad de Datos,
  Análisis Estadístico, Plan de ETL y Datos.
* **CSV** con separador, decimal y codificación configurables.
* **Parquet** para volúmenes grandes.

CSV y Parquet no tienen tope de filas. En Excel, si el listado supera el millón
de filas se parte en hojas sucesivas y la plataforma lo advierte.

### 8. Tres idiomas y sistema de audio

Español, inglés y portugués, con los tres diccionarios verificados por una
prueba automatizada para que ninguno se desincronice. El audio incluye lectura
en voz alta de los resultados con la voz del idioma activo, señales sonoras de
la interfaz y dictado por voz para escribir el objetivo. Todo se sintetiza en el
navegador: no hay servicio externo ni archivos de sonido.

### 9. Dashboards automáticos

Para cualquier dataset (archivo o SQL) la plataforma detecta sola las métricas,
dimensiones y columna de tiempo, arma KPIs con variación contra el período
anterior, gráficos interactivos (línea temporal, barras por dimensión,
histogramas) y una tabla, todo con **filtros** por rango de fechas y por
categoría. Si el dataset tiene predicciones del modelo (`prob_*`,
`prediccion`), se suman como métricas. El tablero completo, ya filtrado, se
exporta a **Excel** (una hoja por gráfico más los datos) o **CSV**. Los filtros
se compilan a SQL parametrizado: no hay inyección posible.

### 10. Preguntas en lenguaje natural

Un espacio de NLP para preguntarle al dataset en tus palabras («¿cuánto se
cobró por sucursal en 2025?»). Con un proveedor de IA configurado, la pregunta
se traduce a SQL de sólo lectura, **se ejecuta de verdad** sobre DuckDB y la
respuesta se narra a partir del resultado real — nunca de memoria del modelo.
Sin IA hay un traductor local que resuelve las preguntas frecuentes
(agregaciones, «por» dimensión, filtros de año, top N). La respuesta muestra el
SQL usado, las filas y se puede escuchar en voz alta.

### 11. Versiones: demo, profesional y owner

Licencias firmadas con **Ed25519**: el binario sólo trae la clave pública, los
tokens se emiten con la privada (secreto del repositorio, nunca en el código).

| | Demo | Profesional | Owner |
|---|---|---|---|
| Filas por dataset | 50.000 | sin límite | sin límite |
| Conectores SQL / IA / texto libre | — | sí | sí |
| Familias de modelos | 3 | todas | todas |
| Diagnóstico y emisión de licencias | — | — | sí |

La demo no degrada números: los resultados son reales, con marca de agua en el
Excel. Activar una licencia convierte la demo en profesional sin reinstalar.

### 12. Instalador de escritorio (Windows)

`desktop/` empaqueta el motor con **Electron + PyInstaller**: un instalador
NSIS que **permite elegir la carpeta de instalación** (no fuerza `C:`), crea
íconos en el escritorio y el menú de inicio, y corre todo local con un token de
sesión entre la ventana y el backend. El workflow
`.github/workflows/desktop.yml` compila en Windows real, corre una prueba de
humo sobre el `.exe` congelado (subida, entrenamiento, AUC verificado) y
publica dos instaladores: la **demo** como release público y la versión
**owner** como *draft* que sólo ven los colaboradores del repositorio. Con los
secretos `MV_LICENSE_PRIVATE_KEY` / `MV_LICENSE_PUBLIC_KEY` las licencias son
estables entre builds; sin ellos se genera un par efímero y el workflow lo
advierte.

### 13. Web de venta

`web/` es el sitio estático de venta que se publica en Vercel, en **castellano,
portugués e inglés**, con el mismo sistema de diseño que el sitio de MV Kobra
AI. Tiene la sección de video con grabaciones del programa real (`web/video/`),
el producto, el método de validación, los planes con interruptor **mensual /
anual** (Demo US$0 · Profesional US$39/mes · Empresa US$129/mes, con
equivalencia en pesos uruguayos), la descarga del instalador y las preguntas
frecuentes.

El despliegue va por git: `vercel.json` en la raíz apunta a `web/` como
directorio de salida, así que cada push a `main` publica el sitio. Los dos
valores a completar cuando estén disponibles son `mercadoPagoMensual` y
`mercadoPagoAnual` del bloque `CONFIG` de `web/index.html`: hasta que tengan el
link de cobro, el botón de compra abre un correo con el plan y el ciclo
elegidos en el idioma activo.

---

## Estructura

```
backend/app/
  main.py            aplicación FastAPI y servido de la interfaz
  config.py          rutas y límites, configurables por entorno
  api/               datasets, connections, etl, automl, ai, exports, jobs,
                     dashboards, licenses, workspaces
  core/              storage, profiling, etl, features, automl, explain,
                     metrics, registry, connectors, exporter, ai, jobs,
                     dashboards, ask, licensing, security, zoo/
  tests/             193 pruebas
frontend/
  index.html         una página, sin build
  assets/css/        sistema de diseño con tema claro y oscuro
  assets/js/         módulos ES: i18n, api, audio, ui, charts, store, vistas
  assets/i18n/       es.json · en.json · pt.json
docs/
  ARQUITECTURA.md    cómo está armado y por qué
  MODELOS_ADJUNTOS.md qué se tomó de los motores ProbPago y V50
scripts/
  run.sh · run.bat   arranque con instalación automática
desktop/
  electron/          ventana, arranque del backend, token de sesión
  backend_entry.py   entrada PyInstaller · mv-backend.spec
  electron-builder.yml  instalador NSIS con elección de carpeta e íconos
web/
  index.html         sitio de venta en tres idiomas (Vercel)
  video/             grabaciones del programa real
```

---

## Pruebas

```bash
pip install pytest
pytest                       # 193 pruebas
ruff check backend           # lint
```

La suite cubre ingesta y detección de formato, perfilado, ETL y auditoría de
fuga, métricas, AutoML en los tres tipos de tarea, registro y scoring,
conectores SQL, proveedores de IA, exportación, la API completa de extremo a
extremo y la consistencia de los tres idiomas. No sale a internet en ningún
momento.

Hay además una prueba de humo en navegador real
(`node scripts/browser-smoke.cjs`, con el servidor levantado) que recorre las
nueve vistas en los tres idiomas verificando que no haya errores de consola. No
corre en CI a propósito: depende del entorno, y una prueba así vuelve rojo el
pipeline por motivos que no son del código.

---

## Documentación

* [Arquitectura](docs/ARQUITECTURA.md) — cómo está armado, por qué no hay
  límite de tamaño y qué hace cada módulo.
* [Modelos adjuntos](docs/MODELOS_ADJUNTOS.md) — qué se tomó de los motores
  ProbPago v12/v13 y MV AutoML V50, qué no, y por qué.
* [dashAI](docs/DASHAI.md) — qué se tomó de su código real (registro de
  componentes, catálogo sklearn, texto) y qué se hizo distinto a propósito.
* [`examples/`](examples/README.md) — datasets sintéticos listos para recorrer
  la plataforma, incluida una columna de texto libre y un panel de cobranzas
  con fuga contable para que la auditoría trabaje.
