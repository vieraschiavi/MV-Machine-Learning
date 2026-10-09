"""Portafolio y mercado desde una celda de notebook: `mv.contribucion`, `mv.mercado` y la salida a Power BI."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from app import notebook as mv

EJEMPLOS = Path(__file__).resolve().parents[2] / "examples"


class _SparkFalso:
    """Lo único que el notebook le pide a un DataFrame de Spark: `toPandas()`."""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def toPandas(self) -> pd.DataFrame:  # noqa: N802 — nombre de la API de Spark
        return self._df


def test_la_matriz_acepta_un_dataframe_de_spark():
    ventas = _SparkFalso(pd.read_csv(EJEMPLOS / "portafolio_sintetico.csv"))
    m = mv.contribucion(ventas, entidad="pais", valor="ventas_usd", mix="presentacion",
                        grupo="area_terapeutica", periodo="periodo")
    assert "Todas" in m and "Cardiometabólica" in m
    assert m["Cardiometabólica"]["acciones"]["proteger"]


def test_mercado_combina_propuesta_y_estudios_y_proyecta_el_lanzamiento():
    est = pd.read_csv(EJEMPLOS / "estudios_mercado_sintetico.csv")
    propuesta = est[est["pais"] == "Chile"].assign(origen="IA (a validar)", valor=lambda d: d["valor"])
    r = mv.mercado(supuestos=propuesta, estudios=est[est["pais"] != "Chile"],
                   lanzamiento={"pico": 0.1, "meses_al_pico": 12, "horizonte": 12},
                   inicio="2027-01", n_sim=200)
    assert r["evidencia"]["nivel"] == "mixta"
    assert r["lanzamiento"][0]["periodo"] == "2027-01"


def test_la_salida_a_powerbi_desde_el_notebook(tmp_path):
    m = mv.contribucion(pd.read_csv(EJEMPLOS / "portafolio_sintetico.csv"), entidad="marca",
                        valor="ventas_usd", grupo="area_terapeutica", periodo="periodo",
                        etiqueta="marcas")
    out = mv.portafolio_para_powerbi(tmp_path / "pbi", contribucion=m)
    ent = pd.read_parquet(out["portafolio_entidades"])
    assert set(ent["eje_x"]) == {"crecimiento"}
    assert (tmp_path / "pbi" / "medidas_portafolio.dax").exists()


def test_una_ruta_abfss_se_rechaza_explicando_que_hacer(tmp_path):
    m = mv.contribucion(pd.read_csv(EJEMPLOS / "portafolio_sintetico.csv"), entidad="pais",
                        valor="ventas_usd", mix="presentacion")
    with pytest.raises(ValueError, match="notebookutils"):
        mv.portafolio_para_powerbi("abfss://ws@onelake.dfs.fabric.microsoft.com/x", contribucion=m)


def test_el_modulo_de_portafolio_se_importa_solo_sin_import_circular():
    # En un proceso aparte: sacar módulos de sys.modules acá descolocaría a las demás pruebas.
    import subprocess
    import sys
    backend = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-c", "import app.notebook_portafolio as m; print(callable(m.contribucion))"],
                       cwd=backend, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "True"
