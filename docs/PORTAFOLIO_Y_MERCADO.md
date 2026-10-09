# Portafolio y mercado: contribución, mercado latente y agente de proyección

Dos piezas que trabajan juntas, en la pestaña **Portafolio y mercado** del
programa, desde un notebook de Fabric (`mv.contribucion`, `mv.mercado`) y en
Power BI:

1. **La matriz de contribución y mix** — la lámina de «una plataforma regional,
   con motores de crecimiento diferentes por mercado», calculada: quién
   sostiene el negocio, qué tan avanzado está su mix de presentaciones y qué
   conviene proteger, acelerar o desarrollar en cada mercado, molécula o marca,
   por área terapéutica.
2. **El agente de mercado** — proyecta lanzamientos y ventas mirando también a
   la gente que **no está en ninguna base de datos**: quien tiene síntomas y no
   consulta al médico, quien tiene el diagnóstico y no se trata. Los supuestos
   salen de estudios de mercado por país; si todavía no hay, el motor de IA
   propone una primera versión que queda marcada «a validar».

---

## 1. La matriz de contribución y mix

### Qué datos necesita

Una tabla de ventas con, como mínimo:

| Columna | Ejemplo | Para qué |
|---|---|---|
| entidad | `pais`, `molecula` o `marca` | cada burbuja |
| valor | `ventas_usd` | la contribución (eje Y y tamaño) |
| mix *(opcional)* | `presentacion` | el eje X: escalón de la terapia |
| grupo *(opcional)* | `area_terapeutica` | una matriz por área, con selector |
| período *(opcional)* | `periodo` (`2025 YTD`, `2026 YTD`) | crecimiento; se mide sobre el último |

Hace falta el mix **o** el período: sin mix, el eje X pasa a ser el
crecimiento contra el período anterior (útil para comparar marcas que no
tienen escalera de combinaciones).

### Cómo se calcula

* **Contribución** = ventas de la entidad / ventas del área (o del total). Tres
  niveles, como en la lámina: **alta** (>10 %), **media** (3–10 %) y **baja**
  (<3 %). Los umbrales se cambian.
* **Índice de mix** (eje X, de 0 a 1): promedio del escalón de cada
  presentación, ponderado por sus ventas. 0 es todo en monoterapia, 1 todo en
  el último escalón (triple). El escalón sale del nombre —`Olmesartán/HCTZ` es
  doble, `Olmesartán/Amlodipino/HCTZ` triple— o se pasa a mano con
  `niveles_mix` cuando las presentaciones tienen nombre de marca
  (`{"Marca": 1, "Marca HCT": 2, "Marca AM": 2, "Marca AM HCT": 3}`).
* **Acción**: alta → **proteger**, media → **acelerar**, baja → **desarrollar**.
* **Siguiente motor**: el primer escalón del mix donde la entidad está por
  debajo del 80 % de lo que pesa esa presentación en la región. Es la idea de
  la lámina hecha regla: *la oportunidad no está en uniformar el mix sino en
  activar el siguiente motor relevante en cada mercado*. Un mercado que ya
  está por encima de la región en todo dice «Consolidar el mix actual».
* **Lectura estratégica**: ESCALA (cuántas entidades explican qué parte),
  DIRECCIÓN (peso de las combinaciones) y DIVERSIDAD (rango del índice de mix).

---

## 2. El agente de mercado

### El embudo

Por país y segmento (hombres y mujeres por defecto; puede ser edad, región…):

```
población → prevalentes → diagnosticados → tratados → en la clase → en la marca
                │               │
                │               └─ diagnosticados sin tratamiento   ┐
                └─ sin diagnóstico (síntomas, no consulta)          ┘  = mercado latente
```

| Parámetro | Qué es | Tipo |
|---|---|---|
| `poblacion` | personas del segmento | obligatorio |
| `prevalencia` | fracción con la enfermedad | obligatorio |
| `diagnosticados` | fracción de prevalentes con diagnóstico | obligatorio |
| `tratados` | fracción de diagnosticados con tratamiento | obligatorio |
| `clase` | fracción de tratados en la clase o molécula | opcional (1) |
| `participacion` | participación de la marca en la clase | opcional |
| `dosis_dia`, `dias_tratamiento`, `adherencia` | unidades por paciente | opcional, **se avisa** si falta |
| `precio_unidad` | para pasar a valor | opcional |
| `diagnosticados_objetivo`, `tratados_objetivo` | lo alcanzable con campañas | opcional |

Cada supuesto lleva **valor, mínimo, máximo, origen y fuente**. Las tasas se
aceptan en fracción o en porcentaje (`30` se lee como 0,30 y se avisa). La
plantilla vacía se baja desde la pantalla o con `GET /api/mercado/plantilla`.

### De dónde salen los números

1. **Estudios de mercado** (los que la empresa ya compra o encarga: encuestas
   nacionales de salud, estudios poblacionales, auditorías de prescripción):
   se cargan como un dataset con el formato de la plantilla. **Siempre mandan.**
2. **Propuesta del motor de IA** (botón *Proponer supuestos con IA*): el agente
   pide al proveedor configurado en la pestaña de IA el embudo por país y
   segmento, y la **casuística del área terapéutica**: subdiagnóstico por sexo
   y edad, brecha de tratamiento, escalonamiento mono → doble → triple, dosis y
   titulación, adherencia, acceso y genéricos. Todo queda marcado
   `IA (a validar)`, con la consigna explícita de no inventar citas.
3. Al combinar, cada supuesto de un estudio **pisa** al de la IA. El resultado
   dice el **nivel de evidencia**: `estudios`, `mixta` o `solo IA`.

> Un modelo de lenguaje puede dar cifras desactualizadas y citar estudios que
> no existen. Por eso nada de lo que propone se presenta como dato: es un punto
> de partida para pedirle a inteligencia de mercado lo que falta.

### Qué devuelve

* **Mercado actual y latente por país**, con rango P10–P90 (simulación de los
  supuestos entre su mínimo y su máximo).
* **Lectura por país**: *desarrollar* si el subdiagnóstico domina (≥40 % de los
  prevalentes sin diagnóstico: detección, tamizaje, educación, empezando por el
  segmento que menos consulta); *acelerar* si hay muchos diagnosticados sin
  tratar (activación médica, adherencia, acceso); *proteger* si el mercado ya
  está tratado.
* **Tornado**: qué supuesto mueve más el resultado → cuál validar primero.
* **Lanzamiento**: curva mensual de adopción (difusión de Bass, 90 % del pico
  en los meses indicados; forma rápida, media o lenta) hacia la participación
  al pico, con P10–P90.
* **Contraste con la historia** (si se pasan las ventas reales por país):
  si los supuestos explican lo que se vende, si se vende *más* que todo el
  mercado tratado (supuestos subestimados o canal fuera del embudo) y si una
  proyección por historia supera el techo del mercado tratado.

### Lo que el rango no es

Sin historia propia —un lanzamiento— no hay backtest posible: la curva sale de
los supuestos. El P10–P90 mide cuánto se mueve el resultado con lo que no se
sabe de los supuestos; **no** es el error de un modelo medido contra ventas
reales. Cuando el producto ya vende, la proyección por historia (pestaña
*Proyecciones*, con su backtest) y el embudo se controlan entre sí con el
contraste.

---

## 3. En Power BI: la página con el formato de la lámina

### Generar las tablas

Desde la pantalla: **Paquete para Power BI** (baja un zip). Desde un notebook
de Fabric:

```python
from app import notebook as mv

matriz = mv.contribucion(ventas, entidad="pais", valor="ventas_usd",
                         mix="presentacion", grupo="area_terapeutica", periodo="periodo")
analisis = mv.mercado(estudios=estudios,
                      lanzamiento={"pico": 0.12, "meses_al_pico": 18, "horizonte": 36},
                      inicio="2027-01")
mv.portafolio_para_powerbi("/lakehouse/default/Files/mv/portafolio",
                           contribucion=matriz, mercado=analisis)
```

Para la vista por **moléculas o marcas** dentro de cada área, la misma llamada
con `entidad="molecula"` (o `"marca"`) y `etiqueta="moléculas"`.

Salen las tablas (`portafolio_*`, `mercado_*`) y el kit:

| Archivo | Para qué |
|---|---|
| `tema_portafolio.json` | Vista → Temas → Buscar temas |
| `medidas_portafolio.dax` | las medidas: tarjetas, lectura, banda de acciones, mercado |
| `burbujas_contribucion.vl.json` | la matriz de burbujas para el visual **Deneb** |

### Armar la página «Contribución»

1. **Segmentador** de `portafolio_entidades[grupo]` en **selección única**
   (las contribuciones ya vienen calculadas dentro de cada área; sumar dos
   áreas mezcla denominadores).
2. **Banda superior** — tres tarjetas: `[Ventas total]`, `[Combinaciones]` con
   `[Texto combinaciones]` debajo, `[Concentracion top]` con
   `[Texto concentracion]`.
3. **Matriz de burbujas** — visual Deneb (certificado, desde AppSource): se
   arrastran `entidad`, `contribucion`, `indice_mix`, `accion`, `etapa_mix` y
   `siguiente_motor` de `portafolio_entidades` (sin resumir: «No resumir») y se
   pega el contenido de `burbujas_contribucion.vl.json`. Sale con las tres
   zonas de mix de fondo, las franjas baja/media/alta y las etiquetas
   «México 31,2 %». **Sin Deneb**: gráfico de dispersión nativo con X =
   `indice_mix`, Y = `contribucion`, tamaño = `contribucion`, leyenda =
   `accion` y color por `[Color accion]`; pierde las zonas de fondo.
4. **Lectura estratégica** — tres tarjetas de texto con `[Lectura escala]`,
   `[Lectura direccion]` y `[Lectura diversidad]`.
5. **Banda inferior** — tres tarjetas con `[Lista proteger]`,
   `[Lista acelerar]` y `[Lista desarrollar]`, tituladas «¿Qué debemos
   proteger?», «¿Qué debemos acelerar?», «¿Qué debemos desarrollar?».
6. Para la contribución de cada **área terapéutica** al total:
   `portafolio_grupos` en un gráfico de barras (`grupo`, `contribucion`) con
   `principales` en la información sobre herramientas.

### Página «Mercado»

* Embudo: visual de embudo con `mercado_embudo[etapa]` ordenado por `orden` y
  `pacientes`, segmentado por `pais` y `segmento`.
* Tarjetas: `[Pacientes en clase P50]`, `[Mercado latente P50]`,
  `[Latente sobre prevalentes]`, `[Supuestos a validar]`.
* Tabla `mercado_lecturas` (país, acción, lectura) y barras de
  `mercado_sensibilidad[oscilacion]` por `parametro` (tornado).
* Línea de `mercado_lanzamiento`: `mes` en X, `unidades_p50` (o `valor_p50`)
  y la banda `_p10`/`_p90`, filtrando `pais = "Total"` o por país.

---

## Lo que se probó y lo que no

| Pieza | Estado |
|---|---|
| Embudo, latente, P10–P90, tornado, lanzamiento y contraste | probado (`test_mercado.py`) |
| Agente: propuesta, filtros, origen, estudios que pisan, lecturas | probado con IA simulada (`test_agente_mercado.py`) |
| Matriz de contribución, índice de mix, siguiente motor, lectura | probado (`test_contribucion.py`) |
| Tablas y kit de Power BI; columnas que usan las medidas DAX y Deneb | probado (`test_powerbi_portafolio.py`) |
| API y notebook | probado (`test_api_mercado.py`, `test_notebook_portafolio.py`) |
| Especificación Deneb compilada y dibujada con Vega-Lite 5 | probado fuera de la suite, con los datos de ejemplo |
| Pantalla «Portafolio y mercado» recorrida en Chromium | probado fuera de la suite |
| Propuesta contra un proveedor de IA real | **no probado en este entorno: no hay clave configurada** |
| Carga del kit en un Power BI Desktop real | **no probado: no hay Power BI en el entorno de desarrollo** |

Los ejemplos (`examples/portafolio_sintetico.csv`,
`examples/estudios_mercado_sintetico.csv`) son **inventados**: marcas,
moléculas propias, ventas y tasas. Los genera `examples/generar_portafolio.py`.
