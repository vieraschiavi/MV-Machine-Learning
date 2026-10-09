"""Endpoints del programa de relacionamiento con consentimiento.

* ``GET /api/relacionamiento/plantilla/{tabla}`` — CSV de ejemplo para cargar
  cada tabla (contactos, contenidos, interacciones, población, prevalencias, escucha).
* ``POST /api/relacionamiento/analizar`` — recomendaciones, embudo, KPIs,
  auditoría y, si se cargaron, cobertura territorial y escucha agregada.
* ``POST /api/relacionamiento/exportar`` — zip con las tablas y medidas para
  Power BI y el modelo estrella para el Lakehouse de Fabric.
* ``/api/relacionamiento/politicas`` — las reglas por país que validó legal,
  su historial y la planilla de validación (bajar y subir).

Las tablas se suben como cualquier dataset y se referencian por id. Toda la
lógica vive en ``core/programa_relacionamiento.py`` y sus módulos.
"""
from __future__ import annotations

import time
from typing import Any, Literal

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from ..core import catalogo as CAT
from ..core import consentimiento as K
from ..core import fuentes_publicas as FP
from ..core import licensing as L
from ..core import politicas_legales as PL
from ..core import programa_relacionamiento as PR
from ..core import registro_consentimientos as RC
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
    tablas = {**K.plantillas(), **PLANTILLAS_PUBLICAS, "consentimientos": RC.plantilla()}
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

    @model_validator(mode="after")
    def _rx_solo_con_legal(self) -> AjustePais:
        # Abrir la promoción de receta al público es la regla más delicada: no se acepta sin el visto de legal.
        if self.promocion_receta_a_publico and not self.validado_por_legal:
            raise ValueError("promocion_receta_a_publico sólo se puede habilitar con validado_por_legal: true.")
        return self


class AnalizarBody(BaseModel):
    contactos_dataset_id: str
    contenidos_dataset_id: str
    interacciones_dataset_id: str | None = None
    poblacion_dataset_id: str | None = None
    prevalencias_dataset_id: str | None = None
    escucha_dataset_id: str | None = None
    consentimientos_dataset_id: str | None = None
    busquedas_dataset_id: str | None = None
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
        # Entera, sin muestreo: una muestra perdería bajas y envíos, y el tope de frecuencia mentiría.
        return storage.query(storage.dataset_para(ds_id), "SELECT * FROM {t}")
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
            por_contacto=b.por_contacto, consentimientos=_frame(b.consentimientos_dataset_id),
            busquedas=_frame(b.busquedas_dataset_id))
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


# ── reglas por país validadas por legal ─────────────────────────────────────
MAX_PLANILLA = 5 * 1024 * 1024


@router.get("/api/relacionamiento/politicas")
def politicas() -> dict[str, Any]:
    return {"vigentes": PL.vigentes(), "historial": PL.historial(100)}


class ValidarPaisBody(BaseModel):
    cambios: dict[str, bool | int | str] = Field(default_factory=dict, max_length=10)
    validado_por: str = Field("", max_length=120)
    norma: str = Field("", max_length=300)
    nota: str = Field("", max_length=1000)


@router.put("/api/relacionamiento/politicas/{pais}")
def validar_pais(pais: str, body: ValidarPaisBody) -> dict[str, Any]:
    try:
        return PL.guardar(pais, body.cambios, validado_por=body.validado_por, norma=body.norma, nota=body.nota)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/relacionamiento/politicas/planilla")
def planilla_legal() -> Response:
    return Response(PL.planilla(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="validacion_legal_relacionamiento.xlsx"'})


@router.post("/api/relacionamiento/politicas/planilla")
async def subir_planilla(file: UploadFile = File(...)) -> dict[str, Any]:
    contenido = await file.read(MAX_PLANILLA + 1)
    if len(contenido) > MAX_PLANILLA:
        raise HTTPException(413, "La planilla supera los 5 MB: no es la planilla de validación.")
    try:
        return PL.importar_planilla(contenido)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ── captación ───────────────────────────────────────────────────────────────
@router.get("/api/relacionamiento/formulario")
def formulario(idioma: Literal["es", "pt"] = "es", accion: str = "https://crm.ejemplo/consentimientos",
               aviso: str = "https://ejemplo/privacidad", canal: str = "landing") -> Response:
    """El formulario de captación (HTML) para publicar en la landing: envía al CRM, no a este programa."""
    for nombre, url in (("accion", accion), ("aviso", aviso)):
        if not url.startswith("https://") or len(url) > 500:
            raise HTTPException(400, f"«{nombre}» tiene que ser una dirección https://.")
    html = RC.formulario_html(idioma, accion=accion, aviso_privacidad=aviso, canal=canal[:80])
    # Se baja como archivo: es para publicar en otro sitio, no para abrirse dentro del programa.
    return Response(html, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="formulario_captacion_{idioma}.html"'})


@router.get("/api/relacionamiento/textos-consentimiento")
def textos_consentimiento() -> dict[str, Any]:
    return RC.TEXTOS


# ── catálogo ────────────────────────────────────────────────────────────────
class RevisarCatalogoBody(BaseModel):
    contenidos_dataset_id: str
    contactos_dataset_id: str | None = None


@router.post("/api/relacionamiento/revisar-catalogo")
def revisar_catalogo(body: RevisarCatalogoBody) -> dict[str, Any]:
    """Qué contenido no va a llegar a nadie, o no a quien se pensó, antes de cargarlo."""
    try:
        r = CAT.revisar(_frame(body.contenidos_dataset_id), _frame(body.contactos_dataset_id),
                        PL.ajustes())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _limpio({k: (v.astype(object).where(v.notna(), None).to_dict("records")
                        if isinstance(v, pd.DataFrame) else v) for k, v in r.items()})


# ── fuentes públicas reales (OMS, Banco Mundial, Google Trends) ─────────────
class FuentePublicaBody(BaseModel):
    fuente: Literal["oms_prevalencias", "oms_supuestos", "banco_mundial_poblacion"]
    paises: list[str] = Field(min_length=1, max_length=20)
    area: str = "Cardiometabólica"


def _guardar(df: pd.DataFrame, nombre: str, origen: dict[str, Any]) -> dict[str, Any]:
    if df.empty:
        raise HTTPException(404, "La fuente no devolvió datos para esos países.")
    L.check_count(len(storage.list_datasets()), "max_datasets")
    meta = storage.ingest_frames(iter([df]), nombre, source="publica", origin=origen)
    return {"dataset": meta.to_dict(), "filas": len(df),
            "muestra": df.head(20).astype(object).where(df.head(20).notna(), None).to_dict("records")}


@router.post("/api/relacionamiento/fuentes/publicas")
def fuente_publica(body: FuentePublicaBody) -> dict[str, Any]:
    """Trae una fuente pública agregada y la deja como dataset, lista para el análisis o el agente."""
    try:
        if body.fuente == "oms_prevalencias":
            df = FP.prevalencias_oms(body.area, body.paises)
            nombre = f"OMS prevalencias {body.area}"
        elif body.fuente == "oms_supuestos":
            df = FP.supuestos_oms(body.area, body.paises)
            nombre = f"OMS y Banco Mundial supuestos {body.area}"
        else:
            df = FP.poblacion_banco_mundial(body.paises)
            nombre = "Banco Mundial población adulta"
    except ValueError as exc:
        # Un país desconocido es error del pedido; una caída de la red, del servicio de afuera.
        raise HTTPException(400 if "País" in str(exc) or "Área" in str(exc) else 502, str(exc)) from exc
    return _guardar(df, f"{nombre} ({', '.join(body.paises)})"[:120],
                    {"fuente": body.fuente, "paises": body.paises, "area": body.area})


@router.post("/api/relacionamiento/fuentes/trends")
async def fuente_trends(pais: str, termino: str | None = None, file: UploadFile = File(...)) -> dict[str, Any]:
    """La exportación «interés por subregión» de Google Trends, como dataset de búsquedas agregadas."""
    contenido = await file.read(MAX_PLANILLA + 1)
    if len(contenido) > MAX_PLANILLA:
        raise HTTPException(413, "El archivo supera los 5 MB: no es una exportación de Google Trends.")
    try:
        df = FP.trends_csv(contenido, pais, termino)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _guardar(df, f"Google Trends {pais} {termino or ''}".strip(), {"fuente": "google_trends", "pais": pais})
