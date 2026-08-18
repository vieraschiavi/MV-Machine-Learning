"""Familias de gradient boosting. Son las que suelen ganar en tabular."""
from __future__ import annotations

from . import ModelSpec, register

try:
    import lightgbm as lgb
    _LGB = True
except Exception:                                   # pragma: no cover
    _LGB = False
try:
    import xgboost as xgb
    _XGB = True
except Exception:                                   # pragma: no cover
    _XGB = False
try:
    import catboost as cb
    _CB = True
except Exception:                                   # pragma: no cover
    _CB = False

ALL_TASKS = ("binary", "multiclass", "regression")


def _lgbm(task, p, rs):
    kw = dict(verbosity=-1, random_state=rs, n_jobs=-1, subsample_freq=1, **p)
    if task == "regression":
        return lgb.LGBMRegressor(**kw)
    return lgb.LGBMClassifier(class_weight="balanced" if task == "binary" else None, **kw)


register(ModelSpec(
    name="lightgbm", label="LightGBM", matrix="tree", tasks=ALL_TASKS, priority=10,
    available=lambda: _LGB,
    description="Gradient boosting por hojas; rápido y fuerte en tabular.",
    default={"num_leaves": 31, "learning_rate": 0.06, "n_estimators": 300,
             "min_child_samples": 40, "reg_lambda": 5.0,
             "colsample_bytree": 0.8, "subsample": 0.85},
    space=lambda t: {
        "num_leaves": t.suggest_int("num_leaves", 7, 127, log=True),
        "learning_rate": t.suggest_float("learning_rate", 0.02, 0.25, log=True),
        "n_estimators": t.suggest_int("n_estimators", 120, 700),
        "min_child_samples": t.suggest_int("min_child_samples", 5, 200, log=True),
        "reg_lambda": t.suggest_float("reg_lambda", 1e-3, 50.0, log=True),
        "colsample_bytree": t.suggest_float("colsample_bytree", 0.5, 1.0),
        "subsample": t.suggest_float("subsample", 0.6, 1.0),
    },
    make=_lgbm,
))


def _xgboost(task, p, rs):
    kw = dict(random_state=rs, n_jobs=-1, tree_method="hist", verbosity=0,
              enable_categorical=False, **p)
    if task == "regression":
        return xgb.XGBRegressor(**kw)
    return xgb.XGBClassifier(eval_metric="logloss", **kw)


register(ModelSpec(
    name="xgboost", label="XGBoost", matrix="tree", tasks=ALL_TASKS, priority=11,
    available=lambda: _XGB,
    description="Gradient boosting por niveles con regularización fuerte.",
    default={"max_depth": 6, "learning_rate": 0.08, "n_estimators": 300,
             "min_child_weight": 3.0, "reg_lambda": 2.0,
             "subsample": 0.85, "colsample_bytree": 0.8},
    space=lambda t: {
        "max_depth": t.suggest_int("max_depth", 3, 10),
        "learning_rate": t.suggest_float("learning_rate", 0.02, 0.3, log=True),
        "n_estimators": t.suggest_int("n_estimators", 120, 600),
        "min_child_weight": t.suggest_float("min_child_weight", 0.5, 30.0, log=True),
        "reg_lambda": t.suggest_float("reg_lambda", 1e-2, 50.0, log=True),
        "subsample": t.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": t.suggest_float("colsample_bytree", 0.5, 1.0),
    },
    make=_xgboost,
))


def _hgb(task, p, rs):
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    kw = dict(random_state=rs, early_stopping=False, **p)
    return (HistGradientBoostingRegressor(**kw) if task == "regression"
            else HistGradientBoostingClassifier(**kw))


register(ModelSpec(
    name="hist_gradient_boosting", label="Hist. Gradient Boosting", matrix="tree",
    tasks=ALL_TASKS, priority=12,
    description="Boosting con histogramas de scikit-learn; sin dependencias externas.",
    default={"max_leaf_nodes": 31, "learning_rate": 0.07, "max_iter": 250,
             "min_samples_leaf": 30, "l2_regularization": 3.0},
    space=lambda t: {
        "max_leaf_nodes": t.suggest_int("max_leaf_nodes", 7, 96, log=True),
        "learning_rate": t.suggest_float("learning_rate", 0.02, 0.3, log=True),
        "max_iter": t.suggest_int("max_iter", 120, 500),
        "min_samples_leaf": t.suggest_int("min_samples_leaf", 5, 150, log=True),
        "l2_regularization": t.suggest_float("l2_regularization", 1e-3, 30.0, log=True),
    },
    make=_hgb,
))


def _catboost(task, p, rs):
    kw = dict(random_seed=rs, verbose=0, allow_writing_files=False, **p)
    return cb.CatBoostRegressor(**kw) if task == "regression" else cb.CatBoostClassifier(**kw)


register(ModelSpec(
    name="catboost", label="CatBoost", matrix="tree", tasks=ALL_TASKS, priority=20,
    max_rows=60_000, available=lambda: _CB,
    description="Boosting ordenado; competitivo pero lento en datasets grandes.",
    default={"depth": 6, "learning_rate": 0.1, "iterations": 300, "l2_leaf_reg": 3.0},
    space=lambda t: {
        "depth": t.suggest_int("depth", 4, 9),
        "learning_rate": t.suggest_float("learning_rate", 0.03, 0.3, log=True),
        "iterations": t.suggest_int("iterations", 150, 500),
        "l2_leaf_reg": t.suggest_float("l2_leaf_reg", 1.0, 20.0, log=True),
    },
    make=_catboost,
))


def _gb_clasico(task, p, rs):
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
    kw = dict(random_state=rs, **p)
    return (GradientBoostingRegressor(**kw) if task == "regression"
            else GradientBoostingClassifier(**kw))


register(ModelSpec(
    name="gradient_boosting", label="Gradient Boosting clásico", matrix="tree",
    tasks=ALL_TASKS, priority=45, max_rows=30_000,
    description="El boosting original de scikit-learn; preciso pero lento.",
    default={"n_estimators": 200, "learning_rate": 0.08, "max_depth": 3,
             "subsample": 0.9, "min_samples_leaf": 20},
    space=lambda t: {
        "n_estimators": t.suggest_int("n_estimators", 80, 400),
        "learning_rate": t.suggest_float("learning_rate", 0.02, 0.3, log=True),
        "max_depth": t.suggest_int("max_depth", 2, 6),
        "subsample": t.suggest_float("subsample", 0.6, 1.0),
        "min_samples_leaf": t.suggest_int("min_samples_leaf", 5, 100, log=True),
    },
    make=_gb_clasico,
))
