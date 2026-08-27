"""Escribe los subtítulos WebVTT de cada video, en los tres idiomas.

Salen del mismo `guiones.js` que usa la narración, así que el subtítulo dice
palabra por palabra lo que se escucha: no hay forma de que la voz diga una cosa
y el texto de abajo otra.

Los subtítulos no son un adorno de accesibilidad. En la web la mayoría mira el
primer video **sin sonido** —el navegador ni siquiera deja arrancar con audio
sin un click—, así que sin subtítulos el visitante que eligió inglés ve una
grabación muda y se va sin haber leído una sola palabra en su idioma.

Cada línea termina donde empieza la siguiente. Cuando este archivo lo llama
`generar_voz.py`, que sí sabe cuánto dura cada clip de voz, el final se recorta
a la duración real y el subtítulo se apaga cuando la frase termina de sonar.

Uso:
    python web/video/generar_subtitulos.py           # los tres idiomas
    python web/video/generar_subtitulos.py es en     # sólo algunos
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
IDIOMAS = ("es", "en", "pt")
COLA_ULTIMO = 7.0          # cuánto queda en pantalla la última línea
RESPIRO = 0.15             # hueco entre una línea y la siguiente
MIN_CARTEL = 1.4           # lo menos que un cartel puede estar en pantalla

# Dónde se planta el cartel dentro del cuadro. Sin esto el navegador lo ubica
# solo y, con la barra de controles a la vista, lo sube hasta la mitad del
# video: justo encima de lo que se está mostrando. `line:-1` lo pega abajo y
# `size` le pone un ancho máximo para que las líneas no crucen toda la pantalla.
UBICACION = "line:-1 align:center size:84%"


def leer_guiones() -> dict:
    """`window.NARRACION = {...};` → dict. La misma fuente que lee la web."""
    js = (AQUI / "guiones.js").read_text(encoding="utf-8")
    m = re.search(r"^window\.NARRACION\s*=\s*(\{.*?^\});", js, re.S | re.M)
    if not m:
        raise SystemExit("No encontré window.NARRACION en guiones.js")
    return json.loads(m.group(1))


def reloj(segundos: float) -> str:
    segundos = max(0.0, segundos)
    h, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


def partir(texto: str, tope: int = 36) -> list[str]:
    """Renglones de a lo sumo `tope` caracteres, cortando por palabra.

    Partir a la mitad de una palabra obliga a releer, así que el corte va
    siempre en un espacio.
    """
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        if actual and len(actual) + 1 + len(p) > tope:
            lineas.append(actual)
            actual = p
        else:
            actual = f"{actual} {p}".strip()
    if actual:
        lineas.append(actual)
    return lineas


def bloques(texto: str, max_lineas: int = 2) -> list[str]:
    """El texto de un tramo, repartido en carteles de dos renglones.

    Una frase larga entera en pantalla tapa media grabación y nadie la lee: se
    parte en carteles que se van sucediendo, que es como subtitula cualquiera.
    """
    lineas = partir(texto)
    return ["\n".join(lineas[i:i + max_lineas])
            for i in range(0, len(lineas), max_lineas)] or [texto]


def vtt(pasos: list[dict], duraciones: list[float] | None = None,
        largo: float | None = None) -> str:
    """Un WebVTT a partir de los tramos del guion.

    `duraciones` son los segundos reales de cada clip de voz, si se conocen.
    Sin ellas, cada línea dura hasta que arranca la siguiente, que es lo que se
    puede afirmar mirando sólo el guion.
    """
    salida = ["WEBVTT", ""]
    for i, paso in enumerate(pasos):
        desde = float(paso["t"])
        if i + 1 < len(pasos):
            tope = float(pasos[i + 1]["t"]) - RESPIRO
        else:
            tope = desde + COLA_ULTIMO
        hasta = min(desde + duraciones[i], tope) if duraciones else tope
        if largo is not None:
            hasta = min(hasta, largo)
        if hasta <= desde:
            continue
        # El tramo se reparte entre sus carteles por cantidad de caracteres:
        # el que dice más tarda más en decirse, y así el cartel cambia cuando
        # la voz cambia de frase y no antes.
        partes = bloques(paso["text"])
        pesos = [len(p) for p in partes]
        total = sum(pesos) or 1
        cortes, cursor = [], desde
        for peso in pesos:
            cursor = min(cursor + (hasta - desde) * peso / total, hasta)
            cortes.append(cursor)
        # Un cartel de medio segundo es un parpadeo: se le roba el tiempo al
        # anterior hasta llegar al mínimo legible. Pasa con el último pedazo de
        # una frase, que suele ser corto («line of code.») y por peso se
        # llevaría un suspiro.
        for k in range(len(cortes) - 1, 0, -1):
            arranque = cortes[k - 1]
            if cortes[k] - arranque < MIN_CARTEL:
                cortes[k - 1] = max(desde, cortes[k] - MIN_CARTEL)
        cursor = desde
        for parte, fin in zip(partes, cortes, strict=True):
            if fin <= cursor:
                continue
            salida += [f"{reloj(cursor)} --> {reloj(fin)} {UBICACION}",
                       parte, ""]
            cursor = fin
    return "\n".join(salida)


def escribir(nombre: str, lang: str, pasos: list[dict],
             duraciones: list[float] | None = None,
             largo: float | None = None) -> Path:
    destino = AQUI / f"{nombre}-{lang}.vtt"
    destino.write_text(vtt(pasos, duraciones, largo), encoding="utf-8")
    return destino


def main(idiomas: tuple[str, ...]) -> None:
    guiones = leer_guiones()
    for nombre, por_idioma in guiones.items():
        for lang in idiomas:
            if lang not in por_idioma:
                continue
            destino = escribir(nombre, lang, por_idioma[lang])
            print(f"· {destino.name}: {len(por_idioma[lang])} líneas")


if __name__ == "__main__":
    pedidos = tuple(a for a in sys.argv[1:] if a in IDIOMAS) or IDIOMAS
    main(pedidos)
