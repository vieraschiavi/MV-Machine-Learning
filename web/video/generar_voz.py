"""Sintetiza la narración de los videos y la monta sobre el video mudo.

Las voces son **las mismas que ya narran los otros productos de la casa**, para
que todo suene igual. Tres motores, en este orden:

1. **edge-tts** con `es-UY-MateoNeural`, `en-US-GuyNeural` y `pt-BR-AntonioNeural`
   — las de los videos y Reels de MV Cliente IA, familia rioplatense. Gratis y
   sin clave, pero habla por WebSocket: detrás de un proxy que no lo permita
   falla y se pasa al motor siguiente.
2. **Piper**, local y offline, con `es_AR-daniela-high` — la voz de los videos
   de MV Agéndate IA y Project Management MV.
3. **ElevenLabs** (`eleven_multilingual_v2`), la de las demos de Kobra, cuando
   estén configuradas `ELEVENLABS_API_KEY` y `ELEVENLABS_VOICE_ID`. Si hay
   clave se usa primero: es la de mejor calidad.

El guion sale de `guiones.js`, que es también lo que muestra la web: no hay
forma de que el audio diga una cosa y la página otra.

Uso:
    python web/video/generar_voz.py              # todos los idiomas
    python web/video/generar_voz.py es           # sólo uno
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

AQUI = Path(__file__).resolve().parent
IDIOMAS = ("es", "en", "pt")
VIDEOS = ("recorrido", "tablero")

# edge-tts: las voces de los videos de MV Cliente IA (es-UY = rioplatense)
EDGE = {
    "es": "es-UY-MateoNeural",
    "en": "en-US-GuyNeural",
    "pt": "pt-BR-AntonioNeural",
}
# Piper local: las voces de MV Agéndate IA y Project Management MV
PIPER = {
    "es": "es_AR-daniela-high",
    "en": "en_US-amy-medium",
    "pt": "pt_BR-faber-medium",
}
PIPER_URL = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
             "{lang}/{lang}_{pais}/{nombre}/{calidad}/{voz}.onnx")


def ffmpeg() -> str:
    """El ffmpeg del sistema, o el que trae imageio-ffmpeg."""
    for cmd in ("ffmpeg", "/usr/bin/ffmpeg"):
        if subprocess.run(["which", cmd], capture_output=True).returncode == 0:
            return cmd
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def leer_guiones() -> dict:
    """`window.NARRACION = {...};` → dict. Misma fuente que lee la web."""
    js = (AQUI / "guiones.js").read_text(encoding="utf-8")
    m = re.search(r"^window\.NARRACION\s*=\s*(\{.*?^\});", js, re.S | re.M)
    if not m:
        raise SystemExit("No encontré window.NARRACION en guiones.js")
    return json.loads(m.group(1))


# ── motores ──────────────────────────────────────────────────────────────────
def voz_elevenlabs(texto: str, destino: Path, api_key: str, voice_id: str) -> bool:
    import httpx

    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "accept": "audio/mpeg"},
        json={"text": texto, "model_id": "eleven_multilingual_v2",
              "voice_settings": {"stability": 0.45, "similarity_boost": 0.8}},
        timeout=90)
    if r.status_code != 200:
        print(f"  ElevenLabs respondió {r.status_code}: {r.text[:120]}")
        return False
    destino.write_bytes(r.content)
    return True


def voz_edge(texto: str, destino: Path, lang: str) -> bool:
    """La voz de los videos de MV Cliente IA. Habla por WebSocket."""
    import asyncio
    import ssl

    try:
        import aiohttp
        import edge_tts
    except ImportError:
        return False

    async def hablar() -> None:
        ctx = ssl.create_default_context(cafile=os.getenv("SSL_CERT_FILE") or None)
        com = edge_tts.Communicate(texto, EDGE[lang],
                                   connector=aiohttp.TCPConnector(ssl=ctx))
        await com.save(str(destino))

    try:
        asyncio.run(hablar())
        return destino.exists() and destino.stat().st_size > 500
    except Exception as exc:
        print(f"  edge-tts no pudo ({type(exc).__name__}), se usa la voz local")
        return False


def modelo_piper(lang: str) -> Path:
    voz = PIPER[lang]
    carpeta = AQUI / ".voces"
    carpeta.mkdir(exist_ok=True)
    onnx = carpeta / f"{voz}.onnx"
    if onnx.exists():
        return onnx
    idioma, pais = voz.split("-")[0].split("_")
    url = PIPER_URL.format(lang=idioma, pais=pais, nombre=voz.split("-")[1],
                           calidad=voz.split("-")[2], voz=voz)
    print(f"  bajando la voz {voz}…")
    import httpx
    for sufijo in ("", ".json"):
        with httpx.stream("GET", url + sufijo, follow_redirects=True, timeout=300) as r:
            r.raise_for_status()
            with open(str(onnx) + sufijo, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    return onnx


def voz_piper(texto: str, destino: Path, lang: str) -> bool:
    from piper import PiperVoice

    voz = PiperVoice.load(str(modelo_piper(lang)))
    wav = destino.with_suffix(".wav")
    with wave.open(str(wav), "wb") as w:
        voz.synthesize_wav(texto, w)
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(wav),
                    "-codec:a", "libmp3lame", "-b:a", "128k", str(destino)], check=True)
    wav.unlink()
    return True


def duracion(archivo: Path) -> float:
    """Segundos del archivo. Se lee del propio ffmpeg: ffprobe puede no estar
    (el binario que trae imageio-ffmpeg viene solo)."""
    out = subprocess.run([ffmpeg(), "-i", str(archivo)],
                         capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d\d):(\d\d\.\d+)", out.stderr)
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


# ── montaje ──────────────────────────────────────────────────────────────────
def montar(video: Path, tramos: list[tuple[float, Path]], salida: Path) -> None:
    """Pone cada tramo en su segundo y mezcla la pista sobre el video.

    El video no se recodifica (`-c:v copy`): sólo se le agrega la pista de
    audio, así no se pierde calidad ni se tarda de más.
    """
    entradas, filtros, etiquetas = ["-i", str(video)], [], []
    for i, (t, mp3) in enumerate(tramos):
        entradas += ["-i", str(mp3)]
        filtros.append(f"[{i + 1}:a]adelay={int(t * 1000)}|{int(t * 1000)}[a{i}]")
        etiquetas.append(f"[a{i}]")
    # `apad` rellena con silencio hasta que termina el video: sin eso,
    # `-shortest` corta la imagen en cuanto se acaba la última frase y se
    # pierde el final del recorrido.
    filtros.append(f"{''.join(etiquetas)}amix=inputs={len(tramos)}:"
                   f"dropout_transition=0:normalize=0,apad[out]")
    cmd = [ffmpeg(), "-y", "-loglevel", "error", *entradas,
           "-filter_complex", ";".join(filtros), "-map", "0:v", "-map", "[out]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", str(salida)]
    subprocess.run(cmd, check=True)


def main(idiomas: tuple[str, ...]) -> None:
    guiones = leer_guiones()
    key = os.getenv("ELEVENLABS_API_KEY", "")
    voice = os.getenv("ELEVENLABS_VOICE_ID", "") or os.getenv("ELEVENLABS_VOICE_ID_GESTOR", "")
    premium = len(key) > 10 and bool(voice)
    print("voz:", "ElevenLabs, la de las demos de Kobra" if premium
          else "edge-tts (es-UY-MateoNeural), con Piper local de respaldo")

    tmp = AQUI / ".audio"
    tmp.mkdir(exist_ok=True)
    for nombre in VIDEOS:
        for lang in idiomas:
            mudo = AQUI / f"{nombre}-{lang}.mp4"
            if not mudo.exists():
                print(f"· falta {mudo.name}, se saltea")
                continue
            print(f"· {nombre} [{lang}]")
            tramos = []
            for i, tramo in enumerate(guiones[nombre][lang]):
                mp3 = tmp / f"{nombre}-{lang}-{i:02d}.mp3"
                if not mp3.exists():
                    ok = ((voz_elevenlabs(tramo["text"], mp3, key, voice) if premium else False)
                          or voz_edge(tramo["text"], mp3, lang)
                          or voz_piper(tramo["text"], mp3, lang))
                    if not ok:
                        raise SystemExit("no se pudo sintetizar la narración")
                tramos.append((tramo["t"], mp3))
            largo = duracion(mudo)
            ultimo = tramos[-1][0] + duracion(tramos[-1][1])
            if ultimo > largo + 1.5:
                print(f"  aviso: la narración termina en {ultimo:.1f} s y el video "
                      f"dura {largo:.1f} s — se corta al final del video")
            montar(mudo, tramos, AQUI / f"{nombre}-{lang}.con-voz.mp4")
            (AQUI / f"{nombre}-{lang}.con-voz.mp4").replace(mudo)
            # el webm se rearma desde el mp4 ya narrado
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(mudo),
                            "-c:v", "libvpx-vp9", "-crf", "34", "-b:v", "0",
                            "-c:a", "libopus", "-b:a", "96k",
                            str(AQUI / f"{nombre}-{lang}.webm")], check=True)
            print(f"  listo: {mudo.name} ({mudo.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    pedidos = tuple(a for a in sys.argv[1:] if a in IDIOMAS) or IDIOMAS
    main(pedidos)
