"""Endpoints del motor de ETL: proponer, revisar y ejecutar el plan."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import etl as E
from ..core import jobs, storage

router = APIRouter(prefix="/api/etl", tags=["etl"])


class ProposeBody(BaseModel):
    dataset_id: str
    target: str | None = None
    options: dict[str, Any] | None = None


@router.post("/propose")
def propose(body: ProposeBody) -> dict[str, Any]:
    try:
        return E.propose(body.dataset_id, body.target, body.options)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"No se pudo analizar el dataset: {exc}") from exc


class CompileBody(BaseModel):
    dataset_id: str
    plan: dict[str, Any]


@router.post("/compile")
def compile_sql(body: CompileBody) -> dict[str, Any]:
    return {"sql": E.compile_sql(body.dataset_id, body.plan)}


class ExecuteBody(BaseModel):
    dataset_id: str
    plan: dict[str, Any]
    name: str | None = None


@router.post("/execute")
def execute(body: ExecuteBody) -> dict[str, Any]:
    def work(progress):
        progress(10, "Compilando el plan a SQL")
        r = E.execute(body.dataset_id, body.plan, body.name)
        progress(95, f"{r['rows_out']:,} filas escritas")
        return r

    return jobs.run("etl", "Ejecución del ETL", work,
                    meta={"dataset_id": body.dataset_id})


class LeakageBody(BaseModel):
    dataset_id: str
    target: str
    threshold: float = 0.98


@router.post("/leakage")
def leakage(body: LeakageBody) -> dict[str, Any]:
    return {"findings": E.audit_leakage(body.dataset_id, body.target, body.threshold)}
