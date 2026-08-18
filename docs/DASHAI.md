# Qué se tomó de dashAI, y qué se hizo distinto

Se estudió el código real de [DashAISoftware/DashAI](https://github.com/DashAISoftware/dashAI)
(clonado, no la landing). Tres ideas suyas valían la pena; las tres se
incorporaron adaptadas, no copiadas.

## 1. Catálogo de modelos por registro de componentes

dashAI registra cada modelo como una clase con su schema declarativo
(`component_registry`, ~36 wrappers de scikit-learn). Acá quedó como
`backend/app/core/zoo/`: cada familia es un `ModelSpec` en un archivo del
paquete y se autodescubre al importar. **Agregar un modelo es agregar un
archivo; el motor no se toca.**

La diferencia deliberada: en dashAI el spec declara el formulario de la UI;
acá declara el **espacio de búsqueda de Optuna, la prioridad de competencia y
el tope de filas**. Lo que este motor automatiza es la optimización y la
validación de tres ventanas — cualquier familia registrada las hereda gratis.

Familias incorporadas del catálogo de dashAI que faltaban: KNN, MLP, AdaBoost,
Gradient Boosting clásico, árbol de decisión, Elastic Net, SGD y Naive Bayes.
Con las existentes (LightGBM, XGBoost, CatBoost, HistGB, Random Forest, Extra
Trees, lineal) el catálogo queda en **15 familias**, con *gating* por tamaño:
KNN o MLP no entran a competir con 300.000 filas salvo pedido explícito.

## 2. Texto libre

dashAI trae `tfidf_logreg` y BoW como **modelos de texto separados**: o
clasificás tabular o clasificás texto. Acá el texto es **una feature más**:
una columna de observaciones se detecta sola (largo y variedad), se vectoriza
con TF-IDF + SVD truncado dentro del `Preprocessor` — ajustado únicamente
sobre la ventana de entrenamiento — y sus componentes conviven con las
columnas numéricas y categóricas en el mismo modelo. El ETL la declara
(`text_column`) y la protege de los pasos que la destruirían (descarte por
única, agrupado de raras).

## 3. Persistencia y aislamiento

dashAI usa SQLAlchemy + Alembic como base global. Acá la escala pedía menos
maquinaria y más aislamiento: **workspaces** (`X-Workspace`) que separan
datasets, modelos, conexiones, exportaciones e historial, cada uno con un
**catálogo SQLite** (`catalog.db`) que indexa los artefactos y persiste el
historial de trabajos entre reinicios. El filesystem sigue siendo la verdad
(Parquet/joblib/JSON): si el catálogo se pierde, se reconstruye del disco.

## Lo que no se copió

* Los modelos de NLP/traducción/LLM/imagen (46 de sus 76): dependen de
  transformers y GPU; fuera del alcance tabular de esta plataforma. El
  registro extensible deja la puerta abierta.
* El job queue con base de datos: acá los trabajos son hilos con progreso por
  SSE y su historial persiste en SQLite, suficiente para un solo proceso.
* Los schemas de formulario multiidioma por modelo: la UI de esta plataforma
  expone presupuesto y familias, no cada hiperparámetro — la búsqueda es de
  Optuna, no del usuario.
