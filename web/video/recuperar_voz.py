"""Rescata la narración ya sintetizada de un video, para poder regrabarlo.

`generar_voz.py` sintetiza desde cero, y es el camino normal. Pero necesita
salir a internet: edge-tts habla por WebSocket y Piper baja el modelo de voz.
Detrás de un proxy que no lo permita, regrabar el video obligaría a cambiar de
voz —y quedarían dos videos del mismo producto con dos narradores distintos— o
directamente a no regrabarlo.

La voz ya está: es la pista del video anterior, montada con `adelay` en el
segundo exacto de cada tramo del guion. Se corta ahí mismo y vuelve a
`.audio/`, que es de donde la toma el grabador. El texto no cambió; lo que
cambió es lo que se ve.

Uso:
    python web/video/recuperar_voz.py recorrido es en pt
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from generar_subtitulos import leer_guiones
from generar_voz import duracion, ffmpeg

AQUI = Path(__file__).resolve().parent
IDIOMAS = ("es", "en", "pt")


def recortar(fuente: Path, desde: float, hasta: float | None, destino: Path) -> None:
    cmd = [ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{desde:.3f}"]
    if hasta is not None:
        cmd += ["-to", f"{hasta:.3f}"]
    cmd += ["-i", str(fuente), "-vn", "-codec:a", "libmp3lame", "-b:a", "128k",
            str(destino)]
    subprocess.run(cmd, check=True)


def main(video: str, idiomas: tuple[str, ...]) -> None:
    guiones = leer_guiones()
    salida = AQUI / ".audio"
    salida.mkdir(exist_ok=True)
    for lang in idiomas:
        fuente = AQUI / f"{video}-{lang}.mp4"
        if not fuente.exists():
            print(f"· falta {fuente.name}, se saltea")
            continue
        pasos = guiones[video][lang]
        largo = duracion(fuente)
        print(f"· {fuente.name}: {len(pasos)} tramos sobre {largo:.1f} s")
        for i, paso in enumerate(pasos):
            desde = float(paso["t"])
            # Hasta donde arranca el siguiente. El sobrante es silencio, y al
            # volver a montarlo con `adelay` en el mismo segundo la mezcla queda
            # igual: sumar silencio no corre ni tapa nada.
            hasta = float(pasos[i + 1]["t"]) if i + 1 < len(pasos) else None
            destino = salida / f"{video}-{lang}-{i:02d}.mp3"
            recortar(fuente, desde, hasta, destino)
        print(f"  {len(pasos)} archivos en {salida.name}/")


if __name__ == "__main__":
    args = sys.argv[1:]
    video = args[0] if args and args[0] not in IDIOMAS else "recorrido"
    pedidos = tuple(a for a in args if a in IDIOMAS) or IDIOMAS
    main(video, pedidos)
