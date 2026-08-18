"""Endpoints de seguimiento de trabajos en segundo plano."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..core import jobs as J

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def listing(limit: int = 50) -> dict[str, Any]:
    return {"jobs": J.listing(limit)}


@router.get("/{job_id}")
def get(job_id: str) -> dict[str, Any]:
    job = J.public(job_id)
    if not job:
        raise HTTPException(404, "Trabajo inexistente.")
    return job


@router.post("/{job_id}/cancel")
def cancel(job_id: str) -> dict[str, Any]:
    return {"cancelled": J.cancel(job_id)}


@router.get("/{job_id}/stream")
async def stream(job_id: str):
    """Progreso en vivo por server-sent events."""
    if J.public(job_id) is None:
        raise HTTPException(404, "Trabajo inexistente.")

    async def gen():
        last = -1
        idle = 0
        while True:
            job = J.public(job_id)
            if job is None:
                break
            if job["version"] != last:
                last = job["version"]
                idle = 0
                payload = {k: v for k, v in job.items() if k != "result"}
                if job["status"] in ("terminado", "error", "cancelado"):
                    payload["result"] = job.get("result")
                yield f"data: {json.dumps(payload, default=str)}\n\n"
                if job["status"] in ("terminado", "error", "cancelado"):
                    break
            else:
                idle += 1
                if idle % 40 == 0:
                    yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})
