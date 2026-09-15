"""El motor usado desde un notebook de Python (Fabric, Jupyter, Databricks).

En Fabric no hay servidor que levantar ni archivo que subir: el dato ya está en
el Lakehouse y el notebook lo tiene en un DataFrame. Estas pruebas fijan ese
camino de punta a punta —entrenar, predecir, guardar, volver a cargar y dejar
la salida para Power BI— sin pasar por la API HTTP.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from app import notebook as N
from app.core import licensing as L


@pytest.fixture(scope="module")
def ventas() -> pd.DataFrame:
    """Réplica sintética de una tabla del Lakehouse: nunca datos reales."""
    rng = np.random.default_rng(7)
    n = 600
    zona = rng.choice(["norte", "sur", "centro"], n)
    visitas = rng.integers(1, 12, n)
    base = 0.15 + 0.05 * visitas + np.where(zona == "centro", 0.15, 0.0)
    return pd.DataFrame({
        "cliente": [f"c{i:04d}" for i in range(n)],
        "zona": zona,
        "visitas": visitas,
        "descuento": rng.uniform(0, 0.3, n).round(3),
        "compro": rng.binomial(1, np.clip(base, 0, 0.95), n),
    })


@pytest.fixture(scope="module")
def modelo(ventas):
    return N.entrenar(ventas, objetivo="compro", excluir=["cliente"],
                      presupuesto_segundos=6, max_modelos=2, explicacion_shap=False)


class FakeSparkDF:
    """Lo que un notebook de Fabric tiene en la mano: un DataFrame de Spark.

    No se instala PySpark para probar esto: lo único que el módulo necesita de
    un DataFrame de Spark es que sepa convertirse con ``toPandas()``.
    """

    def __init__(self, pdf: pd.DataFrame) -> None:
        self._pdf = pdf
        self.llamadas = 0

    def toPandas(self) -> pd.DataFrame:      # noqa: N802 - así se llama en Spark
        self.llamadas += 1
        return self._pdf.copy()


# ── entrada de datos ─────────────────────────────────────────────────────────
def test_entrena_con_un_dataframe_de_pandas(modelo):
    inf = modelo.informe
    assert inf["target"] == "compro"
    assert inf["task"] == "binary"
    # el número que se reporta sale del holdout ciego, no de la ventana de selección
    assert inf["split"]["holdout"] > 0
    assert modelo.resumen()["filas"] == 600


def test_entrena_con_un_dataframe_de_spark(ventas):
    spark_df = FakeSparkDF(ventas)
    res = N.entrenar(spark_df, objetivo="compro", excluir=["cliente"],
                     presupuesto_segundos=4, max_modelos=1, explicacion_shap=False)
    assert spark_df.llamadas == 1
    assert res.informe["rows_used"] > 0


def test_el_objetivo_inexistente_avisa_con_el_nombre(ventas):
    with pytest.raises(ValueError, match="cobro"):
        N.entrenar(ventas, objetivo="cobro", presupuesto_segundos=2)


def test_una_tabla_vacia_no_llega_al_motor():
    with pytest.raises(ValueError, match="sin filas"):
        N.entrenar(pd.DataFrame({"a": [], "b": []}), objetivo="b")


# ── predicción ───────────────────────────────────────────────────────────────
def test_predice_una_fila_por_cada_fila_de_entrada(modelo, ventas):
    pred = modelo.predecir(ventas.head(25))
    assert len(pred) == 25
    assert "prediccion" in pred.columns
    assert any(c.startswith("prob_") for c in pred.columns)


def test_predecir_acepta_spark_y_devuelve_pandas(modelo, ventas):
    pred = modelo.predecir(FakeSparkDF(ventas.head(10)))
    assert isinstance(pred, pd.DataFrame) and len(pred) == 10


def test_predecir_con_columnas_de_contexto(modelo, ventas):
    pred = modelo.predecir(ventas.head(10), conservar=["cliente"])
    assert list(pred["cliente"]) == list(ventas.head(10)["cliente"])


# ── guardar y volver a cargar ────────────────────────────────────────────────
def test_el_modelo_guardado_predice_igual_al_recargado(modelo, ventas, tmp_path):
    carpeta = modelo.guardar(tmp_path / "modelo_compras")
    assert (carpeta / "modelo.joblib").exists()
    assert (carpeta / "ficha.json").exists()

    recargado = N.cargar(carpeta)
    a = modelo.predecir(ventas.head(40))
    b = recargado.predecir(ventas.head(40))
    pd.testing.assert_frame_equal(a, b)
    assert recargado.informe["target"] == "compro"


def test_guardar_en_una_ruta_de_onelake_explica_que_hacer(modelo):
    with pytest.raises(ValueError, match="abfss"):
        modelo.guardar("abfss://espacio@onelake.dfs.fabric.microsoft.com/lh/Files/mv")


# ── salida para Power BI ─────────────────────────────────────────────────────
def test_para_powerbi_deja_las_tres_tablas(modelo, ventas, tmp_path):
    salida = modelo.para_powerbi(tmp_path / "pbi", datos=ventas.head(50),
                                 conservar=["cliente", "zona"])
    assert set(salida) == {"predicciones", "metricas", "importancias", "resumen"}

    pred = pd.read_parquet(salida["predicciones"])
    assert len(pred) == 50
    assert {"cliente", "zona", "prediccion"} <= set(pred.columns)

    met = pd.read_parquet(salida["metricas"])
    # formato largo: una fila por métrica y ventana, que es lo que Power BI
    # necesita para armar un visual sin pivotear a mano
    assert {"metrica", "ventana", "valor"} <= set(met.columns)
    assert set(met["ventana"]) == {"seleccion", "holdout"}

    imp = pd.read_parquet(salida["importancias"])
    assert {"variable", "aporte"} <= set(imp.columns)
    assert len(imp) > 0

    resumen = pd.read_parquet(salida["resumen"])
    assert len(resumen) == 1
    assert resumen["objetivo"].iloc[0] == "compro"


def test_para_powerbi_sin_datos_no_escribe_predicciones(modelo, tmp_path):
    salida = modelo.para_powerbi(tmp_path / "pbi_solo_metricas")
    assert "predicciones" not in salida
    assert set(salida) == {"metricas", "importancias", "resumen"}


def test_para_powerbi_en_csv(modelo, ventas, tmp_path):
    salida = modelo.para_powerbi(tmp_path / "pbi_csv", datos=ventas.head(10), formato="csv")
    assert salida["metricas"].suffix == ".csv"
    assert len(pd.read_csv(salida["predicciones"])) == 10


def test_formato_desconocido_se_rechaza(modelo, tmp_path):
    with pytest.raises(ValueError, match="formato"):
        modelo.para_powerbi(tmp_path / "pbi_malo", formato="xlsx")


# ── topes de la licencia: el notebook no es una puerta de atrás ──────────────
def test_el_nivel_demo_corta_por_filas(ventas, monkeypatch):
    monkeypatch.setattr(L, "load", lambda: None)              # sin licencia ⇒ demo
    monkeypatch.setitem(L.TIERS, "demo", dataclasses.replace(L.TIERS["demo"], max_rows=100))
    with pytest.raises(PermissionError, match="filas"):
        N.entrenar(ventas, objetivo="compro", presupuesto_segundos=2)


def test_el_nivel_demo_recorta_el_presupuesto(ventas, monkeypatch):
    visto = {}
    monkeypatch.setattr(L, "load", lambda: None)
    monkeypatch.setattr(N.A, "train",
                        lambda df, cfg, progress=None: visto.update(
                            segundos=cfg.budget_seconds, familias=cfg.max_models) or
                        {"report": {"target": cfg.target}, "bundle": {}})
    N.entrenar(ventas.head(50), objetivo="compro", presupuesto_segundos=9000, max_modelos=20)
    assert visto["segundos"] == L.TIERS["demo"].max_budget_seconds
    assert visto["familias"] == L.TIERS["demo"].max_model_families


# ── informe legible ──────────────────────────────────────────────────────────
def test_resumen_trae_el_veredicto_y_la_brecha(modelo):
    r = modelo.resumen()
    assert {"modelo", "metrica", "holdout", "brecha", "veredicto", "filas"} <= set(r)
    assert isinstance(r["veredicto"], str) and r["veredicto"]


def test_tabla_de_modelos_ordenada_por_la_ventana_de_seleccion(modelo):
    tabla = modelo.tabla_modelos()
    assert isinstance(tabla, pd.DataFrame) and len(tabla) >= 1
    assert {"modelo", "seleccion", "holdout"} <= set(tabla.columns)


def test_importancias_devuelve_las_columnas_que_importan(modelo):
    imp = modelo.importancias(n=3)
    assert len(imp) <= 3
    assert list(imp.columns)[:2] == ["variable", "aporte"]
