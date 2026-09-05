"""Qué significa cada paso del pipeline, dicho dos veces.

El programa ya guardaba el motivo de cada transformación, pero escrito para
quien lo iba a ejecutar: «Imputación por mediana (32.418) sobre 4.2% de
nulos». Eso le sirve a quien programa y no le dice nada a quien firma.

Acá vive la traducción, una sola vez y en un solo lugar:

  * ``tecnico``  — qué hace exactamente, con el nombre de la operación, la
    función SQL y los parámetros. Es lo que audita un programador.
  * ``criollo``  — lo mismo sin una sola palabra de jerga, para que un jefe
    entienda qué le pasó a sus datos.
  * ``porque``   — la razón de negocio o estadística por la que se hizo.
  * ``impacto``  — qué cambia aguas abajo, o qué pasaría si el paso no
    estuviera. Es la columna que convierte una lista en una explicación.

Las plantillas se completan con los datos reales del plan ejecutado: nunca se
describe un paso que no ocurrió, ni con números que no salgan del linaje.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Paso:
    titulo: str
    tecnico: str
    criollo: str
    porque: str
    impacto: str


# ═══════════════════════════════════════════════ operaciones del ETL ═════════
# Las claves son las mismas que compila `etl.compile_sql`: si aparece una
# operación nueva sin entrada acá, `bitacora` la muestra igual con su motivo
# original, pero la prueba de cobertura avisa que le falta la traducción.
OPS: dict[str, Paso] = {
    "drop_column": Paso(
        titulo="Descarte de columnas",
        tecnico=("Se excluyen {n} columnas del SELECT: {columnas}. El planificador las marca por "
                 "valor único (constante), por ser identificador de fila, o por superar el umbral "
                 "de vacíos configurado."),
        criollo=("Se dejaron afuera {n} columnas que no ayudaban a predecir nada: algunas tenían "
                 "siempre el mismo valor, otras eran un número de expediente distinto en cada "
                 "fila, y otras estaban casi siempre en blanco."),
        porque=("Una columna con un solo valor no distingue un caso de otro. Un número de "
                "expediente distingue todos los casos y no explica ninguno: el modelo se lo "
                "aprende de memoria y después falla con datos nuevos."),
        impacto=("El modelo entrena con menos ruido y más rápido. Si estas columnas quedaran, el "
                 "resultado se vería mejor en las pruebas y peor en la realidad."),
    ),
    "cast_numeric": Paso(
        titulo="Importes de texto a número",
        tecnico=("TRY_CAST a DOUBLE sobre {columnas}, previa limpieza con regexp_replace de "
                 "símbolos de moneda, porcentajes y espacios, y normalización del separador "
                 "decimal. El valor que no convierte queda vacío en vez de romper la consulta."),
        criollo=("Las columnas con importes escritos como texto —del estilo «$ 1.234,56»— pasaron "
                 "a ser números con los que se puede sumar y promediar."),
        porque=("Mientras el importe sea texto, para el programa «$ 1.000» y «$ 999» se ordenan "
                "como palabras: el 1.000 va antes que el 999. No se puede sumar ni comparar."),
        impacto=("Recién con la columna convertida el modelo puede usar la magnitud del importe. "
                 "Antes de esto, la columna entraba como una etiqueta más y perdía todo su valor."),
    ),
    "parse_datetime": Paso(
        titulo="Fechas de texto a fecha real",
        tecnico=("TRY_CAST a TIMESTAMP sobre {columnas}, con TRIM previo. Lo que no convierte "
                 "queda vacío en lugar de abortar la consulta."),
        criollo=("Las fechas que venían escritas como texto pasaron a ser fechas de verdad, para "
                 "poder ordenarlas y calcular cuánto tiempo pasó entre una y otra."),
        porque=("Una fecha guardada como texto no se puede ordenar ni restar. Es la diferencia "
                "entre saber que algo pasó «el 03/12» y saber que pasó hace 40 días."),
        impacto=("Habilita el paso siguiente, que es el que realmente le sirve al modelo: separar "
                 "el año, el mes y el día."),
    ),
    "expand_datetime": Paso(
        titulo="Apertura de la fecha en sus partes",
        tecnico=("De {columnas} se derivan columnas nuevas por cada parte pedida (year, month, "
                 "day, dayofweek, week) y se descarta la original, que como valor continuo no "
                 "aporta al modelo."),
        criollo=("De cada fecha se sacaron el año, el mes, el día y el día de la semana en "
                 "columnas separadas, y se guardó la fecha original a un costado."),
        porque=("Un modelo no aprende de una fecha entera, porque cada fecha aparece una sola "
                "vez. Sí aprende que en diciembre se vende más, o que los lunes se cobra peor."),
        impacto=("Es lo que permite descubrir estacionalidad. Sin este paso, toda la información "
                 "del calendario se pierde."),
    ),
    "trim_text": Paso(
        titulo="Limpieza de espacios en el texto",
        tecnico=("TRIM sobre {columnas} y NULLIF de la cadena vacía, para que « Norte», «Norte » "
                 "y «Norte» dejen de ser tres categorías distintas."),
        criollo=("Se emparejaron los textos que sólo se diferenciaban por un espacio de más al "
                 "principio o al final."),
        porque=("Para el programa, «Norte» y «Norte » son dos cosas distintas. Los espacios "
                "invisibles parten una categoría en varias y diluyen su peso."),
        impacto=("Cada categoría vuelve a contarse una sola vez, con todos sus casos juntos."),
    ),
    "missing_indicator": Paso(
        titulo="Marca de dato faltante",
        tecnico=("Antes de completar los vacíos se agrega, por cada columna de {columnas}, una "
                 "columna 0/1 que registra si el valor original venía vacío."),
        criollo=("Antes de rellenar los huecos se dejó anotado en qué filas el dato venía vacío."),
        porque=("Que un dato falte suele ser información: quien no declara ingreso se comporta "
                "distinto de quien declara poco. Si se rellena sin dejar la marca, ese dato se "
                "borra para siempre."),
        impacto=("El modelo puede aprender del hueco además de aprender del valor. En carteras de "
                 "crédito esta marca suele estar entre las variables más predictivas."),
    ),
    "impute_numeric": Paso(
        titulo="Relleno de vacíos numéricos",
        tecnico=("COALESCE con la mediana de la propia columna sobre {columnas}. Se usa mediana y "
                 "no promedio porque no se desplaza con los valores extremos."),
        criollo=("Los huecos de las columnas de números se completaron con el valor del medio de "
                 "esa misma columna."),
        porque=("La mayoría de los algoritmos no acepta filas con huecos: o se completa el dato o "
                "se tira la fila entera, y tirar filas es perder casos reales."),
        impacto=("Se conservan todas las filas. El valor del medio es el que menos deforma la "
                 "distribución, y la marca del paso anterior deja registro de que era un relleno."),
    ),
    "impute_categorical": Paso(
        titulo="Relleno de vacíos de texto",
        tecnico=("COALESCE a la categoría explícita «(sin dato)» sobre {columnas}, en lugar de la "
                 "moda: inventar la categoría más común donde no había dato agrega señal falsa."),
        criollo=("Donde faltaba una categoría se puso «(sin dato)», que pasa a ser una categoría "
                 "más, en vez de suponer cuál era."),
        porque=("Poner la opción más común sería inventar; «(sin dato)» dice la verdad y además "
                "deja que el modelo aprenda si no tener el dato significa algo."),
        impacto=("No se pierden filas y no se inventan valores. En el informe final «(sin dato)» "
                 "aparece como una categoría propia y se puede ver cuánto pesa."),
    ),
    "clip_outliers": Paso(
        titulo="Recorte de valores extremos",
        tecnico=("Se recortan {columnas} a los percentiles 1 y 99 (winsorización): el valor por "
                 "debajo o por encima se reemplaza por el del límite, sin eliminar la fila."),
        criollo=("Los valores exageradamente altos o bajos se llevaron al borde de lo razonable, "
                 "sin borrar la fila."),
        porque=("Un solo importe mal cargado, con tres ceros de más, alcanza para torcer un "
                "promedio y con él todo lo que el modelo deduzca de esa columna."),
        impacto=("Las relaciones se calculan sobre el grueso de los casos. Es un paso opcional: "
                 "los modelos de árboles no lo necesitan y viene apagado por omisión."),
    ),
    "log_transform": Paso(
        titulo="Compresión de escala",
        tecnico=("ln(x + 1) sobre {columnas}, para achatar colas largas y acercar la distribución "
                 "a una forma simétrica."),
        criollo=("Las columnas donde unos pocos casos son enormes frente al resto se pasaron a "
                 "una escala comprimida, para que los casos grandes no tapen a los demás."),
        porque=("En ingresos o facturación, el 1% más alto puede ser mil veces el promedio: sin "
                "comprimir la escala, el modelo sólo ve a ese 1%."),
        impacto=("Mejora sobre todo a los modelos lineales. Los resultados se informan siempre en "
                 "la escala original, con la corrección correspondiente."),
    ),
    "group_rare": Paso(
        titulo="Agrupación de categorías raras",
        tecnico=("Las categorías de {columnas} que no alcanzan el umbral de frecuencia se "
                 "reemplazan por «(otros)» con un CASE WHEN, conservando las frecuentes."),
        criollo=("Las opciones que aparecían muy poquitas veces se juntaron todas bajo la "
                 "etiqueta «(otros)», y las habituales quedaron como estaban."),
        porque=("Una categoría con tres casos no permite aprender nada: el modelo memoriza esos "
                "tres casos y después se equivoca con el cuarto."),
        impacto=("Menos columnas y menos memorización. Si mañana aparece una categoría que nunca "
                 "se había visto, cae en «(otros)» y el modelo sigue funcionando."),
    ),
    "filter_null_target": Paso(
        titulo="Filas sin respuesta, afuera",
        tecnico=("WHERE {columnas} IS NOT NULL: las filas sin valor en la columna objetivo no "
                 "pueden usarse ni para entrenar ni para evaluar."),
        criollo=("Se apartaron las filas donde justamente falta el dato que se quiere predecir."),
        porque=("Sin la respuesta conocida, esa fila no enseña nada ni permite corregir al "
                "modelo: no hay contra qué comparar."),
        impacto=("Bajan las filas disponibles, y ese descuento queda a la vista en el resumen. "
                 "Esas filas siguen siendo válidas después, para predecirles el valor que falta."),
    ),
    "drop_duplicates": Paso(
        titulo="Filas repetidas, una sola vez",
        tecnico=("SELECT DISTINCT sobre el resultado: se conserva una sola copia de cada fila "
                 "idéntica en todas sus columnas."),
        criollo=("Las filas exactamente repetidas quedaron una sola vez."),
        porque=("Una fila cargada dos veces pesa el doble sin aportar información nueva, y si "
                "aparece de los dos lados de la prueba, infla el resultado sin merecerlo."),
        impacto=("El conteo final baja y el resultado deja de estar inflado por copias."),
    ),
    "filter_rows": Paso(
        titulo="Filtro definido por el usuario",
        tecnico=("Condición SQL agregada al WHERE: {detalle}"),
        criollo=("Se aplicó el filtro que se pidió a mano, para quedarse sólo con las filas que "
                 "interesan."),
        porque=("Lo definió quien conoce el negocio: hay recortes —una sucursal, un período— que "
                "ningún análisis automático puede adivinar."),
        impacto=("Todo lo que sigue se calcula sólo sobre las filas que pasaron el filtro."),
    ),
}


# ═══════════════════════════════════════════ etapas del modelado ═════════════
# No tienen plantilla de columnas: describen una decisión del pipeline, y los
# números concretos van en la evidencia de cada paso.
ETAPAS: dict[str, Paso] = {
    "objetivo": Paso(
        titulo="Qué se predice y con qué vara se mide",
        tecnico=("Se determina el tipo de tarea a partir del objetivo y se fija la métrica de "
                 "decisión, que es la única que ordena el leaderboard y elige al campeón."),
        criollo=("Se definió qué se quiere predecir y con qué número se va a decidir cuál modelo "
                 "es el mejor."),
        porque=("Sin una vara única elegida de antemano, siempre se puede encontrar una medida "
                "que haga quedar bien al modelo que a uno le gusta."),
        impacto=("Todo el proceso posterior optimiza esa medida. Cambiarla puede cambiar cuál "
                 "modelo gana."),
    ),
    "particion": Paso(
        titulo="Los datos se parten en tres, antes de tocar nada",
        tecnico=("Partición en entrenamiento, selección y una ventana final que no interviene en "
                 "ninguna decisión. Con columna de tiempo la partición es temporal —el futuro no "
                 "entra al pasado—; si no, es aleatoria estratificada."),
        criollo=("Los datos se separaron en tres montones: uno para que el sistema aprenda, otro "
                 "para elegir entre los candidatos, y un tercero que se guarda cerrado y recién "
                 "se abre al final para saber cuánto se le puede creer."),
        porque=("Si el mismo dato se usa para aprender, para elegir y para medir, el resultado "
                "que se informa es el de un examen con las respuestas a la vista."),
        impacto=("El número final del informe sale sólo de ese tercer montón. Es más bajo que el "
                 "de las pruebas internas, y es el único que se parece a lo que va a pasar en "
                 "producción."),
    ),
    "preparacion": Paso(
        titulo="Preparación de las columnas para el algoritmo",
        tecnico=("El preprocesador se ajusta ÚNICAMENTE con el tramo de entrenamiento y después "
                 "se aplica igual a los tres tramos: codificación de categóricas, tratamiento de "
                 "texto libre y escalado para las familias que lo requieren."),
        criollo=("Las columnas se dejaron en el formato que el algoritmo sabe leer, y las reglas "
                 "para hacerlo se calcularon mirando solamente el montón de aprendizaje."),
        porque=("Si esas reglas se calcularan con todos los datos, algo de lo que se guarda para "
                "la prueba final se filtraría al entrenamiento y el resultado quedaría inflado."),
        impacto=("Es una de las defensas silenciosas del pipeline: sin ella el examen final "
                 "estaría contaminado y nadie lo notaría mirando el número."),
    ),
    "objetivo_log": Paso(
        titulo="El objetivo se modela en escala comprimida",
        tecnico=("El objetivo está sesgado a la derecha: se modela en logaritmo y la predicción "
                 "se devuelve a la escala original con corrección de smearing, que compensa el "
                 "sesgo que introduce la vuelta atrás."),
        criollo=("Como los valores a predecir tienen unos pocos casos enormes, se trabajó en una "
                 "escala comprimida y después se devolvió el resultado a pesos, con un ajuste "
                 "para que los totales no queden cortos."),
        porque=("Sin comprimir, el modelo se concentra en los casos grandes y le erra a la "
                "mayoría; al volver a la escala original sin ajuste, los totales quedan por "
                "debajo de la realidad."),
        impacto=("Las predicciones se informan siempre en la unidad original, ya corregidas."),
    ),
    "entrenamiento": Paso(
        titulo="Competencia entre familias de modelos",
        tecnico=("Cada familia se optimiza por separado con búsqueda bayesiana dentro del "
                 "presupuesto de tiempo, y se compara en la ventana de selección con la métrica "
                 "de decisión."),
        criollo=("Se probaron varios tipos de modelo distintos, cada uno con muchas "
                 "configuraciones, y compitieron entre ellos con la misma vara."),
        porque=("No hay un tipo de modelo que gane siempre: depende de la forma de los datos. "
                "Probar uno solo es apostar."),
        impacto=("La tabla de posiciones muestra a todos los competidores, no sólo al ganador: "
                 "se puede ver por cuánto ganó y si el segundo era más simple."),
    ),
    "seleccion": Paso(
        titulo="Depuración de variables",
        tecnico=("Se recorta el conjunto de variables por importancia y se reajusta el "
                 "preprocesador con las que quedan, verificando que el rendimiento en la ventana "
                 "de selección no caiga."),
        criollo=("Se sacaron las columnas que no estaban aportando, después de comprobar que sin "
                 "ellas el resultado se mantiene."),
        porque=("Un modelo con menos columnas es más barato de alimentar todos los meses, más "
                "fácil de explicar y más difícil de romper."),
        impacto=("Menos columnas que mantener en producción, con el mismo resultado."),
    ),
    "calibracion": Paso(
        titulo="Calibración de las probabilidades",
        tecnico=("Regresión isotónica ajustada sobre la ventana de selección: corrige la escala "
                 "de las probabilidades sin alterar el orden de los casos."),
        criollo=("Se ajustó la escala para que cuando el sistema diga «70% de probabilidad», de "
                 "cada cien casos así ocurran unos setenta de verdad."),
        porque=("Muchos algoritmos ordenan bien pero exageran la confianza. Si el número se usa "
                "para decidir cortes o presupuestos, tiene que significar lo que dice."),
        impacto=("El orden de prioridad no cambia; lo que cambia es que el porcentaje se puede "
                 "leer literalmente y usarlo para estimar cuántos casos esperar."),
    ),
    "evaluacion": Paso(
        titulo="Medición sobre la ventana cerrada",
        tecnico=("Se calculan las métricas sobre la ventana que no participó de ninguna "
                 "decisión, y se informa la distancia contra la ventana de selección."),
        criollo=("Recién acá se abrió el montón que estaba guardado y se midió cuánto acierta el "
                 "modelo con datos que nunca vio."),
        porque=("Es la única medición que no está contaminada por las decisiones que se tomaron "
                 "durante el armado."),
        impacto=("Este es el número que hay que citar cuando se presenta el modelo. La distancia "
                 "contra la ventana de selección avisa si el modelo se aprendió los datos."),
    ),
    "explicacion": Paso(
        titulo="Qué variables pesan y en qué sentido",
        tecnico=("Se mide el aporte de cada variable y se ordena el ranking, con el sentido del "
                 "efecto cuando la técnica lo permite."),
        criollo=("Se identificó qué columnas son las que más mueven el resultado y si lo empujan "
                 "para arriba o para abajo."),
        porque=("Un modelo que nadie puede explicar no se aprueba, no se audita y no se corrige "
                "cuando falla."),
        impacto=("Permite dos cosas: revisar si lo que el modelo aprendió tiene sentido de "
                 "negocio, y detectar la columna que contiene la respuesta disfrazada."),
    ),
    "veredicto": Paso(
        titulo="Lectura final y advertencias",
        tecnico=("Se contrasta el resultado contra los umbrales de la métrica y contra la "
                 "distancia entre ventanas, y se emiten las advertencias que correspondan."),
        criollo=("El sistema deja escrito qué tan confiable es lo que consiguió y qué conviene "
                 "revisar antes de usarlo."),
        porque=("Un resultado sin lectura se malinterpreta en las dos direcciones: se descarta un "
                "modelo útil o se lleva a producción uno que hace trampa."),
        impacto=("Es la sección que hay que leer antes de aprobar el modelo."),
    ),
}


def op(nombre: str) -> Paso | None:
    return OPS.get(nombre)


def etapa(nombre: str) -> Paso | None:
    return ETAPAS.get(nombre)
