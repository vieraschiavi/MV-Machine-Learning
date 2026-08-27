# Los videos del sitio, en tres idiomas

Seis archivos: `recorrido` y `tablero`, cada uno en castellano, inglés y
portugués, con **narración e imagen en el mismo idioma** y subtítulos propios.
Todo se regenera con comandos; no hay ningún paso a mano.

## La cadena

```
web/video/guiones.js          el texto y el segundo en que se dice cada frase
        │
        ├─▶ generar_voz.py         sintetiza la voz y la monta sobre el video
        │      (o recuperar_voz.py: rescata la voz del video anterior)
        │
        ├─▶ scripts/grabar_video.cjs   recorre el programa de verdad y filma
        │
        └─▶ generar_subtitulos.py      escribe los .vtt desde el mismo guion
```

Una sola fuente para las tres cosas. El subtítulo no puede decir algo distinto
de lo que se escucha porque sale del mismo archivo, y hay una prueba que lo
comprueba (`backend/tests/test_sitio.py`).

## Regenerar todo

```bash
# 1. backend levantado, con token
MV_API_TOKEN=tok-video ./scripts/run.sh

# 2. la voz: normalmente se sintetiza
python web/video/generar_voz.py
#    sin salida a internet, se rescata la del video anterior
python web/video/recuperar_voz.py recorrido es en pt

# 3. filmar (dos videos × tres idiomas)
MV_API_TOKEN=tok-video node scripts/grabar_video.cjs recorrido es
MV_API_TOKEN=tok-video node scripts/grabar_video.cjs tablero en

# 4. subtítulos
python web/video/generar_subtitulos.py
```

## Decisiones que no son obvias

**El dataset del video también habla el idioma del video.** Un KPI se llama
como la columna de la que sale, así que filmando el archivo en castellano el
video en inglés mostraba `MontoACobrarVencido` mientras la voz hablaba en
inglés. `examples/traducir.py` escribe los mismos datos con los nombres
traducidos —sólo renombra, no regenera— y el grabador elige el archivo según el
idioma. Los tres videos se pueden comparar cuadro a cuadro.

**La página tiene que cambiar el archivo, no sólo los textos.** Los seis videos
existían desde hacía semanas, pero `setLang()` llamaba a una función
`cambiarVideos()` que no estaba definida en ninguna parte: la página tiraba
`ReferenceError` en cada cambio de idioma y el visitante que elegía inglés
seguía escuchando la narración en castellano. El HTML no se compila, así que
nadie se enteró hasta que se miró la consola. Ahora hay una prueba que revisa
que ninguna página llame a una función que no existe.

**Los subtítulos van encendidos.** En la web el navegador no deja arrancar un
video con sonido sin un click, así que la mayoría lo mira mudo. Sin subtítulo
encendido, la grabación no dice una sola palabra en ningún idioma.

**El grabador espera a que la pantalla esté lista, no un tiempo fijo.** El mapa
de correlaciones se calcula la primera vez que se pide; sin esa espera, el
video mostraba un cartel de «Cargando» justo cuando la voz decía «el mapa de
correlaciones muestra de una qué variables se mueven juntas». Las escenas que
dependen de un cálculo se abren unos segundos antes y esperan al elemento.

**El ffmpeg de Playwright no sirve para montar la voz.** Viene compilado con
`--disable-everything`: no tiene códecs de audio ni los filtros `adelay`/`amix`.
El grabador busca uno completo —el de `imageio-ffmpeg`, que ya viene con las
dependencias de Python— y verifica que tenga `adelay` antes de usarlo.
