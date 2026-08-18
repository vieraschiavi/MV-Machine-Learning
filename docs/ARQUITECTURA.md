# Arquitectura

## Panorama

```
navegador  ──HTTP/SSE──▶  FastAPI  ──▶  motores  ──▶  Parquet en disco
(sin build)                (un proceso)     │
                                            ├── DuckDB      consultas fuera de memoria
                                            ├── scikit-learn / LightGBM / XGBoost / CatBoost
                                            ├── SQLAlchemy  cualquier servidor SQL
                                            └── httpx       proveedores de IA
```

Un solo proceso sirve la API y la interfaz. No hay base de datos de aplicación,
ni cola de mensajes, ni build de frontend: se clona, se corre `scripts/run.sh` y
funciona.

## Por qué no hay límite de tamaño

Tres decisiones encadenadas:

1. **La subida no pasa por memoria.** El navegador manda el archivo como cuerpo
   crudo y el servidor lo escribe a disco a medida que llega
   (`POST /api/datasets/upload-stream`). No hay `read()` del archivo entero.
2. **La conversión es por bloques.** CSV con `chunksize`, Excel con el parser
   SAX de openpyxl en modo `read_only`, SQL con cursor del lado del servidor.
   Cada bloque se escribe como un Parquet independiente.
3. **Las consultas no cargan nada.** Perfilado, calidad, ETL y exportación se
   resuelven como SQL sobre DuckDB apuntando al Parquet. El perfil de 200 filas
   y el de 200 millones usan el mismo código y la misma RAM.

El único paso que necesita los datos en memoria es el entrenamiento. Ahí sí se
muestrea, de forma reproducible, hasta `MV_MAX_TRAIN_ROWS` filas (400.000 por
omisión) y la interfaz avisa cuántas filas se usaron sobre cuántas hay.

## Módulos del backend

| Archivo | Responsabilidad |
|---|---|
| `core/storage.py` | Ingesta sin límite, detección de encoding/separador/decimal, almacén Parquet, consultas DuckDB |
| `core/profiling.py` | Perfil por columna, calidad de datos, correlaciones, análisis del objetivo, inferencia del tipo de tarea |
| `core/etl.py` | Propuesta del plan, detección de tipos reales, auditoría de fuga, compilación a SQL, ejecución |
| `core/features.py` | Codificación dual: matriz de árboles (ordinal, admite nulos) y matriz lineal (one-hot, imputada, escalada) |
| `core/automl.py` | Partición en tres ventanas, catálogo de modelos, optimización con Optuna, calibración, combinación, veredicto |
| `core/explain.py` | Importancia nativa, permutación sobre el holdout y SHAP con dirección del efecto |
| `core/metrics.py` | Métricas con dirección, formato y explicación en lenguaje llano |
| `core/registry.py` | Guardado de modelos, ficha, predicción puntual y scoring por bloques |
| `core/connectors.py` | SQL Server, PostgreSQL, MySQL, SQLite, DuckDB y URL libre de SQLAlchemy; sólo lectura |
| `core/exporter.py` | Excel corporativo, CSV y Parquet |
| `core/ai.py` | Cinco proveedores de IA: catálogo de modelos, verificación y asistencias |
| `core/jobs.py` | Trabajos en segundo plano con progreso observable por SSE |

## El protocolo de validación

```
   ENTRENAMIENTO          SELECCIÓN            HOLDOUT CIEGO
   ───────────────        ─────────────        ───────────────
   ajusta los modelos     elige:               no se toca
                          · hiperparámetros    ninguna decisión
                          · features           lo mira.
                          · calibración        Es el único
                          · campeón            número que se
                                               reporta.
```

Si se declara una columna temporal, las tres ventanas son consecutivas en el
tiempo. La diferencia entre selección y holdout se muestra como **degradación**:
cuando es grande, el modelo se ajustó a la ventana con la que se lo eligió y la
interfaz lo dice en vez de esconderlo.

## El plan de ETL se compila a SQL

Cada paso del plan es una transformación declarativa (`cast_numeric`,
`impute_numeric`, `group_rare`, `expand_datetime`…). Al ejecutar, todos los
pasos habilitados se compilan a **una sola sentencia SQL** que la interfaz
muestra tal cual. Eso hace el ETL auditable —se ve exactamente qué corrió—,
reproducible —el mismo plan da el mismo resultado— y escalable —lo ejecuta
DuckDB, no Python fila por fila.

## Frontend sin build

ES modules nativos, sin empaquetador ni dependencias de CDN. Los gráficos son
SVG escritos a mano (`charts.js`) para que la página funcione en una máquina sin
internet. Los textos salen de tres JSON con exactamente las mismas claves; una
prueba automatizada falla si alguno se desincroniza.

## Variables de entorno

| Variable | Por omisión | Para qué |
|---|---|---|
| `MV_HOST` / `MV_PORT` | `127.0.0.1` / `8000` | Dónde escucha |
| `MV_DATA_DIR` | `./data` | Raíz del workspace |
| `MV_CHUNK_ROWS` | `200000` | Filas por bloque de ingesta |
| `MV_MAX_TRAIN_ROWS` | `400000` | Tope de filas en memoria para entrenar |
| `MV_AI_TIMEOUT` | `45` | Segundos de espera a un proveedor de IA |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY`, `GITHUB_TOKEN` | — | Claves alternativas a cargarlas por pantalla |
