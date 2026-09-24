"""Un solo dataset activo para todas las pestañas.

El pedido: al cargar datos propios —archivo o consulta SQL— esos datos tienen
que llegar a TODAS las pestañas, y ninguna puede quedarse con otros. Antes cada
pestaña guardaba su propia elección (Proyecciones y Bitácora se quedaban con la
primera que vieron) y el dataset recién cargado no les llegaba.
"""
from __future__ import annotations

import io
import re
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from app.core import storage
from app.core import workspace as W

WS = "ws-activo"
H = {"X-Workspace": WS}
FRONT = Path(__file__).resolve().parents[2] / "frontend" / "assets" / "js"


def _serie(prefijo: str, n: int = 36, seed: int = 0) -> pd.DataFrame:
    """Serie mensual sintética; cada dataset con columnas propias para detectar mezclas."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        f"{prefijo}_fecha": pd.date_range("2022-01-01", periods=n, freq="MS").strftime("%Y-%m-%d"),
        f"{prefijo}_monto": (1000 + rng.normal(0, 50, n).cumsum()).round(2),
        f"{prefijo}_region": rng.choice(["Norte", "Sur"], n),
    })


def _subir(client, df: pd.DataFrame, nombre: str) -> dict:
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    r = client.post(f"/api/datasets/upload-stream?filename={nombre}.csv&name={nombre}",
                    content=buf.getvalue(), headers=H)
    assert r.status_code == 200, r.text
    return r.json()["dataset"]


def _esperar(client, job_id, timeout=120):
    limite = time.time() + timeout
    while time.time() < limite:
        job = client.get(f"/api/jobs/{job_id}", headers=H).json()
        if job["status"] in ("terminado", "error", "cancelado"):
            return job
        time.sleep(0.2)
    raise AssertionError(f"El trabajo {job_id} no terminó")


@pytest.fixture()
def ws(client):
    client.post("/api/workspaces", json={"name": WS})
    yield client
    client.delete(f"/api/workspaces/{WS}")


# ─────────────────────────────────────────────────────── el resolver ─────────
def test_resolver_sin_datos_elegido_reciente_y_borrado(tmp_root):
    W.create("ws-resolver")
    tok = W.activate("ws-resolver")
    try:
        assert storage.dataset_activo() == {"id": None, "origen": None, "dataset": None}
        with pytest.raises(storage.IngestError):
            storage.dataset_para(None)

        rutas = []
        for i, pref in enumerate(["uno", "dos"]):
            p = tmp_root / f"resolver_{pref}.csv"
            _serie(pref, seed=i).to_csv(p, index=False)
            rutas.append(storage.ingest_file(p, pref))
            time.sleep(0.01)
        uno, dos = rutas

        # sin elección: el último cargado, y se dice que es automático
        assert storage.dataset_activo()["origen"] == "reciente"
        assert storage.dataset_activo()["id"] == dos.id

        assert storage.elegir_dataset_activo(uno.id)["id"] == uno.id
        assert storage.dataset_activo()["origen"] == "elegido"
        assert storage.dataset_para(None) == uno.id
        assert storage.dataset_para(dos.id) == dos.id     # el pedido explícito manda

        with pytest.raises(storage.IngestError):
            storage.elegir_dataset_activo("ds_no_existe00")

        # borrar el activo no deja a las pestañas apuntando a la nada
        storage.delete_dataset(uno.id)
        assert storage.dataset_activo()["id"] == dos.id

        storage.elegir_dataset_activo(dos.id)
        assert storage.limpiar_dataset_activo()["origen"] == "reciente"
    finally:
        W.deactivate(tok)
        W.delete("ws-resolver")


def test_la_eleccion_no_cruza_de_workspace(tmp_root):
    W.create("ws-act-a")
    W.create("ws-act-b")
    try:
        p = tmp_root / "cruce_ws.csv"
        _serie("a").to_csv(p, index=False)
        tok = W.activate("ws-act-a")
        try:
            meta = storage.ingest_file(p, "solo-a")
            storage.elegir_dataset_activo(meta.id)
        finally:
            W.deactivate(tok)
        tok = W.activate("ws-act-b")
        try:
            assert storage.dataset_activo()["id"] is None
            with pytest.raises(storage.IngestError):
                storage.elegir_dataset_activo(meta.id)
        finally:
            W.deactivate(tok)
    finally:
        W.delete("ws-act-a")
        W.delete("ws-act-b")


# ─────────────────────────────────────────── API: todas las pestañas ─────────
def _consumidores(client, ds_id: str, proyeccion_400: bool = False) -> dict[str, set[str]]:
    """Columnas que ve cada pestaña al trabajar con el dataset activo.

    ``proyeccion_400``: la extracción SQL desde SQLite trae la fecha como texto,
    así que la proyección contesta 400 «falta una columna de fecha»; lo que se
    verifica igual es que el mensaje hable del dataset activo y no de otro.
    """
    def cols_de(obj) -> set[str]:
        texto = str(obj)
        return set(re.findall(r"\b(?:uno|dos|sql)_(?:fecha|monto|region)\b", texto))

    vistas = {
        "explorar.preview": client.get(f"/api/datasets/{ds_id}/preview?limit=5", headers=H),
        "explorar.perfil": client.get(f"/api/datasets/{ds_id}/profile", headers=H),
        "tablero": client.get(f"/api/dashboards/{ds_id}/spec", headers=H),
        "proyeccion.columnas": client.get(f"/api/proyeccion/columnas/{ds_id}", headers=H),
        "ingenieria": client.get(f"/api/ingenieria/{ds_id}", headers=H),
        "bitacora": client.get(f"/api/bitacora?dataset_id={ds_id}", headers=H),
        # estos dos reciben el pedido SIN dataset_id: lo resuelve el servidor
        "etl": client.post("/api/etl/propose", json={}, headers=H),
        "proyeccion": client.post("/api/proyeccion", json={"horizonte": 3}, headers=H),
    }
    out = {}
    for nombre, r in vistas.items():
        ok = {200, 400} if (nombre == "proyeccion" and proyeccion_400) else {200}
        assert r.status_code in ok, f"{nombre}: {r.status_code} {r.text[:200]}"
        out[nombre] = cols_de(r.json())
    return out


def test_el_archivo_cargado_llega_a_todas_las_pestanas_sin_mezcla(ws):
    client = ws
    uno = _subir(client, _serie("uno", seed=1), "uno")
    dos = _subir(client, _serie("dos", seed=2), "dos")

    # lo último que el usuario cargó es lo activo, elegido (no automático)
    act = client.get("/api/datasets/active", headers=H).json()
    assert act["id"] == dos["id"] and act["origen"] == "elegido"

    vistas = _consumidores(client, act["id"])
    for nombre, cols in vistas.items():
        assert any(c.startswith("dos_") for c in cols), f"{nombre} no recibió el dataset activo"
        assert not any(c.startswith("uno_") for c in cols), f"{nombre} mezcla otro dataset: {cols}"

    # elegirlo desde cualquier selector cambia TODAS las pestañas
    r = client.put("/api/datasets/active", json={"dataset_id": uno["id"]}, headers=H)
    assert r.status_code == 200 and r.json()["id"] == uno["id"]
    for nombre, cols in _consumidores(client, uno["id"]).items():
        assert not any(c.startswith("dos_") for c in cols), f"{nombre} quedó con el anterior: {cols}"

    # un id ajeno se rechaza y no pisa la elección vigente
    assert client.put("/api/datasets/active", json={"dataset_id": "ds_ajeno000000"},
                      headers=H).status_code == 404
    assert client.get("/api/datasets/active", headers=H).json()["id"] == uno["id"]

    # limpiar la elección vuelve al automático (el último cargado)
    r = client.delete("/api/datasets/active", headers=H).json()
    assert r["origen"] == "reciente" and r["id"] == dos["id"]


def test_la_consulta_sql_extraida_pasa_a_ser_el_dataset_activo(ws, tmp_root):
    client = ws
    _subir(client, _serie("uno", seed=3), "previo")
    base = tmp_root / "activo_sql.db"
    base.unlink(missing_ok=True)
    con = sqlite3.connect(base)
    _serie("sql", seed=4).to_sql("ventas", con, index=False)
    con.close()

    conn = client.post("/api/connections/save", headers=H, json={
        "engine": "sqlite", "database": str(base), "name": "local"}).json()["connection"]
    r = client.post(f"/api/connections/{conn['id']}/extract", headers=H,
                    json={"sql": "SELECT * FROM ventas", "name": "desde sql"})
    assert r.status_code == 200, r.text
    body = r.json()
    job = _esperar(client, (body.get("job") or body)["id"])
    assert job["status"] == "terminado", job
    nuevo = job["result"]["dataset"]["id"]

    act = client.get("/api/datasets/active", headers=H).json()
    assert act["id"] == nuevo and act["origen"] == "elegido"
    for nombre, cols in _consumidores(client, act["id"], proyeccion_400=True).items():
        assert any(c.startswith("sql_") for c in cols), f"{nombre} no recibió lo extraído por SQL"
        assert not any(c.startswith("uno_") for c in cols), f"{nombre} mezcla el anterior: {cols}"


# ─────────────────────────────────────── la interfaz usa esa única fuente ────
def test_ninguna_pestana_guarda_su_propio_dataset():
    """Todas las vistas leen `store.datasetId` y eligen por `store.elegirDataset`."""
    store = (FRONT / "store.js").read_text(encoding="utf-8")
    assert "mv.dataset" not in store, "el dataset activo no se guarda en el navegador"
    assert "/api/datasets/active" in store

    for js in sorted((FRONT / "views").glob("*.js")):
        texto = js.read_text(encoding="utf-8")
        assert not re.search(r"store\.set\(\{[^}]*datasetId", texto), \
            f"{js.name}: cambia el dataset sin pasar por store.elegirDataset"
        assert not re.search(r"\b(elegido|fuente)\.dataset\b", texto), \
            f"{js.name}: guarda una elección de dataset propia de la pestaña"


def test_hay_un_indicador_visible_del_dataset_activo():
    html = (FRONT.parents[1] / "index.html").read_text(encoding="utf-8")
    assert 'id="dataset-chip"' in html
    assert "renderDatasetChip" in (FRONT / "app.js").read_text(encoding="utf-8")
