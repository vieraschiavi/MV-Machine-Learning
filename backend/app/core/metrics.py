"""Métricas de evaluación con nombre y lectura en castellano.

Cada métrica viaja con su dirección (si más alto es mejor), su formato y una
explicación en lenguaje llano, para que el informe se entienda sin ser
científico de datos.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn import metrics as skm

# nombre → (mayor es mejor, formato, explicación)
CATALOG: dict[str, tuple[bool, str, str]] = {
    "auc":        (True,  "0.0000", "Probabilidad de ordenar bien un caso positivo frente a uno negativo. 0,5 es azar."),
    "pr_auc":     (True,  "0.0000", "Precisión promedio. Se compara contra la tasa base, no contra 0,5."),
    "ks":         (True,  "0.000",  "Máxima separación entre las curvas acumuladas de positivos y negativos."),
    "brier":      (False, "0.0000", "Error cuadrático de la probabilidad. Más bajo es mejor."),
    "ece":        (False, "0.0000", "Diferencia entre la probabilidad declarada y la observada. Mide calibración."),
    "logloss":    (False, "0.0000", "Penaliza la confianza equivocada. Más bajo es mejor."),
    "accuracy":   (True,  "0.0%",   "Porcentaje de aciertos."),
    "balanced_accuracy": (True, "0.0%", "Aciertos promediados por clase; no se deja engañar por el desbalance."),
    "precision":  (True,  "0.0%",   "De los que marca como positivos, cuántos lo son."),
    "recall":     (True,  "0.0%",   "De los positivos reales, cuántos detecta."),
    "f1":         (True,  "0.0000", "Media armónica entre precisión y recall."),
    "f1_macro":   (True,  "0.0000", "F1 promediado por clase, sin ponderar por tamaño."),
    "lift_10":    (True,  "0.00x",  "Cuántas veces más positivos hay en el 10% mejor rankeado que en el promedio."),
    "r2":         (True,  "0.0000", "Proporción de la varianza explicada. 0 equivale a predecir siempre la media."),
    "rmse":       (False, "#,##0.00", "Error cuadrático medio, en las unidades del objetivo."),
    "mae":        (False, "#,##0.00", "Error absoluto medio, en las unidades del objetivo."),
    "mape":       (False, "0.0%",   "Error porcentual medio. Se descontrola si hay valores cercanos a cero."),
    "wmape":      (False, "0.0%",   "Error absoluto total sobre volumen total. Es la métrica robusta de negocio."),
    "smape":      (False, "0.0%",   "Error porcentual simétrico."),
    "bias":       (False, "0.0%",   "Desvío sistemático: positivo = el modelo predice de más."),
    "direction":  (True,  "0.0%",   "Porcentaje de veces que acierta el sentido del movimiento."),
}

PRIMARY = {"binary": "auc", "multiclass": "f1_macro", "regression": "wmape"}


def is_better(metric: str, a: float, b: float) -> bool:
    """¿`a` es mejor que `b` para esta métrica?"""
    higher = CATALOG.get(metric, (True, "", ""))[0]
    if not np.isfinite(a):
        return False
    if not np.isfinite(b):
        return True
    return a > b if higher else a < b


def _safe(fn, *a, default=float("nan"), **k):
    try:
        v = float(fn(*a, **k))
        return v if np.isfinite(v) else default
    except Exception:
        return default


def ks_stat(y: np.ndarray, p: np.ndarray) -> float:
    d = pd.DataFrame({"y": y, "p": p}).sort_values("p")
    pos, neg = max((d.y == 1).sum(), 1), max((d.y == 0).sum(), 1)
    return float(np.abs((d.y == 1).cumsum() / pos - (d.y == 0).cumsum() / neg).max())


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    """Error de calibración esperado: |probabilidad dicha − frecuencia observada|."""
    try:
        q = pd.qcut(pd.Series(p), bins, duplicates="drop", labels=False)
    except Exception:
        return float("nan")
    y, p = np.asarray(y, float), np.asarray(p, float)
    e, n = 0.0, len(p)
    for b in pd.Series(q).dropna().unique():
        m = (q == b).values
        if m.sum():
            e += m.sum() / n * abs(y[m].mean() - p[m].mean())
    return float(e)


def lift_at(y: np.ndarray, p: np.ndarray, top: float = 0.10) -> float:
    n = max(int(len(p) * top), 1)
    idx = np.argsort(-np.asarray(p))[:n]
    base = float(np.mean(y))
    return float(np.mean(np.asarray(y)[idx]) / base) if base > 0 else float("nan")


def binary(y, p, threshold: float | None = None) -> dict[str, float]:
    y = np.asarray(y).astype(int)
    p = np.clip(np.asarray(p, float), 0, 1)
    rate = float(y.mean())
    # umbral por defecto: el que reproduce la tasa base observada, no 0,5.
    thr = threshold if threshold is not None else (
        float(np.quantile(p, 1 - rate)) if 0 < rate < 1 else 0.5)
    yh = (p >= thr).astype(int)
    return {
        "auc": _safe(skm.roc_auc_score, y, p, default=0.5),
        "pr_auc": _safe(skm.average_precision_score, y, p, default=rate),
        "ks": _safe(ks_stat, y, p, default=0.0),
        "brier": _safe(skm.brier_score_loss, y, p),
        "ece": _safe(ece, y, p),
        "logloss": _safe(skm.log_loss, y, np.clip(p, 1e-9, 1 - 1e-9)),
        "accuracy": _safe(skm.accuracy_score, y, yh),
        "balanced_accuracy": _safe(skm.balanced_accuracy_score, y, yh),
        "precision": _safe(skm.precision_score, y, yh, zero_division=0),
        "recall": _safe(skm.recall_score, y, yh, zero_division=0),
        "f1": _safe(skm.f1_score, y, yh, zero_division=0),
        "lift_10": _safe(lift_at, y, p),
        "threshold": float(thr), "positive_rate": rate, "n": int(len(y)),
    }


def multiclass(y, proba, classes) -> dict[str, float]:
    y = np.asarray(y)
    proba = np.asarray(proba, float)
    # tras promediar modelos y recortar extremos, las filas pueden dejar de
    # sumar 1; se renormaliza antes de medir para no distorsionar el log loss
    fila = proba.sum(axis=1, keepdims=True)
    proba = np.divide(proba, np.where(fila > 0, fila, 1.0))
    yh = np.asarray(classes)[proba.argmax(1)]
    out = {
        "accuracy": _safe(skm.accuracy_score, y, yh),
        "balanced_accuracy": _safe(skm.balanced_accuracy_score, y, yh),
        "f1_macro": _safe(skm.f1_score, y, yh, average="macro", zero_division=0),
        "precision": _safe(skm.precision_score, y, yh, average="macro", zero_division=0),
        "recall": _safe(skm.recall_score, y, yh, average="macro", zero_division=0),
        "logloss": _safe(skm.log_loss, y, proba, labels=list(classes)),
        "n": int(len(y)),
    }
    if len(classes) > 2:
        out["auc"] = _safe(skm.roc_auc_score, y, proba, multi_class="ovr",
                           average="macro", labels=list(classes), default=float("nan"))
    return out


def regression(y, p) -> dict[str, float]:
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    if len(y) == 0:
        return {"n": 0}
    err = p - y
    denom = np.abs(y).sum()
    nz = np.abs(y) > 1e-9
    d_smape = np.abs(y) + np.abs(p)
    return {
        "r2": _safe(skm.r2_score, y, p),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "mae": float(np.mean(np.abs(err))),
        "mape": float(np.mean(np.abs(err[nz] / y[nz]))) if nz.any() else float("nan"),
        "wmape": float(np.abs(err).sum() / denom) if denom > 0 else float("nan"),
        "smape": float(np.mean(2 * np.abs(err)[d_smape > 0] / d_smape[d_smape > 0])) if (d_smape > 0).any() else float("nan"),
        "bias": float(err.sum() / denom) if denom > 0 else float("nan"),
        "n": int(len(y)),
    }


def evaluate(task: str, y_true, pred, classes=None) -> dict[str, float]:
    if task == "binary":
        return binary(y_true, pred)
    if task == "multiclass":
        return multiclass(y_true, pred, classes)
    return regression(y_true, pred)


def describe(metric: str) -> dict[str, str]:
    higher, fmt, text = CATALOG.get(metric, (True, "0.0000", ""))
    return {"metric": metric, "higher_is_better": higher, "format": fmt, "explanation": text}
