"""Registro de modelos entrenados: guardar, listar y aplicar a datos nuevos."""
from __future__ import annotations

import json
import shutil
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ..config import settings
from . import storage as S


def new_id() -> str:
    return f"mdl_{uuid.uuid4().hex[:12]}"


def model_path(model_id: str) -> Path:
    if not S.SAFE_ID.match(model_id):
        raise ValueError(f"Identificador de modelo inválido: {model_id!r}")
    return settings.model_dir / model_id


def save(bundle: dict[str, Any], report: dict[str, Any], name: str,
         dataset_id: str) -> dict[str, Any]:
    mid = new_id()
    folder = model_path(mid)
    folder.mkdir(parents=True, exist_ok=True)
    cfg = bundle.get("config")
    joblib.dump(bundle, folder / "bundle.joblib", compress=3)
    card = {
        "id": mid, "name": name, "dataset_id": dataset_id,
        "target": report["target"], "task": report["task"],
        "metric": report["metric"],
        "score": report["champion"]["holdout"].get(report["metric"]),
        "model": report["champion"]["model"],
        "created_at": time.time(),
        "config": _cfg_dict(cfg),
        "report": report,
    }
    (folder / "card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2, default=str),
                                      encoding="utf-8")
    return card


def _cfg_dict(cfg) -> dict[str, Any]:
    if cfg is None:
        return {}
    d = dict(getattr(cfg, "__dict__", {}))
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load(model_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    folder = model_path(model_id)
    if not (folder / "bundle.joblib").exists():
        raise FileNotFoundError(f"Modelo inexistente: {model_id}")
    bundle = joblib.load(folder / "bundle.joblib")
    card = json.loads((folder / "card.json").read_text(encoding="utf-8"))
    return bundle, card


def list_models() -> list[dict[str, Any]]:
    out = []
    for folder in sorted(settings.model_dir.glob("mdl_*"),
                         key=lambda p: p.stat().st_mtime, reverse=True):
        f = folder / "card.json"
        if not f.exists():
            continue
        try:
            c = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        c.pop("report", None)          # la ficha corta para el listado
        out.append(c)
    return out


def card(model_id: str) -> dict[str, Any]:
    return json.loads((model_path(model_id) / "card.json").read_text(encoding="utf-8"))


def delete(model_id: str) -> None:
    shutil.rmtree(model_path(model_id), ignore_errors=True)


# ────────────────────────────────────────────────────────────── scoring ───────
def predict_frame(bundle: dict[str, Any], df: pd.DataFrame) -> pd.DataFrame:
    """Aplica el modelo a filas nuevas y devuelve las columnas de salida."""
    pre = bundle["preprocessor"]
    task = bundle["task"]
    tt = bundle["target_transform"]
    feats = bundle["features"]
    X = df.reindex(columns=feats)
    Xt, Xl = pre.transform_tree(X), pre.transform_linear(X)

    members = (bundle["ens_members"] if bundle["champion_key"] == "__ensemble__"
               else [bundle["champion_key"]])
    preds = []
    for fam in members:
        mdl = bundle["models"].get(fam)
        if mdl is None:
            continue
        p = mdl.predict(Xt, Xl)
        if task == "binary":
            iso = bundle["calibrators"].get(fam)
            if iso is not None:
                p = np.clip(iso.predict(p), 0, 1)
        preds.append(p)
    if not preds:
        raise RuntimeError("El modelo guardado no tiene estimadores utilizables.")
    p = np.mean(preds, axis=0)

    out = pd.DataFrame(index=df.index)
    if task == "binary":
        pos = bundle.get("positive") or "1"
        out[f"prob_{_slug(pos)}"] = np.clip(p, 0, 1)
        out["prediccion"] = np.where(p >= 0.5, str(pos), "(otro)")
        neg = next((c for c in (bundle.get("classes") or []) if str(c) != str(pos)), "(otro)")
        out["prediccion"] = np.where(p >= 0.5, str(pos), str(neg))
    elif task == "multiclass":
        classes = bundle.get("classes") or [str(i) for i in range(np.asarray(p).shape[1])]
        arr = np.asarray(p)
        for j, c in enumerate(classes[: arr.shape[1]]):
            out[f"prob_{_slug(c)}"] = arr[:, j]
        out["prediccion"] = [classes[i] for i in arr.argmax(1)]
        out["confianza"] = arr.max(1)
    else:
        out["prediccion"] = tt.inverse(p) if getattr(tt, "use_log", False) else p
    return out


def _slug(v: Any) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9]+", "_", str(v)).strip("_").lower() or "clase"


def score_dataset(model_id: str, dataset_id: str, name: str | None = None,
                  keep_columns: list[str] | None = None) -> dict[str, Any]:
    """Aplica el modelo a un dataset entero, por bloques, sin límite de tamaño."""
    bundle, card_ = load(model_id)
    meta = S.load_meta(dataset_id)
    total = meta.rows
    step = settings.chunk_rows

    def frames() -> Iterator[pd.DataFrame]:
        for off in range(0, max(total, 1), step):
            chunk = S.query(dataset_id, f"SELECT * FROM {{t}} LIMIT {step} OFFSET {off}")
            if chunk.empty:
                break
            pred = predict_frame(bundle, chunk)
            base = chunk[keep_columns] if keep_columns else chunk
            yield pd.concat([base.reset_index(drop=True), pred.reset_index(drop=True)], axis=1)

    out = S.ingest_frames(
        frames(), name or f"{meta.name} · scoring", source="derived",
        origin={"model_id": model_id, "model": card_.get("model"), "parent": dataset_id},
        parent_id=dataset_id)
    return {"dataset": out.to_dict(), "model_id": model_id, "rows": out.rows}
