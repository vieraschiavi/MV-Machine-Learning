"""Endpoints de ingeniería de datos: claves, tiempo, cruces y contrato.

No llevan comprobación de nivel de licencia a propósito. Esto no es un producto
aparte que se venda por separado: es parte del programa, y lo que ya limita al
nivel Demo son los topes de filas y de datasets que se aplican al cargarlos.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..core import ingenieria, storage

router = APIRouter(prefix="/api/ingenieria", tags=["ingenieria"])


def _existe(ds_id: str) -> None:
    try:
        storage.load_meta(ds_id)
    except Exception as exc:
        raise HTTPException(404, f"Dataset inexistente: {ds_id}") from exc


@router.get("/dialectos")
def dialectos() -> dict[str, Any]:
    """Motores para los que se puede generar el DDL."""
    return {"dialectos": [{"id": k, "label": v["label"]}
                          for k, v in ingenieria.DIALECTOS.items()]}


@router.get("/{ds_id}")
def informe(ds_id: str, dialecto: str = Query("sqlserver"),
            columna_tiempo: str | None = Query(None)) -> dict[str, Any]:
    """El análisis completo: claves, tiempo y contrato, en una sola pasada."""
    _existe(ds_id)
    try:
        return ingenieria.informe(ds_id, dialecto, columna_tiempo)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{ds_id}/claves")
def claves(ds_id: str) -> dict[str, Any]:
    _existe(ds_id)
    return ingenieria.claves(ds_id)


@router.get("/{ds_id}/tiempo")
def tiempo(ds_id: str, columna: str | None = Query(None)) -> dict[str, Any]:
    _existe(ds_id)
    r = ingenieria.tiempo(ds_id, columna)
    if r is None:
        # No es un error: hay datasets sin ninguna columna de fecha, y la
        # interfaz tiene que poder decirlo sin mostrar una pantalla rota.
        return {"disponible": False,
                "motivo": "Este dataset no tiene ninguna columna de fecha reconocida."}
    return {"disponible": True, **r}


@router.get("/{ds_id}/contrato")
def contrato(ds_id: str, dialecto: str = Query("sqlserver")) -> dict[str, Any]:
    _existe(ds_id)
    try:
        return ingenieria.contrato(ds_id, dialecto)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class CruceReq(BaseModel):
    datasets: list[str] | None = None
    min_solape: float = 20.0


@router.post("/cruces")
def cruces(req: CruceReq) -> dict[str, Any]:
    """Cruces posibles entre los datasets cargados, con su riesgo."""
    return ingenieria.joins(req.datasets, req.min_solape)
