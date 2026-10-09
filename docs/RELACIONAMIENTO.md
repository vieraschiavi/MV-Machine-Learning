# Relacionamiento con consentimiento

Una base propia de pacientes, cuidadores y profesionales, el «siguiente mejor
contenido» para cada persona (el mismo tipo de recomendador que un
marketplace) y la medición completa, **dentro de lo que la ley y cada persona
permiten**. Está en la pestaña **Relacionamiento**, en
`mv.relacionamiento(...)` desde un notebook y sale a Power BI y a un Lakehouse
de Fabric.

Guía para gerentes, técnicos y legal, con la estrategia de comunicación por
canal: [Word](relacionamiento/Relacionamiento-con-Consentimiento.docx) ·
[web](relacionamiento/Relacionamiento-con-Consentimiento.html).

> El mapa legal y las reglas por país son **conservadores por defecto** y
> quedan marcados «a validar por legal». El programa aplica reglas; no da
> asesoramiento jurídico.

## Principios

1. **Sólo datos propios y consentidos**, por finalidad: contacto, comercial,
   salud y personalización. Lo vacío o dudoso es «no».
2. **Nunca se infiere una condición de salud**: se usa lo que la persona
   declaró (áreas de interés, productos recetados).
3. **Las reglas van antes del algoritmo**: el recomendador sólo puntúa lo que
   se le puede enviar a esa persona.
4. **Lo público entra agregado** (censo, encuestas de salud, escucha social) y
   se cruza por el territorio declarado, nunca por la persona. Las celdas
   chicas no se publican.
5. **Minimización**: la analítica usa un id seudónimo; mail, teléfono, nombre
   y documento se descartan al cargar y viven en el CRM.

## Tablas de entrada

Hay plantillas en la pantalla y en `GET /api/relacionamiento/plantilla/{tabla}`,
y un ejemplo sintético completo en `examples/` (`generar_relacionamiento.py`).

| Tabla | Obligatoria | Columnas |
|---|---|---|
| contactos | sí | `id_contacto`, `pais`, `ciudad`, `barrio`, `sexo`, `rango_edad`, `tipo` (paciente, cuidador, profesional), `consiente_contacto`, `consiente_marketing`, `consiente_salud`, `consiente_perfilado`, `doble_optin`, `baja`, `areas_interes`, `productos_recetados` (listas con `;`) |
| contenidos | sí | `id_contenido`, `titulo`, `tipo` (concientizacion, programa_paciente, promocion_marca, beneficio, educacion_medica), `area_terapeutica`, `producto`, `condicion_venta` (receta, venta_libre; lo desconocido = receta), `audiencia`, `paises` |
| interacciones | no | `id_contacto`, `id_contenido`, `fecha`, `evento` (envio, apertura, clic, inscripcion, canje, baja, queja) |
| población | no | `pais`, `ciudad`, `barrio`, `sexo`, `rango_edad`, `nse`, `poblacion` (censo) |
| prevalencias | no | `pais`, `area_terapeutica`, `sexo`, `rango_edad` (o «Total»), `prevalencia` (0–1), `fuente` |
| escucha | no | `fecha`, `pais`, `texto` (autores, URL e ids se descartan) |

## Reglas de elegibilidad (`core/consentimiento.py`)

Para cada par persona × contenido, el **primer** motivo que bloquea:

| Motivo | Cuándo |
|---|---|
| `baja` | pidió la baja (en el CRM o en un envío) |
| `sin_consentimiento_contacto` | no consintió que lo contacten |
| `sin_doble_optin` | el país la exige (ajuste de legal) y no la tiene |
| `pais` | el contenido no está habilitado en su país |
| `audiencia` | educación médica a quien no es profesional; programa o beneficio a un profesional |
| `receta_al_publico` | cualquier contenido que nombre un producto bajo receta, a quien no es profesional (salvo programa o beneficio de una receta declarada); con producto y sin condición de venta se asume receta |
| `venta_libre_al_publico` | promoción de venta libre donde legal no la habilitó |
| `sin_consentimiento_marketing` | promoción o beneficio sin permiso comercial |
| `sin_consentimiento_salud` | contenido de un área (o programa) sin permiso de salud |
| `area_no_declarada` | el área no está entre las que declaró |
| `programa_sin_receta_declarada` | programa o beneficio de un producto bajo receta sin la receta declarada |

Las políticas por país (`Politica`) traen ley, autoridad sanitaria, tope de
envíos en 30 días (4), doble opt-in y promoción al público. Legal ajusta por
país con `ajustes={"Uruguay": {"frecuencia_max_30d": 2, "validado_por_legal": True}}` (el país
se reconoce con o sin tildes y por su código: «Mexico», «MX»). Habilitar
`promocion_receta_a_publico` exige `validado_por_legal: true` en el mismo ajuste.

Los consentimientos aceptan sí/no, 1/0 y verdadero/falso; lo vacío es «no». La
`baja` al revés: un valor que no es claramente «no» se respeta como baja, con
aviso. Los ids se normalizan igual en todas las tablas (`1`, `1.0` y `"1"` son
el mismo contacto) y las fechas con zona horaria se pasan a UTC.

## Recomendador (`core/relacionamiento.py`)

Entre lo elegible, fuera lo enviado en los últimos 30 días, lo ya convertido y
lo que motivó una queja; se respeta el cupo del mes. Puntaje:

* peso por tipo (programa 3; concientización y educación 2; beneficio y marca 1,5);
* +2 si el área es una de las declaradas;
* +2 × interés global del contenido (suavizado hacia el promedio; no es perfilado);
* con **consentimiento de personalización**: +3 × (afinidad con el tipo − 0,5)
  y +3 × similitud coseno con un contenido que le interesó («a quienes les
  interesó X también les interesó esto»; mínimo dos personas en común).

Cada recomendación trae su porqué en texto.

## KPIs y auditoría

* **Embudo** por país (y Total): captados → contactables → con cada
  consentimiento → alcanzados → activos → convertidos.
* **Por contenido**: envíos, aperturas, clics, conversiones, bajas, quejas y sus tasas.
* **Bloqueos**: pares por país, tipo de contacto, tipo de contenido y motivo.
* **Envíos no elegibles**: lo que se envió y con los consentimientos de hoy no
  cumpliría (lo enviado antes de una baja no cuenta).
* **Frecuencia excedida** por país.

## Fuentes públicas

* `core/territorio.py` — `enriquecer` (NSE de la zona declarada), `cobertura`
  (casos estimados con censo × prevalencia contra captados del área, por
  ciudad o barrio y opcionalmente sexo, edad o NSE). Captados = pacientes o
  cuidadores sin baja, con el área declarada y permiso de salud. Los conteos de
  1 a 9 (en la base, en los captados o en su complemento) se suprimen, también
  en la brecha, con supresión complementaria dentro de cada zona. La
  prevalencia usa el estrato más específico (sexo y edad → sexo → edad → total)
  y promedia fuentes repetidas.
* `core/escucha.py` — menciones por país, semana y tema con sentimiento
  (léxico es/pt con negación), términos frecuentes y conteo de **posibles
  eventos adversos** por producto propio para farmacovigilancia. Sin autores ni
  textos; celdas de menos de 5 menciones fuera.

## Las cinco etapas para ponerlo en marcha

1. **Validación legal** (`core/politicas_legales.py`). Las reglas de cada país
   (promoción de receta y de venta libre al público, doble opt-in, tope de
   envíos en 30 días) se guardan por workspace con historial. Aflojar una regla
   exige la firma de legal (`validado_por`) y la norma que la respalda.
   `GET /api/relacionamiento/politicas/planilla` baja un Excel con una pregunta
   por regla y país; legal lo completa y `POST …/politicas/planilla` aplica sólo
   las filas firmadas.
2. **Captación** (`core/registro_consentimientos.py`). Un libro de eventos
   (`otorga`, `retira`, `confirma`, `baja`) con fecha, canal y la versión del
   texto aceptado (`v-` + hash del texto): el último evento de cada finalidad
   manda sobre la tabla de contactos. `GET /api/relacionamiento/formulario` da
   el formulario con las cuatro casillas sin marcar (contacto obligatorio) que
   envía al CRM; `GET …/textos-consentimiento` da los textos en es y pt.
3. **Catálogo** (`core/catalogo.py`). `POST /api/relacionamiento/revisar-catalogo`
   revisa cada contenido antes de cargarlo (errores, avisos e información) y,
   con la base de contactos, cuántas personas lo podrían recibir hoy.
4. **Fuentes públicas** (`core/fuentes_publicas.py`). Prevalencias de la OMS
   (hipertensión, diagnóstico y tratamiento; diabetes; obesidad), población por
   sexo y edad del Banco Mundial, censos publicados a lo ancho y el CSV de
   Google Trends. `POST /api/relacionamiento/fuentes/publicas` los guarda como
   dataset; los supuestos de la OMS entran al agente de mercado con su
   intervalo como mínimo y máximo.
5. **Fabric** (`core/fabric_relacionamiento.py`). Ver abajo: carga incremental
   por MERGE, modelo semántico en TMDL y notebook.

## Salida

`POST /api/relacionamiento/exportar` (o `mv.relacionamiento_para_powerbi`):

* `relacionamiento_*.csv|parquet` + `medidas_relacionamiento.dax` — el tablero.
* `modelo_fabric/` — modelo estrella (`dim_geografia`, `dim_contacto`,
  `dim_contenido`, `dim_producto`, `dim_area`, `dim_fecha`,
  `puente_contacto_area`, `fact_interacciones`, `fact_recomendaciones`,
  `fact_consentimientos`, `fact_busquedas`, `fact_poblacion`,
  `fact_prevalencia`, `fact_escucha`, `fact_cobertura`) con
  `crear_tablas.sql` (Delta), `modelo.json` (relaciones) y
  `cargar_en_lakehouse.py` (primera carga). Claves estables por hash del
  nombre normalizado y columnas `*_clave` para relacionarse con las
  dimensiones de Analysis Services o del data warehouse.
* `modelo_fabric/merge_incremental.py` y `notebook_relacionamiento.ipynb` — las
  cargas siguientes. Las dimensiones hacen MERGE por su clave (actualiza y
  agrega); los hechos y el puente reemplazan la porción que trae la carga (los
  días de interacciones o consentimientos, la foto del día de recomendaciones,
  las zonas de población y cobertura). Cada carga trae completos los días o
  zonas que cubre: repetirla no duplica nada y dos clics iguales del mismo día
  siguen siendo dos. El notebook termina contando claves huérfanas y con
  `OPTIMIZE`. `fabric_relacionamiento.fusionar` es la misma lógica en pandas y
  es la que prueban los tests.
* `modelo_fabric/Relacionamiento.SemanticModel/` — el modelo semántico en TMDL,
  Direct Lake sobre el Lakehouse, con la estructura que usa la integración de
  Fabric con Git: tablas, relaciones (la de producto → área queda inactiva para
  que no haya dos caminos) y medidas (contactables, envíos, tasas de apertura,
  clic, conversión y baja, consentimientos otorgados y retirados, casos
  estimados, penetración, sentimiento neto, interés de búsqueda). En
  `definition/expressions.tmdl` se reemplazan `SERVIDOR_SQL_DEL_LAKEHOUSE` y
  `NOMBRE_DEL_LAKEHOUSE` por los del workspace. Antes de escribirlo,
  `verificar_tmdl` revisa que cada relación y cada medida apunten a algo que
  existe.

## Derechos de la persona

`relacionamiento.acceso(contactos, interacciones, id)` devuelve todo lo que la
base tiene de alguien; `relacionamiento.suprimir(...)` lo borra con su
historial y devuelve la **huella** (SHA-256 del id) para la lista de supresión,
que evita volver a importarlo.
