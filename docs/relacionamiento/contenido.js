/**
 * Contenido de la guía del programa de relacionamiento (gerentes, técnicos y legal).
 *
 *   node docs/presentacion/generar.js --contenido docs/relacionamiento/contenido.js
 *
 * Los números y las imágenes salen de correr el programa sobre los ejemplos
 * sintéticos de `examples/` (contactos, contenidos, interacciones, censo,
 * prevalencias y escucha): son datos INVENTADOS, no describen a nadie.
 *
 * El mapa legal es un punto de partida para la conversación con legal y
 * compliance, no asesoramiento jurídico: cada fila dice «a validar».
 *
 * Marcas de texto: **negrita** y `código`.
 */
'use strict';

const META = {
  producto: 'MV AutoML Studio',
  titulo: 'Relacionamiento con consentimiento',
  marca: 'MV AutoML Studio · Guía para gerentes, técnicos y legal',
  bajada: 'Una base propia de pacientes, cuidadores y médicos, un recomendador al estilo de un marketplace '
    + 'y una estrategia de comunicación por canal, todo dentro de lo que la ley y cada persona permiten. '
    + 'De dónde salen los datos, qué se puede decir a quién y cómo se mide.',
  version: 'Versión 1.0 · octubre de 2026',
  autor: 'Martín Viera',
  archivo: 'Relacionamiento-con-Consentimiento',
};

const KPIS = [
  ['4', 'consentimientos por separado: contacto, comercial, salud y personalización'],
  ['11', 'reglas que se chequean antes de recomendar nada'],
  ['0', 'medicamentos bajo receta promocionados al público'],
  ['57', 'pruebas automáticas sobre el programa'],
];

const SECCIONES = [
  {
    id: 'resumen',
    titulo: 'En una página',
    para: 'gerentes',
    bloques: [
      { t: 'lead', x: 'La idea es la de MercadoLibre o Temu: que cada persona reciba **lo que más le sirve**, aprendiendo de lo que hace. La diferencia es de dónde salen los datos y qué se le puede ofrecer: **sólo datos propios, consentidos, y sólo contenidos que la ley permite enviarle**.' },
      { t: 'p', x: 'En criollo: no salimos a leer Twitter para encontrar enfermos. Armamos **nuestra propia base** con gente que entra porque quiere —un programa de pacientes, una landing de concientización, un registro de médicos, la compra de un producto de venta libre— y que nos dice, finalidad por finalidad, qué podemos hacer con sus datos. Sobre esa base, el programa elige el **siguiente mejor contenido** para cada persona, igual que un marketplace elige el siguiente producto.' },
      { t: 'h3', x: 'Qué entrega' },
      { t: 'ul', items: [
        '**Quién se puede contactar, para qué y con qué**, persona por persona, con el motivo cuando algo no se puede enviar.',
        '**El siguiente mejor contenido** de cada persona, con el porqué («a quienes les interesó X también les interesó esto»).',
        '**El embudo de la base**: captados, contactables, con cada consentimiento, alcanzados, activos e inscriptos.',
        '**KPIs por contenido**: apertura, clics, conversión, bajas y quejas.',
        '**Dónde está el mercado que no alcanzamos**: la base contra el censo y las encuestas de salud, por ciudad, barrio, sexo, edad y nivel socioeconómico.',
        '**De qué se habla en redes**, agregado y sin autores, con alerta para farmacovigilancia.',
        '**La auditoría**: lo que se envió y hoy no cumple, y los países cuyas reglas legal todavía no validó.',
        '**Todo en Power BI y en Fabric**: tablas, medidas y un modelo estrella que se cruza con Analysis Services y el data warehouse.',
      ] },
      { t: 'callout', tipo: 'ok', titulo: 'La regla que lo hace posible', x: 'Las reglas van **antes** del algoritmo. El recomendador nunca ve un contenido que no se le puede enviar a esa persona: un medicamento bajo receta no le llega a un paciente como promoción, le llega la concientización sin marca o el programa del producto que declaró que le recetaron.' },
    ],
  },
  {
    id: 'por-que-no',
    titulo: '¿Por qué no hacemos lo mismo que MercadoLibre?',
    para: 'gerentes',
    bloques: [
      { t: 'p', x: 'Sí hacemos lo mismo: **el algoritmo es el mismo tipo** (filtrado colaborativo más historial propio). Lo que no se puede copiar son tres cosas:' },
      { t: 'steps', items: [
        ['De dónde salen los datos', 'Cuando alguien busca vitaminas en MercadoLibre, busca **adentro de MercadoLibre**: está logueado y aceptó sus términos. No es lo mismo que leer lo que alguien publica en otra red y cruzarlo con su mail, su ciudad y su nivel económico. Lo equivalente para nosotros es lo que pasa en nuestros canales.'],
        ['Qué se recomienda', 'Las vitaminas son de venta libre y se pueden publicitar al público. Un medicamento bajo receta **no se puede promocionar al paciente** en ninguno de nuestros países: sólo a profesionales. Por eso MercadoLibre tampoco recomienda medicamentos con receta.'],
        ['El dato de salud es sensible', '«Compró vitaminas» es un dato de consumo. «Buscó obesidad mórbida» es un dato de salud: todas las leyes de la región piden **consentimiento expreso** para usarlo, y prohíben inferirlo por la espalda.'],
      ] },
      { t: 'callout', tipo: 'warn', titulo: 'El riesgo que se evita', x: 'Además de multas y de la suspensión de las cuentas en las redes (sus políticas restringen segmentar por condiciones de salud), el riesgo mayor es el titular: **«laboratorio rastrea enfermos en las redes»**. Una base consentida no tiene ese titular; tiene pacientes que eligieron estar.' },
    ],
  },
  {
    id: 'fuentes',
    titulo: 'De dónde salen los datos',
    para: 'todos',
    bloques: [
      { t: 'p', x: 'Hay dos niveles, y la separación entre los dos es lo que hace todo legal:' },
      { t: 'table', head: ['Nivel', 'Fuentes', 'Cómo se usa'], ancho: [18, 46, 36], filas: [
        ['**Persona** (base propia)', 'Formularios y landings, programa de pacientes, call center, e-commerce de venta libre, eventos, registro de profesionales (matrículas, proveedores licenciados).', 'Con consentimiento por finalidad. Sólo lo **declarado**: áreas de interés, productos recetados, ciudad y barrio.'],
        ['**Territorio y segmento** (público)', 'Censos por país, ciudad y barrio, con edad, sexo y nivel socioeconómico (INE, INDEC, INEGI, IBGE, DANE). Encuestas de salud (ENSANUT, ENFR, PNS, ENS, STEPS-OMS, GBD). Mercado (IQVIA, Close-Up). Búsquedas agregadas (Google Trends).', 'Agregado: nunca identifica a nadie. Se cruza con la base **por el territorio declarado**, no por la persona.'],
        ['**Conversación** (redes)', 'Exportación de una herramienta de escucha con licencia, o la API oficial de cada red dentro de sus términos.', 'Sólo conteos: temas, sentimiento, país y semana. Sin autores ni textos.'],
      ] },
      { t: 'p', x: 'Ejemplo del cruce: a un contacto que declaró vivir en Pocitos se le asigna el **nivel socioeconómico de Pocitos** según el censo, no uno inferido para él. Y comparando la base con la población se ve, por barrio, edad y sexo, cuánta gente con la enfermedad estimada hay y cuánta tenemos captada.' },
    ],
  },
  {
    id: 'legal',
    titulo: 'El mapa legal (a validar con legal)',
    para: 'legal',
    bloques: [
      { t: 'callout', tipo: 'info', titulo: 'Qué es y qué no es', x: 'Un punto de partida para la conversación con legal y compliance, no asesoramiento jurídico. El programa trae **valores conservadores por defecto** en cada país y los marca «a validar» hasta que legal los confirme; los ajustes que legal valide se cargan por país sin tocar código.' },
      { t: 'table', head: ['País', 'Datos personales', 'Autoridad sanitaria', 'Lo que el programa asume'], ancho: [12, 34, 16, 38], filas: [
        ['Uruguay', 'Ley 18.331 (URCDP). Salud es dato sensible: consentimiento expreso.', 'MSP', 'Rx sólo a profesionales; venta libre al público con permiso comercial.'],
        ['Argentina', 'Ley 25.326 (AAIP). Datos sensibles; registro de bases.', 'ANMAT', 'Ídem.'],
        ['México', 'LFPDPPP (ley nueva de 2025). Sensibles: consentimiento expreso y por escrito.', 'COFEPRIS', 'Ídem; la publicidad de venta libre requiere permiso.'],
        ['Brasil', 'LGPD (ANPD). Dato de salud: consentimiento específico y destacado.', 'ANVISA', 'Ídem.'],
        ['Colombia', 'Ley 1581 (SIC). Autorización previa, expresa e informada; registro de bases.', 'INVIMA', 'Ídem.'],
        ['Chile', 'Ley 19.628, reformada por la Ley 21.719 (verificar vigencia).', 'ISP', 'Ídem.'],
        ['Perú', 'Ley 29733 (ANPD).', 'DIGEMID', 'Ídem.'],
        ['Ecuador', 'Ley Orgánica de Protección de Datos Personales.', 'ARCSA', 'Ídem.'],
      ] },
      { t: 'p', x: 'Encima de las leyes van los **códigos de ética de la industria** (IFPMA y las cámaras locales) y las **políticas de publicidad de cada red**, que restringen la segmentación por condiciones de salud y exigen cumplir la regulación local de medicamentos.' },
    ],
  },
  {
    id: 'canales',
    titulo: 'Qué decir, a quién y por dónde',
    para: 'gerentes',
    bloques: [
      { t: 'table', head: ['Canal', 'Para quién', 'Se puede', 'No se puede'], ancho: [20, 16, 34, 30], filas: [
        ['**Concientización sin marca**', 'Público', 'Educar sobre la enfermedad, invitar a consultar, captar con consentimiento.', 'Nombrar el producto bajo receta o insinuarlo.'],
        ['**Programa de pacientes**', 'Quien declaró la receta', 'Adherencia, recordatorios, acompañamiento, beneficios del producto recetado.', 'Usarlo para promocionar otros productos bajo receta.'],
        ['**Venta libre**', 'Público', 'Promoción de marca y recomendación «estilo marketplace», con permiso comercial.', 'Prometer efectos que la autoridad no aprobó.'],
        ['**Profesionales**', 'Médicos registrados', 'Promoción de productos bajo receta, educación médica, estudios.', 'Regalos o beneficios fuera del código de ética.'],
        ['**Escucha social**', 'Nadie en particular', 'Detectar temas, dudas y sentimiento; ajustar contenidos.', 'Contactar o perfilar a quien publicó.'],
        ['**Pauta en redes**', 'Audiencias amplias', 'Concientización con segmentación por contexto, edad y región.', 'Audiencias armadas con datos de salud.'],
      ] },
    ],
  },
  {
    id: 'consentimiento',
    titulo: 'Cómo se pide el consentimiento',
    para: 'todos',
    bloques: [
      { t: 'p', x: 'El consentimiento se pide **por finalidad**, con casillas separadas y **ninguna marcada de antemano**. Cada una se puede retirar sola:' },
      { t: 'table', head: ['Casilla', 'Texto de ejemplo', 'Qué habilita'], ancho: [20, 50, 30], filas: [
        ['Contacto', '«Quiero recibir información de salud y novedades del programa por email o WhatsApp.»', 'Que se le escriba.'],
        ['Comercial', '«Acepto recibir ofertas y promociones de productos de venta libre.»', 'Promoción de marca y beneficios.'],
        ['Salud', '«Autorizo el uso de las áreas de salud y tratamientos que declaro para recibir contenido sobre ellos.»', 'Contenidos por área y programas.'],
        ['Personalización', '«Acepto que se use mi actividad (aperturas, clics) para elegir lo que me llega.»', 'El historial y el «a otros como vos».'],
      ] },
      { t: 'ul', items: [
        '**Aviso de privacidad** en lenguaje claro, con responsable, finalidades, plazo y cómo ejercer derechos.',
        '**Doble confirmación** (doble opt-in) donde legal lo pida: se activa por país.',
        '**Evidencia**: fecha, canal y versión del texto aceptado, guardados en el CRM.',
        '**Baja en un clic** en cada envío; una baja registrada en un envío se respeta aunque el CRM todavía no la tenga.',
        '**Minimización**: la analítica trabaja con un id seudónimo; el mail, el teléfono y el nombre se quedan en el CRM. Si llegan datos de salud sin consentimiento de salud, no se usan y el programa avisa.',
      ] },
    ],
  },
  {
    id: 'recomendador',
    titulo: 'Cómo elige el siguiente mejor contenido',
    para: 'tecnicos',
    bloques: [
      { t: 'p', x: 'Dos pasos, siempre en este orden:' },
      { t: 'steps', items: [
        ['Primero, las reglas', 'Para cada par persona × contenido se busca el primer motivo que lo bloquea: baja, falta de consentimiento, doble confirmación, país, audiencia, receta al público, área no declarada, programa sin receta declarada. Lo que queda es lo **elegible**.'],
        ['Después, el puntaje', 'Entre lo elegible, se ordena por lo que más le sirve a la persona, se saca lo que se le envió en los últimos 30 días, aquello en lo que ya se inscribió y lo que motivó una queja, y se respeta el **tope de envíos por mes** de su país.'],
      ] },
      { t: 'table', head: ['Componente del puntaje', 'Peso', 'Requiere'], ancho: [52, 18, 30], filas: [
        ['Tipo de contenido (programa 3; concientización y educación 2; beneficio y marca 1,5)', 'base', 'nada'],
        ['El área está entre las que declaró', '+2', 'consentimiento de salud'],
        ['Lo que mejor funciona en general (interés por envío, suavizado)', 'hasta +2', 'nada: no es perfilado'],
        ['Su afinidad con ese tipo de contenido (su historial)', '±1,5', '**personalización**'],
        ['«A quienes les interesó X también les interesó esto» (coseno entre contenidos)', 'hasta +3', '**personalización**'],
      ] },
      { t: 'p', x: 'Cada recomendación sale con su porqué en texto, para que el equipo y la persona entiendan por qué le llegó.' },
      { t: 'img', src: 'img/recomendaciones.png', pie: 'Ejemplo con datos sintéticos: el siguiente mejor contenido por persona (id seudónimo), con el puntaje, si está personalizado y el porqué.' },
    ],
  },
  {
    id: 'pantalla',
    titulo: 'Cómo se ve',
    para: 'gerentes',
    bloques: [
      { t: 'p', x: 'En la pestaña **Relacionamiento** se eligen las tablas (las dos propias son obligatorias; las públicas, opcionales) y se analiza. Arriba, el resumen; el último número dice cuántos envíos del historial hoy no cumplirían.' },
      { t: 'img', src: 'img/tarjetas.png', pie: 'Contactos y su porcentaje contactable, recomendaciones y envíos a revisar con compliance.' },
      { t: 'img', src: 'img/embudo_bloqueos.png', pie: 'El embudo de la base y por qué no se envía lo que no se envía. El motivo más común en el ejemplo es «área no declarada»: el programa no infiere enfermedades.' },
      { t: 'img', src: 'img/cobertura.png', pie: 'El mercado sin alcanzar: casos estimados con censo y prevalencias contra la base. Las celdas con menos de 10 personas no se publican.' },
      { t: 'img', src: 'img/politicas.png', pie: 'Las reglas por país, con su ley, autoridad, tope de envíos y si legal ya las validó.' },
    ],
  },
  {
    id: 'kpis',
    titulo: 'Qué se mide',
    para: 'gerentes',
    bloques: [
      { t: 'table', head: ['KPI', 'Definición', 'Para qué'], ancho: [24, 44, 32], filas: [
        ['% contactable', 'Contactables / captados', 'Calidad de la captación.'],
        ['% con cada consentimiento', 'Con comercial, salud o personalización / contactables', 'Qué tanto se puede hacer con la base.'],
        ['Alcance', 'Personas con al menos un envío', 'Cobertura de la comunicación.'],
        ['Apertura y CTR', 'Aperturas y clics / envíos, por contenido, tipo y canal', 'Qué contenido interesa.'],
        ['Conversión', 'Inscripciones al programa y canjes / envíos', 'Valor para el paciente y para el negocio.'],
        ['Bajas y quejas', 'Bajas y quejas / envíos', 'Si se está cansando a la gente.'],
        ['Penetración por zona', 'Captados del área / casos estimados', 'Dónde está el mercado latente sin alcanzar.'],
        ['Envíos a revisar', 'Envíos del historial que no cumplen las reglas de hoy', 'Cumplimiento: tiene que ser cero.'],
      ] },
    ],
  },
  {
    id: 'fabric',
    titulo: 'En Fabric y Power BI, junto a lo que ya hay',
    para: 'tecnicos',
    bloques: [
      { t: 'p', x: 'Todo sale en dos formatos desde el botón **Power BI y Fabric** o desde un notebook (`mv.relacionamiento(...)` y `mv.relacionamiento_para_powerbi(...)`):' },
      { t: 'ul', items: [
        '**Tablas del tablero** (`relacionamiento_*`) y `medidas_relacionamiento.dax`: embudo, KPIs por contenido, recomendaciones, bloqueos, envíos a revisar, cobertura, escucha y farmacovigilancia.',
        '**Modelo estrella** en `modelo_fabric/`, con `crear_tablas.sql` (DDL Delta), `modelo.json` (relaciones) y `cargar_en_lakehouse.py` (la celda que las carga).',
      ] },
      { t: 'table', head: ['Tabla', 'Grano', 'Se relaciona con'], ancho: [28, 36, 36], filas: [
        ['dim_geografia', 'país · ciudad · barrio', 'contactos, población, prevalencias, escucha, cobertura'],
        ['dim_contacto', 'persona (id seudónimo), con consentimientos', 'interacciones, recomendaciones, puente de áreas'],
        ['dim_contenido · dim_producto · dim_area', 'catálogo', 'interacciones, recomendaciones, prevalencias'],
        ['dim_fecha', 'día', 'interacciones, recomendaciones, escucha'],
        ['fact_interacciones', 'evento', '—'],
        ['fact_poblacion · fact_prevalencia', 'zona · sexo · edad · NSE', '—'],
        ['fact_escucha · fact_cobertura', 'país · semana · tema / zona · segmento', '—'],
      ] },
      { t: 'p', x: 'Las claves sustitutas salen de un hash del nombre normalizado: son **estables entre cargas** (sirven para un MERGE incremental o para migrar de entorno) y cada dimensión trae su columna `*_clave` sin tildes para relacionarse con las mismas dimensiones de **Analysis Services** o del **data warehouse** (país, producto, área). Así, las ventas que ya están en el modelo corporativo se cruzan con la base y el mercado sin rehacer nada.' },
      { t: 'callout', tipo: 'info', titulo: 'Lo que no entra al modelo', x: 'Mail, teléfono, nombre, documento, autores y textos de redes. Los datos que identifican viven en el CRM, con acceso restringido; el Lakehouse sólo ve el id seudónimo.' },
    ],
  },
  {
    id: 'controles',
    titulo: 'Riesgos y controles',
    para: 'legal',
    bloques: [
      { t: 'table', head: ['Riesgo', 'Control en el programa'], ancho: [36, 64], filas: [
        ['Promocionar un producto bajo receta al público', 'Regla «receta al público» antes del puntaje; condición de venta desconocida = receta.'],
        ['Usar un dato de salud sin permiso', 'Se descarta al cargar y se avisa; el área exige consentimiento de salud.'],
        ['Inferir una enfermedad', 'Sólo lo declarado; el nivel socioeconómico es el de la zona, no el de la persona.'],
        ['Reidentificar a alguien en una tabla agregada', 'Supresión de celdas chicas (menos de 10 en la base, menos de 5 menciones en la escucha), también en la brecha.'],
        ['Cansar o molestar', 'Tope de envíos por país, ventana de 30 días, exclusión tras una queja, baja en un clic.'],
        ['Un evento adverso en redes', 'Conteo por producto y aviso a farmacovigilancia, que revisa caso por caso en la herramienta de escucha.'],
        ['Derechos de la persona', '`acceso` (todo lo que la base tiene de alguien) y `suprimir` (borra y deja una huella para que no se vuelva a importar).'],
        ['Envíos pasados que hoy no cumplen', 'Auditoría con el motivo, para revisar con compliance.'],
      ] },
    ],
  },
  {
    id: 'proximo',
    titulo: 'Próximos pasos',
    para: 'todos',
    bloques: [
      { t: 'steps', items: [
        ['Validar las reglas con legal', 'País por país, empezando por uno; cargar los ajustes validados y marcar «validado por legal».'],
        ['Diseñar la captación', 'Formularios con las cuatro casillas, aviso de privacidad y doble confirmación; una landing de concientización por área.'],
        ['Armar el catálogo', 'Contenidos tipificados (concientización, programa, beneficio, marca, educación médica) con su condición de venta y audiencia.'],
        ['Cargar las fuentes públicas', 'Censo y encuesta de salud de un país piloto; contratar la herramienta de escucha con su circuito de farmacovigilancia.'],
        ['Conectar Fabric', 'Subir el modelo estrella al Lakehouse y relacionarlo con el modelo corporativo de Analysis Services.'],
      ] },
    ],
  },
  {
    id: 'preguntas',
    titulo: 'Preguntas que van a aparecer',
    para: 'gerentes',
    bloques: [
      { t: 'qa', items: [
        ['¿No es más lento que comprar una base?', 'Al principio sí. Pero una base comprada con datos de salud no se puede usar legalmente, y una propia se puede usar todos los días, con mejor respuesta porque la gente eligió estar.'],
        ['¿Podemos usar el nivel económico para ofrecer productos caros?', 'El del barrio, sí, para planificar campañas y contenidos de venta libre. No se infiere el de la persona ni se usa para negarle información.'],
        ['¿Y si alguien escribe en redes que toma nuestro producto?', 'Cuenta como mención agregada. Si describe un posible efecto adverso, farmacovigilancia lo revisa en la herramienta de escucha. No se lo contacta para venderle.'],
        ['¿Qué pasa si legal dice que un país permite más?', 'Se carga el ajuste para ese país (por ejemplo, otro tope de envíos) y queda marcado como validado. El código no cambia.'],
        ['¿Sirve para médicos?', 'Sí: a profesionales registrados se les puede promocionar productos bajo receta y enviar educación médica; el recomendador los trata como otra audiencia.'],
      ] },
    ],
  },
];

const CIERRE = 'El programa recomienda como un marketplace, pero con una base que la gente eligió y reglas que van antes que el algoritmo. Así se puede medir todo y crecer sin que nadie pueda decir que lo rastreamos.';

module.exports = { META, KPIS, SECCIONES, CIERRE };
