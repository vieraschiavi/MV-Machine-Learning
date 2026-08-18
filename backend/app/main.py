"""MV AutoML Studio — aplicación FastAPI.

Sirve la API y la interfaz estática desde el mismo proceso: se levanta con un
comando y no necesita build de frontend ni servidor web adicional.
"""
from __future__ import annotations

import logging
import os
import platform
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import ai, automl, connectors, datasets, etl, exports, jobs, workspaces
from .config import settings
from .core import workspace as W

log = logging.getLogger("mv")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

VERSION = "1.0.0"

app = FastAPI(
    title="MV AutoML Studio",
    version=VERSION,
    description="Plataforma de ETL automático, AutoML y análisis estadístico sobre cualquier dataset.",
    docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("MV_CORS_ORIGINS", "*").split(","),
    allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
)

for r in (datasets.router, connectors.router, etl.router, automl.router,
          ai.router, exports.router, jobs.router, workspaces.router):
    app.include_router(r)


@app.middleware("http")
async def workspace_middleware(request: Request, call_next):
    """Activa el workspace del encabezado X-Workspace (o query ?workspace=).

    El query param existe porque EventSource y los links de descarga no pueden
    mandar encabezados. Un workspace inexistente cae al principal en las
    lecturas y devuelve 400 en el alta de datos.
    """
    name = (request.headers.get("x-workspace")
            or request.query_params.get("workspace") or W.DEFAULT)
    if not W.exists(name):
        name = W.DEFAULT
    token = W.activate(name)
    try:
        response = await call_next(request)
    finally:
        W.deactivate(token)
    response.headers["X-Workspace"] = W.normalize(name)
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Ningún error interno llega crudo al navegador."""
    log.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Error interno: {type(exc).__name__}: {str(exc)[:400]}",
                 "path": request.url.path},
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    from .core import automl as A

    return {
        "ok": True, "version": VERSION,
        "python": sys.version.split()[0], "platform": platform.platform(),
        "engines": {"lightgbm": A.HAS_LGB, "xgboost": A.HAS_XGB,
                    "catboost": A.HAS_CB, "optuna": A.HAS_OPTUNA},
        "paths": {"datasets": str(settings.dataset_dir), "models": str(settings.model_dir),
                  "exports": str(settings.export_dir)},
        "limits": {"chunk_rows": settings.chunk_rows,
                   "max_train_rows": settings.max_train_rows,
                   "upload_max_bytes": None},
    }


@app.get("/api/capabilities")
def capabilities() -> dict[str, Any]:
    from .core import ai as AI
    from .core import connectors as C
    from .core import storage as S

    return {
        "file_formats": sorted(S.SUPPORTED_EXT),
        "sql_engines": [{"id": k, "label": v["label"]} for k, v in C.ENGINES.items()],
        "ai_providers": [{"id": k, "label": v["label"]} for k, v in AI.PROVIDERS.items()],
        "tasks": ["binary", "multiclass", "regression"],
        "export_formats": ["xlsx", "csv", "parquet"],
        "languages": ["es", "en", "pt"],
    }


# ── interfaz estática ────────────────────────────────────────────────────────
if settings.frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=settings.frontend_dir / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(settings.frontend_dir / "index.html")

    @app.get("/{path:path}")
    def spa(path: str):
        """Sirve archivos de la interfaz; el resto cae en el index.

        Las rutas bajo /api que no existen NO caen acá: devolver el HTML de la
        interfaz ante un endpoint mal escrito esconde el error y el cliente
        termina intentando parsear una página como si fuera JSON.
        """
        if path.startswith("api/") or path == "api":
            return JSONResponse(status_code=404,
                                content={"detail": f"Endpoint inexistente: /{path}"})
        candidate = (settings.frontend_dir / path).resolve()
        if (str(candidate).startswith(str(settings.frontend_dir.resolve()))
                and candidate.is_file()):
            return FileResponse(candidate)
        return FileResponse(settings.frontend_dir / "index.html")


def main() -> None:
    import uvicorn

    host = os.environ.get("MV_HOST", "127.0.0.1")
    port = int(os.environ.get("MV_PORT", 8000))
    print(f"\n  MV AutoML Studio {VERSION}\n  http://{host}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
