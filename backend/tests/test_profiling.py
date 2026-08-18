"""Perfilado estadístico, calidad y relación con el objetivo."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.core import profiling


def test_perfil_detecta_tipos_y_nulos(dataset_binary):
    prof = profiling.profile(dataset_binary.id)
    cols = {c["name"]: c for c in prof["columns"]}
    assert cols["edad"]["kind"] == "numeric"
    assert cols["region"]["kind"] == "categorical"
    assert cols["constante"]["constant"] is True
    assert cols["casi_vacia"]["null_pct"] > 80
    assert cols["ingreso"]["nulls"] == 60
    assert cols["id"]["unique_key"] is True


def test_estadisticos_numericos_son_coherentes(dataset_binary, frame_binary):
    prof = profiling.profile(dataset_binary.id)
    st = next(c for c in prof["columns"] if c["name"] == "edad")["stats"]
    assert st["min"] == pytest.approx(frame_binary.edad.min(), rel=1e-6)
    assert st["max"] == pytest.approx(frame_binary.edad.max(), rel=1e-6)
    assert st["mean"] == pytest.approx(frame_binary.edad.mean(), rel=1e-6)
    assert st["p25"] <= st["median"] <= st["p75"]


def test_histograma_tiene_bins_y_suma_positiva(dataset_binary):
    prof = profiling.profile(dataset_binary.id)
    hist = next(c for c in prof["columns"] if c["name"] == "ingreso")["histogram"]
    assert len(hist) == 20
    assert sum(b["count"] for b in hist) > 0


def test_calidad_reporta_hallazgos_accionables(dataset_binary):
    prof = profiling.profile(dataset_binary.id)
    q = prof["quality"]
    assert 0 <= q["score"] <= 100
    codigos = {i["code"] for i in q["issues"]}
    assert "constant" in codigos
    assert "nulls_high" in codigos
    assert "identifier" in codigos


def test_correlaciones(dataset_binary):
    corr = profiling.correlations(dataset_binary.id)
    assert len(corr["columns"]) >= 2
    n = len(corr["columns"])
    assert len(corr["pearson"]) == n and len(corr["pearson"][0]) == n
    for i in range(n):
        assert corr["pearson"][i][i] == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("serie,esperado", [
    (pd.Series([0, 1, 0, 1, 1, 0]), "binary"),
    (pd.Series(["a", "b", "c", "a", "b", "c"]), "multiclass"),
    (pd.Series(np.linspace(0, 100, 300)), "regression"),
    (pd.Series(["si", "no"] * 20), "binary"),
])
def test_inferencia_del_tipo_de_tarea(serie, esperado):
    assert profiling.infer_task(serie) == esperado


def test_analisis_del_objetivo(dataset_binary):
    r = profiling.target_analysis(dataset_binary.id, "objetivo")
    assert r["task"] == "binary"
    assert r["distribution"]["type"] == "categorical"
    assert r["distribution"]["n_classes"] == 2
    cols = {a["column"] for a in r["associations"]}
    assert "ingreso" in cols
    fuerza = {a["column"]: a["strength"] for a in r["associations"]}
    # el ingreso genera el objetivo: debe pesar más que una columna sin relación
    assert fuerza["ingreso"] > fuerza.get("region", 0)


def test_objetivo_inexistente_da_error_claro(dataset_binary):
    with pytest.raises(ValueError):
        profiling.target_analysis(dataset_binary.id, "no_existe")
