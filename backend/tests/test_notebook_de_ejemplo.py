"""El notebook de ejemplo de Fabric, corrido de verdad celda por celda.

Un notebook que nadie ejecuta es documentación que envejece sin avisar: el día
que cambie un nombre de función, el archivo sigue prolijo y el cliente se come
el error en Fabric. Acá se ejecuta el mismo archivo que se entrega, en el mismo
orden, y se revisa que haya dejado los archivos que promete.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

NOTEBOOK = Path(__file__).resolve().parents[2] / "examples" / "fabric" / "mv_automl_en_fabric.ipynb"


def _celdas_de_codigo() -> list[str]:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def test_el_notebook_existe_y_es_json_valido():
    assert NOTEBOOK.exists(), f"falta el notebook de ejemplo: {NOTEBOOK}"
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    assert len(_celdas_de_codigo()) >= 5


def test_el_notebook_no_trae_datos_reales_ni_credenciales():
    texto = NOTEBOOK.read_text(encoding="utf-8").lower()
    for prohibido in ("password", "secret", "@adium", ".onmicrosoft.com", "bearer "):
        assert prohibido not in texto, f"el notebook de ejemplo menciona «{prohibido}»"


def test_el_notebook_corre_entero_y_deja_la_salida(tmp_path, monkeypatch):
    """Sin Lakehouse montado toma el camino de ejemplo: el mismo que usa quien prueba."""
    monkeypatch.chdir(tmp_path)
    entorno: dict[str, object] = {"__name__": "__notebook__"}
    for i, celda in enumerate(_celdas_de_codigo(), 1):
        try:
            exec(compile(celda, f"<celda {i}>", "exec"), entorno)      # noqa: S102
        except Exception as exc:                                        # pragma: no cover
            pytest.fail(f"la celda {i} del notebook falló: {type(exc).__name__}: {exc}")

    salida = tmp_path / "salida_mv"
    assert (salida / "modelo_compras" / "modelo.joblib").exists()
    assert (salida / "modelo_compras" / "ficha.json").exists()

    pbi = salida / "powerbi"
    for tabla in ("predicciones", "metricas", "importancias", "resumen"):
        assert (pbi / f"{tabla}.parquet").exists(), f"falta la tabla {tabla} para Power BI"

    pred = pd.read_parquet(pbi / "predicciones.parquet")
    assert len(pred) == 800 and "cliente_id" in pred.columns
    assert entorno["recargado"].informe["target"] == "compro"


def test_el_notebook_escribe_en_el_lakehouse_cuando_esta_montado(tmp_path, monkeypatch):
    """Con el punto de montaje presente, la salida va al Lakehouse y no al disco local."""
    falso_lakehouse = tmp_path / "lakehouse" / "default" / "Files"
    falso_lakehouse.mkdir(parents=True)

    # `as_posix()` y no `str()`: la ruta se INYECTA dentro de un literal de
    # Python del notebook, y en Windows `str(WindowsPath)` trae barras
    # invertidas — `Path("C:\Users\...")` es `\U`, o sea `SyntaxError:
    # truncated \UXXXXXXXX escape` antes de ejecutar una sola línea. Es un
    # defecto del test, no del notebook: `Path` acepta barras normales en
    # Windows y la comparación de abajo sigue dando igual.
    celda = _celdas_de_codigo()[0].replace("/lakehouse/default/Files",
                                           falso_lakehouse.as_posix())
    monkeypatch.chdir(tmp_path)
    entorno: dict[str, object] = {}
    exec(compile(celda, "<celda 1>", "exec"), entorno)                  # noqa: S102
    assert entorno["SALIDA"] == falso_lakehouse / "mv"


def test_la_guia_de_fabric_esta_escrita():
    guia = Path(__file__).resolve().parents[2] / "docs" / "FABRIC_Y_POWERBI.md"
    assert guia.exists(), "falta la guía docs/FABRIC_Y_POWERBI.md"
    texto = guia.read_text(encoding="utf-8")
    for tema in ["Entra ID", "ODBC", "Power BI", "notebook", "holdout"]:
        assert tema.lower() in texto.lower(), f"la guía no habla de «{tema}»"
