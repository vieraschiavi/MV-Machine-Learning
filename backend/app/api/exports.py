"""Endpoints de exportación: Excel corporativo, CSV y Parquet."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import settings
from ..core import exporter, jobs, registry, storage

router = APIRouter(prefix="/api/exports", tags=["exports"])


class ExcelBody(BaseModel):
    dataset_id: str | None = None
    model_id: str | None = None
    include_profile: bool = True
    include_etl: bool = True
    include_data: bool = True
    data_limit: int = 200_000
    title: str = "MV AutoML Studio"


@router.post("/excel")
def excel(body: ExcelBody) -> dict[str, Any]:
    if not body.dataset_id and not body.model_id:
        raise HTTPException(400, "Indicá al menos un dataset o un modelo para exportar.")

    def work(progress):
        from ..core import profiling

        report = etl_info = profile = None
        ds_id = body.dataset_id
        if body.model_id:
            progress(15, "Leyendo la ficha del modelo")
            card = registry.card(body.model_id)
            report = card.get("report")
            ds_id = ds_id or card.get("dataset_id")
        if ds_id and body.include_profile:
            progress(35, "Calculando el perfil estadístico")
            profile = profiling.profile(ds_id)
        if ds_id and body.include_etl:
            meta = storage.load_meta(ds_id)
            if meta.source == "derived" and meta.origin.get("sql"):
                parent = storage.load_meta(meta.parent_id) if meta.parent_id else None
                etl_info = {"applied": [{"op": s["op"], "column": s.get("column"),
                                         "reason": s["reason"]}
                                        for s in meta.origin.get("steps", [])],
                            "sql": meta.origin.get("sql"),
                            "rows_in": parent.rows if parent else meta.rows,
                            "rows_out": meta.rows,
                            "columns_in": len(parent.columns) if parent else len(meta.columns),
                            "columns_out": len(meta.columns)}
        progress(60, "Escribiendo el libro de Excel")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = settings.export_dir / f"MV_AutoML_Informe_{stamp}.xlsx"
        info = exporter.build_report(
            out, report=report, profile=profile, etl=etl_info,
            dataset_id=ds_id if body.include_data else None,
            data_limit=body.data_limit, title=body.title)
        info["filename"] = out.name
        info["download_url"] = f"/api/exports/download/{out.name}"
        return info

    return jobs.run("export", "Informe en Excel", work)


class DataBody(BaseModel):
    dataset_id: str
    format: str = "csv"
    sep: str = ";"
    decimal: str = ","
    encoding: str = "utf-8-sig"
    limit: int | None = None


@router.post("/data")
def data(body: DataBody) -> dict[str, Any]:
    if body.format not in ("csv", "parquet"):
        raise HTTPException(400, "Formato no soportado. Usá csv o parquet.")

    def work(progress):
        progress(10, f"Exportando a {body.format.upper()}")
        info = exporter.export_dataset(body.dataset_id, body.format, body.sep,
                                       body.decimal, body.encoding, body.limit)
        info["download_url"] = f"/api/exports/download/{info['filename']}"
        return info

    return jobs.run("export", f"Exportación {body.format.upper()}", work,
                    meta={"dataset_id": body.dataset_id})


@router.get("/list")
def listing() -> dict[str, Any]:
    files = []
    for p in sorted(settings.export_dir.glob("*"), key=lambda p: -p.stat().st_mtime)[:100]:
        if p.is_file():
            files.append({"filename": p.name, "size_bytes": p.stat().st_size,
                          "modified": p.stat().st_mtime,
                          "download_url": f"/api/exports/download/{p.name}"})
    return {"files": files}


@router.get("/download/{filename}")
def download(filename: str):
    path = (settings.export_dir / filename).resolve()
    if not str(path).startswith(str(settings.export_dir.resolve())) or not path.is_file():
        raise HTTPException(404, "Archivo inexistente.")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")
