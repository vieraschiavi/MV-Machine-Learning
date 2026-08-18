"""Consistencia de la interfaz: los tres idiomas y las claves que usa el HTML."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[2] / "frontend"
I18N = FRONT / "assets" / "i18n"
IDIOMAS = ["es", "en", "pt"]


def _claves(d: dict, prefijo: str = "") -> set[str]:
    out: set[str] = set()
    for k, v in d.items():
        out |= _claves(v, f"{prefijo}{k}.") if isinstance(v, dict) else {f"{prefijo}{k}"}
    return out


def _dic(lang: str) -> dict:
    return json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("lang", IDIOMAS)
def test_el_diccionario_es_json_valido_y_tiene_metadatos(lang):
    d = _dic(lang)
    assert d["meta"]["code"] == lang
    assert d["meta"]["speech"]          # hace falta para la síntesis de voz
    assert d["meta"]["label"]


def test_los_tres_idiomas_tienen_exactamente_las_mismas_claves():
    base = _claves(_dic("es"))
    assert len(base) > 250
    for lang in ["en", "pt"]:
        otras = _claves(_dic(lang))
        assert not (base - otras), f"{lang}: faltan {sorted(base - otras)}"
        assert not (otras - base), f"{lang}: sobran {sorted(otras - base)}"


@pytest.mark.parametrize("lang", IDIOMAS)
def test_ningun_texto_queda_vacio(lang):
    def recorrer(d, prefijo=""):
        for k, v in d.items():
            if isinstance(v, dict):
                recorrer(v, f"{prefijo}{k}.")
            else:
                assert str(v).strip(), f"{lang}: {prefijo}{k} está vacío"
    recorrer(_dic(lang))


@pytest.mark.parametrize("lang", IDIOMAS)
def test_la_interfaz_no_usa_emojis(lang):
    """El diseño es tipográfico: los iconos son SVG, no emojis."""
    emoji = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF]")
    texto = (I18N / f"{lang}.json").read_text(encoding="utf-8")
    assert not emoji.search(texto), f"{lang} contiene emojis"


def test_el_html_no_usa_emojis():
    emoji = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")
    assert not emoji.search((FRONT / "index.html").read_text(encoding="utf-8"))


def test_todas_las_claves_del_html_existen_en_los_diccionarios():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    usadas = set(re.findall(r'data-i18n(?:-placeholder|-title)?="([^"]+)"', html))
    base = _claves(_dic("es"))
    assert usadas, "el HTML no declara ninguna clave traducible"
    assert usadas <= base, f"claves inexistentes en el diccionario: {sorted(usadas - base)}"


def test_todas_las_claves_usadas_por_el_javascript_existen():
    base = _claves(_dic("es"))
    faltantes: dict[str, set[str]] = {}
    for js in (FRONT / "assets" / "js").rglob("*.js"):
        texto = js.read_text(encoding="utf-8")
        usadas = set(re.findall(r"\bt\(\s*'([a-z_]+(?:\.[a-z_0-9]+)+)'", texto))
        # las claves compuestas en tiempo de ejecución no se pueden verificar
        malas = {k for k in usadas if k not in base}
        if malas:
            faltantes[js.name] = malas
    assert not faltantes, f"claves inexistentes: {faltantes}"


def test_los_modulos_del_frontend_estan_todos_presentes():
    js = FRONT / "assets" / "js"
    for nombre in ["app.js", "api.js", "i18n.js", "audio.js", "ui.js", "charts.js", "store.js"]:
        assert (js / nombre).exists(), nombre
    for vista in ["overview", "data", "explore", "etl", "model", "results", "ai", "export"]:
        assert (js / "views" / f"{vista}.js").exists(), vista


def test_el_html_carga_la_aplicacion_como_modulo():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert 'type="module"' in html
    assert "/assets/js/app.js" in html
    assert "/assets/css/app.css" in html
    # nada de CDN: la interfaz funciona sin internet
    assert "http://" not in html.replace("http://www.w3.org", "")
    assert "https://" not in html


def test_el_css_define_los_dos_temas():
    css = (FRONT / "assets" / "css" / "app.css").read_text(encoding="utf-8")
    assert ":root {" in css
    assert '[data-theme="dark"]' in css
    # cada variable del tema claro tiene su equivalente en el oscuro
    claro = set(re.findall(r"--([\w-]+):", css.split('[data-theme="dark"]')[0]))
    oscuro = set(re.findall(r"--([\w-]+):", css.split('[data-theme="dark"]')[1].split("* {")[0]))
    esenciales = {"bg", "surface", "border", "text", "accent", "ok", "warn", "bad"}
    assert esenciales <= claro and esenciales <= oscuro


def test_el_sistema_de_audio_cubre_los_tres_idiomas():
    for lang in IDIOMAS:
        assert _dic(lang)["meta"]["speech"].split("-")[0] == lang
