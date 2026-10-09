"""Endpoints del programa de relacionamiento con consentimiento.

* ``GET /api/relacionamiento/plantilla/{tabla}`` — CSV de ejemplo para cargar
  cada tabla (contactos, contenidos, interacciones, población, prevalencias, escucha).
* ``POST /api/relacionamiento/analizar`` — recomendaciones, embudo, KPIs,
  auditoría y, si se cargaron, cobertura territorial y escucha agregada.
* ``POST /api/relacionamiento/exportar`` — zip con las tablas y medidas para
  Power BI y el modelo estrella para el Lakehouse de Fabric.

Las tablas se suben como cualquier dataset y se referencian por id. Toda la
lógica vive en ``core/programa_relacionamiento.py`` y sus módulos.
"""
from __future__ import annotations

import time
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..core import consentimiento as K
from ..core import programa_relacionamiento as PR
from ..core import storage, workspace
from .mercado import _limpio

router = APIRouter(tags=["relacionamiento"])

PLANTILLAS_PUBLICAS = {
    "poblacion": pd.DataFrame([{"pais": "Uruguay", "ciudad": "Montevideo", "barrio": "Pocitos", "sexo": "Mujeres",
                                "rango_edad": "40-59", "nse": "alto", "poblacion": 12000}]),
    "prevalencias": pd.DataFrame([{"pais": "Uruguay", "area_terapeutica": "Cardiometabólica", "sexo": "Mujeres",
                                   "rango_edad": "40-59", "prevalencia": 0.27,
                                   "fuente": "Encuesta nacional de factores de riesgo (año)"}]),
    "escucha": pd.DataFrame([{"fecha": "2026-10-01", "pais": "Uruguay",
                              "texto": "texto de la publicación (las columnas de autor y URL se descartan)"}]),
}


@router.get("/api/relacionamiento/plantilla/{tabla}")
def plantilla(tabla: str) -> Response:
    tablas = {**K.plantillas(), **PLANTILLAS_PUBLICAS}
    if tabla not in tablas:
        raise HTTPException(404, f"No hay plantilla «{tabla}». Hay: {', '.join(tablas)}.")
    return Response(tablas[tabla].to_csv(index=False), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="plantilla_{tabla}.csv"'})


class AjustePais(BaseModel):
    """Lo que legal valida por país. Lo que no se indica queda en el valor conservador."""
    promocion_receta_a_publico: bool | None = None
    promocion_venta_libre_a_publico: bool | None = None
    doble_optin_obligatorio: bool | None = None
    frecuencia_max_30d: int | None = Field(None, ge=0, le=30)
    validado_por_legal: bool | None = None


class AnalizarBody(BaseModel):
    contactos_dataset_id: str
    contenidos_dataset_id: str
    interacciones_dataset_id: str | None = None
    poblacion_dataset_id: str | None = None
    prevalencias_dataset_id: str | None = None
    escucha_dataset_id: str | None = None
    area: str | None = None
    por_barrio: bool = False
    segmentar: list[Literal["sexo", "rango_edad", "nse"]] = Field(default_factory=list, max_length=3)
    temas: dict[str, list[str]] | None = Field(None, max_length=100)
    hoy: str | None = None
    por_contacto: int = Field(3, ge=1, le=10)
    ajustes: dict[str, AjustePais] | None = Field(None, max_length=50)


def _frame(ds_id: str | None) -> pd.DataFrame | None:
    if not ds_id:
        return None
    try:
        return storage.load_frame(storage.dataset_para(ds_id))
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc


def _analizar(b: AnalizarBody) -> dict[str, Any]:
    ajustes = {p: a.model_dump(exclude_none=True) for p, a in (b.ajustes or {}).items()}
    try:
        return PR.analizar(
            _frame(b.contactos_dataset_id), _frame(b.contenidos_dataset_id), _frame(b.interacciones_dataset_id),
            poblacion=_frame(b.poblacion_dataset_id), prevalencias=_frame(b.prevalencias_dataset_id),
            escucha=_frame(b.escucha_dataset_id), area=b.area or None, por_barrio=b.por_barrio,
            segmentar=tuple(b.segmentar), temas=b.temas, hoy=b.hoy or None, ajustes=ajustes,
            por_contacto=b.por_contacto)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/relacionamiento/analizar")
def analizar(body: AnalizarBody) -> dict[str, Any]:
    return _limpio(PR.a_json(_analizar(body)))


class ExportarBody(AnalizarBody):
    formato: Literal["parquet", "csv"] = "csv"


@router.post("/api/relacionamiento/exportar")
def exportar(body: ExportarBody) -> dict[str, Any]:
    r = _analizar(body)
    nombre = f"relacionamiento_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    destino = workspace.dir_for("exports") / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Se arma al lado y se renombra: la lista de exportaciones nunca ve uno a medio escribir.
    parcial = destino.with_name(destino.name + ".part")
    try:
        PR.empaquetar(r, parcial, formato=body.formato)
    except ValueError as exc:
        parcial.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    parcial.replace(destino)
    return {"filename": nombre, "download_url": f"/api/exports/download/{nombre}",
            "size_bytes": destino.stat().st_size}
