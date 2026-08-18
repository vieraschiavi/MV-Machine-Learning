"""Endpoints de licencia: estado, activación y emisión (sólo owner)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import licensing as L

router = APIRouter(prefix="/api/license", tags=["license"])


@router.get("/status")
def status() -> dict[str, Any]:
    """Nivel vigente y sus topes. Nunca devuelve el token de la licencia."""
    return L.status()


@router.get("/tiers")
def tiers() -> dict[str, Any]:
    """Comparativa de niveles, para la pantalla de planes."""
    from dataclasses import asdict

    return {"tiers": [asdict(t) for t in L.TIERS.values()]}


class ActivateBody(BaseModel):
    token: str
    persist: bool = True


@router.post("/activate")
def activate(body: ActivateBody) -> dict[str, Any]:
    try:
        lic = L.activate(body.token, body.persist)
    except L.LicenseError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"activated": True, "tier": lic.tier, "status": L.status()}


@router.post("/deactivate")
def deactivate() -> dict[str, Any]:
    L.deactivate()
    return {"activated": False, "status": L.status()}


class IssueBody(BaseModel):
    tier: str
    licensee: str
    days: int | None = None
    notes: str = ""
    private_key: str | None = None


@router.post("/issue")
def issue(body: IssueBody) -> dict[str, Any]:
    """Emite una licencia. Requiere nivel owner y la clave privada de firma."""
    L.require("diagnostics")          # sólo el nivel owner llega acá
    try:
        token = L.issue(body.tier, body.licensee, body.days,
                        body.private_key, body.notes)
    except L.LicenseError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"token": token, "tier": body.tier, "licensee": body.licensee}
