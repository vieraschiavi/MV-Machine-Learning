"""Endpoints del tablero automático."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import dashboards as D
from ..core import jobs, storage

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


@router.get("/{dataset_id}/spec")
def spec(dataset_id: str) -> dict[str, Any]:
    """Propone el tablero para el dataset: KPIs, gráficos, filtros y tabla."""
    try:
        return D.detect_spec(dataset_id)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc


class RunBody(BaseModel):
    spec: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None


@router.post("/{dataset_id}/run")
def run(dataset_id: str, body: RunBody) -> dict[str, Any]:
    try:
        return D.run(dataset_id, body.spec, body.filters)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"El tablero no pudo ejecutarse: {exc}") from exc


class ExportBody(BaseModel):
    spec: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None
    format: str = "xlsx"


@router.post("/{dataset_id}/export")
def export(dataset_id: str, body: ExportBody) -> dict[str, Any]:
    if body.format not in ("xlsx", "csv"):
        raise HTTPException(400, "Formato no soportado: usá xlsx o csv.")

    def work(progress):
        progress(10, "Ejecutando el tablero filtrado")
        info = D.export(dataset_id, body.spec, body.filters, body.format)
        info["download_url"] = f"/api/exports/download/{info['filename']}"
        return info

    return jobs.run("export", "Exportación del tablero", work,
                    meta={"dataset_id": dataset_id})
