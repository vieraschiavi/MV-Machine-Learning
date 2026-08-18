"""Endpoints de workspaces: espacios de trabajo aislados."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import licensing as L
from ..core import workspace as W

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("")
def listing() -> dict[str, Any]:
    return {"workspaces": W.listing(), "active": W.current()}


class CreateBody(BaseModel):
    name: str


@router.post("")
def create(body: CreateBody) -> dict[str, Any]:
    L.check_count(len(W.listing()), "max_workspaces")
    try:
        return {"workspace": W.create(body.name)}
    except W.WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/{name}")
def delete(name: str) -> dict[str, Any]:
    try:
        W.delete(name)
    except W.WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"deleted": name}


@router.post("/rebuild")
def rebuild() -> dict[str, Any]:
    """Reconstruye el catálogo SQLite del workspace activo desde el disco."""
    return {"rebuilt": W.rebuild_from_disk(), "workspace": W.current()}


@router.get("/jobs-history")
def jobs_history(limit: int = 100) -> dict[str, Any]:
    """Historial durable de trabajos (sobrevive al reinicio del proceso)."""
    return {"jobs": W.job_history(limit), "workspace": W.current()}
