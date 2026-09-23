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


def _clasificar(ds_id: str) -> tuple[list[str], list[str], list[str]]:
    """`(fechas, numéricas, categóricas)` del dataset, por tipo de Arrow."""
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
    return fechas, numericas, categoricas


@router.get("/columnas/{ds_id}")
def columnas(ds_id: str) -> dict[str, Any]:
    """Qué columnas sirven de fecha y cuáles de valor, para armar el formulario."""
    fechas, numericas, categoricas = _clasificar(ds_id)
    return {"fechas": fechas, "numericas": numericas, "categoricas": categoricas,
            "granos": sorted(P.GRANOS), "agregaciones": sorted(P.AGREGACIONES)}


class ProyectarBody(BaseModel):
    dataset_id: str
    # Opcionales a propósito. Eran `str` obligatorios, y cuando el dataset
    # no tenía fecha o número la pantalla avisaba «sin fecha» pero dejaba el
    # botón habilitado: el pedido salía con `null` y el usuario veía el 422
    # crudo de pydantic —`[{"type":"string_type","loc":["body",
    # "columna_tiempo"],...}]`—, que no dice qué hacer. Ahora, si no vienen,
    # se eligen solas; y si el dataset no tiene con qué, se dice en castellano.
    columna_tiempo: str | None = None
    columna_valor: str | None = None
    horizonte: int = Field(6, ge=1, le=120)
    grano: str = "month"
    agregacion: str = "sum"
    filtro: dict[str, str] | None = None


def _resolver_columnas(body: ProyectarBody) -> tuple[str, str]:
    """Las columnas del pedido, o las primeras que sirven si no vinieron."""
    if body.columna_tiempo and body.columna_valor:
        return body.columna_tiempo, body.columna_valor
    fechas, numericas, categoricas = _clasificar(body.dataset_id)
    tiempo = body.columna_tiempo or (fechas[0] if fechas else None)
    valor = body.columna_valor or (numericas[0] if numericas else None)
    if tiempo and valor:
        return tiempo, valor
    falta = " ni ".join(x for x, ok in (("una columna de fecha", tiempo),
                                        ("una columna numérica", valor)) if not ok)
    hay = ", ".join((fechas + numericas + categoricas)[:12]) or "ninguna"
    raise HTTPException(400, (
        f"Para proyectar hace falta {falta}, y este dataset no tiene. Columnas "
        f"que trae: {hay}. Si es un Excel con varias hojas, puede que se haya "
        f"cargado la hoja equivocada (por ejemplo, un diccionario de datos): "
        f"subí la hoja que tiene la fecha y el valor."))


@router.post("")
def proyectar(body: ProyectarBody) -> dict[str, Any]:
    tiempo, valor = _resolver_columnas(body)
    try:
        return P.proyectar(body.dataset_id, tiempo, valor,
                           horizonte=body.horizonte, grano=body.grano,
                           agregacion=body.agregacion, filtro=body.filtro)
    except ValueError as exc:
        # Serie corta, horizonte imposible, columna que no es fecha: todos son
        # pedidos mal formados, y el texto del error ya explica qué hacer.
        raise HTTPException(400, str(exc)) from exc
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc
