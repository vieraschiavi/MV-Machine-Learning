"""Dónde escribe el programa: que se pueda sacar del disco del sistema.

En Windows el perfil del usuario vive en C:. Clavar ahí los datasets, los
modelos y los informes tiene dos consecuencias que aparecen tarde:

  · el disco del sistema se llena con archivos de trabajo —y en muchas
    máquinas C: es justo el disco chico, el SSD, y D: el que tiene lugar—;
  · una copia descomprimida en otro disco igual escribe en C:, así que
    «portable» no era portable.

La regla es una carpeta `datos` al lado del programa: si está, se usa. No se
crea sola a propósito. Una instalación normal escribe en el directorio del
programa sin problemas, así que crearla al vuelo convertiría toda instalación
en portable —y el desinstalador borra ese directorio: los datasets del cliente
se irían con él—. Que exista es la señal explícita, y el .zip portable la trae
hecha.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MODULO = RAIZ / "desktop" / "electron" / "carpeta-datos.cjs"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="hace falta Node para correr el módulo")


def _resolver(**opciones) -> str:
    """Corre la resolución de verdad, en Node, sobre carpetas de verdad."""
    guion = (
        f"const {{ carpetaDeDatos }} = require({json.dumps(str(MODULO))});\n"
        f"console.log(carpetaDeDatos({json.dumps(opciones)}));\n"
    )
    r = subprocess.run(["node", "-e", guion], capture_output=True,
                       encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr[-600:]
    return r.stdout.strip()


@pytest.fixture()
def instalacion(tmp_path: Path):
    """Un programa empaquetado y un perfil de usuario, cada uno por su lado."""
    programa = tmp_path / "MV AutoML Studio"
    (programa / "resources").mkdir(parents=True)
    perfil = tmp_path / "perfil"
    perfil.mkdir()
    return programa, perfil


def test_la_variable_de_entorno_manda_sobre_todo(instalacion, tmp_path):
    """El escape para el que quiere los datos en un disco cualquiera."""
    programa, perfil = instalacion
    (programa / "datos").mkdir()
    elegida = tmp_path / "otro-disco"

    assert _resolver(entorno=str(elegida), empaquetado=True,
                     raizDelPrograma=str(programa),
                     perfilDelUsuario=str(perfil)) == str(elegida)


def test_con_la_carpeta_al_lado_no_toca_el_perfil_del_usuario(instalacion):
    """El modo portable: descomprimir en D:\\MV y que todo quede en D:."""
    programa, perfil = instalacion
    (programa / "datos").mkdir()

    destino = _resolver(entorno="", empaquetado=True,
                        raizDelPrograma=str(programa),
                        perfilDelUsuario=str(perfil))
    assert destino == str(programa / "datos")
    assert str(perfil) not in destino


def test_sin_la_carpeta_al_lado_sigue_en_el_perfil(instalacion):
    """Una instalación normal no cambia de comportamiento.

    Importa: el desinstalador borra el directorio del programa. Si los datos
    se mudaran ahí solos, desinstalar se llevaría los datasets del cliente.
    """
    programa, perfil = instalacion
    assert not (programa / "datos").exists()

    assert _resolver(entorno="", empaquetado=True,
                     raizDelPrograma=str(programa),
                     perfilDelUsuario=str(perfil)) == str(perfil / "data")


def test_no_crea_la_carpeta_para_decidir(instalacion):
    """Preguntar no debe cambiar la respuesta de la próxima vez."""
    programa, perfil = instalacion
    _resolver(entorno="", empaquetado=True, raizDelPrograma=str(programa),
              perfilDelUsuario=str(perfil))
    assert not (programa / "datos").exists(), (
        "la resolución creó la carpeta que usa como señal: a partir de "
        "ahora toda instalación se comportaría como portable")


def test_si_no_se_puede_escribir_al_lado_vuelve_al_perfil(instalacion):
    """Un programa en una carpeta de sólo lectura tiene que arrancar igual."""
    programa, perfil = instalacion
    # Un archivo llamado `datos` existe pero no admite escritura adentro:
    # es la forma portable de simular «está, pero no sirve».
    (programa / "datos").write_text("no soy una carpeta", encoding="utf-8")

    assert _resolver(entorno="", empaquetado=True,
                     raizDelPrograma=str(programa),
                     perfilDelUsuario=str(perfil)) == str(perfil / "data")


def test_en_desarrollo_usa_el_perfil(instalacion):
    """Sin empaquetar no hay «al lado del programa» que valga."""
    programa, perfil = instalacion
    (programa / "datos").mkdir()

    assert _resolver(entorno="", empaquetado=False,
                     raizDelPrograma=str(programa),
                     perfilDelUsuario=str(perfil)) == str(perfil / "data")


def test_no_deja_basura_de_la_prueba_de_escritura(instalacion):
    """El testigo con el que se prueba escribir se borra."""
    programa, perfil = instalacion
    datos = programa / "datos"
    datos.mkdir()

    _resolver(entorno="", empaquetado=True, raizDelPrograma=str(programa),
              perfilDelUsuario=str(perfil))
    assert list(datos.iterdir()) == [], f"quedó basura: {list(datos.iterdir())}"


def test_main_usa_esta_resolucion_y_no_el_perfil_a_secas():
    """Que el módulo exista no sirve si `main.cjs` sigue con lo de antes."""
    main = (RAIZ / "desktop" / "electron" / "main.cjs").read_text(encoding="utf-8")
    assert "carpeta-datos" in main, "main.cjs no importa la resolución"
    assert "getPath('userData'), 'data'" not in main, (
        "main.cjs sigue armando la ruta de datos por su cuenta: la decisión "
        "tiene que estar en un solo lugar")
