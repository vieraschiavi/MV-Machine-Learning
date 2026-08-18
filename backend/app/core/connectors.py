"""Conexión a cualquier servidor SQL y extracción del dataset por streaming.

Motores soportados de fábrica: SQL Server, PostgreSQL, MySQL/MariaDB, SQLite
y DuckDB; además de una URL de SQLAlchemy libre para cualquier otro motor con
driver instalado (Oracle, Snowflake, BigQuery, Redshift, Databricks…).

La extracción usa cursor del lado del servidor y escribe a Parquet por
bloques: una tabla de 50 millones de filas no entra en RAM y no hace falta
que entre.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd

from ..config import settings
from . import storage as S

ENGINES: dict[str, dict[str, Any]] = {
    "sqlserver": {"label": "Microsoft SQL Server", "driver": "mssql+pymssql", "port": 1433,
                  "schema_query": "sys.tables"},
    "postgresql": {"label": "PostgreSQL", "driver": "postgresql+psycopg2", "port": 5432},
    "mysql": {"label": "MySQL / MariaDB", "driver": "mysql+pymysql", "port": 3306},
    "sqlite": {"label": "SQLite", "driver": "sqlite", "port": None},
    "duckdb": {"label": "DuckDB", "driver": "duckdb", "port": None},
    "custom": {"label": "URL de SQLAlchemy", "driver": None, "port": None},
}

DANGEROUS = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|merge|exec|execute|"
    r"sp_|xp_|into\s+outfile|backup|restore)\b", re.I)


class ConnectionError_(RuntimeError):
    """Error de conexión con mensaje pensado para el usuario final."""


# ───────────────────────────────────────────────────────────── perfiles ───────
def _profiles_file() -> Path:
    return settings.secrets_dir / "connections.json"


def _read_profiles() -> dict[str, dict]:
    f = _profiles_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_profiles(d: dict[str, dict]) -> None:
    f = _profiles_file()
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def public(p: dict) -> dict:
    """Perfil sin credenciales, apto para devolver al navegador."""
    out = {k: v for k, v in p.items() if k not in ("password", "url")}
    out["has_password"] = bool(p.get("password"))
    if p.get("url"):
        out["url_masked"] = re.sub(r"://[^@/]*@", "://•••@", str(p["url"]))
    return out


def save_profile(profile: dict[str, Any]) -> dict[str, Any]:
    profiles = _read_profiles()
    pid = profile.get("id") or f"conn_{uuid.uuid4().hex[:10]}"
    old = profiles.get(pid, {})
    if not profile.get("password") and old.get("password"):
        profile["password"] = old["password"]      # no se pisa al editar sin re-tipear
    profile["id"] = pid
    profile["updated_at"] = time.time()
    profiles[pid] = profile
    _write_profiles(profiles)
    return public(profile)


def list_profiles() -> list[dict[str, Any]]:
    return [public(p) for p in sorted(_read_profiles().values(),
                                      key=lambda p: -(p.get("updated_at") or 0))]


def get_profile(pid: str) -> dict[str, Any]:
    p = _read_profiles().get(pid)
    if not p:
        raise ConnectionError_(f"No existe la conexión guardada «{pid}».")
    return p


def delete_profile(pid: str) -> None:
    profiles = _read_profiles()
    profiles.pop(pid, None)
    _write_profiles(profiles)


# ────────────────────────────────────────────────────────────── motor ─────────
def build_url(p: dict[str, Any]) -> str:
    eng = p.get("engine", "postgresql")
    if eng == "custom" or p.get("url"):
        url = p.get("url")
        if not url:
            raise ConnectionError_("Falta la URL de conexión.")
        return url
    if eng not in ENGINES:
        raise ConnectionError_(f"Motor no soportado: {eng}")
    if eng in ("sqlite", "duckdb"):
        path = p.get("database") or ":memory:"
        return f"{'sqlite' if eng == 'sqlite' else 'duckdb'}:///{path}"
    spec = ENGINES[eng]
    host = p.get("host") or "localhost"
    port = int(p.get("port") or spec["port"])
    db = p.get("database") or ""
    user = quote_plus(str(p.get("username") or ""))
    pwd = quote_plus(str(p.get("password") or ""))
    auth = f"{user}:{pwd}@" if user else ""
    extra = ""
    if eng == "sqlserver":
        # pymssql no necesita ODBC: evita el clásico "driver not found" en Linux
        extra = "?charset=utf8" + (f"&tds_version={p['tds_version']}" if p.get("tds_version") else "")
    return f"{spec['driver']}://{auth}{host}:{port}/{db}{extra}"


def make_engine(p: dict[str, Any], timeout: int = 15):
    from sqlalchemy import create_engine

    url = build_url(p)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    eng = p.get("engine")
    if eng in ("postgresql", "mysql"):
        kwargs["connect_args"] = {"connect_timeout": timeout}
    elif eng == "sqlserver":
        kwargs["connect_args"] = {"timeout": timeout, "login_timeout": timeout}
    try:
        return create_engine(url, **kwargs)
    except Exception as exc:
        raise ConnectionError_(_friendly(exc)) from exc


def _friendly(exc: Exception) -> str:
    m = str(exc)
    low = m.lower()
    if "no module named" in low or "can't load plugin" in low:
        mod = re.search(r"no module named '?([\w\.]+)", low)
        return ("Falta el driver de Python para este motor"
                + (f" ({mod.group(1)})" if mod else "")
                + ". Instalalo con pip y volvé a probar.")
    if "timed out" in low or "timeout" in low:
        return "El servidor no respondió a tiempo. Revisá host, puerto y si hay firewall en el medio."
    if "authentication" in low or "login failed" in low or "password" in low:
        return "Credenciales rechazadas por el servidor: usuario o contraseña incorrectos."
    if "unknown database" in low or "does not exist" in low:
        return "La base indicada no existe en ese servidor."
    if "could not translate host" in low or "name or service not known" in low:
        return "No se pudo resolver el host. Verificá el nombre o usá la IP."
    return m.split("\n")[0][:300]


def test_connection(p: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import text

    t0 = time.time()
    engine = make_engine(p)
    try:
        with engine.connect() as con:
            version = None
            for q in ("SELECT version()", "SELECT @@VERSION", "SELECT sqlite_version()"):
                try:
                    version = str(con.execute(text(q)).scalar())
                    break
                except Exception:
                    continue
        return {"ok": True, "ms": int((time.time() - t0) * 1000),
                "engine": p.get("engine"), "version": (version or "").split("\n")[0][:200],
                "url": re.sub(r"://[^@/]*@", "://•••@", build_url(p))}
    except Exception as exc:
        return {"ok": False, "error": _friendly(exc), "ms": int((time.time() - t0) * 1000)}
    finally:
        engine.dispose()


# ─────────────────────────────────────────────────────────── metadatos ────────
def list_tables(p: dict[str, Any], schema: str | None = None) -> dict[str, Any]:
    from sqlalchemy import inspect

    engine = make_engine(p)
    try:
        insp = inspect(engine)
        schemas = []
        try:
            schemas = [s for s in insp.get_schema_names()
                       if s not in ("information_schema", "pg_catalog", "pg_toast", "sys")]
        except Exception:
            pass
        target = schema or (p.get("schema") or (schemas[0] if schemas else None))
        tables = [{"schema": target, "name": t, "type": "tabla"}
                  for t in insp.get_table_names(schema=target)]
        try:
            tables += [{"schema": target, "name": v, "type": "vista"}
                       for v in insp.get_view_names(schema=target)]
        except Exception:
            pass
        return {"schemas": schemas, "schema": target,
                "tables": sorted(tables, key=lambda t: t["name"])}
    except Exception as exc:
        raise ConnectionError_(_friendly(exc)) from exc
    finally:
        engine.dispose()


def describe_table(p: dict[str, Any], table: str, schema: str | None = None) -> dict[str, Any]:
    from sqlalchemy import inspect

    engine = make_engine(p)
    try:
        insp = inspect(engine)
        cols = [{"name": c["name"], "type": str(c["type"]), "nullable": bool(c.get("nullable", True))}
                for c in insp.get_columns(table, schema=schema)]
        return {"table": table, "schema": schema, "columns": cols}
    except Exception as exc:
        raise ConnectionError_(_friendly(exc)) from exc
    finally:
        engine.dispose()


def preview(p: dict[str, Any], sql: str, limit: int = 100) -> dict[str, Any]:
    from sqlalchemy import text

    guard(sql)
    engine = make_engine(p)
    try:
        with engine.connect() as con:
            df = pd.read_sql(text(_wrap_limit(sql, limit, p.get("engine"))), con)
        return {"columns": list(df.columns),
                "rows": json.loads(df.head(limit).to_json(orient="records", date_format="iso")),
                "n": int(len(df))}
    except Exception as exc:
        raise ConnectionError_(_friendly(exc)) from exc
    finally:
        engine.dispose()


def guard(sql: str) -> None:
    """El conector es de sólo lectura. Cualquier verbo que escriba se rechaza."""
    s = re.sub(r"--.*?$|/\*.*?\*/", " ", sql, flags=re.S | re.M)
    if DANGEROUS.search(s):
        raise ConnectionError_(
            "La consulta contiene una sentencia de escritura. El conector es de sólo lectura: "
            "usá SELECT (o una vista) para extraer los datos.")
    if s.count(";") > 1 or (";" in s.strip()[:-1]):
        raise ConnectionError_("Enviá una sola sentencia SELECT por consulta.")


def _wrap_limit(sql: str, limit: int, engine: str | None) -> str:
    s = sql.strip().rstrip(";")
    if re.search(r"\blimit\s+\d+|\btop\s+\d+|\bfetch\s+first\b", s, re.I):
        return s
    if engine == "sqlserver":
        return f"SELECT TOP {int(limit)} * FROM ({s}) AS _q"
    return f"SELECT * FROM ({s}) AS _q LIMIT {int(limit)}"


# ─────────────────────────────────────────────────────────── extracción ───────
def extract(p: dict[str, Any], sql: str, name: str,
            progress=lambda *_: None, max_rows: int | None = None) -> dict[str, Any]:
    """Trae el resultado de la consulta y lo materializa como dataset."""
    from sqlalchemy import text

    guard(sql)
    engine = make_engine(p, timeout=60)
    t0 = time.time()
    stats = {"rows": 0}

    def frames() -> Iterator[pd.DataFrame]:
        with engine.connect().execution_options(stream_results=True, max_row_buffer=settings.chunk_rows) as con:
            result = con.execute(text(sql.strip().rstrip(";")))
            cols = list(result.keys())
            while True:
                batch = result.fetchmany(settings.chunk_rows)
                if not batch:
                    break
                df = pd.DataFrame(batch, columns=cols)
                stats["rows"] += len(df)
                progress(min(95.0, stats["rows"] / max(max_rows or 1_000_000, 1) * 90),
                         f"{stats['rows']:,} filas extraídas")
                yield df
                if max_rows and stats["rows"] >= max_rows:
                    break

    try:
        meta = S.ingest_frames(
            frames(), name, source="sql",
            origin={"connection": p.get("id"), "engine": p.get("engine"),
                    "host": p.get("host"), "database": p.get("database"), "sql": sql})
        return {"dataset": meta.to_dict(), "seconds": round(time.time() - t0, 1)}
    except Exception as exc:
        raise ConnectionError_(_friendly(exc)) from exc
    finally:
        engine.dispose()
