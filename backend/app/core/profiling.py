"""Perfilado y análisis estadístico del dataset.

Todo el cálculo pesado se hace en SQL sobre DuckDB contra el Parquet en disco.
Nunca se carga el dataset entero en memoria, así que el perfilado de 200 filas
y el de 200 millones usan el mismo código y la misma RAM.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from . import storage as S

NUMERIC_TYPES = ("int", "float", "double", "decimal", "hugeint", "uint")
TEMPORAL_TYPES = ("date", "timestamp", "time")
BOOL_TYPES = ("bool",)


def kind_of(arrow_type: str) -> str:
    t = arrow_type.lower()
    if any(k in t for k in BOOL_TYPES):
        return "boolean"
    if any(k in t for k in TEMPORAL_TYPES):
        return "datetime"
    if any(k in t for k in NUMERIC_TYPES):
        return "numeric"
    return "categorical"


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def profile(ds_id: str, top_k: int = 12, hist_bins: int = 20) -> dict[str, Any]:
    """Perfil completo: tipo, nulos, cardinalidad, estadísticos y distribución."""
    meta = S.load_meta(ds_id)
    con = S.connect()
    t = S.glob_expr(ds_id)
    try:
        cols: list[dict[str, Any]] = []
        for c in meta.columns:
            name, kind = c["name"], kind_of(c["arrow_type"])
            info: dict[str, Any] = {"name": name, "kind": kind, "arrow_type": c["arrow_type"]}
            q = _q(name)
            # count(distinct) exacto mientras sea barato; aproximado si el
            # dataset es enorme (el approx sobreestima y rompe la detección
            # de claves únicas si se usa siempre).
            dexpr = f"count(DISTINCT {q})" if meta.rows <= 5_000_000 else f"approx_count_distinct({q})"
            base = con.execute(
                f"SELECT count(*) n, count({q}) nn, {dexpr} nd FROM {t}"
            ).fetchone()
            n, nn, nd = int(base[0]), int(base[1] or 0), int(base[2] or 0)
            info.update(
                count=n, non_null=nn, nulls=n - nn,
                null_pct=round((n - nn) / n * 100, 3) if n else 0.0,
                distinct=nd,
                distinct_pct=round(nd / nn * 100, 3) if nn else 0.0,
                constant=nd <= 1,
                unique_key=bool(nn == n and nd >= max(n - 1, 1) and n > 0),
            )
            if kind == "numeric":
                r = con.execute(f"""
                    SELECT min({q}), max({q}), avg({q}), stddev_samp({q}),
                           median({q}), quantile_cont({q},0.01), quantile_cont({q},0.25),
                           quantile_cont({q},0.75), quantile_cont({q},0.99),
                           sum(CASE WHEN {q}=0 THEN 1 ELSE 0 END),
                           sum(CASE WHEN {q}<0 THEN 1 ELSE 0 END),
                           skewness({q}), kurtosis({q})
                    FROM {t} WHERE {q} IS NOT NULL AND isfinite({q}::DOUBLE)
                """).fetchone()
                keys = ["min", "max", "mean", "std", "median", "p01", "p25", "p75", "p99",
                        "zeros", "negatives", "skew", "kurtosis"]
                stats = {k: (None if v is None else float(v)) for k, v in zip(keys, r, strict=False)}
                iqr = (stats["p75"] - stats["p25"]) if (stats["p75"] is not None and stats["p25"] is not None) else None
                if iqr is not None:
                    lo, hi = stats["p25"] - 1.5 * iqr, stats["p75"] + 1.5 * iqr
                    out = con.execute(
                        f"SELECT count(*) FROM {t} WHERE {q} IS NOT NULL AND ({q} < {lo} OR {q} > {hi})"
                    ).fetchone()[0]
                    stats["iqr"] = iqr
                    stats["outliers"] = int(out)
                    stats["outlier_pct"] = round(int(out) / nn * 100, 3) if nn else 0.0
                stats["cv"] = (abs(stats["std"] / stats["mean"])
                               if stats["mean"] not in (None, 0) and stats["std"] is not None else None)
                info["stats"] = _clean(stats)
                info["histogram"] = _histogram(con, t, q, stats, hist_bins)
            elif kind == "datetime":
                r = con.execute(f"SELECT min({q}), max({q}) FROM {t}").fetchone()
                info["stats"] = {"min": str(r[0]) if r[0] is not None else None,
                                 "max": str(r[1]) if r[1] is not None else None}
            if kind in ("categorical", "boolean") or (kind == "numeric" and nd <= top_k):
                tv = con.execute(f"""
                    SELECT CAST({q} AS VARCHAR) v, count(*) c FROM {t}
                    WHERE {q} IS NOT NULL GROUP BY 1 ORDER BY c DESC LIMIT {int(top_k)}
                """).df()
                info["top_values"] = [
                    {"value": str(v), "count": int(c),
                     "pct": round(int(c) / nn * 100, 2) if nn else 0.0}
                    for v, c in zip(tv["v"], tv["c"], strict=False)
                ]
                if kind == "categorical":
                    lens = con.execute(
                        f"SELECT avg(length({q})), max(length({q})) FROM {t} WHERE {q} IS NOT NULL"
                    ).fetchone()
                    info["stats"] = {"avg_len": _f(lens[0]), "max_len": _f(lens[1])}
            cols.append(info)

        dups = con.execute(f"SELECT count(*) FROM (SELECT * FROM {t} GROUP BY ALL HAVING count(*)>1)").fetchone()[0]
        return {
            "dataset_id": ds_id, "name": meta.name, "rows": meta.rows,
            "n_columns": len(cols), "size_bytes": meta.size_bytes,
            "duplicate_row_groups": int(dups),
            "columns": cols,
            "quality": quality_report(meta.rows, cols, int(dups)),
        }
    finally:
        con.close()


def _f(v):
    return None if v is None else float(v)


def _clean(d: dict) -> dict:
    return {k: (None if (isinstance(v, float) and not math.isfinite(v)) else v) for k, v in d.items()}


def _histogram(con, t, q, stats, bins) -> list[dict[str, Any]]:
    lo, hi = stats.get("p01"), stats.get("p99")
    if lo is None or hi is None or not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        lo, hi = stats.get("min"), stats.get("max")
    if lo is None or hi is None or hi <= lo:
        return []
    w = (hi - lo) / bins
    df = con.execute(f"""
        SELECT least(floor(({q} - {lo}) / {w}), {bins - 1}) b, count(*) c
        FROM {t} WHERE {q} IS NOT NULL AND {q} BETWEEN {lo} AND {hi}
        GROUP BY 1 ORDER BY 1
    """).df()
    counts = {int(b): int(c) for b, c in zip(df["b"], df["c"], strict=False) if b is not None}
    return [{"from": lo + i * w, "to": lo + (i + 1) * w, "count": counts.get(i, 0)}
            for i in range(bins)]


# ───────────────────────────────────────────────── calidad de datos ───────────
def quality_report(rows: int, cols: list[dict], dup_groups: int) -> dict[str, Any]:
    """Hallazgos accionables + un puntaje 0-100 explicable."""
    issues: list[dict[str, Any]] = []
    for c in cols:
        n = c["name"]
        if c["constant"]:
            issues.append({"column": n, "severity": "high", "code": "constant",
                           "detail": "Columna constante: no aporta información."})
        if c["null_pct"] >= 60:
            issues.append({"column": n, "severity": "high", "code": "nulls_high",
                           "detail": f"{c['null_pct']:.1f}% de nulos."})
        elif c["null_pct"] >= 20:
            issues.append({"column": n, "severity": "medium", "code": "nulls_medium",
                           "detail": f"{c['null_pct']:.1f}% de nulos."})
        if c["kind"] == "categorical" and c["distinct"] > 200 and not c["unique_key"]:
            issues.append({"column": n, "severity": "medium", "code": "high_cardinality",
                           "detail": f"{c['distinct']} categorías distintas."})
        if c["unique_key"]:
            issues.append({"column": n, "severity": "low", "code": "identifier",
                           "detail": "Parece un identificador: se excluye como feature."})
        st = c.get("stats") or {}
        if c["kind"] == "numeric" and (st.get("outlier_pct") or 0) > 10:
            issues.append({"column": n, "severity": "medium", "code": "outliers",
                           "detail": f"{st['outlier_pct']:.1f}% de valores fuera del rango intercuartil."})
        if c["kind"] == "numeric" and st.get("skew") is not None and abs(st["skew"]) > 3:
            issues.append({"column": n, "severity": "low", "code": "skewed",
                           "detail": f"Asimetría {st['skew']:.2f}: conviene transformación logarítmica."})
    if dup_groups:
        issues.append({"column": "(filas)", "severity": "medium", "code": "duplicates",
                       "detail": f"{dup_groups} grupos de filas duplicadas."})

    weights = {"high": 8, "medium": 3, "low": 1}
    penalty = sum(weights[i["severity"]] for i in issues)
    score = max(0, min(100, 100 - penalty))
    return {
        "score": score,
        "level": "alta" if score >= 80 else ("media" if score >= 55 else "baja"),
        "issues": sorted(issues, key=lambda i: {"high": 0, "medium": 1, "low": 2}[i["severity"]]),
        "counts": {k: sum(1 for i in issues if i["severity"] == k) for k in weights},
    }


# ─────────────────────────────────────────── correlaciones y target ───────────
def correlations(ds_id: str, max_cols: int = 40, max_rows: int = 200_000) -> dict[str, Any]:
    """Matriz de Pearson y Spearman sobre las columnas numéricas."""
    meta = S.load_meta(ds_id)
    nums = [c["name"] for c in meta.columns if kind_of(c["arrow_type"]) == "numeric"][:max_cols]
    if len(nums) < 2:
        return {"columns": [], "pearson": [], "spearman": [], "top_pairs": []}
    df = S.load_frame(ds_id, columns=nums, max_rows=max_rows).apply(pd.to_numeric, errors="coerce")
    df = df.loc[:, df.nunique(dropna=True) > 1]
    if df.shape[1] < 2:
        return {"columns": [], "pearson": [], "spearman": [], "top_pairs": []}
    pe = df.corr(method="pearson").fillna(0.0)
    sp = df.rank().corr(method="pearson").fillna(0.0)
    pairs = []
    cols = list(pe.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            pairs.append({"a": a, "b": b, "pearson": round(float(pe.loc[a, b]), 4),
                          "spearman": round(float(sp.loc[a, b]), 4)})
    pairs.sort(key=lambda p: -abs(p["pearson"]))
    return {
        "columns": cols,
        "pearson": [[round(float(v), 4) for v in row] for row in pe.values],
        "spearman": [[round(float(v), 4) for v in row] for row in sp.values],
        "top_pairs": pairs[:25],
    }


def target_analysis(ds_id: str, target: str, max_rows: int = 200_000) -> dict[str, Any]:
    """Relación de cada columna con la variable objetivo, antes de entrenar."""
    meta = S.load_meta(ds_id)
    names = [c["name"] for c in meta.columns]
    if target not in names:
        raise ValueError(f"La columna objetivo '{target}' no existe en el dataset.")
    df = S.load_frame(ds_id, max_rows=max_rows)
    y = df[target]
    task = infer_task(y)
    rows = []
    for c in df.columns:
        if c == target:
            continue
        s = df[c]
        rel = _association(s, y, task)
        if rel is not None:
            rows.append({"column": c, **rel})
    rows.sort(key=lambda r: -abs(r.get("strength", 0)))
    return {"target": target, "task": task, "n_used": int(len(df)),
            "distribution": _target_distribution(y, task), "associations": rows}


def infer_task(y: pd.Series) -> str:
    """Clasificación binaria, multiclase o regresión, deducido de los datos."""
    s = y.dropna()
    if s.empty:
        return "regression"
    nun = s.nunique()
    if nun <= 1:
        return "regression"
    if not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s):
        return "binary" if nun == 2 else "multiclass"
    if nun == 2:
        return "binary"
    is_int_like = np.allclose(s.astype(float) % 1, 0, atol=1e-9)
    if is_int_like and nun <= 20 and len(s) / nun > 10:
        return "multiclass"
    return "regression"


def _target_distribution(y: pd.Series, task: str) -> dict[str, Any]:
    s = y.dropna()
    if task == "regression":
        d = s.astype(float)
        return {"type": "numeric", "min": float(d.min()), "max": float(d.max()),
                "mean": float(d.mean()), "median": float(d.median()),
                "std": float(d.std()) if len(d) > 1 else 0.0,
                "skew": float(d.skew()) if len(d) > 2 else 0.0}
    vc = s.astype(str).value_counts()
    total = int(vc.sum())
    classes = [{"value": str(k), "count": int(v), "pct": round(v / total * 100, 2)}
               for k, v in vc.head(30).items()]
    imb = float(vc.max() / max(vc.min(), 1)) if len(vc) > 1 else 1.0
    return {"type": "categorical", "n_classes": int(vc.size), "classes": classes,
            "imbalance_ratio": round(imb, 2),
            "minority_pct": round(float(vc.min() / total * 100), 3) if len(vc) else 0.0}


def _association(x: pd.Series, y: pd.Series, task: str) -> dict[str, Any] | None:
    """Fuerza de asociación x↔y, con la métrica adecuada a cada combinación."""
    ok = x.notna() & y.notna()
    if ok.sum() < 20:
        return None
    x, y = x[ok], y[ok]
    x_num = pd.api.types.is_numeric_dtype(x) and not pd.api.types.is_bool_dtype(x)
    try:
        if task == "regression":
            yf = y.astype(float)
            if x_num:
                r = float(pd.Series(x.astype(float)).corr(yf, method="spearman"))
                return {"metric": "spearman", "value": round(r, 4), "strength": abs(r)}
            eta = _eta_squared(x.astype(str), yf)
            return {"metric": "eta2", "value": round(eta, 4), "strength": eta}
        ycat = y.astype(str)
        if ycat.nunique() < 2:
            return None
        if x_num:
            if task == "binary":
                auc = _auc(ycat, x.astype(float))
                return {"metric": "auc_univariada", "value": round(auc, 4),
                        "strength": abs(auc - 0.5) * 2}
            eta = _eta_squared(ycat, x.astype(float))
            return {"metric": "eta2", "value": round(eta, 4), "strength": eta}
        v = _cramers_v(x.astype(str), ycat)
        return {"metric": "cramers_v", "value": round(v, 4), "strength": v}
    except Exception:
        return None


def _auc(y_cat: pd.Series, x: pd.Series) -> float:
    from sklearn.metrics import roc_auc_score

    pos = y_cat.value_counts().index[0]
    yb = (y_cat == pos).astype(int)
    if yb.nunique() < 2:
        return 0.5
    a = float(roc_auc_score(yb, x))
    # se reporta la AUC orientada (>=0.5): la dirección del signo la da la
    # correlación, y una AUC de 0.13 y una de 0.87 tienen el mismo poder.
    return max(a, 1 - a)


def _eta_squared(cat: pd.Series, num: pd.Series) -> float:
    """Proporción de varianza de `num` explicada por los grupos de `cat`."""
    g = num.groupby(cat.values)
    grand = num.mean()
    ss_between = float(((g.mean() - grand) ** 2 * g.size()).sum())
    ss_total = float(((num - grand) ** 2).sum())
    return ss_between / ss_total if ss_total > 0 else 0.0


def _cramers_v(a: pd.Series, b: pd.Series) -> float:
    """V de Cramér con corrección de sesgo (Bergsma, 2013)."""
    ct = pd.crosstab(a, b)
    if ct.size == 0 or ct.shape[0] < 2 or ct.shape[1] < 2:
        return 0.0
    obs = ct.values.astype(float)
    n = obs.sum()
    exp = obs.sum(1, keepdims=True) @ obs.sum(0, keepdims=True) / n
    chi2 = float(np.nansum((obs - exp) ** 2 / np.where(exp == 0, np.nan, exp)))
    phi2 = chi2 / n
    r, k = obs.shape
    phi2c = max(0.0, phi2 - (k - 1) * (r - 1) / (n - 1))
    rc = r - (r - 1) ** 2 / (n - 1)
    kc = k - (k - 1) ** 2 / (n - 1)
    den = min(kc - 1, rc - 1)
    return float(np.sqrt(phi2c / den)) if den > 0 else 0.0
