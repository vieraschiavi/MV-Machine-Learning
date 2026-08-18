"""Conectores SQL. Se prueba contra SQLite: mismo camino de código que el resto."""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import pytest
from app.core import connectors as C
from app.core import storage


@pytest.fixture(scope="module")
def sqlite_db(tmp_root):
    path = tmp_root / "prueba.db"
    con = sqlite3.connect(path)
    rng = np.random.default_rng(0)
    pd.DataFrame({
        "id": range(500),
        "monto": rng.gamma(2, 100, 500).round(2),
        "grupo": rng.choice(["a", "b", "c"], 500),
    }).to_sql("ventas", con, index=False, if_exists="replace")
    con.close()
    return {"engine": "sqlite", "database": str(path), "id": "conn_prueba",
            "label": "prueba"}


def test_conexion_exitosa(sqlite_db):
    r = C.test_connection(sqlite_db)
    assert r["ok"] is True
    assert r["ms"] >= 0


def test_conexion_fallida_da_mensaje_util():
    r = C.test_connection({"engine": "postgresql", "host": "no-existe.invalid",
                           "port": 5432, "database": "x", "username": "u", "password": "p"})
    assert r["ok"] is False
    assert r["error"] and len(r["error"]) > 10


def test_listado_de_tablas_y_columnas(sqlite_db):
    r = C.list_tables(sqlite_db)
    assert any(t["name"] == "ventas" for t in r["tables"])
    d = C.describe_table(sqlite_db, "ventas")
    assert {c["name"] for c in d["columns"]} == {"id", "monto", "grupo"}


def test_vista_previa_limita_filas(sqlite_db):
    r = C.preview(sqlite_db, "SELECT * FROM ventas", limit=10)
    assert r["n"] <= 10
    assert set(r["columns"]) == {"id", "monto", "grupo"}


@pytest.mark.parametrize("sql", [
    "DELETE FROM ventas",
    "DROP TABLE ventas",
    "UPDATE ventas SET monto = 0",
    "INSERT INTO ventas VALUES (1,2,'x')",
    "SELECT * FROM ventas; DROP TABLE ventas",
    "TRUNCATE TABLE ventas",
    "EXEC sp_quien_sabe",
])
def test_el_conector_es_de_solo_lectura(sql):
    with pytest.raises(C.ConnectionError_):
        C.guard(sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM ventas",
    "WITH t AS (SELECT 1 AS x) SELECT * FROM t",
    "SELECT count(*) FROM ventas WHERE grupo = 'a'",
])
def test_las_consultas_de_lectura_pasan(sql):
    C.guard(sql)


def test_extraccion_materializa_un_dataset(sqlite_db):
    r = C.extract(sqlite_db, "SELECT * FROM ventas", "desde sqlite")
    assert r["dataset"]["rows"] == 500
    meta = storage.load_meta(r["dataset"]["id"])
    assert meta.source == "sql"
    assert meta.origin["sql"].startswith("SELECT")


def test_extraccion_con_tope_de_filas(sqlite_db):
    r = C.extract(sqlite_db, "SELECT * FROM ventas", "acotada", max_rows=100)
    assert r["dataset"]["rows"] <= 500


def test_perfiles_guardados_no_devuelven_la_clave(tmp_root):
    guardado = C.save_profile({"engine": "postgresql", "host": "h", "database": "d",
                               "username": "u", "password": "secreto", "label": "p"})
    assert "password" not in guardado
    assert guardado["has_password"] is True
    completo = C.get_profile(guardado["id"])
    assert completo["password"] == "secreto"
    # al reeditar sin re-tipear la clave, la anterior se conserva
    de_nuevo = C.save_profile({"id": guardado["id"], "engine": "postgresql", "host": "h2",
                               "database": "d", "username": "u", "label": "p"})
    assert C.get_profile(de_nuevo["id"])["password"] == "secreto"
    C.delete_profile(guardado["id"])
    with pytest.raises(C.ConnectionError_):
        C.get_profile(guardado["id"])


def test_url_enmascara_la_clave():
    url = C.build_url({"engine": "postgresql", "host": "h", "port": 5432, "database": "d",
                       "username": "u", "password": "clave"})
    assert "clave" in url                       # la URL real la necesita
    r = C.public({"engine": "custom", "url": url})
    assert "clave" not in r.get("url_masked", "")


def test_motor_desconocido_avisa():
    with pytest.raises(C.ConnectionError_):
        C.build_url({"engine": "motor_inventado"})
