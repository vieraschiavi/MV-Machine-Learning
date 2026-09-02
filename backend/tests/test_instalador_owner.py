"""Que la licencia embebida llegue al instalador, y que valide.

El instalador owner lleva su licencia adentro para arrancar en nivel Owner sin
que nadie pegue nada. Eso son tres archivos que tienen que coincidir en la misma
carpeta, escritos por tres piezas distintas que nunca se miran entre sí:

  · el workflow, que **escribe** `license.key` y `public.key`;
  · `electron-builder.yml`, que **empaqueta** una carpeta y no las demás;
  · `main.cjs`, que las **lee** de `resources/` para pasárselas al backend.

Y así estuvo roto: el workflow dejaba la clave pública en `desktop/keys/`, que
`extraResources` no empaqueta. No viajaba en ningún instalador, `licensing.py`
caía a su marcador —33 bytes, cuando Ed25519 necesita 32— y rechazaba TODAS las
licencias. El owner arrancaba en demo con su licencia adentro; al cliente que
pagaba le rebotaba la suya. Ninguna prueba lo vio porque cada pieza, por
separado, estaba bien.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from app.core import licensing as L

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOW = RAIZ / ".github" / "workflows" / "desktop.yml"
BUILDER = RAIZ / "desktop" / "electron-builder.yml"
MAIN = RAIZ / "desktop" / "electron" / "main.cjs"
ACTIVADOR = RAIZ / "instalador-owner" / "Activar-OWNER.bat"


def _carpetas_empaquetadas() -> set[str]:
    """Los `from:` de `extraResources` que salen de `desktop/`."""
    texto = BUILDER.read_text(encoding="utf-8")
    bloque = texto[texto.index("extraResources:"):]
    bloque = bloque[:bloque.index("\nwin:")]
    return set(re.findall(r"^\s*-\s*from:\s*(?!\.\.)(\S+)", bloque, re.M))


@pytest.mark.parametrize("archivo", ["license.key", "public.key"])
def test_las_credenciales_se_escriben_donde_se_empaquetan(archivo: str):
    escritos = re.findall(rf'open\("desktop/(\S+)/{archivo}"',
                          WORKFLOW.read_text(encoding="utf-8"))
    assert escritos, f"el workflow no escribe {archivo} en ninguna parte"
    empaquetadas = _carpetas_empaquetadas()
    for carpeta in escritos:
        assert carpeta in empaquetadas, (
            f"el workflow escribe {archivo} en desktop/{carpeta}/, que "
            f"electron-builder no empaqueta ({sorted(empaquetadas)}): no viaja "
            f"en ningún instalador")


@pytest.mark.parametrize("archivo", ["license.key", "public.key"])
def test_el_programa_las_lee_de_esa_misma_carpeta(archivo: str):
    leidas = re.findall(rf"recursos\('(\w+)',\s*'{archivo}'\)",
                        MAIN.read_text(encoding="utf-8"))
    assert leidas, f"main.cjs no lee {archivo}"
    escritos = re.findall(rf'open\("desktop/(\S+)/{archivo}"',
                          WORKFLOW.read_text(encoding="utf-8"))
    assert set(leidas) == set(escritos), (
        f"main.cjs lee {archivo} de resources/{leidas} y el workflow la deja "
        f"en desktop/{escritos}: no se encuentran")


def test_sin_la_clave_publica_al_lado_no_valida_ni_la_licencia_del_owner():
    """El modo de falla exacto que tuvo el instalador, escrito una vez.

    Cuando el instalador no trae `public.key`, `licensing.py` se queda con el
    marcador que tiene escrito como valor por omisión, que **no es una clave
    Ed25519 válida** —tiene 33 bytes y hacen falta 32—, así que rechaza hasta
    una licencia legítima. Eso es lo que convierte «no empaqueté un archivo» en
    «el producto no se puede vender», sin un solo error visible en el build.

    Se lee del código y no de `L.PUBLIC_KEY_B64` porque `conftest.py` le pone
    una clave de prueba al entorno: mirando el valor en vivo, esta prueba
    estaría midiendo la suite en vez del binario que se entrega.
    """
    import base64

    fuente = Path(L.__file__).read_text(encoding="utf-8")
    marcador = re.search(r'os\.environ\.get\(\s*"MV_LICENSE_PUBLIC_KEY",\s*\n?\s*"([^"]+)"',
                         fuente).group(1)
    assert len(base64.b64decode(marcador)) != 32, (
        "el marcador por omisión pasó a ser una clave Ed25519 válida: un "
        "instalador sin public.key validaría licencias firmadas con ella")

    priv, pub = L.generate_keypair()
    token = L.issue("owner", "Owner build (CI)", days=None, private_key_b64=priv)
    assert L.verify(token, public_key_b64=pub).tier == "owner"

    with pytest.raises(L.LicenseError, match="clave pública embebida es inválida"):
        L.verify(token, public_key_b64=marcador)


def test_el_activador_tiene_el_hueco_que_el_ci_rellena():
    """El CI mete la licencia con un reemplazo de texto: si el hueco cambia de
    forma, el activador sale sin licencia y vuelve a preguntar."""
    texto = ACTIVADOR.read_text(encoding="ascii")
    assert texto.count('set "LIC_EMBEBIDA="') == 1, (
        "el activador tiene que tener exactamente un hueco "
        '`set "LIC_EMBEBIDA="` para que el workflow lo rellene')


def test_el_activador_del_repositorio_viaja_sin_licencia():
    """La copia versionada es una plantilla, no una llave.

    Una licencia fija acá deja de valer apenas cambien las claves —y mientras
    tanto es una llave del producto guardada en el historial, que no se puede
    borrar de los clones que ya se hicieron.
    """
    texto = ACTIVADOR.read_text(encoding="ascii")
    # Un token de verdad, no la palabra: el script nombra el prefijo en un
    # control y en un mensaje de error, y eso es correcto que esté.
    pegadas = re.findall(rf"{L.PREFIX}\.[A-Za-z0-9_-]{{20,}}\.[A-Za-z0-9_-]{{20,}}", texto)
    assert not pegadas, (
        "hay una licencia pegada en el activador versionado: la pone el CI en "
        "la copia que se publica, nunca el repositorio")
