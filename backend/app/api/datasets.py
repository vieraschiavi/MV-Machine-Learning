"""Endpoints de datasets: subida sin límite de tamaño, perfil y exploración."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from ..config import settings
from ..core import profiling, storage

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

SAFE_NAME = re.compile(r"[^A-Za-z0-9._\- ]+")


def _tmp(filename: str) -> Path:
    safe = SAFE_NAME.sub("_", Path(filename or "dataset.csv").name)[:120] or "dataset.csv"
    return settings.upload_dir / f"{uuid.uuid4().hex[:10]}__{safe}"


@router.get("")
def list_all() -> dict[str, Any]:
    return {"datasets": storage.list_datasets()}


@router.post("/upload-stream")
async def upload_stream(request: Request, filename: str = Query(...),
                        name: str | None = Query(None)) -> dict[str, Any]:
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
        meta = storage.ingest_file(dest, name or Path(filename).stem, source="upload")
        return {"dataset": meta.to_dict(), "bytes_received": written}
    except storage.IngestError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        dest.unlink(missing_ok=True)


@router.post("/upload")
async def upload_multipart(file: UploadFile = File(...),
                           name: str | None = Form(None)) -> dict[str, Any]:
    """Alternativa multipart, para clientes que no puedan mandar el cuerpo crudo."""
    dest = _tmp(file.filename or "dataset.csv")
    try:
        with dest.open("wb") as fh:
            while chunk := await file.read(4 * 1024 * 1024):
                fh.write(chunk)
        meta = storage.ingest_file(dest, name or Path(file.filename or "dataset").stem)
        return {"dataset": meta.to_dict()}
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
