"""Métricas de evaluación."""
from __future__ import annotations

import numpy as np
import pytest
from app.core import metrics as M


def test_clasificacion_perfecta():
    y = np.array([0, 0, 1, 1] * 50)
    p = np.where(y == 1, 0.9, 0.1)
    m = M.binary(y, p)
    assert m["auc"] == pytest.approx(1.0)
    assert m["ks"] == pytest.approx(1.0)
    assert m["recall"] == pytest.approx(1.0)


def test_clasificacion_al_azar_da_auc_media():
    rng = np.random.default_rng(0)
    y = rng.binomial(1, 0.4, 4000)
    p = rng.random(4000)
    m = M.binary(y, p)
    assert 0.44 < m["auc"] < 0.56
    assert m["pr_auc"] == pytest.approx(0.4, abs=0.06)


def test_umbral_por_defecto_reproduce_la_tasa_base():
    rng = np.random.default_rng(1)
    y = rng.binomial(1, 0.2, 3000)
    p = rng.random(3000)
    m = M.binary(y, p)
    assert (p >= m["threshold"]).mean() == pytest.approx(0.2, abs=0.02)


def test_ece_penaliza_la_descalibracion():
    rng = np.random.default_rng(2)
    y = rng.binomial(1, 0.3, 5000)
    calibrada = np.full(5000, 0.3) + rng.normal(0, 0.02, 5000)
    corrida = np.clip(calibrada + 0.4, 0, 1)
    assert M.ece(y, np.clip(calibrada, 0, 1)) < M.ece(y, corrida)


def test_regresion_exacta():
    y = np.linspace(10, 200, 400)
    m = M.regression(y, y)
    assert m["r2"] == pytest.approx(1.0)
    assert m["rmse"] == pytest.approx(0.0, abs=1e-9)
    assert m["wmape"] == pytest.approx(0.0, abs=1e-9)


def test_sesgo_tiene_signo_correcto():
    y = np.full(100, 100.0)
    assert M.regression(y, y * 1.1)["bias"] == pytest.approx(0.1, abs=1e-9)
    assert M.regression(y, y * 0.9)["bias"] == pytest.approx(-0.1, abs=1e-9)


def test_direccion_de_cada_metrica():
    assert M.is_better("auc", 0.9, 0.8)
    assert not M.is_better("auc", 0.7, 0.8)
    assert M.is_better("wmape", 0.1, 0.2)      # menor es mejor
    assert not M.is_better("brier", 0.3, 0.2)
    assert M.is_better("auc", 0.7, float("nan"))


def test_lift_del_decil_superior():
    y = np.concatenate([np.ones(100), np.zeros(900)])
    p = np.concatenate([np.linspace(0.9, 1.0, 100), np.linspace(0, 0.5, 900)])
    assert M.lift_at(y, p, 0.10) == pytest.approx(10.0, rel=0.02)


def test_evaluate_enruta_segun_la_tarea():
    y = np.array([0, 1, 0, 1])
    assert "auc" in M.evaluate("binary", y, np.array([0.1, 0.9, 0.2, 0.8]))
    assert "r2" in M.evaluate("regression", np.arange(10.0), np.arange(10.0))
    proba = np.tile([0.2, 0.3, 0.5], (6, 1))
    assert "f1_macro" in M.evaluate("multiclass", np.array([0, 1, 2] * 2), proba, [0, 1, 2])
