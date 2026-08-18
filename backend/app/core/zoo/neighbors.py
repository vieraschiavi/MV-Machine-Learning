"""Familias por distancia, probabilísticas y redes chicas (para datasets acotados)."""
from __future__ import annotations

from . import ModelSpec, register

CLF = ("binary", "multiclass")
ALL_TASKS = ("binary", "multiclass", "regression")


def _knn(task, p, rs):
    from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
    kw = {"n_neighbors": int(p.get("n_neighbors", 15)),
          "weights": p.get("weights", "distance"), "n_jobs": -1}
    return KNeighborsRegressor(**kw) if task == "regression" else KNeighborsClassifier(**kw)


register(ModelSpec(
    name="knn", label="K vecinos más cercanos", matrix="linear", tasks=ALL_TASKS,
    priority=62, max_rows=25_000,
    description="Vota por cercanía; sirve de contraste porque no asume ninguna forma.",
    default={"n_neighbors": 15, "weights": "distance"},
    space=lambda t: {
        "n_neighbors": t.suggest_int("n_neighbors", 3, 60, log=True),
        "weights": t.suggest_categorical("weights", ["uniform", "distance"]),
    },
    make=_knn,
))


def _mlp(task, p, rs):
    from sklearn.neural_network import MLPClassifier, MLPRegressor
    capa = int(p.get("hidden", 64))
    kw = {"hidden_layer_sizes": (capa, max(capa // 2, 8)),
          "alpha": p.get("alpha", 1e-4), "learning_rate_init": p.get("lr", 1e-3),
          "max_iter": 300, "early_stopping": True, "random_state": rs}
    return MLPRegressor(**kw) if task == "regression" else MLPClassifier(**kw)


register(ModelSpec(
    name="mlp", label="Red neuronal (MLP)", matrix="linear", tasks=ALL_TASKS,
    priority=57, max_rows=40_000,
    description="Perceptrón multicapa chico; a veces suma en el ensamble.",
    default={"hidden": 64, "alpha": 1e-4, "lr": 1e-3},
    space=lambda t: {
        "hidden": t.suggest_int("hidden", 16, 192, log=True),
        "alpha": t.suggest_float("alpha", 1e-6, 1e-2, log=True),
        "lr": t.suggest_float("lr", 1e-4, 1e-2, log=True),
    },
    make=_mlp,
))


def _nb(task, p, rs):
    from sklearn.naive_bayes import GaussianNB
    return GaussianNB(var_smoothing=p.get("var_smoothing", 1e-9))


register(ModelSpec(
    name="naive_bayes", label="Naive Bayes gaussiano", matrix="linear", tasks=CLF,
    priority=70,
    description="Probabilístico ingenuo; línea de base honesta y casi instantánea.",
    default={"var_smoothing": 1e-9},
    space=lambda t: {"var_smoothing": t.suggest_float("var_smoothing", 1e-11, 1e-6, log=True)},
    make=_nb,
))
