"""Configuración central de MV AutoML Studio.

Todas las rutas son relativas a la raíz del repositorio salvo que se
sobreescriban por variable de entorno, de modo que el proyecto sea portable
(Windows, Linux, contenedor) sin editar código.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _path(env: str, default: Path) -> Path:
    p = Path(os.environ.get(env, default))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = field(default_factory=lambda: _path("MV_DATA_DIR", ROOT / "data"))
    upload_dir: Path = field(default_factory=lambda: _path("MV_UPLOAD_DIR", ROOT / "data" / "uploads"))
    dataset_dir: Path = field(default_factory=lambda: _path("MV_DATASET_DIR", ROOT / "data" / "datasets"))
    model_dir: Path = field(default_factory=lambda: _path("MV_MODEL_DIR", ROOT / "data" / "models"))
    export_dir: Path = field(default_factory=lambda: _path("MV_EXPORT_DIR", ROOT / "data" / "exports"))
    secrets_dir: Path = field(default_factory=lambda: _path("MV_SECRETS_DIR", ROOT / "data" / "secrets"))
    frontend_dir: Path = ROOT / "frontend"

    # Ingesta: tamaño de bloque al convertir a Parquet. No hay límite de tamaño
    # total de archivo; el límite es el disco, no la RAM.
    chunk_rows: int = int(os.environ.get("MV_CHUNK_ROWS", 200_000))
    # Filas que se cargan en memoria para entrenar. Datasets mayores se muestrean.
    max_train_rows: int = int(os.environ.get("MV_MAX_TRAIN_ROWS", 400_000))
    # Filas para el perfilado rápido en pantalla.
    preview_rows: int = int(os.environ.get("MV_PREVIEW_ROWS", 100))
    # Timeout de las llamadas a proveedores de IA (segundos).
    ai_timeout: float = float(os.environ.get("MV_AI_TIMEOUT", 45))


settings = Settings()
