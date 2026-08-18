"""AutoML: partición honesta, entrenamiento, registro y scoring."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.core import automl as A
from app.core import registry


@pytest.fixture(scope="module")
def entrenado(frame_binary):
    df = frame_binary.drop(columns=["id", "constante", "casi_vacia", "fecha", "monto_texto"])
    cfg = A.TrainConfig(target="objetivo", budget_seconds=8, max_models=2,
                        shap=False, permutation_importance=True)
    return A.train(df, cfg)


def test_las_tres_ventanas_no_se_solapan(frame_binary):
    cfg = A.TrainConfig(target="objetivo", task="binary")
    y = frame_binary["objetivo"]
    tr, se, ho = A.split_indices(len(frame_binary), frame_binary, cfg, y)[:3]
    assert len(set(tr) & set(se)) == 0
    assert len(set(tr) & set(ho)) == 0
    assert len(set(se) & set(ho)) == 0
    assert len(tr) + len(se) + len(ho) == len(frame_binary)


def test_particion_temporal_respeta_el_orden(frame_binary):
    df = frame_binary.copy()
    df["fecha"] = pd.date_range("2020-01-01", periods=len(df), freq="D")
    cfg = A.TrainConfig(target="objetivo", task="binary", time_column="fecha")
    tr, se, ho, modo = A.split_indices(len(df), df, cfg, df["objetivo"])
    assert modo == "temporal"
    # todo el entrenamiento ocurre antes que la selección, y ésta antes del holdout
    assert df.fecha.iloc[tr].max() <= df.fecha.iloc[se].min()
    assert df.fecha.iloc[se].max() <= df.fecha.iloc[ho].min()


def test_informe_binario_completo(entrenado):
    r = entrenado["report"]
    assert r["task"] == "binary"
    assert r["metric"] == "auc"
    assert 0.0 <= r["champion"]["holdout"]["auc"] <= 1.0
    assert r["champion"]["holdout"]["auc"] > 0.55        # la señal existe en el fixture
    assert r["leaderboard"]
    assert r["features"]["ranking"]
    assert r["diagnostics"]["deciles"]
    assert r["verdict"]["level"] in ("ok", "revisar", "alerta")
    assert r["split"]["train"] > r["split"]["holdout"]


def test_toda_metrica_del_holdout_esta_tambien_en_seleccion(entrenado):
    for fila in entrenado["report"]["leaderboard"]:
        assert set(fila["holdout"]) == set(fila["selection"])


def test_regresion_y_correccion_de_sesgo(frame_regression):
    cfg = A.TrainConfig(target="valor", budget_seconds=8, max_models=2, shap=False)
    r = A.train(frame_regression, cfg)["report"]
    assert r["task"] == "regression"
    assert r["champion"]["holdout"]["r2"] > 0.5
    # el total predicho debe cerrar contra el total real
    assert abs(r["diagnostics"]["totals"]["desvio_pct"]) < 15


def test_multiclase(frame_regression):
    df = frame_regression.copy()
    df["clase"] = pd.qcut(df.valor, 3, labels=["bajo", "medio", "alto"]).astype(str)
    df = df.drop(columns=["valor"])
    r = A.train(df, A.TrainConfig(target="clase", budget_seconds=8, max_models=2, shap=False))["report"]
    assert r["task"] == "multiclass"
    assert len(r["classes"]) == 3
    assert r["diagnostics"]["per_class"]


def test_smearing_de_duan_corrige_hacia_arriba():
    """exp(media del log) subestima la media; el factor debe compensarlo."""
    rng = np.random.default_rng(4)
    y = rng.lognormal(6, 0.9, 3000)
    tt = A.TargetTransform(use_log=True)
    pred_log = np.full(len(y), np.mean(np.log1p(y)))
    tt.calibrate(y, pred_log)
    assert tt.smearing > 1.0
    sin_correccion = float(np.mean(np.expm1(pred_log)))
    con_correccion = float(np.mean(tt.inverse(pred_log)))
    assert abs(con_correccion - y.mean()) < abs(sin_correccion - y.mean())


def test_objetivo_sesgado_activa_el_logaritmo():
    rng = np.random.default_rng(6)
    assert A.should_log(rng.lognormal(5, 1.2, 2000), "auto") is True
    assert A.should_log(rng.normal(100, 10, 2000), "auto") is False
    assert A.should_log(rng.normal(100, 10, 2000), "si") is True


def test_objetivo_inexistente_da_error_claro(frame_binary):
    with pytest.raises(ValueError, match="objetivo"):
        A.train(frame_binary, A.TrainConfig(target="no_existe"))


def test_dataset_demasiado_chico_avisa():
    df = pd.DataFrame({"x": range(10), "y": [0, 1] * 5})
    with pytest.raises(ValueError, match="filas"):
        A.train(df, A.TrainConfig(target="y"))


def test_guardado_carga_y_prediccion(entrenado, frame_binary, dataset_binary):
    card = registry.save(entrenado["bundle"], entrenado["report"], "modelo de prueba",
                         dataset_binary.id)
    assert card["id"].startswith("mdl_")
    assert card["id"] in {m["id"] for m in registry.list_models()}

    bundle, ficha = registry.load(card["id"])
    assert ficha["target"] == "objetivo"

    filas = frame_binary.head(20)
    pred = registry.predict_frame(bundle, filas)
    assert len(pred) == 20
    assert "prediccion" in pred.columns
    prob = [c for c in pred.columns if c.startswith("prob_")]
    assert prob and pred[prob[0]].between(0, 1).all()


def test_scoring_de_un_dataset_entero(entrenado, dataset_binary):
    card = registry.save(entrenado["bundle"], entrenado["report"], "para scoring", dataset_binary.id)
    out = registry.score_dataset(card["id"], dataset_binary.id, keep_columns=["id"])
    assert out["rows"] == dataset_binary.rows
    nombres = [c["name"] for c in out["dataset"]["columns"]]
    assert "prediccion" in nombres and "id" in nombres


def test_progreso_llega_al_final(frame_binary):
    vistos = []
    A.train(frame_binary.drop(columns=["id", "constante", "casi_vacia", "fecha", "monto_texto"]),
            A.TrainConfig(target="objetivo", budget_seconds=4, max_models=1, shap=False,
                          permutation_importance=False),
            progress=lambda p, m: vistos.append((p, m)))
    assert vistos[-1][0] == 100
    assert max(p for p, _ in vistos) == 100
