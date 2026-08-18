"""Ejecutor de trabajos en segundo plano con progreso observable.

Un entrenamiento o una extracción de 40 millones de filas no puede correr
dentro del ciclo de una petición HTTP. Cada tarea larga se lanza como job:
la UI recibe un identificador y sigue el avance por *server-sent events*.
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from collections import deque
from collections.abc import Callable
from typing import Any

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
MAX_JOBS = 200


def _new_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


def create(kind: str, title: str, meta: dict | None = None) -> dict[str, Any]:
    jid = _new_id()
    job = {
        "id": jid, "kind": kind, "title": title, "meta": meta or {},
        "status": "pendiente", "progress": 0.0, "message": "En cola",
        "log": deque(maxlen=400), "result": None, "error": None,
        "created_at": time.time(), "started_at": None, "finished_at": None,
        "version": 0,
    }
    with _LOCK:
        _JOBS[jid] = job
        if len(_JOBS) > MAX_JOBS:
            for old in sorted(_JOBS.values(), key=lambda j: j["created_at"])[:len(_JOBS) - MAX_JOBS]:
                if old["status"] in ("terminado", "error", "cancelado"):
                    _JOBS.pop(old["id"], None)
    return job


def update(jid: str, *, progress: float | None = None, message: str | None = None,
           status: str | None = None) -> None:
    with _LOCK:
        job = _JOBS.get(jid)
        if not job:
            return
        if progress is not None:
            job["progress"] = max(job["progress"], round(float(progress), 2)) if progress > 0 else job["progress"]
        if message:
            job["message"] = message
            job["log"].append({"t": time.time(), "text": message})
        if status:
            job["status"] = status
        job["version"] += 1


def run(kind: str, title: str, fn: Callable[[Callable[[float, str], None]], Any],
        meta: dict | None = None) -> dict[str, Any]:
    """Lanza `fn(progress)` en un hilo y devuelve la ficha del job."""
    job = create(kind, title, meta)
    jid = job["id"]

    def progress(pct: float, msg: str) -> None:
        update(jid, progress=pct, message=msg)

    def target() -> None:
        with _LOCK:
            _JOBS[jid]["status"] = "corriendo"
            _JOBS[jid]["started_at"] = time.time()
        update(jid, progress=1, message="Iniciando")
        try:
            result = fn(progress)
            with _LOCK:
                j = _JOBS[jid]
                j["result"] = result
                j["status"] = "terminado"
                j["progress"] = 100.0
                j["message"] = "Completado"
                j["finished_at"] = time.time()
                j["version"] += 1
        except Exception as exc:
            with _LOCK:
                j = _JOBS[jid]
                j["status"] = "error"
                j["error"] = {"message": str(exc)[:800],
                              "type": type(exc).__name__,
                              "trace": traceback.format_exc()[-3000:]}
                j["message"] = f"Error: {str(exc)[:200]}"
                j["finished_at"] = time.time()
                j["version"] += 1

    threading.Thread(target=target, daemon=True, name=f"job-{kind}").start()
    return public(jid)


def public(jid: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(jid)
        if not job:
            return None
        return {k: (list(v) if isinstance(v, deque) else v)
                for k, v in job.items()}


def listing(limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        jobs = sorted(_JOBS.values(), key=lambda j: -j["created_at"])[:limit]
        return [{k: v for k, v in j.items() if k not in ("log", "result")} for j in jobs]


def cancel(jid: str) -> bool:
    """Marca el job como cancelado (los hilos de cómputo no se interrumpen a la fuerza)."""
    with _LOCK:
        job = _JOBS.get(jid)
        if not job or job["status"] in ("terminado", "error"):
            return False
        job["status"] = "cancelado"
        job["message"] = "Cancelado por el usuario"
        job["finished_at"] = time.time()
        job["version"] += 1
        return True
