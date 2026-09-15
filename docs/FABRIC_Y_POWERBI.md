# MV AutoML Studio en Microsoft Fabric y Power BI

Guía para usar el programa dentro de una empresa que ya tiene sus datos en
**Microsoft Fabric**, sus tableros en **Power BI** y notebooks de Python
habilitados. Son tres caminos independientes: se puede usar uno solo.

| Camino | Qué hace | Quién lo usa |
|---|---|---|
| **A. Notebook de Fabric** | Entrena sobre una tabla del Lakehouse desde una celda de Python | quien ya trabaja en notebooks |
| **B. Programa de escritorio conectado a Fabric** | Lee una tabla por el endpoint SQL y entrena con la interfaz de siempre | quien no escribe código |
| **C. Salida para Power BI** | Deja predicciones, métricas e importancias en archivos que el informe lee directo | el tablero |

Los tres corren el **mismo motor**, con el mismo protocolo: entrenamiento,
selección y **holdout ciego**. El número que se reporta sale siempre de la
ventana que no se usó para decidir nada.

---

## A. Entrenar desde un notebook de Fabric

### A.1 Dejar el programa en el Lakehouse

Copiá la carpeta `backend` del programa a `Files/mv-automl/backend` del
Lakehouse. Se sube desde el panel de Fabric (Lakehouse → Files → Upload folder)
o desde una celda:

```python
notebookutils.fs.cp("abfss://.../Files/origen/backend",
                    "abfss://.../Files/mv-automl/backend", recurse=True)
```

No hay que instalar nada más: el motor usa pandas, NumPy y scikit-learn, que ya
vienen en el runtime de Fabric. Si el entorno tiene además `lightgbm`,
`xgboost`, `catboost`, `optuna` o `shap`, el motor los aprovecha; si no están,
entrena igual con lo que hay y lo dice en el informe.

### A.2 Las cuatro líneas que importan

```python
import sys; sys.path.append("/lakehouse/default/Files/mv-automl/backend")
from app import notebook as mv

datos = spark.sql("SELECT * FROM ventas_clientes").toPandas()
modelo = mv.entrenar(datos, objetivo="compro", excluir=["cliente_id"])
print(modelo.resumen()["veredicto"])
```

`entrenar` acepta un DataFrame de **Spark** (el de Fabric), de pandas, de Polars
o una tabla de PyArrow: los convierte solo.

Parámetros que conviene conocer:

| Parámetro | Para qué |
|---|---|
| `objetivo` | la columna a predecir (obligatorio) |
| `excluir` | identificadores y columnas que no predicen nada |
| `tiempo` | columna de fecha: parte las tres ventanas **en orden temporal** |
| `presupuesto_segundos` | cuánto puede optimizar |
| `max_modelos` | cuántas familias compiten |
| `progreso=True` | imprime el avance en la celda |

**Sobre `tiempo`:** si la tabla tiene fecha y el modelo va a usarse hacia
adelante, declarala. Sin eso las ventanas se reparten al azar, el modelo entrena
con filas del futuro y todas las métricas salen infladas de una forma que no se
puede reproducir en producción.

### A.3 Leer el resultado

```python
modelo.resumen()          # diccionario: modelo, métrica, holdout, brecha, veredicto
modelo.tabla_modelos()    # leaderboard: qué midió cada familia
modelo.importancias(n=10) # qué variables lo sostienen, medido sobre el holdout
modelo.metricas()         # todas las métricas, formato largo
```

La **brecha** (`brecha` en el resumen) es la diferencia entre la ventana de
selección y el holdout. Grande significa que el modelo se ajustó a la ventana
con la que se lo eligió y no sostiene la performance fuera de ella.

### A.4 Guardar y volver a usar

```python
modelo.guardar("/lakehouse/default/Files/mv/modelo_compras")

# mañana, sin reentrenar:
modelo = mv.cargar("/lakehouse/default/Files/mv/modelo_compras")
predicciones = modelo.predecir(nuevos, conservar=["cliente_id"])
```

Se escribe en rutas **montadas** (`/lakehouse/default/Files/...`), no en URLs
`abfss://`. Si el destino está en otro workspace: escribí en la ruta montada y
copiá después con `notebookutils.fs.cp`. El programa avisa con ese mismo texto si
se le pasa una `abfss://`.

### A.5 Notebook listo para importar

`examples/fabric/mv_automl_en_fabric.ipynb` hace todo el recorrido: leer, entrenar,
leer el resultado, guardar y dejar la salida para Power BI. Corre tal cual en
Fabric y también fuera de Fabric —si no encuentra el Lakehouse arma una tabla de
ejemplo y escribe en una carpeta local—, así se prueba el circuito completo antes
de tocar un dato de la empresa.

### A.6 Dejarlo programado

El entrenamiento se decide; el scoring se repite. En una *pipeline* de Fabric
conviene programar sólo la segunda parte:

```python
modelo = mv.cargar("/lakehouse/default/Files/mv/modelo_compras")
hoy = spark.sql("SELECT * FROM ventas_clientes_hoy").toPandas()
modelo.para_powerbi("/lakehouse/default/Files/mv/powerbi", datos=hoy,
                    conservar=["cliente_id"])
```

---

## B. Conectar el programa de escritorio al endpoint SQL de Fabric

Para quien no escribe código: el programa se conecta a Fabric como a cualquier
otro servidor SQL, y de ahí en más es la interfaz de siempre.

### B.1 Qué hace falta

1. **El endpoint SQL.** En Fabric, dentro del Lakehouse o el Warehouse:
   *Configuración → Cadena de conexión del endpoint de análisis SQL*. Es un
   nombre tipo `abcdefg.datawarehouse.fabric.microsoft.com`.
2. **El driver ODBC de Microsoft** instalado en el equipo:
   «ODBC Driver 18 for SQL Server». Es gratis y lo publica Microsoft. Sin él, el
   programa avisa exactamente eso.
3. **Permiso de lectura en Fabric** sobre ese Lakehouse o Warehouse. Alcanza con
   lectura: el conector no escribe (ver B.4).

### B.2 Cargar la conexión

En la pestaña **Datos → Servidor SQL**, elegí el motor
**«Microsoft Fabric (endpoint SQL)»** y completá:

| Campo | Qué va |
|---|---|
| Endpoint SQL de Fabric | `abcdefg.datawarehouse.fabric.microsoft.com` |
| Lakehouse o Warehouse | el nombre del ítem en Fabric |
| ID de aplicación o correo | ver abajo |
| Secreto de la aplicación | ver abajo |

Fabric **no acepta usuario y contraseña de base de datos**: la identidad la da
Entra ID (el ex Azure AD). Hay dos caminos y el programa elige solo según lo que
se cargue:

* **Con tu propio usuario** (dejá el secreto vacío): poné tu correo de la
  organización. Se abre la ventana de Microsoft, admite doble factor. Es el modo
  para trabajar a mano desde el escritorio.
* **Con una aplicación registrada** (ID de aplicación + secreto): es el modo
  desatendido, el que sirve para algo programado. Lo crea el área de sistemas en
  *Microsoft Entra ID → Registros de aplicaciones*, y después hay que darle
  permiso de lectura sobre el ítem de Fabric. En el tenant además tiene que estar
  habilitado el acceso de entidades de servicio a las APIs de Fabric.

### B.3 Probar y extraer

**Probar conexión** responde en milisegundos si la identidad y los permisos están
bien. Después, **Explorar tablas** lista lo que hay, y la consulta se escribe en
SQL normal. La extracción trae los datos por bloques: una tabla grande no tiene
que entrar en memoria.

### B.4 El conector es de sólo lectura, y eso está controlado

La consulta tiene que **ser** una lectura: empezar con `SELECT` o con un `WITH`
que termine en `SELECT`. Cualquier otra cosa se rechaza antes de tocar el
servidor. No es una lista de verbos prohibidos —esas listas siempre se quedan
cortas— sino al revés: lo que no es una lectura, no pasa.

### B.5 Lo que todavía no se probó

El armado de la conexión, el modo de autenticación, el dialecto de las consultas
y el rechazo de escrituras están probados automáticamente
(`backend/tests/test_conector_fabric.py`). **Contra un tenant real de Fabric no
se probó**: en este entorno no hay uno. El primer intento contra el Fabric de la
empresa es el que confirma permisos, red y versión del driver.

---

## C. Que Power BI muestre el resultado

Una llamada deja cuatro tablas en la carpeta que se le indique:

```python
modelo.para_powerbi("/lakehouse/default/Files/mv/powerbi",
                    datos=datos, conservar=["cliente_id", "zona"])
```

| Archivo | Una fila por | Para qué sirve |
|---|---|---|
| `predicciones.parquet` | caso | la lista priorizada: probabilidad por cliente |
| `metricas.parquet` | métrica y ventana | comparar selección contra holdout en un visual |
| `importancias.parquet` | variable | qué sostiene al modelo, medido sobre el holdout |
| `resumen.parquet` | modelo | la tarjeta del tablero: métrica, brecha y veredicto |

En Power BI Desktop: **Obtener datos → OneLake / Lakehouse**, se elige la carpeta
y se cargan los cuatro archivos. Con *Direct Lake* el informe se actualiza solo
la próxima vez que el notebook escriba.

`metricas.parquet` viene en **formato largo** (`metrica · ventana · valor`)
justamente para que un visual salga sin pivotear nada a mano: métrica en el eje,
ventana en la leyenda, y se ve de un golpe si el modelo se sostuvo fuera de la
ventana con la que se lo eligió.

Con `formato="csv"` escribe CSV en vez de Parquet, para un Power BI que lea de
una carpeta común en vez del Lakehouse.

---

## Preguntas que van a aparecer

**¿Esto usa Copilot o los modelos de lenguaje de la empresa?**
No para entrenar. El modelo lo arma el motor de AutoML, que es estadística sobre
los datos de la empresa, no un modelo de lenguaje. El programa tiene aparte una
pestaña de **Motor de IA** que sí llama a un proveedor para redactar y explicar;
acepta OpenAI, Anthropic, Gemini, GitHub Models y cualquier servicio
**compatible con el formato de OpenAI** (ahí entran las pasarelas corporativas y
LiteLLM). Copilot dentro de Microsoft 365 no entrega clave de API, así que ese
camino no aplica; y el formato nativo de Azure OpenAI —con `api-version` en la
URL— **no está probado**.

**El área de IA está armando agentes: ¿se puede llamar al programa desde uno?**
Sí, por dos puertas. La de Python es la de este documento: `mv.entrenar`,
`mv.cargar` y `mv.predecir` son funciones comunes, y un agente que escriba
Python las usa igual que una persona. La otra es la **API HTTP** completa
—subir datos, entrenar, consultar el trabajo, puntuar y exportar—, que se levanta
en modo servidor y se protege con un token
([`docs/modo-servidor.md`](modo-servidor.md)). En los dos casos el agente decide
*qué* pedir; el protocolo de validación no se negocia desde afuera: el número
que devuelve sale siempre del holdout ciego.

**¿Los datos salen de la empresa?**
El entrenamiento no sale a ningún lado: corre donde corre el notebook o el
programa. Lo único que sale es lo que se escriba a mano en la pestaña de IA, y
sólo si se configura una clave.

**¿Se puede usar en la capacidad de Fabric sin instalar nada en las máquinas?**
Sí: el camino A no instala nada en la máquina de nadie. Sólo necesita la carpeta
`backend` en el Lakehouse y un notebook.

**¿Y la licencia?**
Los topes del nivel valen igual desde el notebook: filas por tabla, presupuesto,
familias de modelos y scoring. El notebook no es una puerta de atrás.

---

## Lo que se probó y lo que no

| Pieza | Estado |
|---|---|
| Entrenar desde un DataFrame de pandas, Spark, Polars o PyArrow | probado (`test_notebook_fabric.py`) |
| Guardar, volver a cargar y predecir igual | probado |
| Las cuatro tablas para Power BI, en Parquet y CSV | probado |
| Topes de licencia desde el notebook | probado |
| El notebook de ejemplo, corrido entero | probado (`test_notebook_de_ejemplo.py`) |
| Armado de la conexión a Fabric y modos de Entra ID | probado (`test_conector_fabric.py`) |
| Conexión contra un tenant real de Fabric | **no probado: no hay tenant en el entorno de desarrollo** |
| Carga de las tablas en un Power BI real | **no probado: los archivos sí, el informe no** |
| Formato nativo de Azure OpenAI en la pestaña de IA | **no soportado** |
