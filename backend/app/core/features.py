"""Preparación de features y codificación.

Produce dos representaciones de la misma tabla:

* **matriz de árboles** — numéricos tal cual (los NaN los maneja el propio
  algoritmo) y categóricas como códigos ordinales estables.
* **matriz lineal** — one-hot acotado, imputación y estandarización, que es
  lo que necesitan la regresión logística, Ridge y ElasticNet.

Ambas se derivan del mismo ajuste, así que un modelo lineal y uno de árboles
ven exactamente las mismas columnas de origen y la comparación es justa.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

MAX_ONEHOT_LEVELS = 25


@dataclass
class Preprocessor:
    numeric: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    categories: dict[str, list[str]] = field(default_factory=dict)
    medians: dict[str, float] = field(default_factory=dict)
    scaler: dict[str, tuple[float, float]] = field(default_factory=dict)
    onehot: dict[str, list[str]] = field(default_factory=dict)
    log_cols: list[str] = field(default_factory=list)
    feature_names_tree: list[str] = field(default_factory=list)
    feature_names_linear: list[str] = field(default_factory=list)

    # ── ajuste ────────────────────────────────────────────────────────────────
    def fit(self, X: pd.DataFrame, max_levels: int = 200, add_log: bool = True) -> Preprocessor:
        self.numeric, self.categorical = [], []
        for c in X.columns:
            s = X[c]
            if pd.api.types.is_bool_dtype(s):
                self.numeric.append(c)
            elif pd.api.types.is_numeric_dtype(s):
                self.numeric.append(c)
            elif pd.api.types.is_datetime64_any_dtype(s):
                self.numeric.append(c)      # se convierte a epoch en transform
            else:
                self.categorical.append(c)

        for c in self.numeric:
            v = _to_numeric(X[c])
            med = float(np.nanmedian(v)) if np.isfinite(v).any() else 0.0
            self.medians[c] = med
            mu = float(np.nanmean(v)) if np.isfinite(v).any() else 0.0
            sd = float(np.nanstd(v)) if np.isfinite(v).any() else 0.0
            self.scaler[c] = (mu, sd if sd > 1e-12 else 1.0)
            if add_log:
                fin = v[np.isfinite(v)]
                if len(fin) > 30 and fin.min() >= 0:
                    sk = float(pd.Series(fin).skew())
                    if np.isfinite(sk) and sk > 2 and fin.max() > 0:
                        self.log_cols.append(c)

        for c in self.categorical:
            vc = X[c].astype("string").fillna("(nulo)").value_counts()
            self.categories[c] = [str(v) for v in vc.index[:max_levels]]
            self.onehot[c] = self.categories[c][:MAX_ONEHOT_LEVELS]

        self.feature_names_tree = list(self.numeric) + [f"{c}__log" for c in self.log_cols] + list(self.categorical)
        self.feature_names_linear = (
            list(self.numeric) + [f"{c}__log" for c in self.log_cols]
            + [f"{c}={v}" for c in self.categorical for v in self.onehot[c]]
        )
        return self

    # ── transformación ────────────────────────────────────────────────────────
    def transform_tree(self, X: pd.DataFrame) -> pd.DataFrame:
        out = {}
        for c in self.numeric:
            out[c] = _to_numeric(X[c]) if c in X.columns else np.full(len(X), np.nan)
        for c in self.log_cols:
            out[f"{c}__log"] = np.log1p(np.clip(out[c], 0, None))
        for c in self.categorical:
            cats = self.categories[c]
            s = X[c].astype("string").fillna("(nulo)") if c in X.columns else pd.Series(["(nulo)"] * len(X), dtype="string")
            out[c] = pd.Categorical(s, categories=cats).codes.astype(np.float32)
            out[c] = np.where(out[c] < 0, np.nan, out[c])   # nivel no visto = faltante
        return pd.DataFrame(out, index=X.index)[self.feature_names_tree]

    def transform_linear(self, X: pd.DataFrame) -> np.ndarray:
        blocks = []
        for c in self.numeric:
            v = _to_numeric(X[c]) if c in X.columns else np.full(len(X), np.nan)
            v = np.where(np.isfinite(v), v, self.medians.get(c, 0.0))
            mu, sd = self.scaler.get(c, (0.0, 1.0))
            blocks.append(((v - mu) / sd).reshape(-1, 1))
        for c in self.log_cols:
            v = _to_numeric(X[c]) if c in X.columns else np.full(len(X), np.nan)
            v = np.log1p(np.clip(np.where(np.isfinite(v), v, self.medians.get(c, 0.0)), 0, None))
            blocks.append(v.reshape(-1, 1))
        for c in self.categorical:
            s = X[c].astype("string").fillna("(nulo)") if c in X.columns else pd.Series(["(nulo)"] * len(X), dtype="string")
            for v in self.onehot[c]:
                blocks.append((s == v).to_numpy(dtype=np.float32).reshape(-1, 1))
        if not blocks:
            return np.zeros((len(X), 1), dtype=np.float32)
        M = np.hstack(blocks).astype(np.float32)
        return np.nan_to_num(M, nan=0.0, posinf=0.0, neginf=0.0)

    def categorical_indices(self) -> list[int]:
        return [self.feature_names_tree.index(c) for c in self.categorical]

    def to_dict(self) -> dict[str, Any]:
        return {"numeric": self.numeric, "categorical": self.categorical,
                "log_cols": self.log_cols,
                "n_features_tree": len(self.feature_names_tree),
                "n_features_linear": len(self.feature_names_linear)}


def _to_numeric(s: pd.Series) -> np.ndarray:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.astype("int64").to_numpy(dtype=float) / 1e9
    if pd.api.types.is_bool_dtype(s):
        return s.astype(float).to_numpy()
    return pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)


# ────────────────────────────────────────────── selección de features ────────
def select_by_importance(importances: dict[str, float], keep_min: int = 5,
                         cum_share: float = 0.995,
                         drop_zero: bool = True) -> tuple[list[str], list[str]]:
    """Conserva las features que explican `cum_share` de la importancia total.

    Devuelve (conservadas, descartadas). Nunca deja menos de `keep_min`.
    """
    items = sorted(importances.items(), key=lambda kv: -abs(kv[1]))
    total = sum(abs(v) for _, v in items)
    if total <= 0:
        return [k for k, _ in items], []
    keep, acc = [], 0.0
    for k, v in items:
        if drop_zero and abs(v) <= 0 and len(keep) >= keep_min:
            break
        keep.append(k)
        acc += abs(v) / total
        if acc >= cum_share and len(keep) >= keep_min:
            break
    dropped = [k for k, _ in items if k not in set(keep)]
    return keep, dropped


def base_columns(names: list[str]) -> list[str]:
    """Mapea nombres derivados (`x__log`, `x=valor`) a la columna original."""
    out, seen = [], set()
    for n in names:
        b = n.split("=")[0].replace("__log", "")
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out
