"""Workspaces aislados con catálogo SQLite.

Cada workspace es un espacio de trabajo independiente: sus datasets, modelos,
exportaciones y conexiones no se mezclan con los de otro. El workspace
«principal» conserva el layout histórico (``data/datasets``, ``data/models``…)
para no romper instalaciones existentes; los demás viven bajo
``data/workspaces/<nombre>/``.

Cada workspace lleva además un **catálogo SQLite** (``catalog.db``) que indexa
datasets y modelos y persiste el historial de trabajos. Los artefactos siguen
en el filesystem (Parquet, joblib, JSON): SQLite es el índice durable y
consultable, no el almacén. Si el catálogo se pierde, se reconstruye solo a
partir del disco.

El workspace activo viaja por request (encabezado ``X-Workspace``) y se
propaga con una *context variable*, así los hilos de trabajos largos heredan
el workspace desde el que se lanzaron.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from ..config import settings

DEFAULT = "principal"
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,39}$")

_current: ContextVar[str] = ContextVar("mv_workspace", default=DEFAULT)


class WorkspaceError(RuntimeError):
    """Error de workspace con mensaje para el usuario final."""


def normalize(name: str | None) -> str:
    name = (name or DEFAULT).strip().lower()
    if not SAFE_NAME.match(name):
        raise WorkspaceError(
            f"Nombre de workspace inválido: {name!r}. Usá minúsculas, números, guion y "
            "guion bajo (máximo 40 caracteres).")
    return name


def current() -> str:
    return _current.get()


def activate(name: str | None):
    """Activa un workspace para el contexto actual; devuelve el token de reset."""
    return _current.set(normalize(name))


def deactivate(token) -> None:
    _current.reset(token)


# ─────────────────────────────────────────────────────────────── rutas ────────
def root(name: str | None = None) -> Path:
    ws = normalize(name or current())
    if ws == DEFAULT:
        return settings.data_dir
    p = settings.data_dir / "workspaces" / ws
    p.mkdir(parents=True, exist_ok=True)
    return p


def dir_for(kind: str, name: str | None = None) -> Path:
    """Directorio de un tipo de artefacto en el workspace activo.

    El «principal» respeta los overrides por variable de entorno
    (``MV_DATASET_DIR``…); los demás son subdirectorios de su raíz.
    """
    ws = normalize(name or current())
    if ws == DEFAULT:
        legacy = {"datasets": settings.dataset_dir, "models": settings.model_dir,
                  "exports": settings.export_dir, "secrets": settings.secrets_dir,
                  "uploads": settings.upload_dir}
        p = legacy[kind]
    else:
        p = root(ws) / kind
    p.mkdir(parents=True, exist_ok=True)
    return p


# ─────────────────────────────────────────────────────── administración ───────
def listing() -> list[dict[str, Any]]:
    out = [_describe(DEFAULT)]
    base = settings.data_dir / "workspaces"
    if base.exists():
        for p in sorted(base.iterdir()):
            if p.is_dir() and SAFE_NAME.match(p.name):
                out.append(_describe(p.name))
    return out


def _describe(name: str) -> dict[str, Any]:
    n_ds = len(list(dir_for("datasets", name).glob("ds_*")))
    n_md = len(list(dir_for("models", name).glob("mdl_*")))
    return {"name": name, "is_default": name == DEFAULT,
            "datasets": n_ds, "models": n_md}


def create(name: str) -> dict[str, Any]:
    ws = normalize(name)
    if ws == DEFAULT:
        raise WorkspaceError("«principal» ya existe.")
    p = settings.data_dir / "workspaces" / ws
    if p.exists():
        raise WorkspaceError(f"El workspace «{ws}» ya existe.")
    for kind in ("datasets", "models", "exports", "secrets", "uploads"):
        (p / kind).mkdir(parents=True, exist_ok=True)
    _connect(ws).close()
    return _describe(ws)


def delete(name: str) -> None:
    ws = normalize(name)
    if ws == DEFAULT:
        raise WorkspaceError("El workspace «principal» no se puede eliminar.")
    shutil.rmtree(settings.data_dir / "workspaces" / ws, ignore_errors=True)


def exists(name: str) -> bool:
    try:
        ws = normalize(name)
    except WorkspaceError:
        return False
    return ws == DEFAULT or (settings.data_dir / "workspaces" / ws).is_dir()


# ─────────────────────────────────────────────────── catálogo SQLite ──────────
_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, source TEXT, rows INTEGER,
    n_columns INTEGER, size_bytes INTEGER, parent_id TEXT,
    created_at REAL, meta_json TEXT
);
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, dataset_id TEXT, target TEXT,
    task TEXT, metric TEXT, score REAL, model TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, kind TEXT, title TEXT, status TEXT,
    created_at REAL, finished_at REAL, seconds REAL, error TEXT
);
CREATE INDEX IF NOT EXISTS ix_datasets_created ON datasets (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_models_created ON models (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_jobs_created ON jobs (created_at DESC);
"""


def _db_path(name: str | None = None) -> Path:
    return root(name) / "catalog.db"


def _connect(name: str | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(_db_path(name), timeout=15)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=15000")
    con.executescript(_SCHEMA)
    return con


@contextmanager
def _catalogo(name: str | None = None):
    """Abre el catálogo, confirma y lo **cierra**.

    `with sqlite3.connect(...)` confirma la transacción pero deja la conexión
    viva hasta que pase el recolector. En Windows eso mantiene tomado el
    archivo: el usuario no puede borrar ni mover su propio workspace, y en un
    proceso largo se acumulan conexiones abiertas.
    """
    con = _connect(name)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def record_dataset(meta: dict[str, Any]) -> None:
    """Alta o actualización de un dataset en el catálogo. Nunca rompe el flujo."""
    try:
        with _catalogo() as con:
            con.execute(
                "INSERT OR REPLACE INTO datasets VALUES (?,?,?,?,?,?,?,?,?)",
                (meta["id"], meta["name"], meta.get("source"), meta.get("rows"),
                 meta.get("n_columns") or len(meta.get("columns") or []),
                 meta.get("size_bytes"), meta.get("parent_id"),
                 meta.get("created_at") or time.time(),
                 json.dumps(meta, ensure_ascii=False, default=str)))
    except sqlite3.Error:
        pass


def forget_dataset(ds_id: str) -> None:
    try:
        with _catalogo() as con:
            con.execute("DELETE FROM datasets WHERE id = ?", (ds_id,))
    except sqlite3.Error:
        pass


def record_model(card: dict[str, Any]) -> None:
    try:
        with _catalogo() as con:
            con.execute(
                "INSERT OR REPLACE INTO models VALUES (?,?,?,?,?,?,?,?,?)",
                (card["id"], card["name"], card.get("dataset_id"), card.get("target"),
                 card.get("task"), card.get("metric"),
                 float(card["score"]) if card.get("score") is not None else None,
                 card.get("model"), card.get("created_at") or time.time()))
    except sqlite3.Error:
        pass


def forget_model(model_id: str) -> None:
    try:
        with _catalogo() as con:
            con.execute("DELETE FROM models WHERE id = ?", (model_id,))
    except sqlite3.Error:
        pass


def record_job(job: dict[str, Any]) -> None:
    """Historial durable de trabajos: sobrevive al reinicio del proceso."""
    try:
        err = job.get("error")
        with _connect(job.get("workspace")) as con:
            con.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?)",
                (job["id"], job.get("kind"), job.get("title"), job.get("status"),
                 job.get("created_at"), job.get("finished_at"),
                 round((job.get("finished_at") or 0) - (job.get("started_at") or 0), 2)
                 if job.get("finished_at") and job.get("started_at") else None,
                 (err or {}).get("message") if isinstance(err, dict) else err))
    except sqlite3.Error:
        pass


def job_history(limit: int = 100) -> list[dict[str, Any]]:
    try:
        with _catalogo() as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


def catalog_datasets() -> list[dict[str, Any]] | None:
    """Listado desde SQLite; None si el catálogo no está disponible."""
    try:
        with _catalogo() as con:
            rows = con.execute(
                "SELECT meta_json FROM datasets ORDER BY created_at DESC").fetchall()
            return [json.loads(r[0]) for r in rows]
    except (sqlite3.Error, json.JSONDecodeError):
        return None


def rebuild_from_disk() -> dict[str, int]:
    """Reconstruye el catálogo del workspace activo a partir del filesystem."""

    n_ds = n_md = 0
    for folder in dir_for("datasets").glob("ds_*"):
        f = folder / "meta.json"
        if f.exists():
            try:
                record_dataset(json.loads(f.read_text(encoding="utf-8")))
                n_ds += 1
            except Exception:
                continue
    for folder in dir_for("models").glob("mdl_*"):
        f = folder / "card.json"
        if f.exists():
            try:
                card = json.loads(f.read_text(encoding="utf-8"))
                card.pop("report", None)
                record_model(card)
                n_md += 1
            except Exception:
                continue
    return {"datasets": n_ds, "models": n_md}
