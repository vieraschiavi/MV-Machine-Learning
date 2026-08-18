"""Configuración central de MV AutoML Studio.

Todas las rutas derivan de ``MV_DATA_DIR`` (por omisión ``<repo>/data``): con
esa sola variable se relocaliza el workspace completo. Cada subdirectorio
admite además su override puntual (``MV_DATASET_DIR``…), que tiene prioridad.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _resolve_data_dir() -> Path:
    p = Path(os.environ.get("MV_DATA_DIR", ROOT / "data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _sub(env: str, sub: str) -> Path:
    """Override explícito si existe; si no, subdirectorio del data_dir."""
    p = Path(os.environ[env]) if os.environ.get(env) else _resolve_data_dir() / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = field(default_factory=_resolve_data_dir)
    upload_dir: Path = field(default_factory=lambda: _sub("MV_UPLOAD_DIR", "uploads"))
    dataset_dir: Path = field(default_factory=lambda: _sub("MV_DATASET_DIR", "datasets"))
    model_dir: Path = field(default_factory=lambda: _sub("MV_MODEL_DIR", "models"))
    export_dir: Path = field(default_factory=lambda: _sub("MV_EXPORT_DIR", "exports"))
    secrets_dir: Path = field(default_factory=lambda: _sub("MV_SECRETS_DIR", "secrets"))
    frontend_dir: Path = ROOT / "frontend"

    # Ingesta: tamaño de bloque al convertir a Parquet. No hay límite de tamaño
    # total de archivo; el límite es el disco, no la RAM.
    chunk_rows: int = int(os.environ.get("MV_CHUNK_ROWS", 200_000))
    # Filas que se cargan en memoria para entrenar. Datasets mayores se muestrean.
    max_train_rows: int = int(os.environ.get("MV_MAX_TRAIN_ROWS", 400_000))
    # Filas que se cargan para el perfilado rápido en pantalla.
    preview_rows: int = int(os.environ.get("MV_PREVIEW_ROWS", 100))
    # Timeout de las llamadas a proveedores de IA (segundos).
    ai_timeout: float = float(os.environ.get("MV_AI_TIMEOUT", 45))


settings = Settings()
