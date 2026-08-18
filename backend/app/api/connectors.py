"""Endpoints de conexión a servidores SQL."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import connectors as C
from ..core import jobs
from ..core import licensing as L

router = APIRouter(prefix="/api/connections", tags=["connections"])


class Profile(BaseModel):
    id: str | None = None
    label: str | None = None
    engine: str = "postgresql"
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    schema_: str | None = None
    url: str | None = None
    tds_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        d["schema"] = d.pop("schema_", None)
        return {k: v for k, v in d.items() if v is not None}


@router.get("/engines")
def engines() -> dict[str, Any]:
    return {"engines": [{"id": k, **{kk: vv for kk, vv in v.items() if kk != "schema_query"}}
                        for k, v in C.ENGINES.items()]}


@router.get("")
def list_profiles() -> dict[str, Any]:
    return {"connections": C.list_profiles()}


@router.post("/test")
def test(p: Profile) -> dict[str, Any]:
    L.require("sql_connectors")
    prof = p.to_dict()
    if prof.get("id") and not prof.get("password"):
        try:
            prof = {**C.get_profile(prof["id"]), **prof}
        except C.ConnectionError_:
            pass
    return C.test_connection(prof)


@router.post("/save")
def save(p: Profile) -> dict[str, Any]:
    L.require("sql_connectors")
    return {"connection": C.save_profile(p.to_dict())}


@router.delete("/{profile_id}")
def delete(profile_id: str) -> dict[str, Any]:
    C.delete_profile(profile_id)
    return {"deleted": profile_id}


@router.get("/{profile_id}/tables")
def tables(profile_id: str, schema: str | None = None) -> dict[str, Any]:
    try:
        return C.list_tables(C.get_profile(profile_id), schema)
    except C.ConnectionError_ as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{profile_id}/tables/{table}")
def describe(profile_id: str, table: str, schema: str | None = None) -> dict[str, Any]:
    try:
        return C.describe_table(C.get_profile(profile_id), table, schema)
    except C.ConnectionError_ as exc:
        raise HTTPException(400, str(exc)) from exc


class QueryBody(BaseModel):
    sql: str
    limit: int = 100


@router.post("/{profile_id}/preview")
def preview(profile_id: str, body: QueryBody) -> dict[str, Any]:
    try:
        return C.preview(C.get_profile(profile_id), body.sql, body.limit)
    except C.ConnectionError_ as exc:
        raise HTTPException(400, str(exc)) from exc


class ExtractBody(BaseModel):
    sql: str
    name: str
    max_rows: int | None = None


@router.post("/{profile_id}/extract")
def extract(profile_id: str, body: ExtractBody) -> dict[str, Any]:
    try:
        profile = C.get_profile(profile_id)
    except C.ConnectionError_ as exc:
        raise HTTPException(404, str(exc)) from exc

    L.require("sql_connectors")

    def work(progress):
        return C.extract(profile, body.sql, body.name, progress, body.max_rows)

    return jobs.run("extract", f"Extracción SQL · {body.name}", work,
                    meta={"connection": profile_id})
