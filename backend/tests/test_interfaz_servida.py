"""Que el programa abra el programa, y no un JSON.

El backend monta la interfaz sólo si `settings.frontend_dir` existe. Cuando no
existe no monta ni `/assets` ni la raíz, así que **toda** URL cae en el 404 por
omisión de FastAPI y contesta `{"detail": "Not Found"}`. En el navegador eso
sería un error; adentro de la ventana de Electron es todo lo que el usuario ve
al abrir el programa que compró.

Pasó de verdad: `electron-builder.yml` empaquetaba la interfaz en
`resources/frontend`, pero `main.cjs` no le pasaba `MV_FRONTEND_DIR` al
backend, que entonces la buscaba junto al código fuente —una ruta que dentro
del .exe congelado no existe—. Y el smoke del instalador no lo veía porque
pedía sólo endpoints de `/api` y encima exportaba a mano la variable que el
producto real no pasaba: medía una configuración que no existía.

Estas dos pruebas fijan el par: con la carpeta, la interfaz; sin ella, el
síntoma exacto.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# Se levanta en un proceso aparte: `app.main` decide si monta la interfaz al
# importarse, así que la configuración tiene que estar puesta ANTES del import
# y no se puede cambiar dentro de un mismo intérprete.
GUION = """
import json, os, sys
sys.path.insert(0, %r)
from fastapi.testclient import TestClient
import app.main as m
c = TestClient(m.app)
raiz = c.get("/")
print(json.dumps({
    "monta": m.settings.frontend_dir.exists(),
    "estado": raiz.status_code,
    "es_la_interfaz": "<title>MV AutoML Studio</title>" in raiz.text,
    "cuerpo": raiz.text[:80],
    "assets": c.get("/assets/js/app.js").status_code,
}))
"""


def _pedir_la_raiz(frontend: Path, tmp_path: Path) -> dict:
    entorno = {
        **dict(subprocess.os.environ),
        "MV_FRONTEND_DIR": str(frontend),
        "MV_DATA_DIR": str(tmp_path / "datos"),
    }
    r = subprocess.run([sys.executable, "-c", GUION % str(RAIZ / "backend")],
                       capture_output=True, encoding="utf-8", timeout=180,
                       env=entorno)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_con_la_interfaz_en_su_lugar_la_raiz_devuelve_la_pagina(tmp_path):
    """Lo que `main.cjs` consigue al pasar MV_FRONTEND_DIR."""
    r = _pedir_la_raiz(RAIZ / "frontend", tmp_path)

    assert r["monta"] is True
    assert r["estado"] == 200, f"la raíz devolvió {r['estado']}: {r['cuerpo']}"
    assert r["es_la_interfaz"], f"la raíz no devuelve la interfaz sino: {r['cuerpo']}"
    assert r["assets"] == 200, "no se sirve /assets: la página cargaría sin nada"


def test_sin_la_interfaz_la_ventana_muestra_el_json_del_404(tmp_path):
    """El síntoma exacto que veía el usuario, fijado para que no vuelva.

    No se le pide al backend que reviente sin interfaz —se usa también como
    API sola—, pero sí que este modo de falla quede escrito: si alguien vuelve
    a soltar el `MV_FRONTEND_DIR` del lanzador, la prueba de arriba se cae y
    ésta explica por qué.
    """
    r = _pedir_la_raiz(tmp_path / "no-existe", tmp_path)

    assert r["monta"] is False
    assert r["estado"] == 404
    assert json.loads(r["cuerpo"]) == {"detail": "Not Found"}
