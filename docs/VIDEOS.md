# Los videos del sitio, en tres idiomas

Seis archivos: `recorrido` y `tablero`, cada uno en castellano, inglés y
portugués, con **narración e imagen en el mismo idioma** y subtítulos propios.
Todo se regenera con comandos; no hay ningún paso a mano.

## La cadena

```
web/video/guiones.js          el texto de cada frase
        │
        ├─▶ cronometrar.py         sintetiza, mide y escribe el segundo real de
        │                          cada frase — y los subtítulos
        │
        ├─▶ scripts/grabar_video.cjs   recorre el programa de verdad y filma
        │
        └─▶ generar_voz.py         monta la voz sobre un video ya grabado
```

Una sola fuente para las tres cosas. El subtítulo no puede decir algo distinto
de lo que se escucha porque sale del mismo archivo, y hay una prueba que lo
comprueba (`backend/tests/test_sitio.py`).

## Regenerar todo

```bash
# 1. backend levantado, con token
MV_API_TOKEN=tok-video ./scripts/run.sh

# 2. después de tocar cualquier texto de guiones.js
python web/video/cronometrar.py

# 3. filmar (dos videos × tres idiomas)
MV_API_TOKEN=tok-video node scripts/grabar_video.cjs recorrido es
MV_API_TOKEN=tok-video node scripts/grabar_video.cjs tablero en
```

`generar_voz.py` sirve para volver a montar la voz sobre un video ya filmado sin
regrabar la imagen. `recuperar_voz.py` rescata la narración de un video anterior
cuando no se puede sintetizar.

## Por qué el audio y la imagen van juntos

Cuatro cosas los desincronizaban, y las cuatro están resueltas en el código:

**Los tiempos estaban escritos a ojo.** Cuánto dura una frase depende del
idioma, de la voz y de dónde respira el sintetizador; adivinarlo deja a la voz
hablando de una pantalla que la imagen ya dejó atrás. `cronometrar.py` sintetiza
cada frase, la mide y escribe el segundo en que arranca la siguiente. El
grabador usa esos mismos segundos para mover la pantalla.

**El reloj del grabador no era el del video.** Playwright empieza a grabar
cuando se crea el contexto, pero el recorrido arranca recién cuando la
aplicación cargó. Esos segundos de diferencia corrían el video entero contra el
audio, que se monta contando desde el primer cuadro. Ahora se miden y se
recortan.

**Las pantallas que calculan algo llegaban tarde.** El perfil, el mapa de
correlaciones y el plan de ETL tardan la primera vez que se abren —el plan, más
de veinte segundos—, así que la voz explicaba un cartel de «Cargando». Se
visitan antes de arrancar el reloj, en el tramo que después se recorta.

**Una escena lenta corría a todas las demás.** El bucle esperaba a que cada
escena terminara. Ahora cada una arranca en su segundo exacto y lo que tarde es
problema de ella: manda el guion, no lo que tarde la aplicación.

**Las escenas se agarran del contenido, no de una cantidad de píxeles.** Bajar
«420 píxeles» deja la pantalla donde el alto del momento la deje: la voz decía
«las notas escritas a mano» sobre la tarjeta del importe adeudado. Ahora cada
escena lleva a la vista lo que la frase nombra —la ficha del dataset, la tarjeta
de esa columna— y el scroll a ciegas quedó sólo como respaldo.

**Los selectores cuelgan de `.view.active`.** Las pantallas ya visitadas quedan
en el documento, ocultas. Un `.tab` suelto podía ser el de Resultados, y la
espera del primer indicador del tablero encontraba el del Panel —oculto, así que
se agotaban los treinta segundos enteros antes de seguir.

**Adelantarse a una pantalla le come el final a la frase anterior.** Las escenas
que abren algo que tarda arrancan unos segundos antes; con tres segundos de
adelanto, la frase que todavía se escuchaba terminaba sobre la pantalla
siguiente. Con todo precalentado alcanza con uno.

## Otras decisiones que no son obvias

**El dataset del video también habla el idioma del video.** Un KPI se llama como
la columna de la que sale, así que filmando el archivo en castellano el video en
inglés mostraba `MontoACobrarVencido` mientras la voz hablaba en inglés.
`examples/traducir.py` escribe los mismos datos con los nombres traducidos
—sólo renombra, no regenera— y el grabador elige el archivo según el idioma.

**La narración no nombra lo técnico.** El número del holdout se ve en pantalla;
la voz no dice «AUC» ni «holdout». Quien mira el video decide si le sirve el
producto, no si entiende la sigla: «cuanto más cerca de uno, mejor separa a los
que pagan de los que no» explica lo mismo y lo entiende cualquiera.

**El audio se cachea por texto, no por número de tramo.** Al lado de cada mp3
queda el texto que lo generó. Sin eso, cambiar una frase dejaba el audio viejo
en su lugar y el video seguía diciendo lo de antes mientras el subtítulo mostraba
lo nuevo.

**La página tiene que cambiar el archivo, no sólo los textos.** Los seis videos
existían desde hacía semanas, pero `setLang()` llamaba a una función
`cambiarVideos()` que no estaba definida en ninguna parte: el visitante que
elegía inglés seguía escuchando la narración en castellano. El HTML no se
compila, así que nadie se enteró. Ahora hay una prueba que revisa que ninguna
página llame a una función que no existe.

**Los subtítulos van encendidos.** En la web el navegador no deja arrancar un
video con sonido sin un click, así que la mayoría lo mira mudo. Sin subtítulo
encendido, la grabación no dice una sola palabra en ningún idioma.

**El ffmpeg de Playwright no sirve para montar la voz.** Viene compilado con
`--disable-everything`: no tiene códecs de audio ni los filtros `adelay`/`amix`.
El grabador busca uno completo —el de `imageio-ffmpeg`, que ya viene con las
dependencias de Python— y verifica que tenga `adelay` antes de usarlo.

**edge-tts necesita que le pasen el proxy.** Detrás de un proxy que intercepta
el tráfico, sin configurarlo la conexión se intenta directa y el error llega
como «certificado inválido» — que hace buscar el problema en los certificados
cuando lo único que faltaba era decirle por dónde salir. Sale de `HTTPS_PROXY`.
