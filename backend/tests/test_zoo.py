"""Registro extensible de familias de modelos."""
from __future__ import annotations

import numpy as np
import pytest
from app.core import zoo
from app.core.automl import TrainConfig


def test_el_catalogo_descubre_todas_las_familias():
    nombres = {c["name"] for c in zoo.catalog()}
    # las siete históricas
    assert {"lightgbm", "xgboost", "hist_gradient_boosting", "random_forest",
            "extra_trees", "catboost", "linear"} <= nombres
    # las incorporadas del catálogo de DashAI
    assert {"knn", "mlp", "adaboost", "decision_tree", "gradient_boosting",
            "elastic_net", "sgd", "naive_bayes"} <= nombres
    assert len(nombres) >= 15


def test_la_ficha_publica_esta_completa():
    for c in zoo.catalog():
        assert c["label"] and c["description"]
        assert c["matrix"] in ("tree", "linear")
        assert set(c["tasks"]) <= {"binary", "multiclass", "regression"}


def test_naive_bayes_no_aparece_en_regresion():
    nombres = {c["name"] for c in zoo.catalog(task="regression")}
    assert "naive_bayes" not in nombres
    assert "lightgbm" in nombres


def test_el_gating_por_tamano_filtra_los_lentos():
    cfg = TrainConfig(target="y")
    chico = zoo.build_zoo("binary", cfg, n_rows=5_000, n_feats=10)
    grande = zoo.build_zoo("binary", cfg, n_rows=300_000, n_feats=10)
    assert "knn" in chico and "catboost" in chico
    assert "knn" not in grande and "catboost" not in grande
    assert "lightgbm" in grande     # los sin tope siempre están


def test_la_seleccion_explicita_ignora_el_gating():
    cfg = TrainConfig(target="y", models=["knn", "naive_bayes"])
    z = zoo.build_zoo("binary", cfg, n_rows=300_000, n_feats=10)
    assert set(z) == {"knn", "naive_bayes"}


def test_la_prioridad_ordena_la_competencia():
    cfg = TrainConfig(target="y")
    z = list(zoo.build_zoo("binary", cfg, n_rows=1_000, n_feats=5))
    assert z[0] == "lightgbm"                 # prioridad 10
    assert z.index("lightgbm") < z.index("linear") < z.index("naive_bayes")


@pytest.mark.parametrize("task", ["binary", "multiclass", "regression"])
def test_cada_familia_crea_y_ajusta_un_estimador(task):
    """Cada spec debe poder entrenar y predecir de verdad, no sólo declararse."""
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (120, 4))
    if task == "regression":
        y = X[:, 0] * 2 + rng.normal(0, .1, 120)
    elif task == "binary":
        y = (X[:, 0] > 0).astype(int)
    else:
        y = np.digitize(X[:, 0], [-0.5, 0.5])
    for name, spec in zoo.all_specs().items():
        if task not in spec.tasks or not spec.available():
            continue
        est = spec.make(task, dict(spec.default), 0)
        est.fit(X, y)
        if task == "regression":
            assert np.isfinite(est.predict(X)).all(), name
        else:
            proba = est.predict_proba(X)
            assert np.isfinite(proba).all(), name


def test_el_espacio_de_optuna_es_valido():
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    for name, spec in zoo.all_specs().items():
        study = optuna.create_study()
        params = spec.space(study.ask())
        assert isinstance(params, dict) and params, name


def test_registrar_una_familia_nueva_no_toca_el_motor():
    from sklearn.dummy import DummyClassifier

    spec = zoo.ModelSpec(
        name="dummy_de_prueba", label="Dummy", matrix="linear", tasks=("binary",),
        default={}, space=lambda t: {"strategy": t.suggest_categorical("strategy", ["prior"])},
        make=lambda task, p, rs: DummyClassifier(strategy="prior"),
        priority=99)
    zoo.register(spec)
    try:
        cfg = TrainConfig(target="y", models=["dummy_de_prueba"])
        z = zoo.build_zoo("binary", cfg, 100, 3)
        assert "dummy_de_prueba" in z
    finally:
        zoo._REGISTRY.pop("dummy_de_prueba", None)
