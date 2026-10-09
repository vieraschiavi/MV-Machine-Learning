"""Endpoints de portafolio y mercado.

* ``/api/portafolio/...`` — la matriz de contribución y mix (las burbujas) y
  la descarga del paquete para Power BI.
* ``/api/mercado/...`` — el agente: plantilla de supuestos, propuesta con IA,
  análisis del embudo (actual y latente), lanzamiento y lectura ejecutiva.

Los routers son finos: toda la lógica vive en ``core/contribucion.py``,
``core/mercado.py``, ``core/agente_mercado.py`` y ``core/powerbi_portafolio.py``.
"""
from __future__ import annotations

import math
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..core import agente_mercado as A
from ..core import contribucion as C
from ..core import mercado as M
from ..core import powerbi_portafolio as P
from ..core import storage, workspace

router = APIRouter(tags=["portafolio y mercado"])


def _limpio(x: Any) -> Any:
    """NaN e infinitos a `null`: el JSON estándar no los admite."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _limpio(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_limpio(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, str):      # escalares de NumPy
        return _limpio(x.item())
    return x


def _frame(ds_id: str | None) -> tuple[str, pd.DataFrame]:
    try:
        ds = storage.dataset_para(ds_id)
        return ds, storage.load_frame(ds)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc


# ── portafolio ──────────────────────────────────────────────────────────────
@router.get("/api/portafolio/columnas/{ds_id}")
def columnas(ds_id: str) -> dict[str, Any]:
    """Qué columnas sirven de entidad, de valor, de mix, de grupo y de período."""
    try:
        c = storage.clasificar_columnas(ds_id)
    except storage.IngestError as exc:
        raise HTTPException(404, f"Dataset inexistente: {ds_id}") from exc
    return {"categoricas": c["categoricas"], "numericas": c["numericas"], "fechas": c["fechas"]}


class ContribucionBody(BaseModel):
    dataset_id: str | None = None
    entidad: str
    valor: str
    mix: str | None = None
    niveles_mix: dict[str, int] | None = None
    grupo: str | None = None
    grupo_valor: str | None = None
    periodo: str | None = None
    umbral_alta: float = Field(0.10, gt=0, lt=1)
    umbral_media: float = Field(0.03, ge=0, lt=1)
    top: int = Field(3, ge=1, le=20)
    etiqueta: str = "mercados"

    def config(self) -> C.Config:
        return C.Config(entidad=self.entidad, valor=self.valor, mix=self.mix or None,
                        niveles_mix=self.niveles_mix, grupo=self.grupo or None,
                        periodo=self.periodo or None, umbral_alta=self.umbral_alta,
                        umbral_media=self.umbral_media, top=self.top, etiqueta=self.etiqueta)


@router.post("/api/portafolio/contribucion")
def contribucion(body: ContribucionBody) -> dict[str, Any]:
    ds, df = _frame(body.dataset_id)
    try:
        r = C.calcular(df, body.config(), grupo_valor=body.grupo_valor or None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if body.grupo and body.grupo in df.columns:
        r["grupos_disponibles"] = sorted(df[body.grupo].dropna().astype(str).unique().tolist())
    r["dataset_id"] = ds
    return _limpio(r)


# ── mercado ─────────────────────────────────────────────────────────────────
@router.get("/api/mercado/plantilla")
def plantilla(paises: str, segmentos: str = "Hombres,Mujeres") -> Response:
    """CSV vacío con todos los parámetros, para completar con un estudio de mercado."""
    lista = [p.strip() for p in paises.split(",") if p.strip()]
    segs = [s.strip() for s in segmentos.split(",") if s.strip()] or ["Total"]
    if not lista:
        raise HTTPException(400, "Indicá al menos un país.")
    csv = M.plantilla(lista, segs).to_csv(index=False)
    return Response(csv, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="supuestos_mercado.csv"'})


class ProponerBody(BaseModel):
    area_terapeutica: str
    molecula: str
    enfermedad: str
    paises: list[str] = Field(min_length=1, max_length=30)
    presentacion: str = ""
    segmentos: list[str] = Field(default_factory=lambda: ["Hombres", "Mujeres"], max_length=10)
    notas: str = Field("", max_length=4000)
    provider: str | None = None
    model: str | None = None


@router.post("/api/mercado/proponer")
def proponer(body: ProponerBody) -> dict[str, Any]:
    ctx = A.Contexto(area_terapeutica=body.area_terapeutica, molecula=body.molecula,
                     enfermedad=body.enfermedad, paises=tuple(body.paises),
                     presentacion=body.presentacion, segmentos=tuple(body.segmentos), notas=body.notas)
    try:
        return _limpio(A.proponer(ctx, provider=body.provider, model=body.model))
    except A.AgenteError as exc:
        raise HTTPException(400, str(exc)) from exc


class LanzamientoBody(BaseModel):
    pico: float = Field(gt=0, le=1)
    meses_al_pico: int = Field(24, ge=1, le=120)
    horizonte: int = Field(36, ge=1, le=120)
    forma: str = "media"
    crecimiento_anual: float = Field(0.0, ge=-0.5, le=2)
    pico_min: float | None = Field(None, gt=0, le=1)
    pico_max: float | None = Field(None, gt=0, le=1)


class AnalizarBody(BaseModel):
    supuestos: list[dict[str, Any]] | None = Field(None, max_length=5000)
    estudios_dataset_id: str | None = None
    lanzamiento: LanzamientoBody | None = None
    inicio: str | None = None
    observado: list[dict[str, Any]] | None = Field(None, max_length=500)
    n_sim: int = Field(2000, ge=100, le=20000)


def _analizar(body: AnalizarBody) -> dict[str, Any]:
    estudios = _frame(body.estudios_dataset_id)[1] if body.estudios_dataset_id else None
    propuesta = pd.DataFrame(body.supuestos) if body.supuestos else None
    tabla, avisos = A.combinar(propuesta, estudios)
    plan = M.Lanzamiento(**body.lanzamiento.model_dump()) if body.lanzamiento else None
    obs = pd.DataFrame(body.observado) if body.observado else None
    r = A.analizar(tabla, plan=plan, observado=obs, inicio=body.inicio or None, n_sim=body.n_sim)
    r["avisos"] = [*avisos, *r["avisos"]]
    return r


@router.post("/api/mercado/analizar")
def analizar(body: AnalizarBody) -> dict[str, Any]:
    try:
        return _limpio(_analizar(body))
    except (M.SupuestosInvalidos, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


class NarrarBody(BaseModel):
    resultado: dict[str, Any]
    provider: str | None = None
    model: str | None = None


@router.post("/api/mercado/narrar")
def narrar(body: NarrarBody) -> dict[str, Any]:
    from ..core import ai
    try:
        return A.narrar(body.resultado, provider=body.provider, model=body.model)
    except ai.AIError as exc:
        raise HTTPException(400, str(exc)) from exc


# ── paquete para Power BI ───────────────────────────────────────────────────
class PowerBIBody(BaseModel):
    contribucion: ContribucionBody | None = None
    mercado: AnalizarBody | None = None
    formato: str = "csv"


@router.post("/api/portafolio/powerbi")
def powerbi(body: PowerBIBody) -> dict[str, Any]:
    """Arma el zip con las tablas y el kit (tema, medidas DAX, burbujas Deneb)."""
    try:
        matriz = None
        if body.contribucion:
            _, df = _frame(body.contribucion.dataset_id)
            matriz = C.calcular_por_grupo(df, body.contribucion.config())
        analisis = _analizar(body.mercado) if body.mercado else None
        with tempfile.TemporaryDirectory(prefix="mv-pbi-") as tmp:
            P.escribir(tmp, matriz, analisis, formato=body.formato)
            nombre = f"powerbi_portafolio_{time.strftime('%Y%m%d_%H%M%S')}.zip"
            destino = workspace.dir_for("exports") / nombre
            destino.parent.mkdir(parents=True, exist_ok=True)
            # El zip se arma al lado del destino y se renombra al final: así la
            # lista de exportaciones nunca muestra uno a medio escribir.
            parcial = destino.with_name(destino.name + ".part")
            P.empaquetar(Path(tmp), parcial)
            parcial.replace(destino)
    except (M.SupuestosInvalidos, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"filename": nombre, "download_url": f"/api/exports/download/{nombre}",
            "size_bytes": destino.stat().st_size}
