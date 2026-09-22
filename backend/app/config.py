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


def _tope(env: str) -> int | None:
    """Un tope opcional: `None` cuando no hay ninguno.

    Vacío, `0` o algo que no es un número significan SIN TOPE. Lo último
    a propósito: un `MV_MAX_TRAIN_ROWS=todas` mal puesto tiene que dejar
    el producto sin límite, que es el default, y no tirar `ValueError` al
    importar la configuración — o sea, no arrancar.
    """
    crudo = os.environ.get(env, "").strip()
    if not crudo:
        return None
    try:
        n = int(crudo)
    except ValueError:
        return None
    return n if n > 0 else None


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = field(default_factory=_resolve_data_dir)
    upload_dir: Path = field(default_factory=lambda: _sub("MV_UPLOAD_DIR", "uploads"))
    dataset_dir: Path = field(default_factory=lambda: _sub("MV_DATASET_DIR", "datasets"))
    model_dir: Path = field(default_factory=lambda: _sub("MV_MODEL_DIR", "models"))
    export_dir: Path = field(default_factory=lambda: _sub("MV_EXPORT_DIR", "exports"))
    secrets_dir: Path = field(default_factory=lambda: _sub("MV_SECRETS_DIR", "secrets"))
    frontend_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("MV_FRONTEND_DIR", ROOT / "frontend")))

    # Ingesta: tamaño de bloque al convertir a Parquet. No hay límite de tamaño
    # total de archivo; el límite es el disco, no la RAM.
    chunk_rows: int = int(os.environ.get("MV_CHUNK_ROWS", 200_000))
    # Filas que se cargan en memoria para entrenar. **Sin tope por defecto**:
    # se entrena con el dataset entero. Antes eran 400.000 y el muestreo se
    # aplicaba solo, así que quien subía un millón de filas entrenaba sobre
    # el 40 % sin haberlo pedido — y las métricas que leía eran de ese 40 %.
    # Poner `MV_MAX_TRAIN_ROWS` a un número vuelve a acotar, para una máquina
    # donde el dataset entero no entra en RAM; `0` o vacío es sin tope.
    max_train_rows: int | None = _tope("MV_MAX_TRAIN_ROWS")
    # Filas que se cargan para el perfilado rápido en pantalla.
    preview_rows: int = int(os.environ.get("MV_PREVIEW_ROWS", 100))
    # Timeout de las llamadas a proveedores de IA (segundos).
    ai_timeout: float = float(os.environ.get("MV_AI_TIMEOUT", 45))


settings = Settings()
