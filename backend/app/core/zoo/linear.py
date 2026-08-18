"""Familias lineales: regularización L1/L2 y descenso por gradiente."""
from __future__ import annotations

from . import ModelSpec, register

ALL_TASKS = ("binary", "multiclass", "regression")


def _ridge_logreg(task, p, rs):
    from sklearn.linear_model import LogisticRegression, Ridge
    if task == "regression":
        return Ridge(alpha=p.get("alpha", 1.0), random_state=rs)
    return LogisticRegression(C=1.0 / max(p.get("alpha", 1.0), 1e-6), max_iter=3000,
                              class_weight="balanced" if task == "binary" else None,
                              n_jobs=-1)


register(ModelSpec(
    name="linear", label="Lineal (Ridge / Logística)", matrix="linear", tasks=ALL_TASKS,
    priority=30,
    description="Referencia lineal regularizada; si un árbol no le gana, sospechá.",
    default={"alpha": 1.0},
    space=lambda t: {"alpha": t.suggest_float("alpha", 1e-3, 30.0, log=True)},
    make=_ridge_logreg,
))


def _elastic(task, p, rs):
    from sklearn.linear_model import ElasticNet, LogisticRegression
    if task == "regression":
        return ElasticNet(alpha=p.get("alpha", 0.1), l1_ratio=p.get("l1_ratio", 0.5),
                          max_iter=5000, random_state=rs)
    return LogisticRegression(penalty="elasticnet", solver="saga",
                              C=1.0 / max(p.get("alpha", 0.1), 1e-6),
                              l1_ratio=p.get("l1_ratio", 0.5), max_iter=3000,
                              class_weight="balanced" if task == "binary" else None,
                              n_jobs=-1)


register(ModelSpec(
    name="elastic_net", label="Elastic Net", matrix="linear", tasks=ALL_TASKS,
    priority=55,
    description="Lineal con mezcla L1/L2: además selecciona variables.",
    default={"alpha": 0.05, "l1_ratio": 0.5},
    space=lambda t: {
        "alpha": t.suggest_float("alpha", 1e-4, 5.0, log=True),
        "l1_ratio": t.suggest_float("l1_ratio", 0.05, 0.95),
    },
    make=_elastic,
))


def _sgd(task, p, rs):
    from sklearn.linear_model import SGDClassifier, SGDRegressor
    kw = {"alpha": p.get("alpha", 1e-4), "random_state": rs, "max_iter": 2000,
          "tol": 1e-4, "early_stopping": True}
    if task == "regression":
        return SGDRegressor(loss="huber", **kw)
    # log_loss para tener predict_proba; con hinge sería una SVM sin probabilidad
    return SGDClassifier(loss="log_loss",
                         class_weight="balanced" if task == "binary" else None, **kw)


register(ModelSpec(
    name="sgd", label="SGD (lineal a gran escala)", matrix="linear", tasks=ALL_TASKS,
    priority=58,
    description="Descenso por gradiente estocástico; útil con cientos de miles de filas.",
    default={"alpha": 1e-4},
    space=lambda t: {"alpha": t.suggest_float("alpha", 1e-6, 1e-2, log=True)},
    make=_sgd,
))
