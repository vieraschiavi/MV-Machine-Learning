"""Que el diagnóstico de configuración no se quede viejo.

`/api/estado` es la respuesta a «qué me falta para vender». Sirve mientras diga
la verdad: el día que una función del sitio empiece a leer una variable nueva y
nadie la agregue a la lista, el diagnóstico va a decir «listo» y el cliente que
pague se va a quedar sin su licencia igual — con el agravante de que ahora hay
una pantalla afirmando que estaba todo bien.

Así que la lista se compara contra lo que el código realmente lee, y contra la
plantilla que el dueño copia para cargarlas.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
API = RAIZ / "api"
ESTADO = API / "estado.js"
PLANTILLA = RAIZ / ".env.example"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="hace falta Node para correr las funciones del sitio")

# Variables que las funciones leen pero que no son configuración del dueño:
# tienen un valor por omisión razonable o las pone la plataforma.
NO_SON_CONFIGURACION = {"REPO", "ARCHIVO_INSTALADOR", "ARCHIVO_INSTALADOR_OWNER",
                        "VERCEL_URL", "NODE_ENV"}


def _leidas_por_el_sitio() -> set[str]:
    """Todo lo que las funciones de `api/` sacan del entorno."""
    nombres: set[str] = set()
    for f in API.glob("*.js"):
        nombres |= set(re.findall(r"process\.env\.([A-Z_][A-Z0-9_]*)",
                                  f.read_text(encoding="utf-8")))
    return nombres - NO_SON_CONFIGURACION


def _estado(env: dict[str, str] | None = None, query: dict | None = None) -> dict:
    guion = (
        f"const mod = await import({json.dumps(ESTADO.as_uri())});\n"
        "const res = { setHeader(){}, status(){ return this }, "
        "json(b){ console.log(JSON.stringify(b)) } };\n"
        f"await mod.default({{ query: {json.dumps(query or {})}, headers: {{}} }}, res);\n"
    )
    # El entorno se pasa limpio: heredar el del que corre las pruebas hacía que
    # el resultado dependiera de la máquina.
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, encoding="utf-8", timeout=60,
                       env={"PATH": subprocess.os.environ["PATH"], **(env or {})})
    assert r.returncode == 0, r.stderr[-600:]
    return json.loads(r.stdout)


def test_el_diagnostico_conoce_todo_lo_que_el_sitio_lee():
    declaradas = {v["nombre"] for v in _estado()["variables"]}
    faltantes = _leidas_por_el_sitio() - declaradas
    assert not faltantes, (
        f"{sorted(faltantes)} se lee en api/ y no está en /api/estado: el "
        f"diagnóstico diría «listo» con esa variable sin cargar")


def test_la_plantilla_trae_todas_las_variables():
    texto = PLANTILLA.read_text(encoding="utf-8")
    declaradas = {v["nombre"] for v in _estado()["variables"]}
    faltantes = {v for v in declaradas if f"\n{v}=" not in texto}
    assert not faltantes, f"{sorted(faltantes)} no está en .env.example"


def test_la_plantilla_no_trae_ningun_valor():
    """Un valor pegado acá queda en el historial del repositorio para siempre."""
    for linea in PLANTILLA.read_text(encoding="utf-8").splitlines():
        if linea.startswith("#") or "=" not in linea:
            continue
        nombre, valor = linea.split("=", 1)
        assert not valor.strip(), f"{nombre} tiene un valor en .env.example"


def test_sin_nada_cargado_avisa_que_no_esta_listo():
    e = _estado()
    assert e["listo"] is False
    assert e["faltan_criticas"] >= 5
    for v in e["variables"]:
        assert v["si_falta"], f"{v['nombre']} no dice qué pasa si falta"
        assert v["de_donde_sale"], f"{v['nombre']} no dice de dónde sale el valor"


def test_con_todo_cargado_dice_que_esta_listo():
    completo = {v["nombre"]: "x" for v in _estado()["variables"]}
    assert _estado(completo)["listo"] is True


def test_el_diagnostico_no_devuelve_ningun_valor():
    """Ni recortado: es el endpoint que más tienta a mostrar «los primeros
    caracteres para verificar», y eso es media credencial regalada."""
    secreto = "clave-secretisima-de-prueba-9137"
    crudo = json.dumps(_estado({v["nombre"]: secreto for v in _estado()["variables"]}))
    assert secreto not in crudo
    assert secreto[:8] not in crudo


def test_avisa_cuando_las_dos_claves_de_licencia_no_son_del_mismo_par():
    """Firman licencias que el propio sitio rechaza después. Sin esta prueba,
    eso se descubre en la primera venta."""
    from app.core import licensing as L

    priv, _ = L.generate_keypair()
    _, otra_pub = L.generate_keypair()
    e = _estado({"MV_LICENSE_PRIVATE_KEY": priv, "MV_LICENSE_PUBLIC_KEY": otra_pub},
                query={"probar": "1"})
    prueba = next(v for v in e["variables"]
                  if v["nombre"] == "MV_LICENSE_PRIVATE_KEY")["prueba"]
    assert prueba["anda"] is False
    assert "par" in prueba["detalle"]

    priv2, pub2 = L.generate_keypair()
    e = _estado({"MV_LICENSE_PRIVATE_KEY": priv2, "MV_LICENSE_PUBLIC_KEY": pub2},
                query={"probar": "1"})
    prueba = next(v for v in e["variables"]
                  if v["nombre"] == "MV_LICENSE_PRIVATE_KEY")["prueba"]
    assert prueba["anda"] is True, prueba.get("detalle")
