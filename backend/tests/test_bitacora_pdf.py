"""El PDF de la bitácora en el escritorio, y sus dos riesgos.

En el navegador el PDF sale del cuadro de impresión. En el escritorio se
guarda directo, sin pasar por una impresora, porque Electron sabe imprimir a
PDF por su cuenta. Eso obliga a abrir un canal entre la interfaz y el proceso
principal, y ahí aparecen los dos riesgos que estas pruebas cuidan:

  1. **Que el canal quede desconectado.** El nombre del canal se escribe dos
     veces —una en el puente y otra en el proceso principal— y si no coinciden
     el botón no hace nada, sin error visible. Es exactamente el modo de falla
     del bug de `MV_FRONTEND_DIR`: dos piezas correctas que no se encuentran.

  2. **Que el canal cargue cualquier cosa.** Recibe una URL desde la interfaz
     y la abre en una ventana; si no se valida el origen, deja de ser un
     exportador de PDF y pasa a ser una forma de que una página cargue lo que
     quiera dentro del programa.

Todo se verifica leyendo el código: Electron no corre en este contenedor, y
decirlo es más honesto que simular que se probó la ventana.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
MAIN = RAIZ / "desktop" / "electron" / "main.cjs"
PRELOAD = RAIZ / "desktop" / "electron" / "preload.cjs"


@pytest.fixture(scope="module")
def main() -> str:
    return MAIN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def preload() -> str:
    return PRELOAD.read_text(encoding="utf-8")


def _canales(texto: str, patron: str) -> set[str]:
    return set(re.findall(patron, texto))


def test_el_puente_le_ofrece_a_la_interfaz_guardar_el_pdf(preload):
    assert "guardarPDF" in preload, "sin esto la interfaz cae en el cuadro de impresión"
    assert "ipcRenderer" in preload


def test_el_canal_del_puente_y_el_del_proceso_principal_son_el_mismo(preload, main):
    """Dos nombres distintos = botón que no hace nada y no avisa."""
    pide = _canales(preload, r"ipcRenderer\.invoke\(\s*'([^']+)'")
    atiende = _canales(main, r"ipcMain\.handle\(\s*'([^']+)'")

    assert pide, "el puente no invoca ningún canal"
    assert pide <= atiende, f"canales sin atender del otro lado: {pide - atiende}"


def test_el_proceso_principal_imprime_a_pdf_de_verdad(main):
    assert "printToPDF" in main
    assert "showSaveDialog" in main, "el usuario tiene que elegir dónde guardarlo"


def test_solo_se_imprime_lo_que_sirve_el_backend_local(main):
    """Una URL sin validar convierte al exportador en un cargador de páginas."""
    bloque = main.split("printToPDF")[0]

    assert "127.0.0.1" in bloque, "falta acotar el origen permitido"
    assert "PORT" in bloque, "el puerto tiene que ser el del backend, no cualquiera"


def test_la_ventana_oculta_se_cierra_aunque_falle(main):
    """Una ventana huérfana deja el proceso vivo y la aplicación no cierra."""
    bloque = main.split("mv:guardar-pdf")[1]

    assert "finally" in bloque
    assert "destroy()" in bloque or "close()" in bloque


def test_la_ventana_de_impresion_no_ejecuta_nada_del_documento(main):
    """El documento es HTML propio, pero se carga con las defensas puestas."""
    bloque = main.split("mv:guardar-pdf")[1].split("printToPDF")[0]

    assert "show: false" in bloque
    assert "sandbox: true" in bloque or "nodeIntegration: false" in bloque
