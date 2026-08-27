"""Pone en el guion el segundo real en que empieza a hablar cada frase.

Los tiempos estaban escritos a mano y a ojo. Con frases largas eso se nota: la
voz sigue hablando de una pantalla que la imagen ya dejó atrás, o al revés, la
pantalla cambia y la voz todavía está en lo anterior. Mirar el guion no alcanza
para saber cuánto dura una frase — depende del idioma, de la voz y de dónde
respira el sintetizador.

Así que se mide. Cada frase se sintetiza, se mide su duración real y el arranque
de la siguiente sale de ahí, con una pausa de aire en el medio. El grabador usa
esos mismos segundos para mover la pantalla, así que la imagen acompaña a la voz
por construcción y no por casualidad.

Se corre después de tocar cualquier texto de `guiones.js`, y antes de grabar.

Uso:
    python web/video/cronometrar.py                 # todo
    python web/video/cronometrar.py recorrido es    # sólo un video y un idioma
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import generar_subtitulos
from generar_voz import IDIOMAS, VIDEOS, clip, duracion

AQUI = Path(__file__).resolve().parent
ARRANQUE = 0.6      # aire antes de la primera frase
PAUSA = 0.8         # silencio entre una frase y la siguiente


def cronometrar(nombre: str, lang: str, pasos: list[dict]) -> list[dict]:
    salida, duraciones, cursor = [], [], ARRANQUE
    for i, paso in enumerate(pasos):
        salida.append({"t": round(cursor, 1), "text": paso["text"]})
        dur = duracion(clip(nombre, lang, i, paso["text"]))
        duraciones.append(dur)
        cursor += dur + PAUSA
    # Los subtítulos se escriben acá mismo, con las duraciones que se acaban de
    # medir. Dejarlos para otro paso es lo que hacía que un cambio en el guion
    # quedara a medio aplicar: el audio decía lo nuevo y el cartel, lo viejo.
    generar_subtitulos.escribir(nombre, lang, salida, duraciones)
    print(f"  {nombre} [{lang}]: {len(pasos)} tramos, la voz termina "
          f"en {cursor - PAUSA:.1f} s")
    return salida


def main(videos: tuple[str, ...], idiomas: tuple[str, ...]) -> None:
    archivo = AQUI / "guiones.js"
    js = archivo.read_text(encoding="utf-8")
    m = re.search(r"^window\.NARRACION\s*=\s*(\{.*?^\});", js, re.S | re.M)
    if not m:
        raise SystemExit("No encontré window.NARRACION en guiones.js")
    narracion = json.loads(m.group(1))

    for nombre in videos:
        for lang in idiomas:
            if lang not in narracion.get(nombre, {}):
                continue
            narracion[nombre][lang] = cronometrar(nombre, lang,
                                                  narracion[nombre][lang])

    cuerpo = json.dumps(narracion, ensure_ascii=False, indent=2)
    archivo.write_text(js[:m.start()] + f"window.NARRACION = {cuerpo};\n",
                       encoding="utf-8")
    print(f"escrito: {archivo.name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    pedidos = tuple(a for a in args if a in VIDEOS) or VIDEOS
    langs = tuple(a for a in args if a in IDIOMAS) or IDIOMAS
    main(pedidos, langs)
