"""Endpoints de proyección: qué va a pasar el período que viene.

El endpoint no devuelve sólo la línea proyectada: devuelve también la tabla
del backtest y el veredicto. Es a propósito. Una proyección sin su medición
es una opinión con gráfico, y la interfaz tiene que poder mostrar las dos
cosas juntas.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core import proyeccion as P
from ..core import storage

router = APIRouter(prefix="/api/proyeccion", tags=["proyeccion"])


@router.get("/columnas/{ds_id}")
def columnas(ds_id: str) -> dict[str, Any]:
    """Qué columnas sirven de fecha y cuáles de valor, para armar el formulario."""
    try:
        meta = storage.load_meta(ds_id)
    except Exception as exc:
        raise HTTPException(404, f"Dataset inexistente: {ds_id}") from exc

    fechas, numericas, categoricas = [], [], []
    for c in meta.columns:
        t = str(c.get("arrow_type", "")).lower()
        if any(x in t for x in ("timestamp", "date")):
            fechas.append(c["name"])
        elif any(x in t for x in ("int", "double", "float", "decimal")):
            numericas.append(c["name"])
        else:
            categoricas.append(c["name"])
    return {"fechas": fechas, "numericas": numericas, "categoricas": categoricas,
            "granos": sorted(P.GRANOS), "agregaciones": sorted(P.AGREGACIONES)}


class ProyectarBody(BaseModel):
    dataset_id: str
    columna_tiempo: str
    columna_valor: str
    horizonte: int = Field(6, ge=1, le=120)
    grano: str = "month"
    agregacion: str = "sum"
    filtro: dict[str, str] | None = None


@router.post("")
def proyectar(body: ProyectarBody) -> dict[str, Any]:
    try:
        return P.proyectar(body.dataset_id, body.columna_tiempo, body.columna_valor,
                           horizonte=body.horizonte, grano=body.grano,
                           agregacion=body.agregacion, filtro=body.filtro)
    except ValueError as exc:
        # Serie corta, horizonte imposible, columna que no es fecha: todos son
        # pedidos mal formados, y el texto del error ya explica qué hacer.
        raise HTTPException(400, str(exc)) from exc
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc
