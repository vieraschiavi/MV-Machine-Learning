/**
 * Contenido de la guía del agente de mercado (para gerentes y técnicos).
 *
 * Se genera con el mismo diseño que la guía del programa:
 *
 *   node docs/presentacion/generar.js --contenido docs/agente/contenido.js
 *
 * Los números de los ejemplos salen de correr el agente sobre
 * `examples/estudios_mercado_sintetico.csv` y `examples/portafolio_sintetico.csv`:
 * son datos INVENTADOS, sirven para mostrar el razonamiento, no describen ningún
 * mercado real. Las imágenes de `img/` salen de esa misma corrida.
 *
 * Marcas de texto: **negrita** y `código`.
 */
'use strict';

const META = {
  producto: 'MV AutoML Studio',
  titulo: 'Agente de mercado',
  marca: 'MV AutoML Studio · Guía para gerentes y técnicos',
  bajada: 'Proyectar lanzamientos y ventas mirando también a la gente que no está en ninguna base: '
    + 'quien tiene síntomas y no consulta, quien tiene el diagnóstico y no se trata. '
    + 'Qué hace, de dónde saca los números y cuánto creerle.',
  version: 'Versión 1.0 · octubre de 2026',
  autor: 'Martín Viera',
  archivo: 'Agente-de-Mercado',
};

const KPIS = [
  ['5', 'etapas del embudo, por país y segmento'],
  ['P10–P90', 'rango en cada número que proyecta'],
  ['0', 'cifras de la IA sin la marca «a validar»'],
  ['86', 'pruebas automáticas sobre el agente'],
];

const SECCIONES = [
  {
    id: 'resumen',
    titulo: 'En una página',
    para: 'gerentes',
    bloques: [
      { t: 'lead', x: 'Las proyecciones de siempre miran la historia de ventas. El problema es que la historia sólo ve a quien ya compra. El agente de mercado agrega lo que falta: **cuánta gente tiene la enfermedad y todavía no está en el mercado**, y cuánto de eso se puede ganar.' },
      { t: 'p', x: 'En criollo: para vender un antihipertensivo no alcanza con mirar cuánto vendimos el año pasado. Hay que saber cuántos hipertensos hay en cada país, cuántos lo saben, cuántos se tratan y con qué. En hipertensión, por ejemplo, **los hombres consultan menos que las mujeres**: hay un mercado entero que no aparece en ninguna base porque nunca pisó un consultorio. El agente lo hace visible, país por país.' },
      { t: 'h3', x: 'Qué entrega' },
      { t: 'ul', items: [
        '**El mercado actual y el latente**, separados: tratados, diagnosticados sin tratamiento y gente con la enfermedad sin diagnóstico.',
        '**Una lectura por país**: dónde conviene **desarrollar** (detección), **acelerar** (activación médica) o **proteger** (participación dentro de la clase).',
        '**La curva de un lanzamiento** mes a mes, con su rango de incertidumbre.',
        '**Qué supuesto validar primero**: el que más mueve el resultado.',
        '**El control contra la realidad**: si lo que se vende no cierra con los supuestos, el agente lo dice.',
        '**El tablero de contribución** con el formato de la lámina de portafolio, también en Power BI.',
      ] },
      { t: 'callout', tipo: 'ok', titulo: 'La regla que lo hace confiable', x: 'Los números del mercado salen de **estudios de mercado** por país. Si todavía no hay estudio, el motor de IA propone una primera versión, pero cada cifra queda marcada «IA (a validar)» y el informe dice cuánto de la proyección descansa en hipótesis. Un estudio siempre pisa a la IA.' },
    ],
  },
  {
    id: 'problema',
    titulo: 'El problema: la historia no ve al que no compra',
    para: 'gerentes',
    bloques: [
      { t: 'p', x: 'Un modelo entrenado con ventas pasadas puede proyectar muy bien **lo que ya pasa**. Pero tiene dos puntos ciegos que en farma pesan mucho:' },
      { t: 'steps', items: [
        ['El lanzamiento no tiene historia', 'Un producto nuevo no tiene ventas pasadas: no hay con qué entrenar ni con qué medir. La proyección tiene que salir del mercado, no del producto.'],
        ['El mercado latente no deja rastro', 'El paciente que no consulta no aparece en las recetas, ni en la auditoría de farmacias, ni en el CRM. Si la proyección sólo mira esas fuentes, lo da por inexistente, y es justo donde está el crecimiento.'],
      ] },
      { t: 'p', x: 'El agente resuelve las dos cosas con la herramienta clásica de inteligencia de mercado farmacéutica: el **embudo epidemiológico**, armado país por país con supuestos explícitos, cada uno con su rango y su fuente.' },
    ],
  },
  {
    id: 'embudo',
    titulo: 'Cómo piensa el agente: el embudo',
    para: 'todos',
    bloques: [
      { t: 'p', x: 'Por cada país y segmento (por defecto hombres y mujeres; puede ser edad o región) el agente baja de la población hasta la marca:' },
      { t: 'img', src: 'img/embudo.png', pie: 'Ejemplo con datos sintéticos: de 26,7 millones de personas con hipertensión, 12,3 millones no tienen diagnóstico y 4,9 millones están diagnosticadas sin tratamiento. Ese latente (17,2 millones) es más grande que todo el mercado tratado.' },
      { t: 'table', head: ['Etapa', 'Qué es', 'Supuesto que la define'], ancho: [22, 43, 35], filas: [
        ['Prevalentes', 'Personas con la enfermedad', '`poblacion` × `prevalencia`'],
        ['Diagnosticados', 'Las que lo saben', '`diagnosticados` (fracción de prevalentes)'],
        ['Tratados', 'Las que se tratan', '`tratados` (fracción de diagnosticados)'],
        ['En la clase', 'Tratadas con la clase o molécula', '`clase` (fracción de tratados)'],
        ['En la marca', 'Tratadas con nuestra marca', '`participacion` (dentro de la clase)'],
      ] },
      { t: 'p', x: 'Con `dosis_dia`, `dias_tratamiento` y `adherencia` los pacientes se pasan a **unidades**, y con `precio_unidad` a **valor**. El **mercado latente** es todo lo que queda arriba de «tratados»: sin diagnóstico (síntomas sin consulta) más diagnosticados sin tratamiento.' },
      { t: 'callout', tipo: 'warn', titulo: 'Nada se asume en silencio', x: 'Si falta un supuesto obligatorio (población, prevalencia, diagnóstico, tratamiento), el agente lo reclama y no corre. Si falta uno con valor razonable (una dosis por día, 365 días, adherencia del 100 %), lo usa **y lo avisa**: inflar el mercado callado es la forma más fácil de vender una proyección que no se cumple.' },
    ],
  },
  {
    id: 'fuentes',
    titulo: 'De dónde salen los números',
    para: 'todos',
    bloques: [
      { t: 'steps', items: [
        ['Estudios de mercado (mandan)', 'Encuestas nacionales de salud, estudios poblacionales, auditorías de prescripción, investigaciones que la empresa ya compra o encarga. Se cargan con una plantilla por país y segmento: valor, mínimo, máximo y fuente.'],
        ['Propuesta del motor de IA (a validar)', 'Si todavía no hay estudio, el agente le pide al motor de IA configurado una primera versión del embudo y la **casuística del área terapéutica**: subdiagnóstico por sexo y edad, brecha de tratamiento, escalonamiento mono → doble → triple, dosis y titulación, adherencia, acceso y genéricos. Con la consigna explícita de no inventar citas.'],
        ['Combinación', 'Supuesto por supuesto, el estudio pisa a la IA. El resultado declara su **nivel de evidencia**.'],
      ] },
      { t: 'table', head: ['Nivel de evidencia', 'Qué significa', 'Cómo usar la proyección'], ancho: [22, 40, 38], filas: [
        ['**estudios**', 'Todos los supuestos salen de estudios cargados', 'Para presupuestar y decidir'],
        ['**mixta**', 'Parte estudios, parte IA', 'Como base de trabajo; validar lo marcado'],
        ['**solo IA**', 'Ningún supuesto respaldado por un estudio', 'Como hipótesis para encargar el estudio'],
      ] },
      { t: 'callout', tipo: 'bad', titulo: 'Por qué la IA no alcanza sola', x: 'Un modelo de lenguaje puede dar cifras desactualizadas y citar estudios que no existen. El agente nunca presenta lo que propone como dato: es un punto de partida para pedirle a inteligencia de mercado lo que falta.' },
    ],
  },
  {
    id: 'lectura',
    titulo: 'Qué responde, país por país',
    para: 'gerentes',
    bloques: [
      { t: 'p', x: 'Con los estudios sintéticos de ejemplo (hipertensión en tres países, por sexo), el agente lee así:' },
      { t: 'table', head: ['País', 'Acción', 'Por qué'], ancho: [16, 18, 66], filas: [
        ['México', '**Desarrollar**', 'El 46 % de quienes tienen la enfermedad no está diagnosticado. Mueve más la detección (campañas, tamizaje, educación al paciente), empezando por los hombres.'],
        ['Ecuador', '**Desarrollar**', 'El 56 % no está diagnosticado: el mercado está escondido.'],
        ['Chile', '**Acelerar**', '1,35 millones de diagnosticados sin tratamiento (32 % de los prevalentes): el crecimiento está en activación médica, adherencia y acceso.'],
      ] },
      { t: 'p', x: 'La regla: **desarrollar** si el subdiagnóstico domina (40 % o más de los prevalentes sin diagnóstico); **acelerar** si muchos diagnosticados no se tratan (20 % o más); **proteger** si el mercado ya está tratado y crecer es ganar participación dentro de la clase.' },
      { t: 'h3', x: 'Qué validar primero' },
      { t: 'img', src: 'img/tornado.png', pie: 'Cada barra lleva un supuesto a su mínimo (rojo) y a su máximo (azul) con los demás quietos. El de arriba es el que más mueve el resultado: el primero que conviene confirmar con un estudio.' },
      { t: 'h3', x: 'El lanzamiento' },
      { t: 'img', src: 'img/lanzamiento.png', pie: 'Adopción tipo Bass hacia una participación al pico del 12 % de la clase (entre 8 % y 16 %), con el 90 % del pico en el mes 18. Al mes 36, en el escenario central, unos USD 3,4 millones por mes en los tres países sintéticos.' },
      { t: 'h3', x: 'El control contra la realidad' },
      { t: 'p', x: 'Cuando el producto ya vende, se cargan las ventas reales por país y el agente contrasta: si los supuestos explican lo vendido (**coherente**), si no (**revisar**), si se vende más que todo el mercado tratado (**imposible**: algún supuesto está subestimado o hay canal fuera del embudo) y si una proyección por historia supera el techo del mercado tratado (**fuera de techo**: no se cumple sin activar latente).' },
    ],
  },
  {
    id: 'portafolio',
    titulo: 'La lámina de contribución, calculada',
    para: 'gerentes',
    bloques: [
      { t: 'p', x: 'Junto al agente va la **matriz de contribución y mix**: el formato de la lámina «una plataforma regional, con motores de crecimiento diferentes por mercado», pero calculado desde las ventas. Sirve por país y también por molécula o marca dentro de cada área terapéutica.' },
      { t: 'img', src: 'img/burbujas.png', pie: 'Datos sintéticos. Eje Y: contribución a las ventas (baja < 3 %, media 3–10 %, alta > 10 %). Eje X: evolución del mix, de monoterapia a triple terapia. Tamaño: la contribución.' },
      { t: 'ul', items: [
        '**Proteger** (contribución alta), **acelerar** (media) y **desarrollar** (baja).',
        '**Siguiente motor** de cada mercado: la primera presentación del mix donde está por debajo de la región. La oportunidad no es uniformar el mix, sino activar el motor que sigue en cada país.',
        '**Lectura estratégica** automática: escala (cuántos mercados explican el negocio), dirección (peso de las combinaciones) y diversidad (qué tan distinto está cada uno).',
      ] },
    ],
  },
  {
    id: 'uso',
    titulo: 'Cómo se usa',
    para: 'tecnicos',
    bloques: [
      { t: 'h3', x: 'En el programa' },
      { t: 'p', x: 'Pestaña **Portafolio y mercado**. Arriba, la matriz de contribución (dataset de ventas, entidad, valor, presentación, área y período). Abajo, el agente: área terapéutica, molécula, enfermedad, presentación, países y segmentos; se baja la plantilla, se carga el estudio como dataset o se pide la propuesta a la IA, y se analiza. El botón **Paquete para Power BI** arma el zip con tablas, tema, medidas DAX y la matriz de burbujas para Deneb.' },
      { t: 'h3', x: 'Desde un notebook de Fabric' },
      { t: 'code', x: `from app import notebook as mv

estudios = spark.sql("SELECT * FROM MercadoLH.estudios_hta").toPandas()
plan = {"pico": 0.12, "meses_al_pico": 18, "horizonte": 36}
analisis = mv.mercado(estudios=estudios, lanzamiento=plan,
                      inicio="2027-01")
mv.portafolio_para_powerbi("/lakehouse/default/Files/mv/portafolio",
                           mercado=analisis)` },
      { t: 'h3', x: 'Por API' },
      { t: 'table', head: ['Ruta', 'Para qué'], ancho: [40, 60], filas: [
        ['`GET /api/mercado/plantilla`', 'Plantilla de supuestos en CSV, por países y segmentos'],
        ['`POST /api/mercado/proponer`', 'Propuesta del motor de IA, marcada «a validar»'],
        ['`POST /api/mercado/analizar`', 'Embudo, rango, lecturas, tornado, lanzamiento y contraste'],
        ['`POST /api/mercado/narrar`', 'Lectura ejecutiva redactada por el motor de IA'],
        ['`POST /api/portafolio/contribucion`', 'La matriz de contribución y mix'],
        ['`POST /api/portafolio/powerbi`', 'El paquete para Power BI'],
      ] },
      { t: 'p', x: 'El detalle de cada parámetro y el armado de la página de Power BI están en `docs/PORTAFOLIO_Y_MERCADO.md`.' },
    ],
  },
  {
    id: 'confianza',
    titulo: 'Cuánto creerle',
    para: 'todos',
    bloques: [
      { t: 'p', x: 'El rango **P10–P90** sale de simular todos los supuestos entre su mínimo y su máximo. Mide cuánto se mueve el resultado con lo que no se sabe. **No es** el error de un modelo medido contra ventas reales: en un lanzamiento no hay ventas reales contra las cuales medir. Por eso el agente lo dice en cada informe.' },
      { t: 'table', estado: 1, head: ['Pieza', 'Estado', 'Detalle'], ancho: [34, 16, 50], filas: [
        ['Embudo, rango, tornado, lanzamiento, contraste', 'Verificado', 'Cuentas exactas probadas a mano y casos de borde.'],
        ['Agente: propuesta, estudios que pisan, lecturas', 'Verificado', 'Con un motor de IA simulado en las pruebas.'],
        ['Matriz de contribución y paquete de Power BI', 'Verificado', 'Columnas que usan las medidas DAX y Deneb, comprobadas.'],
        ['Pantalla del programa', 'Verificado', 'Recorrida en un navegador real, sin errores.'],
        ['Propuesta contra un proveedor de IA real', 'Pendiente', 'Falta configurar la clave del proveedor de la empresa.'],
        ['Tablero en Power BI Desktop', 'Parcial', 'El kit está listo; falta armarlo y validarlo en la herramienta.'],
        ['Estudios de mercado reales', 'Pendiente', 'Los ejemplos son sintéticos: hay que cargar los estudios de cada país.'],
      ] },
    ],
  },
  {
    id: 'preguntas',
    titulo: 'Preguntas que van a aparecer',
    para: 'gerentes',
    bloques: [
      { t: 'qa', items: [
        ['¿La IA inventa el mercado?', 'No decide nada sola. Propone una primera versión cuando no hay estudio, marcada «a validar», y el informe dice cuántos supuestos falta confirmar. Los estudios la reemplazan.'],
        ['¿Usa datos de pacientes?', 'No. Trabaja con tasas agregadas por país y segmento (prevalencia, diagnóstico, tratamiento). No identifica a ninguna persona.'],
        ['¿Sirve para un producto que ya se vende?', 'Sí, y ahí rinde doble: el contraste con las ventas reales dice si los supuestos cierran y si la proyección por historia tiene techo.'],
        ['¿Qué pasa si el estudio de un país es viejo?', 'Se carga igual, con un rango más ancho. El tornado muestra si ese supuesto es el que más pesa; si lo es, conviene actualizarlo primero.'],
        ['¿Y otras áreas terapéuticas?', 'El embudo es el mismo para cualquier enfermedad crónica o aguda; lo que cambia son los supuestos y la casuística, que el agente pide por área.'],
      ] },
    ],
  },
  {
    id: 'proximo',
    titulo: 'Próximos pasos',
    para: 'todos',
    bloques: [
      { t: 'steps', items: [
        ['Cargar los estudios reales', 'Empezar por un área y tres países, con la plantilla del agente y la fuente de cada supuesto.'],
        ['Probar el método contra un lanzamiento pasado', 'Armar el embudo con lo que se sabía antes de lanzar un producto que ya tiene dos o tres años, y comparar la curva con lo que pasó. Es la prueba honesta del agente.'],
        ['Conectar el motor de IA de la empresa', 'Para que la propuesta y la lectura ejecutiva corran con el proveedor corporativo.'],
        ['Armar el tablero en Power BI', 'Con el kit (tema, medidas DAX y burbujas Deneb) y validarlo con el equipo comercial.'],
      ] },
    ],
  },
];

const CIERRE = 'El agente no adivina el mercado: lo arma con supuestos a la vista, dice cuáles faltan confirmar y muestra dónde está la gente que hoy no aparece en ninguna base. Eso es lo que convierte una proyección en una decisión.';

module.exports = { META, KPIS, SECCIONES, CIERRE };
