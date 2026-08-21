"""El generador de claves de `web/claves.html` tiene que darle al programa
exactamente el par que el programa espera.

La página existe para que no haya que correr nada: se abre en el navegador y
escupe las dos claves. Pero eso significa que hay una segunda implementación de
Ed25519 dando vueltas, escrita a mano en JavaScript. Si esa implementación se
desviara aunque sea en un bit, el instalador quedaría con una clave pública que
no valida las licencias firmadas con su propia privada — y el error recién
aparecería con el primer cliente que paga.

Así que acá se corre **el mismo código que corre el navegador** y se compara la
clave pública que sale con la que deriva la biblioteca criptográfica de Python.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PAGINA = Path(__file__).resolve().parents[2] / "web" / "claves.html"
pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="hace falta Node para correr el guión de la página")


def _guion_de_la_pagina() -> str:
    """El bloque de criptografía de la página, tal cual está publicado."""
    html = PAGINA.read_text(encoding="utf-8")
    desde = html.index("const P = (1n")
    hasta = html.index("const $ = (id)")        # a partir de acá empieza el DOM
    return html[desde:hasta]


def test_la_pagina_deriva_la_misma_clave_publica_que_el_programa():
    guion = _guion_de_la_pagina() + """
      const b64 = (u) => Buffer.from(u).toString('base64');
      for (let i = 0; i < 8; i++) {
        const semilla = new Uint8Array(32);
        crypto.getRandomValues(semilla);
        console.log(b64(semilla), b64(await publicaDesdeSemilla(semilla)));
      }
    """
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"la página no corrió: {r.stderr[-500:]}"

    pares = [linea.split() for linea in r.stdout.splitlines() if linea.strip()]
    assert len(pares) == 8, r.stdout

    for privada_b64, publica_del_navegador in pares:
        clave = Ed25519PrivateKey.from_private_bytes(base64.b64decode(privada_b64))
        publica_del_programa = base64.b64encode(clave.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        assert publica_del_navegador == publica_del_programa, (
            "la página generó una clave pública distinta de la que deriva el "
            f"programa para la misma privada: {publica_del_navegador} vs "
            f"{publica_del_programa}")
