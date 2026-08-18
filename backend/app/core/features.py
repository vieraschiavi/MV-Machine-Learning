"""Preparación de features y codificación.

Produce dos representaciones de la misma tabla:

* **matriz de árboles** — numéricos tal cual (los NaN los maneja el propio
  algoritmo) y categóricas como códigos ordinales estables.
* **matriz lineal** — one-hot acotado, imputación y estandarización, que es
  lo que necesitan la regresión logística, Ridge y ElasticNet.

* **texto libre** — las columnas de texto (comentarios, descripciones,
  observaciones) se vectorizan con TF-IDF y se comprimen con SVD truncado a
  unas pocas componentes numéricas que entran en LAS DOS matrices. El texto
  no es una tarea aparte: convive con las columnas numéricas y categóricas
  del mismo modelo, y el ajuste se hace sólo sobre la ventana de
  entrenamiento, así que no filtra vocabulario del holdout.

Ambas se derivan del mismo ajuste, así que un modelo lineal y uno de árboles
ven exactamente las mismas columnas de origen y la comparación es justa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

MAX_ONEHOT_LEVELS = 25
TEXT_MIN_AVG_LEN = 25      # largo medio a partir del cual una columna es "texto"
TEXT_MIN_DISTINCT = 0.5    # proporción de valores distintos mínima
TEXT_MAX_FEATURES = 400    # vocabulario TF-IDF por columna
TEXT_COMPONENTS = 24       # componentes SVD que entran al modelo


def looks_like_text(s: pd.Series, sample: int = 2000) -> bool:
    """¿Esta columna es texto libre y no una categórica disfrazada?"""
    v = s.dropna().astype(str)
    if len(v) < 50:
        return False
    v = v.head(sample)
    avg_len = float(v.str.len().mean())
    avg_tokens = float(v.str.split().str.len().mean())
    distinct = v.nunique() / len(v)
    return (avg_len >= TEXT_MIN_AVG_LEN or avg_tokens >= 4) and distinct >= TEXT_MIN_DISTINCT


@dataclass
class Preprocessor:
    numeric: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    text: list[str] = field(default_factory=list)
    text_pipes: dict[str, Any] = field(default_factory=dict)   # col -> (tfidf, svd, mu, sd)
    categories: dict[str, list[str]] = field(default_factory=dict)
    medians: dict[str, float] = field(default_factory=dict)
    scaler: dict[str, tuple[float, float]] = field(default_factory=dict)
    onehot: dict[str, list[str]] = field(default_factory=dict)
    log_cols: list[str] = field(default_factory=list)
    feature_names_tree: list[str] = field(default_factory=list)
    feature_names_linear: list[str] = field(default_factory=list)

    # ── ajuste ────────────────────────────────────────────────────────────────
    def fit(self, X: pd.DataFrame, max_levels: int = 200, add_log: bool = True) -> Preprocessor:
        self.numeric, self.categorical, self.text = [], [], []
        for c in X.columns:
            s = X[c]
            if pd.api.types.is_bool_dtype(s):
                self.numeric.append(c)
            elif pd.api.types.is_numeric_dtype(s):
                self.numeric.append(c)
            elif pd.api.types.is_datetime64_any_dtype(s):
                self.numeric.append(c)      # se convierte a epoch en transform
            elif looks_like_text(s):
                self.text.append(c)
            else:
                self.categorical.append(c)

        for c in self.text:
            self._fit_text(c, X[c])

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

        text_names = [f"{c}__txt{i}" for c in self.text
                      for i in range(self._n_text_components(c))]
        self.feature_names_tree = (list(self.numeric) + [f"{c}__log" for c in self.log_cols]
                                   + list(self.categorical) + text_names)
        self.feature_names_linear = (
            list(self.numeric) + [f"{c}__log" for c in self.log_cols]
            + [f"{c}={v}" for c in self.categorical for v in self.onehot[c]]
            + text_names
        )
        return self

    # ── texto libre: TF-IDF + SVD, ajustado sólo con el entrenamiento ────────
    def _fit_text(self, col: str, s: pd.Series) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        docs = s.fillna("").astype(str).tolist()
        tfidf = TfidfVectorizer(max_features=TEXT_MAX_FEATURES, ngram_range=(1, 2),
                                min_df=2, sublinear_tf=True, strip_accents="unicode",
                                lowercase=True)
        try:
            M = tfidf.fit_transform(docs)
        except ValueError:          # vocabulario vacío (todo stopwords o vacío)
            return
        n_comp = min(TEXT_COMPONENTS, M.shape[1] - 1, max(len(docs) - 1, 1))
        if n_comp < 2:
            return
        svd = TruncatedSVD(n_components=n_comp, random_state=0)
        Z = svd.fit_transform(M)
        mu, sd = Z.mean(0), Z.std(0)
        sd = np.where(sd > 1e-12, sd, 1.0)
        self.text_pipes[col] = (tfidf, svd, mu, sd)

    def _n_text_components(self, col: str) -> int:
        pipe = self.text_pipes.get(col)
        return pipe[1].n_components if pipe else 0

    def _transform_text(self, col: str, s: pd.Series) -> np.ndarray:
        pipe = self.text_pipes.get(col)
        if pipe is None:
            return np.zeros((len(s), 0), dtype=np.float32)
        tfidf, svd, mu, sd = pipe
        Z = svd.transform(tfidf.transform(s.fillna("").astype(str).tolist()))
        return ((Z - mu) / sd).astype(np.float32)

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
        for c in self.text:
            serie = X[c] if c in X.columns else pd.Series([""] * len(X))
            Z = self._transform_text(c, serie)
            for i in range(Z.shape[1]):
                out[f"{c}__txt{i}"] = Z[:, i]
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
        for c in self.text:
            serie = X[c] if c in X.columns else pd.Series([""] * len(X))
            Z = self._transform_text(c, serie)
            if Z.shape[1]:
                blocks.append(Z)
        if not blocks:
            return np.zeros((len(X), 1), dtype=np.float32)
        M = np.hstack(blocks).astype(np.float32)
        return np.nan_to_num(M, nan=0.0, posinf=0.0, neginf=0.0)

    def categorical_indices(self) -> list[int]:
        return [self.feature_names_tree.index(c) for c in self.categorical]

    def to_dict(self) -> dict[str, Any]:
        return {"numeric": self.numeric, "categorical": self.categorical,
                "text": self.text, "log_cols": self.log_cols,
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


def base_column(name: str) -> str:
    """Columna original de un nombre derivado (`x__log`, `x=valor`, `x__txt3`)."""
    return re.sub(r"__txt\d+$", "", name.split("=")[0].replace("__log", ""))


def base_columns(names: list[str]) -> list[str]:
    """Mapea nombres derivados a columnas originales, sin duplicados."""
    out, seen = [], set()
    for n in names:
        b = base_column(n)
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out
