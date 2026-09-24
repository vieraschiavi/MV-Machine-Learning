/**
 * Contenido de la guía del programa para gerentes y técnicos.
 *
 * Se escribe una sola vez y `generar.js` lo vuelca a Word (.docx) y a HTML, así
 * las dos versiones no se desincronizan. Los números salen de medir el
 * repositorio (pruebas, rutas, familias), no de estimarlos: si cambian, se
 * actualizan acá y se vuelve a generar.
 *
 * Marcas de texto: **negrita** y `código`.
 */
'use strict';

const META = {
  producto: 'MV AutoML Studio',
  titulo: 'MV AutoML Studio',
  bajada: 'De cualquier planilla a un modelo validado, explicado y vigilado. '
    + 'Qué hace, cómo llega a cada usuario y por qué se le puede creer al número.',
  version: 'Versión 1.0 · septiembre de 2026',
  autor: 'Martín Viera',
  archivo: 'MV-AutoML-Studio-Guia',
};

const KPIS = [
  ['615', 'pruebas automáticas en cada cambio'],
  ['15', 'familias de modelos compitiendo'],
  ['0', 'filas de tope: el límite es el disco'],
  ['3', 'idiomas: español, inglés y portugués'],
];

const SECCIONES = [
  {
    id: 'resumen',
    titulo: 'En una página',
    para: 'gerentes',
    bloques: [
      { t: 'lead', x: 'MV AutoML Studio agarra una tabla (un Excel, un CSV, una consulta a SQL Server o a Microsoft Fabric) y devuelve un modelo predictivo validado, explicado y listo para usar, sin escribir código. Lo que en un equipo de datos lleva semanas de ida y vuelta, acá lleva una tarde y queda documentado.' },
      { t: 'p', x: 'En criollo: le decís **«quiero saber qué clientes van a pagar en los próximos 30 días»**, y el programa arma la cancha, pone a competir quince tipos de modelos, se queda con el que mejor juega en un partido que nunca vio y te dice cuánto le podés creer. Y ahora, además, te avisa cuando el modelo se quedó sin piernas y hay que reentrenarlo.' },
      { t: 'h3', x: 'Por qué convence' },
      { t: 'ul', items: [
        '**El número no está inflado.** Se mide sobre un holdout ciego: datos que no participaron de ninguna decisión. Si el modelo se desinfla fuera de la ventana donde se lo eligió, el programa lo dice en voz alta.',
        '**Los datos no se van de casa.** Corre en la PC, en el servidor del cliente o adentro de Fabric. La inteligencia artificial es opcional: sin ninguna clave, el ETL, el AutoML y la exportación andan completos.',
        '**Se enchufa con lo que ya hay:** Excel, SQL Server, Microsoft Fabric, Power BI y Copilot.',
        '**Avisa cuando el modelo se pone viejo.** Nuevo en esta versión: el control de deriva compara los datos de hoy con los del entrenamiento y dice «estable», «vigilar» o «reentrenar».',
        '**Está probado en serio:** 615 pruebas automáticas corren en cada cambio, sin salir a internet.',
      ] },
    ],
  },
  {
    id: 'problema',
    titulo: 'El problema que resuelve',
    para: 'gerentes',
    bloques: [
      { t: 'p', x: 'La mayoría de los modelos que fracasan no fracasan por el algoritmo. Fracasan por tres cosas previsibles, y el programa ataca las tres.' },
      { t: 'table', head: ['Problema', 'Qué pasa en la práctica', 'Qué hace el programa'], ancho: [22, 39, 39], filas: [
        ['**Fuga de información**', 'Una columna trae la respuesta escondida (por ejemplo, la fecha de pago para predecir si paga). El modelo da un 0,99 espectacular y en producción no sirve para nada.', 'Audita la fuga **antes** de entrenar: bloquea esas columnas y explica por qué.'],
        ['**Número optimista**', 'Se informa el resultado de la misma ventana con la que se eligió el modelo. Siempre da mejor de lo que el modelo realmente es.', 'Tres ventanas: una entrena, otra elige y la tercera, ciega, reporta. La diferencia entre las dos últimas se muestra como degradación.'],
        ['**Modelo viejo**', 'Cambian los clientes, el canal o los precios. El modelo sigue largando números con cara de serios, pero ya no valen.', 'Control de deriva (PSI): compara los datos nuevos con la foto de entrenamiento y dice qué se movió y si toca reentrenar.'],
      ] },
    ],
  },
  {
    id: 'recorrido',
    titulo: 'El recorrido, de punta a punta',
    para: 'todos',
    bloques: [
      { t: 'p', x: 'Ocho pasos, en este orden. Nada se ejecuta sin que alguien lo apruebe, y cada paso deja rastro.' },
      { t: 'steps', items: [
        ['Traer los datos', 'Archivos sin tope de tamaño (CSV, Excel, Parquet, JSON), que se suben por bloques y se consultan con DuckDB fuera de memoria. O una consulta de **sólo lectura** a Fabric, SQL Server, PostgreSQL, MySQL, Oracle, Snowflake o BigQuery.'],
        ['Entender la tabla', 'Ingeniería de datos medida, no supuesta: qué identifica una fila, qué huecos tiene el tiempo, qué tabla se cruza con cuál y el contrato de datos con su `CREATE TABLE`.'],
        ['Limpiar con un plan aprobado', 'El programa propone el ETL paso por paso, con el motivo de cada uno. Vos aprobás o desactivás. El plan se compila a una sola sentencia SQL que queda a la vista.'],
        ['Decir el objetivo en tus palabras', '«Si el cliente va a pagar en 30 días». El programa encuentra la columna y detecta si es clasificación o regresión, con o sin IA.'],
        ['Poner a competir los modelos', 'Quince familias (LightGBM, XGBoost, CatBoost, bosques, lineales, redes y más) con búsqueda de hiperparámetros dentro de un presupuesto de tiempo que fijás vos.'],
        ['Leer el resultado', 'Métricas explicadas en llano, deciles, lift, curvas ROC y de calibración, y qué variable pesa y hacia dónde empuja. Se puede pedir la explicación a la IA o escucharla en voz alta.'],
        ['Usarlo', 'Aplicar el modelo a un dataset entero, exportar el Excel corporativo de ocho hojas, CSV o Parquet, o dejar las tablas listas para Power BI.'],
        ['Vigilarlo', 'Con cada tanda de datos nuevos, el control de deriva dice si el modelo sigue midiendo la misma población. Si no, se reentrena.'],
      ] },
      { t: 'p', x: 'Además: **Proyecciones** de series de tiempo, que primero miden con un backtest hacia adelante y recién después proyectan; **tableros automáticos** con filtros; **preguntas en lenguaje natural** que se traducen a SQL y se ejecutan de verdad; y una **bitácora** que explica el pipeline a quien no lo programó.' },
    ],
  },
  {
    id: 'logistica',
    titulo: 'Logística: cómo llega a cada usuario',
    para: 'todos',
    bloques: [
      { t: 'p', x: 'El mismo motor se entrega de cuatro maneras. Se elige según dónde tienen que quedar los datos, no según la comodidad del proveedor.' },
      { t: 'table', head: ['Modalidad', 'Para quién', 'Qué se instala', 'Dónde quedan los datos'], ancho: [20, 27, 29, 24], filas: [
        ['**Escritorio Windows**', 'El analista o el gerente con su PC', 'Un instalador de unos 375 MB que deja elegir la carpeta (no obliga a usar el disco C:) y crea los íconos', 'En la PC'],
        ['**Modo servidor**', 'Proyectos con datos de un cliente que no pueden salir de su infraestructura', 'Nada en la laptop: el programa corre en el servidor del cliente, protegido con token, y se usa desde el navegador', 'En el servidor del cliente'],
        ['**Notebook**', 'Equipos que ya trabajan en Fabric, Jupyter o Databricks', 'Una línea de Python: `from app import notebook as mv`', 'En el Lakehouse'],
        ['**Docker**', 'Áreas de TI que quieren estandarizar', '`docker compose up`', 'En el volumen del contenedor'],
      ] },
      { t: 'h3', x: 'Licencias y venta' },
      { t: 'p', x: 'Las licencias se firman con **Ed25519**: el programa sólo trae la clave pública, así que no se pueden fabricar desde afuera. Activar una licencia convierte la demo en versión completa sin reinstalar. La web de venta, publicada en Vercel en tres idiomas, cobra, emite la licencia y entrega la descarga contra esa licencia.' },
      { t: 'table', head: ['Plan', 'Precio publicado', 'Qué incluye'], ancho: [20, 24, 56], filas: [
        ['**Demo**', 'US$ 0', 'Hasta 50.000 filas por dataset y 3 familias de modelos. Los resultados son reales; el Excel sale con marca de agua.'],
        ['**Profesional**', 'US$ 39 por mes, por equipo', 'Sin tope de filas, las 15 familias, conectores SQL, IA, texto libre, tableros y exportación sin marca de agua.'],
        ['**Empresa**', 'US$ 129 por mes, hasta 5 equipos', 'Todo lo del Profesional, más la puesta en marcha sobre el servidor SQL de la empresa y soporte prioritario. Se cobra en pesos uruguayos por MercadoPago, con factura.'],
      ] },
    ],
  },
  {
    id: 'arquitectura',
    titulo: 'Para técnicos: cómo está armado',
    para: 'tecnicos',
    bloques: [
      { t: 'table', head: ['Capa', 'Tecnología', 'Por qué así'], ancho: [18, 38, 44], filas: [
        ['API', 'FastAPI: 13 routers, 73 rutas, 78 operaciones', 'La interfaz usa la misma API que un agente o un script. Contrato OpenAPI.'],
        ['Datos', 'Parquet por bloques + DuckDB', 'Sin tope de filas: se consulta fuera de memoria. El límite es el disco, no la RAM.'],
        ['Catálogo', 'SQLite por workspace', 'Aísla datasets, modelos y conexiones; el historial sobrevive reinicios y se reconstruye desde el disco.'],
        ['Modelos', 'LightGBM, XGBoost, CatBoost, scikit-learn, Optuna', 'Cada familia es un archivo en `core/zoo/`: sumar una no toca el motor y hereda validación y calibración.'],
        ['Explicación', 'Importancia nativa, permutación sobre el holdout y SHAP', 'Tres vías que se controlan entre sí; la permutación se mide donde el modelo no eligió nada.'],
        ['Interfaz', 'Módulos ES nativos, sin compilar; es, en y pt', 'Nada que buildear. Una prueba exige que los tres idiomas tengan las mismas claves.'],
        ['Escritorio', 'Electron + PyInstaller, instalador NSIS', 'Todo local, con un token de sesión entre la ventana y el backend.'],
        ['Modelo guardado', 'Bundle joblib + ficha JSON', 'Viaja con el preprocesamiento, los calibradores y la foto de deriva.'],
      ] },
      { t: 'h3', x: 'El protocolo de validación' },
      { t: 'ventanas' },
      { t: 'p', x: 'El holdout no participa de ninguna decisión: ni de los hiperparámetros, ni de la calibración, ni de la depuración de variables. Con una columna de fecha declarada, las tres ventanas son consecutivas en el tiempo: nunca se entrena con el futuro para predecir el pasado.' },
      { t: 'ul', items: [
        '**Calibración isotónica**, que se aplica sólo si mejora el error de calibración.',
        '**Depuración de variables**, que se acepta sólo si no empeora la métrica.',
        '**Combinación contra el mejor individual**: se comparan y se informan los dos.',
        '**Regresión sesgada** (montos, deudas): se modela en logaritmo con la corrección de Duan, para que el total predicho cierre contra el total real.',
        '**Texto libre** como variable: TF-IDF + SVD ajustado sólo sobre la ventana de entrenamiento.',
      ] },
      { t: 'h3', x: 'Seguridad' },
      { t: 'ul', items: [
        'El conector SQL es de **sólo lectura por lista blanca**: la consulta tiene que empezar con `SELECT` o con un `WITH` que termine en `SELECT`. Enumerar los verbos prohibidos no alcanzaba: `VACUUM INTO` copiaba la base entera sin ser un `INSERT`.',
        'Los filtros de los tableros se compilan a **SQL parametrizado**.',
        'Las claves de IA se guardan en el equipo con permisos restringidos (`0600`) y **nunca vuelven al navegador**.',
        'La clave privada de licencias vive en los secretos del repositorio y de Vercel, nunca en el código.',
        'La suite de pruebas no sale a internet: anula las claves del entorno antes de arrancar.',
      ] },
    ],
  },
  {
    id: 'microsoft',
    titulo: 'Fabric, Power BI y Copilot',
    para: 'todos',
    bloques: [
      { t: 'p', x: 'Para una empresa que ya vive en Microsoft, el programa no pide mudarse: entra por la puerta que ya está abierta.' },
      { t: 'ul', items: [
        '**Dentro de un notebook de Fabric**, sin levantar ningún servidor ni subir archivos: donde ya hay un DataFrame, hay entrenamiento. Acepta pandas, Spark, Polars y PyArrow.',
        '**Contra el endpoint SQL de Fabric**, con identidad de Entra ID, desde la interfaz del programa.',
        '**Hacia Power BI**: deja en el Lakehouse las tablas de predicciones, métricas, importancias y resumen, y ahora también la de **deriva**, para que el tablero tenga su semáforo de «¿hay que reentrenar?».',
        '**Con Copilot** (GitHub Models) como motor de IA para interpretar y narrar. También ChatGPT, Claude, Grok, Gemini o cualquier servicio compatible con OpenAI, incluidos Azure y Ollama.',
      ] },
      { t: 'code', x: 'from app import notebook as mv\n\ndatos = spark.sql("SELECT * FROM ventas_clientes").toPandas()\nmodelo = mv.entrenar(datos, objetivo="compro", excluir=["cliente_id"])\nprint(modelo.resumen()["veredicto"])\n\nmodelo.para_powerbi("/lakehouse/default/Files/mv/powerbi", datos=datos)\nprint(modelo.deriva(datos_del_mes)["veredicto"]["texto"])' },
      { t: 'callout', tipo: 'warn', titulo: 'Lo que todavía no se probó', x: 'La conexión, la autenticación y el rechazo de escrituras contra Fabric están cubiertos por pruebas automáticas, pero **no contra un tenant real**: en el entorno de desarrollo no hay uno. El primer intento contra el Fabric de la empresa es el que confirma permisos, red y versión del driver. Lo mismo con la carga en un Power BI real: los archivos están probados; el informe armado, no.' },
    ],
  },
  {
    id: 'deriva',
    titulo: 'Lo que le faltaba, y ya tiene: el control de deriva',
    para: 'todos',
    bloques: [
      { t: 'lead', x: 'Un modelo no se rompe con un error: se pone viejo en silencio. Por eso, al revisar el programa entero para esta guía, la pieza que faltaba era la vigilancia después de la entrega. Ya está implementada.' },
      { t: 'p', x: 'Al entrenar, el programa guarda **dentro del modelo** una foto de los datos: cada variable sobre la ventana de entrenamiento y la predicción sobre el holdout. Después, contra cualquier tabla nueva, mide el **PSI** (índice de estabilidad poblacional), el estándar de la industria de riesgo crediticio para esta pregunta.' },
      { t: 'psi' },
      { t: 'ul', items: [
        '**Pesa lo que importa.** Si se mueve una variable que el modelo casi no usa, el veredicto es «vigilar». Si se mueve una de las cinco que lo sostienen, o la predicción misma, es «reentrenar».',
        '**Los vacíos cuentan.** Si una columna que venía completa empieza a llegar con un 40 % vacío, se detecta aunque los valores presentes no cambien.',
        '**Las categorías nuevas se informan** (una sucursal o un canal que no existían).',
        '**Los identificadores no se miden**: un número de factura nuevo no es un cambio de población.',
        '**Con menos de 100 filas no opina**: con tan pocas, el PSI mide ruido.',
      ] },
      { t: 'h3', x: 'Una prueba real, con datos de ejemplo' },
      { t: 'p', x: 'Una cartera sintética de 4.000 préstamos: se entrenó un modelo de mora con los datos de «enero» y se controló contra el mismo mes y contra un «septiembre» donde el atraso creció un 80 % y el canal web pasó del 50 % al 80 %.' },
      { t: 'table', semaforo: 4, head: ['Variable', 'Peso en el modelo', 'PSI enero', 'PSI septiembre', 'Veredicto'], ancho: [22, 20, 18, 20, 20], filas: [
        ['(predicción)', '—', '0,010', '0,509', 'Reentrenar'],
        ['atraso', '58,8 %', '0,002', '0,867', 'Reentrenar'],
        ['canal', '13,8 %', '0,000', '0,360', 'Reentrenar'],
        ['ingreso', '27,5 %', '0,001', '0,001', 'Estable'],
        ['edad', '0,0 %', '0,002', '0,002', 'Estable'],
      ] },
      { t: 'p', x: 'Contra enero, todo estable. Contra septiembre, el programa dijo: *«Reentrenar: cambiaron variables que sostienen el modelo: atraso (PSI 0,87), canal (PSI 0,36); la predicción se corrió (PSI 0,51).»* Señaló exactamente lo que se había cambiado, y nada más.' },
      { t: 'h3', x: 'Dónde está' },
      { t: 'ul', items: [
        'En la pantalla de **Resultados**, el botón **Controlar deriva**: se elige el dataset y aparece el semáforo con la tabla.',
        'En la API: `POST /api/automl/monitor` con el modelo y el dataset.',
        'En el notebook: `modelo.deriva(datos)` y la tabla `deriva` para Power BI.',
      ] },
      { t: 'callout', tipo: 'info', titulo: 'Para los modelos que ya existen', x: 'Los modelos entrenados antes de esta versión no tienen la foto guardada. El programa lo dice con esas palabras y no falla: alcanza con reentrenarlos una vez.' },
    ],
  },
  {
    id: 'calidad',
    titulo: 'Cómo sabemos que anda',
    para: 'tecnicos',
    bloques: [
      { t: 'ul', items: [
        '**615 pruebas automáticas** (pytest): ingesta y formatos, perfilado, ETL y fuga, métricas, AutoML en los tres tipos de tarea, registro y scoring, conectores, proveedores de IA, exportación, la API de punta a punta, el notebook y la consistencia de los tres idiomas.',
        '**Integración continua** en GitHub Actions en cada cambio, con lint (`ruff`). Tarda unos cinco minutos.',
        '**Prueba de humo del instalador**: el workflow de escritorio compila en Windows real y, sobre el `.exe` ya congelado, sube un archivo, entrena y verifica el AUC.',
        '**Prueba en navegador real** que recorre todas las vistas en los tres idiomas buscando errores de consola.',
        'El control de deriva entró con **25 pruebas nuevas** (umbrales, bordes, veredicto, API, notebook, licencia) y una corrida real en Chromium sin errores de consola.',
      ] },
    ],
  },
  {
    id: 'estado',
    titulo: 'Qué está verificado y qué falta',
    para: 'todos',
    bloques: [
      { t: 'table', estado: 1, head: ['Pieza', 'Estado', 'Detalle'], ancho: [30, 18, 52], filas: [
        ['Motor, API, interfaz y notebook', 'Verificado', '615 pruebas en verde con este cambio.'],
        ['Control de deriva', 'Verificado', 'Pruebas automáticas y demo en navegador real.'],
        ['Integración continua', 'Verificado', 'Corre en cada cambio; verde en la rama principal.'],
        ['Instalador de Windows con lo último', 'Pendiente', 'El último instalador compilado es del 10 de septiembre. Hay que lanzar a mano el workflow «Escritorio Windows» en GitHub Actions para que incluya lo nuevo.'],
        ['Fabric contra un tenant real', 'Parcial', 'Probado contra réplicas; falta el primer intento contra el Fabric de la empresa.'],
        ['Power BI con el informe armado', 'Parcial', 'Las tablas están probadas; falta armar y validar el tablero.'],
      ] },
    ],
  },
  {
    id: 'proximo',
    titulo: 'Lo que sugiero para la próxima etapa',
    para: 'todos',
    bloques: [
      { t: 'p', x: 'Con el control de deriva, el programa ya cubre el ciclo completo: datos, modelo, uso y vigilancia. Lo que sigue es automatizar esa vigilancia y cerrar el círculo con el resultado real.' },
      { t: 'steps', items: [
        ['Control programado con aviso', 'Hoy el control se corre a pedido. El paso natural es una tarea mensual o semanal que lo corra sola y mande un aviso cuando el veredicto pase a «reentrenar».'],
        ['Historial de deriva', 'Guardar cada control para ver la tendencia en el tablero: un PSI que sube de a poco se anticipa antes de que cruce el umbral.'],
        ['Desempeño real, cuando llega la respuesta', 'A los 30 días se sabe quién pagó. Comparar ese resultado con lo que el modelo prometió en el holdout es la prueba de fuego.'],
        ['Campeón contra retador', 'Antes de reemplazar un modelo en uso, enfrentarlo al reentrenado sobre el mismo holdout y quedarse con el que gane.'],
        ['Usuarios y roles en modo servidor', 'Inicio de sesión con Entra ID y permisos por workspace, para que varios equipos compartan un mismo servidor.'],
      ] },
    ],
  },
  {
    id: 'preguntas',
    titulo: 'Preguntas que van a aparecer',
    para: 'gerentes',
    bloques: [
      { t: 'qa', items: [
        ['¿Hace falta un científico de datos?', 'Para usarlo, no. Para decidir con él, conviene que alguien con criterio revise el plan de limpieza y la lectura del resultado. El programa explica cada paso en llano justamente para eso.'],
        ['¿Y si la IA se equivoca?', 'La IA no calcula ningún número: los números salen del motor estadístico. Cuando se le pregunta algo a los datos en lenguaje natural, la consulta SQL se ejecuta de verdad y se muestra, así que se puede revisar.'],
        ['¿Nuestros datos se suben a algún lado?', 'No. El entrenamiento corre donde corre el programa: la PC, el servidor del cliente o el notebook. Lo único que sale es lo que alguien escriba a propósito en la pestaña de IA, y sólo si hay una IA configurada.'],
        ['¿Aguanta tablas grandes?', 'No tiene tope de filas. Los datos se guardan en Parquet por bloques y se consultan con DuckDB fuera de memoria: el límite es el disco.'],
        ['¿Cada cuánto hay que reentrenar?', 'Cuando lo diga el control de deriva. Como costumbre sana, correrlo con cada tanda nueva de datos, por ejemplo una vez por mes.'],
        ['¿Qué pasa si mañana cambiamos de proveedor de IA?', 'Nada: se cambia en una pantalla. Hay seis opciones y cualquier servicio compatible con OpenAI.'],
      ] },
    ],
  },
];

const CIERRE = 'MV AutoML Studio no promete magia: promete un número honesto, un camino a la vista y un aviso a tiempo cuando ese número deja de valer. Para un gerente eso es tranquilidad; para un técnico, es trabajo que no tiene que rehacer.';

module.exports = { META, KPIS, SECCIONES, CIERRE };
