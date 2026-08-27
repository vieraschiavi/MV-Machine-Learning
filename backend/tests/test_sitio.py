"""La web de venta: que el JavaScript de la página no llame a la nada.

Las páginas de `web/` no tienen build ni empaquetador: son HTML con el guion
adentro, que es lo que las hace desplegables en cualquier lado. El costo de eso
es que **nadie las compila**, así que una función que no existe no se descubre
hasta que un visitante toca el botón.

Y pasó: `setLang()` llamaba a `cambiarVideos(lang)`, que no estaba definida en
ninguna parte. La página tiraba `ReferenceError` en cada cambio de idioma y los
seis videos —narrados y subtitulados en español, inglés y portugués— se
quedaban siempre en el español con el que arrancaban. El visitante elegía
inglés, veía todo el sitio en inglés y escuchaba la voz en castellano.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
PAGINAS = sorted(WEB.glob("*.html"))

# Lo que el navegador ya trae puesto. No es la lista completa de la plataforma
# web: es la de lo que estas páginas usan, que es lo que hay que reconocer para
# no confundir un global legítimo con una función inventada.
DEL_NAVEGADOR = {
    "alert", "confirm", "fetch", "setTimeout", "setInterval", "clearTimeout",
    "requestAnimationFrame", "encodeURIComponent", "decodeURIComponent",
    "parseInt", "parseFloat", "isNaN", "String", "Number", "Boolean", "Object",
    "Array", "Date", "Math", "JSON", "RegExp", "Promise", "Error", "Map", "Set",
    "URL", "URLSearchParams", "IntersectionObserver", "MutationObserver",
    "ResizeObserver", "FormData", "Intl", "atob", "btoa", "crypto", "TextEncoder",
    "TextDecoder", "Uint8Array", "BigInt", "structuredClone", "queueMicrotask",
    "print", "open", "matchMedia", "getComputedStyle", "scrollTo",
    "Blob", "File", "FileReader", "Image", "Audio", "AbortController",
    "Response", "Request", "Headers", "Symbol", "WeakMap", "ArrayBuffer",
}
PALABRAS = {
    "if", "for", "while", "switch", "catch", "function", "return", "typeof",
    "new", "delete", "void", "in", "of", "do", "else", "case", "throw", "await",
    "yield", "instanceof", "async",
}

GUIONES = WEB / "video" / "guiones.js"


def _scripts(html: str) -> str:
    """Todo el JavaScript embebido de una página, junto."""
    return "\n".join(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                                html, re.S | re.I))


def _definidas(js: str) -> set[str]:
    nombres: set[str] = set()
    nombres |= set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", js))
    nombres |= set(re.findall(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)", js))
    # `algo = function(...)` y `algo = (...) => {}` asignados a un nombre suelto
    nombres |= set(re.findall(r"^\s*([A-Za-z_$][\w$]*)\s*=\s*(?:function|\()", js, re.M))
    return nombres


def _llamadas(js: str) -> set[str]:
    """Nombres invocados como función suelta, sin punto adelante."""
    sin_cadenas = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`", "''", js)
    sin_comentarios = re.sub(r"/\*.*?\*/|//[^\n]*", "", sin_cadenas, flags=re.S)
    return {m.group(1) for m in
            re.finditer(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", sin_comentarios)
            if m.group(1) not in PALABRAS}


@pytest.mark.parametrize("pagina", PAGINAS, ids=lambda p: p.name)
def test_no_llama_funciones_que_no_existen(pagina: Path):
    js = _scripts(pagina.read_text(encoding="utf-8"))
    if not js.strip():
        pytest.skip("la página no trae JavaScript embebido")
    faltan = _llamadas(js) - _definidas(js) - DEL_NAVEGADOR
    assert not faltan, (f"{pagina.name} llama a {sorted(faltan)}, que no está "
                        f"definida en la página ni la trae el navegador")


def _videos_declarados(html: str) -> list[str]:
    return re.findall(r'<video[^>]*data-video="([^"]+)"', html)


def test_cada_video_existe_en_los_tres_idiomas():
    """Si falta un archivo, el visitante que elige ese idioma se queda sin video."""
    declarados = _videos_declarados((WEB / "index.html").read_text(encoding="utf-8"))
    assert declarados, "la página de venta no declara ningún video"
    for base in declarados:
        for lang in ("es", "en", "pt"):
            for ext in ("mp4", "webm", "vtt"):
                f = WEB / "video" / f"{base}-{lang}.{ext}"
                assert f.exists() and f.stat().st_size > 0, f"falta {f.name}"


def test_el_idioma_cambia_el_archivo_del_video():
    """La página tiene que reapuntar las fuentes, no sólo traducir los textos."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = _scripts(html)
    assert "cambiarVideos" in js
    cuerpo = js[js.index("function cambiarVideos"):]
    cuerpo = cuerpo[:cuerpo.index("\n}")]
    assert "source" in cuerpo and "load()" in cuerpo, \
        "cambiar el idioma tiene que reapuntar las fuentes y recargar el video"
    assert "track" in cuerpo, "y también la pista de subtítulos"


def _cues(vtt: str) -> list[tuple[float, float, str]]:
    def seg(marca: str) -> float:
        h, m, s = marca.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    salida = []
    for bloque in vtt.split("\n\n"):
        lineas = [ln for ln in bloque.strip().splitlines() if ln.strip()]
        if not lineas or "-->" not in lineas[0]:
            continue
        desde, hasta = lineas[0].split("-->")
        salida.append((seg(desde.strip()), seg(hasta.strip().split()[0]),
                       " ".join(lineas[1:])))
    return salida


@pytest.mark.parametrize("lang", ["es", "en", "pt"])
def test_los_subtitulos_no_se_pisan_entre_si(lang: str):
    """Dos carteles a la vez es texto encima de texto sobre la grabación."""
    for vtt in sorted((WEB / "video").glob(f"*-{lang}.vtt")):
        cues = _cues(vtt.read_text(encoding="utf-8"))
        assert cues, f"{vtt.name} no tiene ningún cartel"
        for (d1, h1, _), (d2, _, _) in zip(cues, cues[1:], strict=False):
            assert h1 <= d2 + 1e-6, f"{vtt.name}: un cartel sigue puesto en {d2:.2f}s"
            assert h1 > d1, f"{vtt.name}: cartel de duración cero en {d1:.2f}s"


@pytest.mark.parametrize("lang", ["es", "en", "pt"])
def test_el_subtitulo_dice_lo_mismo_que_la_voz(lang: str):
    """Salen del mismo guion: si se separan, se lee una cosa y se escucha otra."""
    js = GUIONES.read_text(encoding="utf-8")
    narracion = json.loads(re.search(r"^window\.NARRACION\s*=\s*(\{.*?^\});",
                                     js, re.S | re.M).group(1))
    for nombre, por_idioma in narracion.items():
        dicho = " ".join(p["text"] for p in por_idioma[lang])
        vtt = WEB / "video" / f"{nombre}-{lang}.vtt"
        escrito = " ".join(t for _, _, t in _cues(vtt.read_text(encoding="utf-8")))
        assert " ".join(escrito.split()) == " ".join(dicho.split()), \
            f"{vtt.name} no coincide con el guion de la narración"
