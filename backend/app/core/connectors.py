"""Conexión a cualquier servidor SQL y extracción del dataset por streaming.

Motores soportados de fábrica: Microsoft Fabric, SQL Server, PostgreSQL,
MySQL/MariaDB, SQLite y DuckDB; además de una URL de SQLAlchemy libre para
cualquier otro motor con driver instalado (Oracle, Snowflake, BigQuery,
Redshift, Databricks…).

Fabric es el caso distinto: no acepta usuario y contraseña de base de datos, la
identidad la da Entra ID. Ver ``_url_fabric`` y ``docs/FABRIC_Y_POWERBI.md``.

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
from urllib.parse import quote_plus, urlencode

import pandas as pd

from ..config import settings  # noqa: F401
from . import conector_aas as AASC
from . import storage as S
from . import workspace

# Motores que hablan el dialecto de SQL Server: recortan con TOP, no con LIMIT.
DIALECTO_SQLSERVER = ("sqlserver", "fabric")

# Driver ODBC por omisión para Fabric. Es el que instala Microsoft en Windows;
# se puede cambiar por perfil si el equipo tiene otra versión.
ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

ENGINES: dict[str, dict[str, Any]] = {
    "sqlserver": {"label": "Microsoft SQL Server", "driver": "mssql+pymssql", "port": 1433,
                  "schema_query": "sys.tables"},
    "fabric": {"label": "Microsoft Fabric (endpoint SQL)", "driver": "mssql+pyodbc", "port": 1433,
               "schema_query": "sys.tables"},
    "postgresql": {"label": "PostgreSQL", "driver": "postgresql+psycopg2", "port": 5432},
    "mysql": {"label": "MySQL / MariaDB", "driver": "mysql+pymysql", "port": 3306},
    "sqlite": {"label": "SQLite", "driver": "sqlite", "port": None},
    "duckdb": {"label": "DuckDB", "driver": "duckdb", "port": None},
    "aas": {"label": "Azure Analysis Services / Power BI (MDW)", "driver": None, "port": None},
    "custom": {"label": "URL de SQLAlchemy", "driver": None, "port": None},
}
# Analysis Services no es SQL: va por DAX con el conector de la suite (``conector_aas``).
AAS = "aas"

# Lista blanca: la consulta tiene que SER una lectura. Es lo único que no
# depende de acordarse de todos los verbos que escriben —«VACUUM INTO» copió
# una base entera justamente porque no estaba en ninguna lista negra—.
SOLO_LECTURA = re.compile(r"^(select|with)\b", re.I)

# Segunda barrera, para lo que empieza con SELECT o WITH y aun así escribe:
# el `WITH x AS (DELETE … RETURNING *)` de PostgreSQL, o el `SELECT … INTO
# tabla` de SQL Server.
DANGEROUS = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|grant|revoke|merge|exec|execute|"
    r"sp_|xp_|into|backup|restore|attach|vacuum|pragma|copy|load_extension)\b", re.I)


class ConnectionError_(RuntimeError):
    """Error de conexión con mensaje pensado para el usuario final."""


# ───────────────────────────────────────────────────────────── perfiles ───────
def _profiles_file() -> Path:
    return workspace.dir_for("secrets") / "connections.json"


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
    if eng == AAS:
        raise ConnectionError_("Analysis Services no es una base SQL: se lee con DAX (EVALUATE), no por URL.")
    if eng in ("sqlite", "duckdb"):
        path = p.get("database") or ":memory:"
        return f"{'sqlite' if eng == 'sqlite' else 'duckdb'}:///{path}"
    if eng == "fabric":
        return _url_fabric(p)
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


def _url_fabric(p: dict[str, Any]) -> str:
    """URL del endpoint SQL de Fabric, que se autentica contra Entra ID.

    Fabric no acepta usuario y contraseña de base de datos: la identidad la da
    Entra ID (el ex Azure AD). Dos caminos, y el perfil elige solo:

    * **Aplicación registrada** (usuario = ID de aplicación, contraseña =
      secreto): es el modo desatendido, el que sirve para un entrenamiento
      programado.
    * **Inicio interactivo** (usuario = el correo de la persona, sin
      contraseña): abre la ventana de Microsoft y soporta doble factor. Es el
      modo para el equipo de escritorio.
    """
    host = (p.get("host") or "").strip()
    if not host:
        raise ConnectionError_(
            "Falta el endpoint SQL de Fabric. Está en el Lakehouse o el Warehouse, "
            "en «Configuración → Cadena de conexión del endpoint de análisis SQL».")
    db = (p.get("database") or "").strip()
    if not db:
        raise ConnectionError_("Falta el nombre del Lakehouse o Warehouse en Fabric.")
    user = str(p.get("username") or "").strip()
    if not user:
        raise ConnectionError_(
            "Falta la identidad de Entra ID: poné el ID de aplicación (con su secreto) "
            "o tu correo de la organización para entrar de forma interactiva.")
    pwd = str(p.get("password") or "")
    modo = "ActiveDirectoryServicePrincipal" if pwd else "ActiveDirectoryInteractive"
    auth = f"{quote_plus(user)}:{quote_plus(pwd)}@" if pwd else f"{quote_plus(user)}@"
    query = urlencode({
        "driver": p.get("odbc_driver") or ODBC_DRIVER,
        "Authentication": modo,
        "Encrypt": "yes",
        "TrustServerCertificate": "no",
    })
    port = int(p.get("port") or ENGINES["fabric"]["port"])
    return f"mssql+pyodbc://{auth}{host}:{port}/{db}?{query}"


def make_engine(p: dict[str, Any], timeout: int = 15):
    from sqlalchemy import create_engine

    url = build_url(p)
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    eng = p.get("engine")
    if eng in ("postgresql", "mysql"):
        kwargs["connect_args"] = {"connect_timeout": timeout}
    elif eng == "sqlserver":
        kwargs["connect_args"] = {"timeout": timeout, "login_timeout": timeout}
    elif eng == "fabric":
        # El inicio interactivo abre una ventana del navegador: si el timeout es
        # el de una conexión normal, corta antes de que la persona alcance a
        # escribir el segundo factor.
        kwargs["connect_args"] = {"timeout": max(timeout, 120)}
    try:
        return create_engine(url, **kwargs)
    except Exception as exc:
        raise ConnectionError_(_friendly(exc)) from exc


def _friendly(exc: Exception) -> str:
    m = str(exc)
    low = m.lower()
    if "libodbc" in low or ("odbc" in low and ("driver manager" in low
                                               or "data source name" in low
                                               or "not found" in low)):
        return ("Falta el driver ODBC de Microsoft para SQL Server / Fabric. "
                "Instalá «ODBC Driver 18 for SQL Server» desde el sitio de Microsoft "
                "(en Linux, además, el administrador unixODBC) y volvé a probar.")
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

    if p.get("engine") == AAS:
        return AASC.test_connection(p)

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

    if p.get("engine") == AAS:
        try:
            return AASC.list_tables(p, schema)
        except AASC.ErrorAAS as exc:
            raise ConnectionError_(str(exc)) from exc

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

    if p.get("engine") == AAS:
        try:
            df = AASC.leer(p, AASC.consulta_de_tabla(table), 1, schema)
        except AASC.ErrorAAS as exc:
            raise ConnectionError_(str(exc)) from exc
        return {"table": table, "schema": schema,
                "columns": [{"name": str(c), "type": str(t), "nullable": True} for c, t in df.dtypes.items()]}

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


def _filas(df: pd.DataFrame, limit: int) -> dict[str, Any]:
    return {"columns": [str(c) for c in df.columns],
            "rows": json.loads(df.head(limit).to_json(orient="records", date_format="iso")),
            "n": int(len(df))}


def preview(p: dict[str, Any], sql: str, limit: int = 100, schema: str | None = None) -> dict[str, Any]:
    from sqlalchemy import text

    if p.get("engine") == AAS:
        try:
            return _filas(AASC.leer(p, sql, limit, schema), limit)
        except AASC.ErrorAAS as exc:
            raise ConnectionError_(str(exc)) from exc
    guard(sql)
    engine = make_engine(p)
    try:
        with engine.connect() as con:
            df = pd.read_sql(text(_wrap_limit(sql, limit, p.get("engine"))), con)
        return _filas(df, limit)
    except Exception as exc:
        raise ConnectionError_(_friendly(exc)) from exc
    finally:
        engine.dispose()


def _sin_ruido(sql: str) -> str:
    """La consulta sin comentarios y sin literales de texto.

    Los literales se sacan porque el control mira palabras: sin esto,
    ``WHERE nota LIKE '%delete%'`` se rechazaba como si borrara algo, y
    ``VACUUM INTO '/ruta'`` se escondía detrás de su propia ruta.
    """
    s = re.sub(r"--.*?$|/\*.*?\*/", " ", sql, flags=re.S | re.M)
    s = re.sub(r"'(?:''|[^'])*'", "''", s)
    return s.strip()


def guard(sql: str) -> None:
    """El conector es de sólo lectura, y eso se decide por lista blanca.

    La base del otro lado suele ser la de producción de un cliente. Enumerar
    los verbos que escriben no alcanza —``VACUUM INTO`` copió una base entera a
    un archivo, ``ATTACH DATABASE`` creó otro, y ninguno de los dos figuraba en
    ninguna lista—: se exige que la consulta sea una lectura, y recién después
    se mira si esconde una escritura adentro.
    """
    s = _sin_ruido(sql)
    if not s:
        raise ConnectionError_("La consulta está vacía.")
    if not SOLO_LECTURA.match(s):
        verbo = re.match(r"[A-Za-z_]+", s)
        raise ConnectionError_(
            f"El conector es de sólo lectura y «{verbo.group(0) if verbo else s[:20]}» no es una "
            "consulta de lectura. Empezá con SELECT, o con un WITH que termine en SELECT.")
    if DANGEROUS.search(s):
        raise ConnectionError_(
            "La consulta contiene una sentencia de escritura. El conector es de sólo lectura: "
            "usá SELECT (o una vista) para extraer los datos.")
    if s.count(";") > 1 or (";" in s[:-1]):
        raise ConnectionError_("Enviá una sola sentencia SELECT por consulta.")


def _wrap_limit(sql: str, limit: int, engine: str | None) -> str:
    s = sql.strip().rstrip(";")
    if re.search(r"\blimit\s+\d+|\btop\s+\d+|\bfetch\s+first\b", s, re.I):
        return s
    if engine in DIALECTO_SQLSERVER:
        return f"SELECT TOP {int(limit)} * FROM ({s}) AS _q"
    return f"SELECT * FROM ({s}) AS _q LIMIT {int(limit)}"


# ─────────────────────────────────────────────────────────── extracción ───────
def _extract_aas(p: dict[str, Any], consulta: str, name: str, progress, max_rows: int | None,
                 schema: str | None) -> dict[str, Any]:
    """Analysis Services devuelve el resultado entero (ADOMD no tiene cursor): se ingesta por bloques igual."""
    t0 = time.time()
    progress(5.0, "Consultando Analysis Services…")
    try:
        df = AASC.leer(p, consulta, max_rows, schema)
    except AASC.ErrorAAS as exc:
        raise ConnectionError_(str(exc)) from exc
    progress(60.0, f"{len(df):,} filas leídas")
    paso = max(int(settings.chunk_rows), 1)
    bloques = (df.iloc[i:i + paso] for i in range(0, max(len(df), 1), paso))
    meta = S.ingest_frames(
        bloques, name, source="aas",
        origin={"connection": p.get("id"), "engine": AAS, "host": p.get("host"),
                "database": schema or p.get("database"), "sql": consulta})
    return {"dataset": meta.to_dict(), "seconds": round(time.time() - t0, 1)}


def extract(p: dict[str, Any], sql: str, name: str,
            progress=lambda *_: None, max_rows: int | None = None,
            schema: str | None = None) -> dict[str, Any]:
    """Trae el resultado de la consulta y lo materializa como dataset."""
    from sqlalchemy import text

    if p.get("engine") == AAS:
        return _extract_aas(p, sql, name, progress, max_rows, schema)
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


def consulta_de_tabla(p: dict[str, Any], table: str, schema: str | None = None) -> str:
    """La consulta que trae una tabla entera, con los nombres citados como los escribe ese motor."""
    if p.get("engine") == AAS:
        return AASC.consulta_de_tabla(table)
    engine = make_engine(p)
    try:
        q = engine.dialect.identifier_preparer
        return f"SELECT * FROM {q.quote_schema(schema) + '.' if schema else ''}{q.quote(table)}"
    finally:
        engine.dispose()


def extract_many(p: dict[str, Any], tables: list[dict[str, Any]], progress=lambda *_: None,
                 max_rows: int | None = None) -> dict[str, Any]:
    """Varias tablas de una vez: un dataset por tabla. Una que falla no tira las demás; se informa."""
    if not tables:
        raise ConnectionError_("Elegí al menos una tabla.")
    hechos, errores = [], []
    t0 = time.time()
    for i, tb in enumerate(tables):
        nombre, schema = str(tb.get("name") or ""), tb.get("schema") or None
        base = 100.0 * i / len(tables)
        tramo = 100.0 / len(tables)

        def avance(pct, msg, _base=base, _tramo=tramo, _n=nombre):
            progress(min(99.0, _base + _tramo * float(pct) / 100.0), f"{_n}: {msg}")

        try:
            out = extract(p, consulta_de_tabla(p, nombre, schema), nombre, avance, max_rows, schema)
            hechos.append(out["dataset"])
        except Exception as exc:        # una tabla sin permiso no frena las otras
            errores.append({"table": nombre, "error": str(exc)[:300]})
    if not hechos:
        raise ConnectionError_("No se pudo extraer ninguna tabla: "
                               + "; ".join(f"{e['table']}: {e['error']}" for e in errores))
    return {"datasets": hechos, "errors": errores, "seconds": round(time.time() - t0, 1)}
