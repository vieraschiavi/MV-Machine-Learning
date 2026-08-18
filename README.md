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

* columnas constantes, identificadores y columnas casi vacías;
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

### 3. Decís qué querés predecir, en tus palabras

Escribís *"si el cliente va a pagar en los próximos 30 días"* y la plataforma
identifica la columna objetivo, detecta si el problema es de clasificación
binaria, multiclase o regresión, y te muestra cómo se relaciona cada variable
con el objetivo. Funciona **con o sin IA configurada**: sin clave usa una
heurística propia que entiende los tres idiomas.

### 4. AutoML con validación honesta

Compiten LightGBM, XGBoost, CatBoost, HistGradientBoosting, Random Forest,
Extra Trees y modelos lineales, con búsqueda de hiperparámetros (Optuna) sujeta
a un presupuesto de tiempo que fijás vos. Además:

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

---

## Estructura

```
backend/app/
  main.py            aplicación FastAPI y servido de la interfaz
  config.py          rutas y límites, configurables por entorno
  api/               datasets, connections, etl, automl, ai, exports, jobs
  core/              storage, profiling, etl, features, automl, explain,
                     metrics, registry, connectors, exporter, ai, jobs
  tests/             132 pruebas
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
```

---

## Pruebas

```bash
pip install pytest
pytest                       # 132 pruebas
ruff check backend           # lint
```

La suite cubre ingesta y detección de formato, perfilado, ETL y auditoría de
fuga, métricas, AutoML en los tres tipos de tarea, registro y scoring,
conectores SQL, proveedores de IA, exportación, la API completa de extremo a
extremo y la consistencia de los tres idiomas. No sale a internet en ningún
momento.

Hay además una prueba de humo en navegador real
(`node scripts/browser-smoke.cjs`, con el servidor levantado) que recorre las
ocho vistas en los tres idiomas verificando que no haya errores de consola. No
corre en CI a propósito: depende del entorno, y una prueba así vuelve rojo el
pipeline por motivos que no son del código.

---

## Documentación

* [Arquitectura](docs/ARQUITECTURA.md) — cómo está armado, por qué no hay
  límite de tamaño y qué hace cada módulo.
* [Modelos adjuntos](docs/MODELOS_ADJUNTOS.md) — qué se tomó de los motores
  ProbPago v12/v13 y MV AutoML V50, qué no, y por qué.
