"""Familias de árboles con bagging y boosting adaptativo."""
from __future__ import annotations

from . import ModelSpec, register

ALL_TASKS = ("binary", "multiclass", "regression")


def _forest(task, p, rs, extra: bool):
    from sklearn.ensemble import (
        ExtraTreesClassifier,
        ExtraTreesRegressor,
        RandomForestClassifier,
        RandomForestRegressor,
    )
    kw = dict(random_state=rs, n_jobs=-1, **p)
    if task == "regression":
        return (ExtraTreesRegressor if extra else RandomForestRegressor)(**kw)
    return (ExtraTreesClassifier if extra else RandomForestClassifier)(
        class_weight="balanced_subsample" if task == "binary" else None, **kw)


_FOREST_SPACE = lambda t: {  # noqa: E731 - espacio compartido entre las dos familias
    "n_estimators": t.suggest_int("n_estimators", 150, 500),
    "max_depth": t.suggest_int("max_depth", 5, 28),
    "min_samples_leaf": t.suggest_int("min_samples_leaf", 1, 40, log=True),
    "max_features": t.suggest_float("max_features", 0.3, 1.0),
}

register(ModelSpec(
    name="random_forest", label="Random Forest", matrix="tree", tasks=ALL_TASKS,
    priority=15,
    description="Bagging de árboles profundos; robusto sin ajuste fino.",
    default={"n_estimators": 250, "max_depth": 18, "min_samples_leaf": 5, "max_features": 0.7},
    space=_FOREST_SPACE,
    make=lambda task, p, rs: _forest(task, p, rs, extra=False),
))

register(ModelSpec(
    name="extra_trees", label="Extra Trees", matrix="tree", tasks=ALL_TASKS,
    priority=16,
    description="Árboles con cortes aleatorios; menos varianza que Random Forest.",
    default={"n_estimators": 250, "max_depth": 20, "min_samples_leaf": 3, "max_features": 0.8},
    space=_FOREST_SPACE,
    make=lambda task, p, rs: _forest(task, p, rs, extra=True),
))


def _tree(task, p, rs):
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
    kw = dict(random_state=rs, **p)
    return DecisionTreeRegressor(**kw) if task == "regression" else DecisionTreeClassifier(**kw)


register(ModelSpec(
    name="decision_tree", label="Árbol de decisión", matrix="tree", tasks=ALL_TASKS,
    priority=60,
    description="Un solo árbol; débil como predictor, útil como referencia interpretable.",
    default={"max_depth": 8, "min_samples_leaf": 20},
    space=lambda t: {
        "max_depth": t.suggest_int("max_depth", 3, 20),
        "min_samples_leaf": t.suggest_int("min_samples_leaf", 2, 200, log=True),
        "min_samples_split": t.suggest_int("min_samples_split", 2, 50, log=True),
    },
    make=_tree,
))


def _adaboost(task, p, rs):
    from sklearn.ensemble import AdaBoostClassifier, AdaBoostRegressor
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
    depth = int(p.pop("base_depth", 3))
    kw = dict(random_state=rs, **p)
    if task == "regression":
        return AdaBoostRegressor(estimator=DecisionTreeRegressor(max_depth=depth), **kw)
    return AdaBoostClassifier(estimator=DecisionTreeClassifier(max_depth=depth), **kw)


register(ModelSpec(
    name="adaboost", label="AdaBoost", matrix="tree", tasks=ALL_TASKS,
    priority=48, max_rows=60_000,
    description="Boosting adaptativo sobre árboles cortos.",
    default={"n_estimators": 150, "learning_rate": 0.5, "base_depth": 3},
    space=lambda t: {
        "n_estimators": t.suggest_int("n_estimators", 50, 400),
        "learning_rate": t.suggest_float("learning_rate", 0.05, 1.5, log=True),
        "base_depth": t.suggest_int("base_depth", 1, 6),
    },
    make=_adaboost,
))
