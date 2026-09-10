"""Endpoints de la bitácora: verla y llevársela en HTML o en Word.

El PDF no se genera acá. Sale de imprimir el mismo HTML —el escritorio lo
hace con un clic y el navegador con Ctrl+P—, así los tres formatos muestran
exactamente lo mismo y el instalador no carga una biblioteca de PDF para algo
que el sistema operativo ya sabe hacer. Pedirlo igual no falla en silencio:
contesta explicando por dónde va.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core import bitacora as B
from ..core import documento, storage, workspace

router = APIRouter(prefix="/api/bitacora", tags=["bitacora"])

FORMATOS = {"html", "docx"}
PREFIJO = "MV_Bitacora_"


def _armar(dataset_id: str | None, model_id: str | None) -> dict[str, Any]:
    try:
        return B.construir(dataset_id=dataset_id, model_id=model_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (storage.IngestError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("")
def ver(dataset_id: str | None = Query(None), model_id: str | None = Query(None)) -> dict[str, Any]:
    """La bitácora completa del pipeline, en orden de ejecución."""
    return _armar(dataset_id, model_id)


class ExportarBody(BaseModel):
    dataset_id: str | None = None
    model_id: str | None = None
    formato: str = "html"


@router.post("/exportar")
def exportar(body: ExportarBody) -> dict[str, Any]:
    fmt = (body.formato or "").lower().strip()
    if fmt == "pdf":
        raise HTTPException(400, "El PDF se obtiene imprimiendo la bitácora desde el programa "
                                 "(botón «Guardar PDF»), que usa el mismo documento HTML.")
    if fmt not in FORMATOS:
        raise HTTPException(400, f"Formato no soportado: {body.formato!r}. Usá html o docx.")

    libro = _armar(body.dataset_id, body.model_id)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    destino = workspace.dir_for("exports") / f"{PREFIJO}{stamp}.{fmt}"
    if fmt == "html":
        destino.write_text(documento.a_html(libro), encoding="utf-8")
    else:
        documento.a_docx(libro, destino)

    return {"filename": destino.name, "size_bytes": destino.stat().st_size,
            "pasos": len(libro["pasos"]), "formato": fmt,
            "download_url": f"/api/bitacora/descargar/{destino.name}"}


@router.get("/descargar/{filename}")
def descargar(filename: str):
    """Entrega una bitácora ya generada.

    Sirve HTML con su tipo real —hace falta para poder imprimirlo y así
    obtener el PDF—, y por eso acota qué archivos alcanza: sólo los que
    generó este módulo. Un HTML servido desde el origen del backend corre con
    su mismo permiso; que este endpoint pudiera entregar cualquier archivo de
    la carpeta de exportaciones sería darle esa puerta a algo que no escribió
    el programa.
    """
    base = workspace.dir_for("exports").resolve()
    path = (base / filename).resolve()
    # `is_relative_to` compara RUTAS, no texto. Con `startswith`, un directorio
    # hermano llamado `exports-privado` pasaba el control por empezar igual que
    # `exports`, y su contenido se servía.
    if not path.is_relative_to(base) or not path.is_file():
        raise HTTPException(404, "Archivo inexistente.")
    if not path.name.startswith(PREFIJO) or path.suffix.lstrip(".") not in FORMATOS:
        raise HTTPException(404, "Archivo inexistente.")
    tipo = "text/html; charset=utf-8" if path.suffix == ".html" else "application/octet-stream"
    return FileResponse(path, filename=path.name, media_type=tipo)
