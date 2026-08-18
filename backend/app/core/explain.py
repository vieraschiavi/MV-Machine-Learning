"""Análisis de variables: cuánto aporta cada una y en qué sentido.

Tres lecturas complementarias, porque cada una miente de una forma distinta:

* **importancia nativa** — rápida, pero sesgada hacia variables con muchos
  valores distintos;
* **importancia por permutación** — mide la caída real de la métrica al
  romper la variable; es la que manda cuando hay desacuerdo;
* **SHAP** — reparte la predicción entre variables e indica la dirección
  del efecto (sube o baja el resultado).
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from . import metrics as MT
from .features import Preprocessor


def explain_model(task: str, champion: dict, fitted: dict, ens_members: list[str],
                  pre: Preprocessor, data: dict, tt, metric: str, cfg,
                  progress=lambda *_: None) -> dict[str, Any]:
    names_tree = pre.feature_names_tree
    names_lin = pre.feature_names_linear

    # ── importancia nativa, agregada a nivel de columna original ─────────────
    native: dict[str, float] = {}
    members = ens_members if champion["type"] == "ensemble" else [champion["model"]]
    for fam in members:
        mdl = fitted.get(fam)
        if mdl is None:
            continue
        names = names_tree if mdl.matrix == "tree" else names_lin
        imp = mdl.importances(names)
        total = sum(abs(v) for v in imp.values()) or 1.0
        for k, v in imp.items():
            col = k.split("=")[0].replace("__log", "")
            native[col] = native.get(col, 0.0) + abs(v) / total / len(members)

    # ── importancia por permutación sobre el holdout ciego ───────────────────
    perm: dict[str, dict[str, float]] = {}
    if cfg.permutation_importance:
        try:
            perm = _permutation(task, champion, fitted, ens_members, pre, data, tt, metric)
        except Exception:
            perm = {}

    # ── SHAP: dirección del efecto ───────────────────────────────────────────
    shap_out: dict[str, Any] = {}
    if cfg.shap:
        try:
            shap_out = _shap(task, champion, fitted, ens_members, pre, data)
        except Exception as exc:
            shap_out = {"available": False, "reason": str(exc)[:200]}

    cols = sorted(set(native) | set(perm) | set(shap_out.get("by_column", {})),
                  key=lambda c: -(perm.get(c, {}).get("drop_pct", 0) or native.get(c, 0)))
    ranking = []
    for c in cols:
        p = perm.get(c, {})
        ranking.append({
            "column": c,
            "native": round(native.get(c, 0.0), 6),
            "permutation_drop": p.get("drop"),
            "permutation_drop_pct": p.get("drop_pct"),
            "shap_mean_abs": shap_out.get("by_column", {}).get(c, {}).get("mean_abs"),
            "shap_direction": shap_out.get("by_column", {}).get(c, {}).get("direction"),
        })
    top = [r["column"] for r in ranking[:5]]
    return {
        "ranking": ranking,
        "top": top,
        "narrative": _narrative(ranking, task, metric),
        "shap": {k: v for k, v in shap_out.items() if k != "by_column"},
        "method_notes": [
            "La importancia por permutación se mide sobre el holdout ciego: es cuánto empeora "
            f"«{metric}» al romper la relación de esa columna con el objetivo.",
            "La importancia nativa del algoritmo favorece a las columnas con más valores distintos; "
            "cuando discrepa con la permutación, manda la permutación.",
        ],
    }


def _predict(champion, fitted, ens_members, task, tt, Xt, Xl) -> np.ndarray:
    members = ens_members if champion["type"] == "ensemble" else [champion["model"]]
    preds = []
    for fam in members:
        mdl = fitted.get(fam)
        if mdl is None:
            continue
        p = mdl.predict(Xt, Xl)
        preds.append(tt.inverse(p) if task == "regression" else p)
    return np.mean(preds, axis=0)


def _permutation(task, champion, fitted, ens_members, pre, data, tt, metric,
                 n_repeats: int = 2, max_rows: int = 20_000, budget_s: float = 45) -> dict:
    higher = MT.CATALOG.get(metric, (True,))[0]
    Xt, Xl, y = data["Xt_ho"], data["Xl_ho"], data["y_ho_raw"]
    if len(Xt) > max_rows:
        idx = np.random.default_rng(7).choice(len(Xt), max_rows, replace=False)
        Xt, Xl, y = Xt.iloc[idx], Xl[idx], y[idx]

    base_pred = _predict(champion, fitted, ens_members, task, tt, Xt, Xl)
    base = MT.evaluate(task, y, base_pred, data.get("classes")).get(metric, np.nan)
    if not np.isfinite(base):
        return {}

    rng = np.random.default_rng(11)
    out: dict[str, dict[str, float]] = {}
    t0 = time.time()
    lin_index: dict[str, list[int]] = {}
    for j, n in enumerate(pre.feature_names_linear):
        lin_index.setdefault(n.split("=")[0].replace("__log", ""), []).append(j)

    columns = list(dict.fromkeys([c.split("=")[0].replace("__log", "")
                                  for c in pre.feature_names_tree]))
    for col in columns:
        if time.time() - t0 > budget_s:
            break
        drops = []
        for _ in range(n_repeats):
            order = rng.permutation(len(Xt))
            Xt2 = Xt.copy()
            for c in [c for c in Xt.columns if c.split("=")[0].replace("__log", "") == col]:
                Xt2[c] = Xt[c].to_numpy()[order]
            Xl2 = Xl.copy()
            for j in lin_index.get(col, []):
                Xl2[:, j] = Xl[order, j]
            s = MT.evaluate(task, y, _predict(champion, fitted, ens_members, task, tt, Xt2, Xl2),
                            data.get("classes")).get(metric, np.nan)
            if np.isfinite(s):
                drops.append((base - s) if higher else (s - base))
        if drops:
            d = float(np.mean(drops))
            out[col] = {"drop": round(d, 6),
                        "drop_pct": round(d / abs(base) * 100, 3) if base else None,
                        "baseline": round(float(base), 6)}
    return out


def _shap(task, champion, fitted, ens_members, pre, data, max_rows: int = 2000) -> dict[str, Any]:
    import shap  # import perezoso: sólo si se pide

    fam = ens_members[0] if champion["type"] == "ensemble" else champion["model"]
    mdl = fitted.get(fam)
    if mdl is None or mdl.matrix != "tree":
        return {"available": False, "reason": "SHAP se calcula sobre el modelo de árboles del campeón."}
    X = data["Xt_ho"]
    if len(X) > max_rows:
        X = X.sample(max_rows, random_state=3)
    explainer = shap.TreeExplainer(mdl.est)
    vals = explainer.shap_values(X, check_additivity=False)
    if isinstance(vals, list):
        vals = np.mean([np.abs(v) for v in vals], axis=0)
        signed = None
    else:
        vals = np.asarray(vals)
        if vals.ndim == 3:                       # (n, features, clases)
            signed = None
            vals = np.abs(vals).mean(2)
        else:
            signed = vals
            vals = np.abs(vals)

    by_col: dict[str, dict[str, Any]] = {}
    for j, name in enumerate(X.columns):
        col = name.split("=")[0].replace("__log", "")
        e = by_col.setdefault(col, {"mean_abs": 0.0, "corr": []})
        e["mean_abs"] += float(np.mean(vals[:, j]))
        if signed is not None:
            x = pd.to_numeric(X.iloc[:, j], errors="coerce").to_numpy(dtype=float)
            ok = np.isfinite(x)
            if ok.sum() > 30 and np.std(x[ok]) > 0:
                c = float(np.corrcoef(x[ok], signed[ok, j])[0, 1])
                if np.isfinite(c):
                    e["corr"].append(c)
    for e in by_col.values():
        cs = e.pop("corr")
        mean_c = float(np.mean(cs)) if cs else None
        e["mean_abs"] = round(e["mean_abs"], 6)
        e["direction"] = (None if mean_c is None else
                          ("sube el resultado" if mean_c > 0.05 else
                           ("baja el resultado" if mean_c < -0.05 else "efecto no monótono")))
    return {"available": True, "model": fam, "n_rows": int(len(X)), "by_column": by_col}


def _narrative(ranking: list[dict], task: str, metric: str) -> list[str]:
    if not ranking:
        return []
    out = []
    top = [r for r in ranking[:5] if (r.get("permutation_drop_pct") or r.get("native") or 0)]
    if top:
        nombres = ", ".join(f"«{r['column']}»" for r in top[:3])
        out.append(f"Las variables que más pesan son {nombres}.")
    for r in top[:3]:
        piezas = []
        if r.get("permutation_drop_pct") is not None:
            piezas.append(f"al romperla, {metric} empeora {abs(r['permutation_drop_pct']):.1f}%")
        if r.get("shap_direction"):
            piezas.append(r["shap_direction"])
        if piezas:
            out.append(f"«{r['column']}»: " + "; ".join(piezas) + ".")
    irrel = [r["column"] for r in ranking if (r.get("permutation_drop_pct") or 0) <= 0][:6]
    if irrel:
        out.append("Sin aporte medible al predecir: " + ", ".join(f"«{c}»" for c in irrel) +
                   ". Se pueden sacar del dataset sin perder performance.")
    return out
