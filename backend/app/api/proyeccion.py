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
    """`(fechas, numéricas, categóricas)` del dataset.

    Antes sólo contaba como fecha lo que Arrow tipaba como fecha: un
    ``2024-01-31`` guardado como texto, o un período ``202401``, quedaban
    afuera y la pantalla decía «sin fecha» sobre un dataset lleno de fechas.
    Ahora se mira el contenido (ver ``core/fechas.py``).
    """
    try:
        c = storage.clasificar_columnas(ds_id)
    except storage.IngestError as exc:
        raise HTTPException(404, f"Dataset inexistente: {ds_id}") from exc
    return c["fechas"], c["numericas"], c["categoricas"]


def _otras_hojas(ds_id: str) -> list[dict[str, Any]]:
    """Hojas del mismo libro de Excel que SÍ se pueden proyectar."""
    out = []
    for d in storage.hermanas(ds_id):
        try:
            c = storage.clasificar_columnas(d["id"])
        except storage.IngestError:
            continue
        if c["fechas"] and c["numericas"]:
            out.append({"id": d["id"], "name": d.get("name"),
                        "sheet": (d.get("origin") or {}).get("sheet")})
    return out


@router.get("/columnas/{ds_id}")
def columnas(ds_id: str) -> dict[str, Any]:
    """Qué columnas sirven de fecha y cuáles de valor, para armar el formulario."""
    fechas, numericas, categoricas = _clasificar(ds_id)
    otras = _otras_hojas(ds_id) if not (fechas and numericas) else []
    return {"fechas": fechas, "numericas": numericas, "categoricas": categoricas,
            "granos": sorted(P.GRANOS), "agregaciones": sorted(P.AGREGACIONES),
            "otras_hojas": otras}


class ProyectarBody(BaseModel):
    # Sin dataset_id se proyecta sobre el dataset activo del workspace.
    dataset_id: str | None = None
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
    msg = f"Para proyectar hace falta {falta}, y este dataset no tiene. Columnas que trae: {hay}."
    otras = _otras_hojas(body.dataset_id)
    if otras:
        # el libro trae la hoja buena: se dice cuál, en vez de mandar a re-subir
        nombres = ", ".join(f"«{o['sheet'] or o['name']}» (dataset «{o['name']}»)"
                            for o in otras[:6])
        msg += f" Otras hojas del mismo Excel sí tienen fecha y valor: {nombres}. Elegí una de esas."
    else:
        msg += (" Si salió de un Excel con varias hojas (por ejemplo, un diccionario de "
                "datos), subí el libro entero: cada hoja queda como un dataset aparte y "
                "podés elegir la que tiene la fecha y el valor.")
    raise HTTPException(400, msg)


@router.post("")
def proyectar(body: ProyectarBody) -> dict[str, Any]:
    try:
        body.dataset_id = storage.dataset_para(body.dataset_id)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc
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
