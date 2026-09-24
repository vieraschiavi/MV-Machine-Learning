"""Endpoints de datasets: subida sin límite de tamaño, perfil y exploración."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..core import licensing as L
from ..core import profiling, storage, workspace

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

SAFE_NAME = re.compile(r"[^A-Za-z0-9._\- ]+")


def _tmp(filename: str) -> Path:
    safe = SAFE_NAME.sub("_", Path(filename or "dataset.csv").name)[:120] or "dataset.csv"
    return workspace.dir_for("uploads") / f"{uuid.uuid4().hex[:10]}__{safe}"


def _ingestar(archivo: Path, nombre: str, hoja: str | None = None) -> list[storage.DatasetMeta]:
    """Leer el archivo y escribir el Parquet: minutos de trabajo bloqueante.

    Vive en una función aparte porque las rutas de subida son `async` y esto
    tiene que correr FUERA del event loop. Adentro ocuparía el único hilo que
    atiende a todo el servidor: mientras un usuario sube su archivo, nadie más
    recibe respuesta. Medido sobre 9 MB, la latencia del resto pasaba de 3 ms a
    955 ms, y escala con el tamaño —justo lo que este producto no limita—.

    Un Excel de varias hojas devuelve un dataset por hoja, el más útil primero
    (ver ``storage.ingest_workbook``). Los topes de la licencia se aplican hoja
    por hoja en ese orden: si no entran todas, se queda la mejor.
    """
    previos = len(storage.list_datasets())
    L.check_count(previos, "max_datasets")
    opts = {"sheet": hoja} if hoja else None
    if archivo.suffix.lower() in storage.EXCEL_EXT:
        metas = storage.ingest_workbook(archivo, nombre, source="upload", opts=opts)
    else:
        metas = [storage.ingest_file(archivo, nombre, source="upload", opts=opts)]
    guardadas: list[storage.DatasetMeta] = []
    primer_error: PermissionError | None = None
    for m in metas:
        try:
            L.check_count(previos + len(guardadas), "max_datasets")
            L.check_rows(m.rows)
            guardadas.append(m)
        except PermissionError as exc:
            storage.delete_dataset(m.id)     # no se deja a medias en el workspace
            primer_error = primer_error or exc
    if not guardadas:
        raise primer_error or storage.IngestError("El archivo no produjo datos.")
    # lo que el usuario acaba de cargar pasa a ser el dataset de TODAS las pestañas
    storage.elegir_dataset_activo(guardadas[0].id)
    return guardadas


def _respuesta(metas: list[storage.DatasetMeta]) -> dict[str, Any]:
    """`dataset` es el activo (como siempre); `hojas`, todo lo que dejó el libro."""
    return {"dataset": metas[0].to_dict(),
            "hojas": [{"id": m.id, "name": m.name, "rows": m.rows,
                       "sheet": (m.origin or {}).get("sheet")} for m in metas]}


@router.get("")
def list_all() -> dict[str, Any]:
    return {"datasets": storage.list_datasets()}


class ActivoBody(BaseModel):
    dataset_id: str


@router.get("/active")
def activo() -> dict[str, Any]:
    """El dataset sobre el que trabajan todas las pestañas del workspace."""
    return storage.dataset_activo()


@router.put("/active")
def elegir_activo(body: ActivoBody) -> dict[str, Any]:
    try:
        return storage.elegir_dataset_activo(body.dataset_id)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/active")
def limpiar_activo() -> dict[str, Any]:
    return storage.limpiar_dataset_activo()


@router.post("/upload-stream")
async def upload_stream(request: Request, filename: str = Query(...),
                        name: str | None = Query(None),
                        sheet: str | None = Query(None)) -> dict[str, Any]:
    """Sube por streaming crudo: el archivo nunca se carga entero en memoria.

    Es la vía que usa la interfaz. No hay tope de tamaño: el límite es el
    espacio en disco.
    """
    dest = _tmp(filename)
    written = 0
    try:
        with dest.open("wb") as fh:
            async for chunk in request.stream():
                if chunk:
                    fh.write(chunk)
                    written += len(chunk)
        if written == 0:
            raise HTTPException(400, "El archivo llegó vacío.")
        metas = await run_in_threadpool(_ingestar, dest, name or Path(filename).stem, sheet)
        return {**_respuesta(metas), "bytes_received": written}
    except storage.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        dest.unlink(missing_ok=True)


@router.post("/upload")
async def upload_multipart(file: UploadFile = File(...),
                           name: str | None = Form(None),
                           sheet: str | None = Form(None)) -> dict[str, Any]:
    """Alternativa multipart, para clientes que no puedan mandar el cuerpo crudo."""
    dest = _tmp(file.filename or "dataset.csv")
    try:
        with dest.open("wb") as fh:
            while chunk := await file.read(4 * 1024 * 1024):
                fh.write(chunk)
        metas = await run_in_threadpool(
            _ingestar, dest, name or Path(file.filename or "dataset").stem, sheet)
        return _respuesta(metas)
    except storage.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        dest.unlink(missing_ok=True)


@router.get("/{dataset_id}")
def get_one(dataset_id: str) -> dict[str, Any]:
    try:
        return {"dataset": storage.load_meta(dataset_id).to_dict()}
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{dataset_id}/preview")
def preview(dataset_id: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    try:
        df = storage.head(dataset_id, limit, offset)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "columns": list(df.columns),
        "rows": json.loads(df.to_json(orient="records", date_format="iso")),
        "total": storage.load_meta(dataset_id).rows,
    }


@router.get("/{dataset_id}/profile")
def profile(dataset_id: str) -> dict[str, Any]:
    try:
        return profiling.profile(dataset_id)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{dataset_id}/correlations")
def correlations(dataset_id: str) -> dict[str, Any]:
    return profiling.correlations(dataset_id)


@router.get("/{dataset_id}/target-analysis")
def target_analysis(dataset_id: str, target: str) -> dict[str, Any]:
    try:
        return profiling.target_analysis(dataset_id, target)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class SqlBody(BaseModel):
    sql: str
    limit: int = 500


@router.post("/{dataset_id}/query")
def run_query(dataset_id: str, body: SqlBody) -> dict[str, Any]:
    """Consulta SQL libre sobre el dataset (sólo lectura, sobre el Parquet)."""
    sql = body.sql.strip().rstrip(";")
    if not re.match(r"^\s*(select|with)\b", sql, re.I):
        raise HTTPException(400, "Sólo se aceptan consultas SELECT o WITH.")
    try:
        df = storage.query(dataset_id, f"SELECT * FROM ({sql}) LIMIT {int(body.limit)}")
    except Exception as exc:
        raise HTTPException(400, f"Error en la consulta: {exc}") from exc
    return {"columns": list(df.columns),
            "rows": json.loads(df.to_json(orient="records", date_format="iso")),
            "n": int(len(df))}


@router.delete("/{dataset_id}")
def delete(dataset_id: str) -> dict[str, Any]:
    storage.delete_dataset(dataset_id)
    return {"deleted": dataset_id}
