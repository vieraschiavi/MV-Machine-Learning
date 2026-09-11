"""«Sólo lectura» tiene que significar sólo lectura, contra la base del cliente.

El conector se conecta a la base de producción de otra empresa. Si desde el
programa se puede escribir ahí, no importa cuánto valga el resto: es el tipo de
incidente que termina un contrato.

El control era una **lista negra de verbos** (`insert|update|delete|drop…`).
Una lista negra falla por lo que no enumera, y esto se verificó ejecutando
contra una base SQLite real, por el camino de extracción del programa:

    VACUUM INTO '/tmp/copia-robada.db'

pasó el control, se ejecutó, y dejó en disco una **copia completa de la base**
—verificado abriéndola: las dos facturas del cliente adentro—. `ATTACH
DATABASE` también pasó y creó su archivo. `REPLACE INTO` pasó el control y sólo
no persistió porque la transacción se revirtió sola.

El arreglo no agrega verbos a la lista negra —siempre va a faltar uno—: exige
que la consulta SEA una lectura. Una sola sentencia que empiece en `SELECT` o
en un `WITH` que termine en `SELECT`. La lista negra queda como segunda
barrera, para el `WITH x AS (DELETE … RETURNING *)` de PostgreSQL.
"""
from __future__ import annotations

import sqlite3

import pytest
from app.core import connectors as C


@pytest.fixture
def base_del_cliente(tmp_path):
    """Una base con datos que no pueden cambiar ni salir."""
    ruta = tmp_path / "clientes.db"
    con = sqlite3.connect(ruta)
    con.executescript(
        "CREATE TABLE facturas (id INTEGER PRIMARY KEY, cliente TEXT, monto REAL);"
        "INSERT INTO facturas VALUES (1,'Lácteos SA',15000.0),(2,'Lácteos SA',22000.0);")
    con.commit()
    con.close()
    return ruta


ESCRITURAS = [
    pytest.param("VACUUM INTO '{destino}'", id="vacuum-into-copia-la-base-entera"),
    pytest.param("ATTACH DATABASE '{destino}' AS z", id="attach-crea-un-archivo"),
    pytest.param("REPLACE INTO facturas VALUES (1,'BORRADO',0)", id="replace-into-escribe"),
    pytest.param("PRAGMA journal_mode=DELETE", id="pragma-cambia-la-base"),
    pytest.param("SELECT * INTO respaldo FROM facturas", id="select-into-crea-tabla"),
    pytest.param("COPY (SELECT 1) TO PROGRAM 'id'", id="copy-to-program-postgres"),
]


@pytest.mark.parametrize("plantilla", ESCRITURAS)
def test_el_guard_rechaza_todo_lo_que_no_sea_una_lectura(plantilla, tmp_path):
    sql = plantilla.format(destino=tmp_path / "robada.db")
    with pytest.raises(C.ConnectionError_, match="(?i)sólo lectura|solo lectura|SELECT"):
        C.guard(sql)


def test_la_extraccion_no_deja_escribir_en_la_base_del_cliente(base_del_cliente, tmp_path):
    """La demostración completa, por el camino real: `extract` no envuelve la
    consulta, así que lo que el control deje pasar se ejecuta tal cual."""
    perfil = {"engine": "sqlite", "database": str(base_del_cliente), "name": "cliente"}
    robada = tmp_path / "copia-robada.db"

    with pytest.raises(C.ConnectionError_):
        C.extract(perfil, f"VACUUM INTO '{robada}'", name="robo")

    assert not robada.exists(), (
        "una consulta «de sólo lectura» dejó una copia completa de la base del "
        "cliente en disco")
    con = sqlite3.connect(base_del_cliente)
    assert con.execute("SELECT count(*), sum(monto) FROM facturas").fetchone() == (2, 37000.0)
    con.close()


LECTURAS = [
    "SELECT * FROM facturas",
    "select cliente, sum(monto) from facturas group by cliente",
    "  \n-- el informe mensual\nSELECT * FROM facturas WHERE monto > 100",
    "WITH grandes AS (SELECT * FROM facturas WHERE monto > 100) SELECT * FROM grandes",
    "SELECT * FROM facturas ORDER BY monto DESC;",
]


@pytest.mark.parametrize("sql", LECTURAS)
def test_las_consultas_de_verdad_siguen_pasando(sql):
    """El límite del arreglo: endurecer no puede romper el trabajo normal."""
    C.guard(sql)


def test_una_lectura_real_sigue_trayendo_los_datos(base_del_cliente):
    perfil = {"engine": "sqlite", "database": str(base_del_cliente), "name": "cliente"}
    r = C.preview(perfil, "SELECT * FROM facturas", limit=10)
    assert r["n"] == 2
    assert {f["cliente"] for f in r["rows"]} == {"Lácteos SA"}
