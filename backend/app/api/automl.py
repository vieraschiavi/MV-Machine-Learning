"""Endpoints de AutoML: entrenamiento, modelos guardados y scoring."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import automl as A
from ..core import jobs, registry, storage

router = APIRouter(prefix="/api/automl", tags=["automl"])


class TrainBody(BaseModel):
    dataset_id: str
    target: str
    task: str = "auto"
    time_column: str | None = None
    exclude: list[str] = []
    metric: str | None = None
    budget_seconds: int = 120
    max_models: int = 6
    feature_selection: bool = True
    calibrate: bool = True
    ensemble: bool = True
    log_target: str = "auto"
    shap: bool = True
    permutation_importance: bool = True
    selection_size: float = 0.20
    holdout_size: float = 0.20
    max_rows: int | None = None
    name: str | None = None


@router.post("/train")
def train(body: TrainBody) -> dict[str, Any]:
    try:
        meta = storage.load_meta(body.dataset_id)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc
    names = {c["name"] for c in meta.columns}
    if body.target not in names:
        raise HTTPException(400, f"La columna objetivo «{body.target}» no existe en el dataset.")

    cfg = A.TrainConfig(
        target=body.target, task=body.task, time_column=body.time_column,
        exclude=body.exclude, metric=body.metric, budget_seconds=body.budget_seconds,
        max_models=body.max_models, feature_selection=body.feature_selection,
        calibrate=body.calibrate, ensemble=body.ensemble, log_target=body.log_target,
        shap=body.shap, permutation_importance=body.permutation_importance,
        selection_size=body.selection_size, holdout_size=body.holdout_size,
        max_rows=body.max_rows,
    )

    def work(progress):
        progress(2, f"Cargando datos ({meta.rows:,} filas)")
        df = storage.load_frame(body.dataset_id, max_rows=body.max_rows)
        if len(df) < meta.rows:
            progress(3, f"Muestreo reproducible: {len(df):,} de {meta.rows:,} filas "
                        f"para que el entrenamiento entre en memoria")
        res = A.train(df, cfg, progress)
        card = registry.save(res["bundle"], res["report"],
                             body.name or f"{meta.name} · {body.target}", body.dataset_id)
        return {"model_id": card["id"], "report": res["report"],
                "sampled_rows": int(len(df)), "dataset_rows": meta.rows}

    return jobs.run("training", f"Entrenamiento sobre «{body.target}»", work,
                    meta={"dataset_id": body.dataset_id, "target": body.target})


@router.get("/models")
def models() -> dict[str, Any]:
    return {"models": registry.list_models()}


@router.get("/models/{model_id}")
def model_card(model_id: str) -> dict[str, Any]:
    try:
        return registry.card(model_id)
    except Exception as exc:
        raise HTTPException(404, f"Modelo inexistente: {model_id}") from exc


@router.delete("/models/{model_id}")
def delete_model(model_id: str) -> dict[str, Any]:
    registry.delete(model_id)
    return {"deleted": model_id}


class ScoreBody(BaseModel):
    model_id: str
    dataset_id: str
    name: str | None = None
    keep_columns: list[str] | None = None


@router.post("/score")
def score(body: ScoreBody) -> dict[str, Any]:
    def work(progress):
        progress(5, "Aplicando el modelo por bloques")
        return registry.score_dataset(body.model_id, body.dataset_id,
                                      body.name, body.keep_columns)

    return jobs.run("scoring", "Scoring del dataset", work,
                    meta={"model_id": body.model_id, "dataset_id": body.dataset_id})


class PredictBody(BaseModel):
    model_id: str
    rows: list[dict[str, Any]]


@router.post("/predict")
def predict(body: PredictBody) -> dict[str, Any]:
    """Predicción puntual sobre filas escritas a mano (prueba rápida del modelo)."""
    import pandas as pd

    try:
        bundle, _ = registry.load(body.model_id)
    except Exception as exc:
        raise HTTPException(404, f"Modelo inexistente: {body.model_id}") from exc
    if not body.rows:
        raise HTTPException(400, "No se enviaron filas para predecir.")
    df = pd.DataFrame(body.rows)
    try:
        out = registry.predict_frame(bundle, df)
    except Exception as exc:
        raise HTTPException(400, f"No se pudo predecir: {exc}") from exc
    return {"predictions": json.loads(out.to_json(orient="records", date_format="iso"))}
