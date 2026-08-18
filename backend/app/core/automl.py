"""Motor de AutoML: elige, optimiza y valida el modelo para la variable objetivo.

Protocolo de validación (es lo que separa un número honesto de uno inflado)
--------------------------------------------------------------------------
Los datos se parten en **tres**, no en dos:

    ENTRENAMIENTO ── se ajustan los modelos
    SELECCIÓN     ── se eligen hiperparámetros, features, calibración y campeón
    HOLDOUT CIEGO ── no se toca en ninguna decisión; es el único número que se reporta

Reportar la ventana con la que se eligió el modelo siempre da mejor de lo que
el modelo realmente es. La brecha entre selección y holdout se informa de forma
explícita: si es grande, el modelo no generaliza y hay que decirlo.

Si se declara una columna temporal, las tres ventanas son consecutivas en el
tiempo (walk-forward): entrenar con el futuro y predecir el pasado infla todas
las métricas y no se puede reproducir en producción.
"""
from __future__ import annotations

import time
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from . import metrics as MT
from .features import Preprocessor, base_columns, select_by_importance

warnings.filterwarnings("ignore")

try:
    HAS_LGB = True
except Exception:                                   # pragma: no cover
    HAS_LGB = False
try:
    HAS_XGB = True
except Exception:                                   # pragma: no cover
    HAS_XGB = False
try:
    HAS_CB = True
except Exception:                                   # pragma: no cover
    HAS_CB = False
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except Exception:                                   # pragma: no cover
    HAS_OPTUNA = False


Progress = Callable[[float, str], None]


def _noop(pct: float, msg: str) -> None:
    return None


# ═══════════════════════════════════════════════════════ configuración ═══════
@dataclass
class TrainConfig:
    target: str
    task: str = "auto"                 # auto | binary | multiclass | regression
    time_column: str | None = None     # activa validación temporal
    exclude: list[str] = field(default_factory=list)
    metric: str | None = None          # None ⇒ métrica primaria de la tarea
    selection_size: float = 0.20
    holdout_size: float = 0.20
    budget_seconds: int = 120          # presupuesto de optimización
    max_models: int = 6
    models: list[str] | None = None    # familias explícitas del catálogo (None = automático)
    feature_selection: bool = True
    calibrate: bool = True             # calibración isotónica (clasificación)
    ensemble: bool = True              # combinar los mejores en vez de coronar uno
    log_target: str = "auto"           # auto | si | no (regresión sesgada)
    permutation_importance: bool = True
    shap: bool = True
    random_state: int = 42
    max_rows: int | None = None


# ══════════════════════════════════════════════════════════ partición ════════
def split_indices(n: int, df: pd.DataFrame, cfg: TrainConfig,
                  y: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    """Devuelve (train, selección, holdout, modo)."""
    if cfg.time_column and cfg.time_column in df.columns:
        order = np.argsort(pd.to_datetime(df[cfg.time_column], errors="coerce")
                           .fillna(pd.Timestamp.min).to_numpy(), kind="stable")
        n_hold = max(int(n * cfg.holdout_size), 1)
        n_sel = max(int(n * cfg.selection_size), 1)
        cut2, cut1 = n - n_hold, n - n_hold - n_sel
        if cut1 < 10:
            cut1, cut2 = int(n * 0.6), int(n * 0.8)
        return order[:cut1], order[cut1:cut2], order[cut2:], "temporal"

    rng = np.random.default_rng(cfg.random_state)
    idx = np.arange(n)
    stratify = None
    if cfg.task in ("binary", "multiclass"):
        vc = y.astype(str).value_counts()
        if (vc >= 3).all() and len(vc) < n / 5:
            stratify = y.astype(str).to_numpy()
    if stratify is None:
        rng.shuffle(idx)
        c1, c2 = int(n * (1 - cfg.selection_size - cfg.holdout_size)), int(n * (1 - cfg.holdout_size))
        return idx[:c1], idx[c1:c2], idx[c2:], "aleatoria"

    tr, se, ho = [], [], []
    for cls in np.unique(stratify):
        pos = idx[stratify == cls].copy()
        rng.shuffle(pos)
        c1 = int(len(pos) * (1 - cfg.selection_size - cfg.holdout_size))
        c2 = int(len(pos) * (1 - cfg.holdout_size))
        c1, c2 = max(c1, 1), max(c2, 2)
        tr += list(pos[:c1])
        se += list(pos[c1:c2])
        ho += list(pos[c2:])
    return np.array(tr), np.array(se), np.array(ho), "estratificada"


# ═══════════════════════════════════════════════════════════ modelos ═════════
class Model:
    """Envoltorio uniforme sobre familias de modelos muy distintas entre sí."""

    def __init__(self, name: str, family: str, matrix: str, estimator, task: str):
        self.name, self.family, self.matrix = name, family, matrix
        self.est, self.task = estimator, task

    def fit(self, Xt, Xl, y, cat_idx=None):
        X = Xt if self.matrix == "tree" else Xl
        if self.family == "lightgbm":
            self.est.fit(X, y, categorical_feature=cat_idx or "auto")
        else:
            self.est.fit(X, y)
        return self

    def predict(self, Xt, Xl):
        X = Xt if self.matrix == "tree" else Xl
        if self.task == "regression":
            return np.asarray(self.est.predict(X), dtype=float)
        proba = self.est.predict_proba(X)
        return proba[:, 1] if self.task == "binary" else proba

    def importances(self, names: list[str]) -> dict[str, float]:
        e = self.est
        v = getattr(e, "feature_importances_", None)
        if v is None:
            c = getattr(e, "coef_", None)
            if c is None:
                return {}
            v = np.abs(np.asarray(c)).mean(0) if np.asarray(c).ndim > 1 else np.abs(np.asarray(c))
        v = np.asarray(v, dtype=float).ravel()
        return {n: float(x) for n, x in zip(names, v[: len(names)], strict=False)}


def _n_classes(y) -> int:
    return int(pd.Series(y).nunique())


def build_zoo(task: str, cfg: TrainConfig, n_rows: int, n_feats: int) -> dict[str, dict]:
    """Catálogo de familias, resuelto por el registro extensible (`core/zoo`)."""
    from . import zoo as Z

    return Z.build_zoo(task, cfg, n_rows, n_feats)


def _hgb(task: str, params: dict, rs: int):
    """Acceso directo al HistGradientBoosting del catálogo (uso interno)."""
    from . import zoo as Z

    return Z.all_specs()["hist_gradient_boosting"].make(task, params, rs)


# ═════════════════════════════════════════════════ transformación target ═════
class TargetTransform:
    """log1p + corrección de smearing de Duan (1983) para regresión sesgada.

    `exp(E[log Y])` subestima `E[Y]` por la desigualdad de Jensen: el monto
    predicho queda sistemáticamente por debajo del real. El factor de smearing
    —la media de los residuos exponenciados— devuelve la escala correcta.
    """

    def __init__(self, use_log: bool):
        self.use_log = use_log
        self.smearing = 1.0

    def fit(self, y: np.ndarray) -> TargetTransform:
        return self

    def forward(self, y: np.ndarray) -> np.ndarray:
        return np.log1p(np.clip(y, 0, None)) if self.use_log else y

    def calibrate(self, y_true: np.ndarray, y_pred_log: np.ndarray) -> None:
        if self.use_log:
            resid = self.forward(y_true) - y_pred_log
            s = float(np.mean(np.exp(resid[np.isfinite(resid)])))
            self.smearing = float(np.clip(s, 0.2, 5.0)) if np.isfinite(s) else 1.0

    def inverse(self, p: np.ndarray) -> np.ndarray:
        return np.expm1(np.clip(p, -50, 50)) * self.smearing if self.use_log else p


def should_log(y: np.ndarray, mode: str) -> bool:
    if mode == "si":
        return True
    if mode == "no":
        return False
    fin = y[np.isfinite(y)]
    if len(fin) < 50 or fin.min() < 0:
        return False
    sk = float(pd.Series(fin).skew())
    return bool(np.isfinite(sk) and sk > 1.5)


# ═══════════════════════════════════════════════════════ optimización ════════
def _score(task: str, y_true, pred, metric: str, classes=None) -> float:
    m = MT.evaluate(task, y_true, pred, classes)
    v = m.get(metric)
    return float(v) if v is not None and np.isfinite(v) else float("-inf" if MT.CATALOG.get(metric, (True,))[0] else "inf")


def optimize_family(family: str, spec: dict, task: str, cfg: TrainConfig,
                    data: dict, metric: str, budget: float,
                    progress: Progress) -> dict[str, Any]:
    """Búsqueda de hiperparámetros de una familia contra la ventana de SELECCIÓN."""
    higher = MT.CATALOG.get(metric, (True,))[0]
    t0 = time.time()
    trials: list[dict[str, Any]] = []

    def evaluate(params: dict) -> float:
        est = spec["make"](params)
        mdl = Model(family, family, spec["matrix"], est, task)
        mdl.fit(data["Xt_tr"], data["Xl_tr"], data["y_tr"], data.get("cat_idx"))
        pred = mdl.predict(data["Xt_se"], data["Xl_se"])
        pred = data["tt"].inverse(pred) if task == "regression" else pred
        s = _score(task, data["y_se_raw"], pred, metric, data.get("classes"))
        trials.append({"params": params, "score": s})
        return s

    best_params, best_score = dict(spec["default"]), evaluate(dict(spec["default"]))

    if HAS_OPTUNA and budget > 3:
        sampler = optuna.samplers.TPESampler(seed=cfg.random_state, n_startup_trials=5)
        study = optuna.create_study(direction="maximize" if higher else "minimize", sampler=sampler)
        study.enqueue_trial(dict(spec["default"]))

        def objective(trial):
            if time.time() - t0 > budget:
                raise optuna.TrialPruned()
            return evaluate(spec["space"](trial))

        try:
            study.optimize(objective, timeout=max(budget - (time.time() - t0), 1),
                           n_trials=60, catch=(Exception,), show_progress_bar=False)
        except Exception:
            pass
        done = [t for t in trials if np.isfinite(t["score"])]
        if done:
            best = max(done, key=lambda t: t["score"]) if higher else min(done, key=lambda t: t["score"])
            best_params, best_score = best["params"], best["score"]

    progress(0, f"{family}: {len(trials)} configuraciones probadas, mejor {metric}={best_score:.4f}")
    return {"family": family, "params": best_params, "selection_score": best_score,
            "n_trials": len(trials), "seconds": round(time.time() - t0, 1)}


# ══════════════════════════════════════════════════════════ ENTRENAR ═════════
def train(df: pd.DataFrame, cfg: TrainConfig, progress: Progress = _noop) -> dict[str, Any]:
    """Corre el pipeline completo y devuelve el informe."""
    t_start = time.time()
    from . import profiling as P

    if cfg.target not in df.columns:
        raise ValueError(f"La variable objetivo «{cfg.target}» no está en el dataset.")

    df = df[df[cfg.target].notna()].reset_index(drop=True)
    if len(df) < 40:
        raise ValueError(f"Sólo quedan {len(df)} filas con la variable objetivo cargada. "
                         "Se necesitan al menos 40 para validar de forma honesta.")

    task = cfg.task if cfg.task != "auto" else P.infer_task(df[cfg.target])
    cfg.task = task
    metric = cfg.metric or MT.PRIMARY[task]
    progress(4, f"Tarea detectada: {_task_label(task)} · métrica de decisión: {metric}")

    drop = set(cfg.exclude) | {cfg.target}
    feat_cols = [c for c in df.columns if c not in drop]
    if cfg.time_column and cfg.time_column in feat_cols:
        feat_cols.remove(cfg.time_column)
    if not feat_cols:
        raise ValueError("No quedan columnas predictoras después de las exclusiones.")

    X_all, y_all = df[feat_cols], df[cfg.target]
    classes: list[Any] | None = None
    if task in ("binary", "multiclass"):
        classes = sorted(pd.Series(y_all).astype(str).unique().tolist())
        y_enc = pd.Series(y_all).astype(str)
        if task == "binary":
            positive = _positive_class(y_enc)
            y_num = (y_enc == positive).astype(int).to_numpy()
        else:
            positive = None
            code = {c: i for i, c in enumerate(classes)}
            y_num = y_enc.map(code).to_numpy()
    else:
        positive = None
        y_num = pd.to_numeric(y_all, errors="coerce").to_numpy(dtype=float)

    i_tr, i_se, i_ho, split_mode = split_indices(len(df), df, cfg, pd.Series(y_num))
    if min(len(i_tr), len(i_se), len(i_ho)) < 5:
        raise ValueError("El dataset es demasiado chico para partir en tres ventanas.")
    progress(8, f"Partición {split_mode}: {len(i_tr):,} entrenamiento · {len(i_se):,} selección · "
                f"{len(i_ho):,} holdout ciego")

    pre = Preprocessor().fit(X_all.iloc[i_tr])
    Xt = pre.transform_tree(X_all)
    Xl = pre.transform_linear(X_all)
    cat_idx = pre.categorical_indices()

    tt = TargetTransform(should_log(y_num, cfg.log_target) if task == "regression" else False)
    y_model = tt.forward(y_num) if task == "regression" else y_num

    data = {
        "Xt_tr": Xt.iloc[i_tr], "Xl_tr": Xl[i_tr], "y_tr": y_model[i_tr],
        "Xt_se": Xt.iloc[i_se], "Xl_se": Xl[i_se], "y_se_raw": y_num[i_se],
        "Xt_ho": Xt.iloc[i_ho], "Xl_ho": Xl[i_ho], "y_ho_raw": y_num[i_ho],
        "cat_idx": cat_idx, "tt": tt, "classes": list(range(len(classes))) if classes else None,
    }
    if task == "regression" and tt.use_log:
        base = Model("cal", "hist_gradient_boosting", "tree",
                     _hgb(task, {"max_leaf_nodes": 31, "learning_rate": 0.1, "max_iter": 150,
                                 "min_samples_leaf": 20, "l2_regularization": 1.0}, cfg.random_state), task)
        base.fit(data["Xt_tr"], data["Xl_tr"], data["y_tr"])
        tt.calibrate(y_num[i_tr], base.predict(data["Xt_tr"], data["Xl_tr"]))
        progress(10, f"Objetivo sesgado: se modela en logaritmo con corrección de smearing "
                     f"(factor {tt.smearing:.3f})")

    # ── 1. optimización por familia ──────────────────────────────────────────
    zoo = build_zoo(task, cfg, len(i_tr), len(feat_cols))
    families = list(zoo)[: cfg.max_models]
    per_family = max(cfg.budget_seconds / max(len(families), 1), 4)
    results: list[dict[str, Any]] = []
    for k, fam in enumerate(families):
        progress(12 + 40 * k / len(families), f"Optimizando {fam} ({k+1}/{len(families)})")
        try:
            results.append(optimize_family(fam, zoo[fam], task, cfg, data, metric,
                                           per_family, progress))
        except Exception as exc:
            results.append({"family": fam, "params": {}, "selection_score": float("nan"),
                            "error": str(exc)[:200], "n_trials": 0, "seconds": 0})
    ok = [r for r in results if np.isfinite(r.get("selection_score", float("nan")))]
    if not ok:
        raise RuntimeError("Ninguna familia de modelos pudo entrenarse: " +
                           "; ".join(f"{r['family']}: {r.get('error', 's/d')}" for r in results))
    higher = MT.CATALOG.get(metric, (True,))[0]
    ok.sort(key=lambda r: r["selection_score"], reverse=higher)

    # ── 2. selección de features sobre el mejor ──────────────────────────────
    feature_report: dict[str, Any] = {"applied": False}
    if cfg.feature_selection and len(pre.feature_names_tree) > 8:
        progress(56, "Depurando features por importancia")
        feature_report = _feature_selection(ok[0], zoo, task, cfg, data, pre, X_all,
                                            i_tr, i_se, metric, progress)
        if feature_report.get("applied"):
            pre, Xt, Xl = feature_report["pre"], feature_report["Xt"], feature_report["Xl"]
            cat_idx = pre.categorical_indices()
            data.update({"Xt_tr": Xt.iloc[i_tr], "Xl_tr": Xl[i_tr],
                         "Xt_se": Xt.iloc[i_se], "Xl_se": Xl[i_se],
                         "Xt_ho": Xt.iloc[i_ho], "Xl_ho": Xl[i_ho], "cat_idx": cat_idx})
            feature_report.pop("pre")
            feature_report.pop("Xt")
            feature_report.pop("Xl")

    # ── 3. ajuste final de cada familia y predicciones ───────────────────────
    progress(62, "Ajustando los modelos finalistas")
    fitted: dict[str, Model] = {}
    pred_se: dict[str, np.ndarray] = {}
    pred_ho: dict[str, np.ndarray] = {}
    for r in ok:
        fam = r["family"]
        try:
            mdl = Model(fam, fam, zoo[fam]["matrix"], zoo[fam]["make"](r["params"]), task)
            mdl.fit(data["Xt_tr"], data["Xl_tr"], data["y_tr"], cat_idx)
            ps = mdl.predict(data["Xt_se"], data["Xl_se"])
            ph = mdl.predict(data["Xt_ho"], data["Xl_ho"])
            if task == "regression":
                ps, ph = tt.inverse(ps), tt.inverse(ph)
            fitted[fam], pred_se[fam], pred_ho[fam] = mdl, ps, ph
        except Exception as exc:
            r["error"] = str(exc)[:200]

    if not fitted:
        raise RuntimeError("No se pudo ajustar ningún modelo final.")

    # ── 4. calibración isotónica (clasificación) ─────────────────────────────
    calibrators: dict[str, Any] = {}
    if cfg.calibrate and task == "binary":
        progress(70, "Calibrando probabilidades (isotónica sobre la ventana de selección)")
        for fam in list(fitted):
            try:
                iso = IsotonicRegression(out_of_bounds="clip").fit(pred_se[fam], data["y_se_raw"])
                cal_se, cal_ho = np.clip(iso.predict(pred_se[fam]), 0, 1), np.clip(iso.predict(pred_ho[fam]), 0, 1)
                if MT.is_better("ece", MT.ece(data["y_se_raw"], cal_se),
                                MT.ece(data["y_se_raw"], pred_se[fam])):
                    calibrators[fam] = iso
                    pred_se[fam], pred_ho[fam] = cal_se, cal_ho
            except Exception:
                continue

    # ── 5. campeón vs combinación ────────────────────────────────────────────
    progress(76, "Comparando el mejor modelo contra la combinación de modelos")
    board: list[dict[str, Any]] = []
    for fam in fitted:
        board.append({
            "model": fam, "type": "individual",
            "params": next(r["params"] for r in ok if r["family"] == fam),
            "n_trials": next(r.get("n_trials", 0) for r in ok if r["family"] == fam),
            "selection": MT.evaluate(task, data["y_se_raw"], pred_se[fam], data.get("classes")),
            "holdout": MT.evaluate(task, data["y_ho_raw"], pred_ho[fam], data.get("classes")),
            "calibrated": fam in calibrators,
        })
    board.sort(key=lambda b: b["selection"].get(metric, float("nan")), reverse=higher)

    ens_members: list[str] = []
    if cfg.ensemble and len(fitted) >= 2:
        ens_members = [b["model"] for b in board[:3]]
        ps = np.mean([pred_se[m] for m in ens_members], axis=0)
        ph = np.mean([pred_ho[m] for m in ens_members], axis=0)
        board.append({
            "model": "ensemble(" + " + ".join(ens_members) + ")", "type": "ensemble",
            "params": {"miembros": ens_members, "combinacion": "promedio simple"},
            "n_trials": 0,
            "selection": MT.evaluate(task, data["y_se_raw"], ps, data.get("classes")),
            "holdout": MT.evaluate(task, data["y_ho_raw"], ph, data.get("classes")),
            "calibrated": any(m in calibrators for m in ens_members),
        })
        pred_se["__ensemble__"], pred_ho["__ensemble__"] = ps, ph

    board.sort(key=lambda b: b["selection"].get(metric, float("nan")), reverse=higher)
    champion = board[0]
    champ_key = "__ensemble__" if champion["type"] == "ensemble" else champion["model"]
    p_ho = pred_ho[champ_key]

    sel_v, hold_v = champion["selection"].get(metric), champion["holdout"].get(metric)
    # La brecha se normaliza para que POSITIVO signifique siempre "el holdout
    # salió peor", sin importar si la métrica se maximiza o se minimiza.
    if sel_v is None or hold_v is None:
        gap = float("nan")
    else:
        gap = (float(sel_v) - float(hold_v)) if higher else (float(hold_v) - float(sel_v))

    # ── 6. importancia y explicabilidad ──────────────────────────────────────
    progress(84, "Midiendo el aporte de cada variable")
    from .explain import explain_model
    explanation = explain_model(
        task=task, champion=champion, fitted=fitted, ens_members=ens_members,
        pre=pre, data=data, tt=tt, metric=metric, cfg=cfg, progress=progress)

    # ── 7. diagnóstico del holdout ───────────────────────────────────────────
    progress(94, "Armando el diagnóstico")
    diagnostics = _diagnostics(task, data["y_ho_raw"], p_ho, classes, positive)

    bundle = {
        "preprocessor": pre, "models": fitted, "calibrators": calibrators,
        "ens_members": ens_members, "champion_key": champ_key,
        "target_transform": tt, "classes": classes, "positive": positive,
        "features": feat_cols, "task": task, "config": cfg,
    }

    report = {
        "task": task, "task_label": _task_label(task), "target": cfg.target,
        "metric": metric, "metric_info": MT.describe(metric),
        "rows_used": int(len(df)), "n_features_in": len(feat_cols),
        "n_features_used": len(pre.feature_names_tree),
        "split": {"mode": split_mode, "train": int(len(i_tr)), "selection": int(len(i_se)),
                  "holdout": int(len(i_ho)), "time_column": cfg.time_column},
        "champion": {
            "model": champion["model"], "type": champion["type"], "params": champion["params"],
            "selection": champion["selection"], "holdout": champion["holdout"],
            "gap": None if not np.isfinite(gap) else round(gap, 5),
            "calibrated": champion["calibrated"],
        },
        "leaderboard": board,
        "features": explanation,
        "feature_selection": feature_report,
        "diagnostics": diagnostics,
        "target_transform": {"log": tt.use_log, "smearing": round(tt.smearing, 4)},
        "classes": classes, "positive_class": positive,
        "seconds": round(time.time() - t_start, 1),
        "verdict": _verdict(task, metric, champion, gap, board),
    }
    progress(100, "Listo")
    return {"report": report, "bundle": bundle}


def _task_label(task: str) -> str:
    return {"binary": "clasificación binaria", "multiclass": "clasificación multiclase",
            "regression": "regresión"}.get(task, task)


def _positive_class(y: pd.Series) -> str:
    """Clase positiva = la minoritaria, salvo que haya un valor canónico (1/sí/true)."""
    vc = y.value_counts()
    for cand in ("1", "1.0", "True", "true", "SI", "Sí", "si", "Y", "YES", "yes"):
        if cand in vc.index:
            return cand
    return str(vc.index[-1])


def _feature_selection(best: dict, zoo: dict, task: str, cfg: TrainConfig, data: dict,
                       pre: Preprocessor, X_all: pd.DataFrame, i_tr, i_se,
                       metric: str, progress: Progress) -> dict[str, Any]:
    """Poda features poco informativas y sólo la acepta si NO empeora la selección."""
    fam = best["family"]
    try:
        mdl = Model(fam, fam, zoo[fam]["matrix"], zoo[fam]["make"](best["params"]), task)
        mdl.fit(data["Xt_tr"], data["Xl_tr"], data["y_tr"], data.get("cat_idx"))
        names = (pre.feature_names_tree if zoo[fam]["matrix"] == "tree" else pre.feature_names_linear)
        imp = mdl.importances(names)
        if not imp:
            return {"applied": False, "reason": "el modelo no expone importancias"}
        keep_feats, dropped = select_by_importance(imp, keep_min=max(5, len(imp) // 6))
        keep_cols = [c for c in X_all.columns if c in set(base_columns(keep_feats))]
        if len(keep_cols) >= len(X_all.columns) or len(keep_cols) < 2:
            return {"applied": False, "reason": "no hay features prescindibles"}

        base_score = best["selection_score"]
        pre2 = Preprocessor().fit(X_all[keep_cols].iloc[i_tr])
        Xt2, Xl2 = pre2.transform_tree(X_all[keep_cols]), pre2.transform_linear(X_all[keep_cols])
        m2 = Model(fam, fam, zoo[fam]["matrix"], zoo[fam]["make"](best["params"]), task)
        m2.fit(Xt2.iloc[i_tr], Xl2[i_tr], data["y_tr"], pre2.categorical_indices())
        p2 = m2.predict(Xt2.iloc[i_se], Xl2[i_se])
        p2 = data["tt"].inverse(p2) if task == "regression" else p2
        s2 = _score(task, data["y_se_raw"], p2, metric, data.get("classes"))

        higher = MT.CATALOG.get(metric, (True,))[0]
        tol = 0.002 if higher else -0.002
        accept = (s2 >= base_score - tol) if higher else (s2 <= base_score - tol)
        out = {"applied": bool(accept), "kept": keep_cols,
               "dropped": [c for c in X_all.columns if c not in keep_cols],
               "score_before": round(float(base_score), 5), "score_after": round(float(s2), 5),
               "reason": ("se descartaron features sin costo de performance" if accept
                          else "podar empeoraba la métrica: se conservan todas")}
        if accept:
            out.update({"pre": pre2, "Xt": Xt2, "Xl": Xl2})
            progress(60, f"Features: {len(X_all.columns)} → {len(keep_cols)} sin perder performance")
        return out
    except Exception as exc:
        return {"applied": False, "reason": f"no se pudo evaluar la poda: {exc}"[:200]}


def _diagnostics(task: str, y, p, classes, positive) -> dict[str, Any]:
    """Curvas y tablas del holdout para mostrar en pantalla."""
    y = np.asarray(y)
    out: dict[str, Any] = {}
    if task == "binary":
        p = np.asarray(p, float)
        d = pd.DataFrame({"y": y, "p": p}).sort_values("p", ascending=False).reset_index(drop=True)
        d["decil"] = pd.qcut(d.index, 10, labels=False, duplicates="drop") + 1
        g = d.groupby("decil").agg(n=("y", "size"), positivos=("y", "sum"),
                                   prob_media=("p", "mean"), tasa_real=("y", "mean"))
        base = float(d.y.mean()) or 1e-9
        g["lift"] = g.tasa_real / base
        g["captura_acum"] = g.positivos.cumsum() / max(d.y.sum(), 1)
        out["deciles"] = [{"decil": int(i), **{k: float(v) for k, v in r.items()}}
                          for i, r in g.iterrows()]
        from sklearn.metrics import precision_recall_curve, roc_curve
        fpr, tpr, _ = roc_curve(y, p)
        step = max(len(fpr) // 120, 1)
        out["roc"] = [{"fpr": float(a), "tpr": float(b)} for a, b in zip(fpr[::step], tpr[::step], strict=False)]
        pr, rc, _ = precision_recall_curve(y, p)
        step = max(len(pr) // 120, 1)
        out["pr"] = [{"precision": float(a), "recall": float(b)} for a, b in zip(pr[::step], rc[::step], strict=False)]
        bins = pd.qcut(pd.Series(p), 10, duplicates="drop", labels=False)
        cal = pd.DataFrame({"b": bins, "y": y, "p": p}).groupby("b").agg(
            predicha=("p", "mean"), observada=("y", "mean"), n=("y", "size"))
        out["calibration"] = [{"predicha": float(r.predicha), "observada": float(r.observada),
                               "n": int(r.n)} for _, r in cal.iterrows()]
        thr = float(np.quantile(p, 1 - d.y.mean())) if 0 < d.y.mean() < 1 else 0.5
        yh = (p >= thr).astype(int)
        out["confusion"] = {"vp": int(((yh == 1) & (y == 1)).sum()), "fp": int(((yh == 1) & (y == 0)).sum()),
                            "fn": int(((yh == 0) & (y == 1)).sum()), "vn": int(((yh == 0) & (y == 0)).sum()),
                            "umbral": thr}
        out["positive_class"] = positive
    elif task == "multiclass":
        proba = np.asarray(p, float)
        yh = proba.argmax(1)
        k = proba.shape[1]
        cm = np.zeros((k, k), int)
        for a, b in zip(y.astype(int), yh, strict=False):
            cm[a, b] += 1
        out["confusion_matrix"] = cm.tolist()
        out["classes"] = classes
        out["per_class"] = [
            {"clase": classes[i] if classes and i < len(classes) else str(i),
             "soporte": int(cm[i].sum()),
             "recall": float(cm[i, i] / cm[i].sum()) if cm[i].sum() else 0.0,
             "precision": float(cm[i, i] / cm[:, i].sum()) if cm[:, i].sum() else 0.0}
            for i in range(k)]
    else:
        p = np.asarray(p, float)
        res = p - y
        out["residuals"] = {"mean": float(np.mean(res)), "std": float(np.std(res)),
                            "p05": float(np.quantile(res, .05)), "p95": float(np.quantile(res, .95))}
        n = min(len(y), 1500)
        idx = np.linspace(0, len(y) - 1, n).astype(int)
        out["scatter"] = [{"real": float(y[i]), "pred": float(p[i])} for i in idx]
        try:
            b = pd.qcut(pd.Series(p), 10, duplicates="drop", labels=False)
            g = pd.DataFrame({"b": b, "y": y, "p": p}).groupby("b").agg(
                real=("y", "mean"), pred=("p", "mean"), n=("y", "size"))
            out["bins"] = [{"decil": int(i) + 1, "real": float(r.real), "pred": float(r.pred),
                            "n": int(r.n)} for i, r in g.iterrows()]
        except Exception:
            out["bins"] = []
        total_real, total_pred = float(np.sum(y)), float(np.sum(p))
        out["totals"] = {"real": total_real, "predicho": total_pred,
                         "desvio_pct": (total_pred / total_real - 1) * 100 if total_real else None}
    return out


def _verdict(task: str, metric: str, champion: dict, gap: float, board: list[dict]) -> dict[str, Any]:
    """Lectura del resultado en lenguaje llano, con su semáforo."""
    hold = champion["holdout"].get(metric)
    notes: list[dict[str, str]] = []
    level = "ok"

    if task == "binary":
        auc = champion["holdout"].get("auc", 0.5)
        if auc >= 0.99:
            level = "alerta"
            notes.append({"level": "alerta", "text":
                          f"AUC de {auc:.4f} en holdout ciego. Un valor así casi siempre indica que "
                          f"alguna columna contiene la respuesta. Revisá la auditoría de fuga antes de usarlo."})
        elif auc >= 0.85:
            notes.append({"level": "ok", "text": f"AUC {auc:.4f}: capacidad de ordenamiento alta."})
        elif auc >= 0.70:
            notes.append({"level": "ok", "text": f"AUC {auc:.4f}: capacidad de ordenamiento útil para priorizar."})
        else:
            level = "revisar"
            notes.append({"level": "revisar", "text":
                          f"AUC {auc:.4f}: el modelo apenas ordena mejor que el azar. Hacen falta mejores variables."})
        ece_v = champion["holdout"].get("ece")
        if ece_v is not None and np.isfinite(ece_v):
            notes.append({"level": "ok" if ece_v < 0.05 else "revisar",
                          "text": f"Error de calibración {ece_v:.4f}: "
                                  + ("las probabilidades se pueden leer como probabilidades."
                                     if ece_v < 0.05 else
                                     "las probabilidades están corridas; usalas para ordenar, no como porcentaje literal.")})
    elif task == "regression":
        r2 = champion["holdout"].get("r2", 0.0)
        wm = champion["holdout"].get("wmape")
        if r2 < 0:
            level = "revisar"
            notes.append({"level": "revisar", "text":
                          "R² negativo en holdout: el modelo predice peor que la media del objetivo."})
        else:
            notes.append({"level": "ok", "text": f"R² {r2:.4f} y WMAPE {wm:.1%} en holdout ciego." if wm is not None
                          else f"R² {r2:.4f} en holdout ciego."})
        bias = champion["holdout"].get("bias")
        if bias is not None and np.isfinite(bias) and abs(bias) > 0.05:
            level = "revisar" if level == "ok" else level
            notes.append({"level": "revisar", "text":
                          f"Sesgo agregado de {bias:+.1%}: el total predicho no cierra contra el total real."})
    else:
        acc = champion["holdout"].get("balanced_accuracy", 0)
        notes.append({"level": "ok" if acc > 0.6 else "revisar",
                      "text": f"Exactitud balanceada {acc:.1%} en holdout ciego."})

    if np.isfinite(gap):
        big = gap > 0.05
        notes.append({"level": "revisar" if big else "ok", "text":
                      f"Degradación de selección a holdout: {gap:+.4f} en {metric}. "
                      + ("Es grande: el modelo se ajustó a la ventana con la que se lo eligió y "
                         "no sostiene la performance fuera de ella."
                         if big else "Es chica: el resultado se sostiene fuera de la ventana de elección.")})
        if big and level == "ok":
            level = "revisar"

    ens = next((b for b in board if b["type"] == "ensemble"), None)
    if ens:
        best_single = next((b for b in board if b["type"] == "individual"), None)
        if best_single:
            a, b = ens["holdout"].get(metric), best_single["holdout"].get(metric)
            if a is not None and b is not None and np.isfinite(a) and np.isfinite(b):
                notes.append({"level": "info", "text":
                              f"Combinación vs mejor modelo individual en holdout: {a:.4f} vs {b:.4f}. "
                              + ("Combinar generalizó mejor." if MT.is_better(metric, a, b)
                                 else "El modelo individual se sostuvo mejor.")})
    return {"level": level, "headline_metric": metric,
            "headline_value": None if hold is None else float(hold), "notes": notes}
