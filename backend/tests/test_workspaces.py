"""Workspaces aislados y catálogo SQLite."""
from __future__ import annotations

import io
import time

import numpy as np
import pandas as pd
import pytest
from app.core import storage
from app.core import workspace as W


def _csv(n=60, seed=0):
    rng = np.random.default_rng(seed)
    buf = io.BytesIO()
    pd.DataFrame({"x": rng.normal(0, 1, n), "y": rng.binomial(1, .5, n)}).to_csv(buf, index=False)
    return buf.getvalue()


def test_nombres_invalidos_se_rechazan():
    for malo in ["Con Mayúsculas!", "a/b", "../fuga", "x" * 50, "-empieza-mal"]:
        with pytest.raises(W.WorkspaceError):
            W.normalize(malo)
    assert W.normalize("equipo-a_1") == "equipo-a_1"
    # vacío o None equivalen a "sin encabezado": caen al principal
    assert W.normalize("") == W.DEFAULT
    assert W.normalize(None) == W.DEFAULT


def test_crear_listar_y_borrar():
    W.create("ws-vida")
    assert any(w["name"] == "ws-vida" for w in W.listing())
    with pytest.raises(W.WorkspaceError):
        W.create("ws-vida")
    W.delete("ws-vida")
    assert not any(w["name"] == "ws-vida" for w in W.listing())
    with pytest.raises(W.WorkspaceError):
        W.delete("principal")


def test_los_datasets_no_se_ven_entre_workspaces(tmp_root):
    W.create("ws-a")
    W.create("ws-b")
    try:
        path = tmp_root / "aislado.csv"
        path.write_bytes(_csv())
        tok = W.activate("ws-a")
        try:
            meta = storage.ingest_file(path, "solo-de-a")
            assert any(d["id"] == meta.id for d in storage.list_datasets())
        finally:
            W.deactivate(tok)
        tok = W.activate("ws-b")
        try:
            assert not any(d["name"] == "solo-de-a" for d in storage.list_datasets())
            with pytest.raises(storage.IngestError):
                storage.load_meta(meta.id)
        finally:
            W.deactivate(tok)
        # el principal tampoco lo ve
        assert not any(d["name"] == "solo-de-a" for d in storage.list_datasets())
    finally:
        W.delete("ws-a")
        W.delete("ws-b")


def test_catalogo_sqlite_se_reconstruye_desde_el_disco(tmp_root):
    W.create("ws-cat")
    try:
        tok = W.activate("ws-cat")
        try:
            path = tmp_root / "cat.csv"
            path.write_bytes(_csv())
            meta = storage.ingest_file(path, "catalogado")
            # se borra el catálogo: el listado debe reconstruirlo desde el disco
            (W.root("ws-cat") / "catalog.db").unlink()
            listado = storage.list_datasets()
            assert any(d["id"] == meta.id for d in listado)
            assert any(d["id"] == meta.id for d in (W.catalog_datasets() or []))
        finally:
            W.deactivate(tok)
    finally:
        W.delete("ws-cat")


def test_api_aisla_por_encabezado(client):
    client.post("/api/workspaces", json={"name": "ws-api"})
    try:
        r = client.post("/api/datasets/upload-stream?filename=w.csv&name=en-ws-api",
                        content=_csv(), headers={"X-Workspace": "ws-api"})
        assert r.status_code == 200
        assert r.headers["x-workspace"] == "ws-api"
        ids_api = {d["name"] for d in client.get(
            "/api/datasets", headers={"X-Workspace": "ws-api"}).json()["datasets"]}
        ids_main = {d["name"] for d in client.get("/api/datasets").json()["datasets"]}
        assert "en-ws-api" in ids_api
        assert "en-ws-api" not in ids_main
    finally:
        client.delete("/api/workspaces/ws-api")


def test_workspace_inexistente_cae_al_principal(client):
    r = client.get("/api/datasets", headers={"X-Workspace": "no-existe"})
    assert r.status_code == 200
    assert r.headers["x-workspace"] == "principal"


def test_el_historial_de_trabajos_persiste_en_sqlite(client):
    client.post("/api/workspaces", json={"name": "ws-jobs"})
    try:
        r = client.post("/api/datasets/upload-stream?filename=j.csv&name=para-job",
                        content=_csv(), headers={"X-Workspace": "ws-jobs"})
        ds = r.json()["dataset"]["id"]
        job = client.post("/api/exports/data", json={"dataset_id": ds, "format": "csv"},
                          headers={"X-Workspace": "ws-jobs"}).json()
        for _ in range(40):
            st = client.get(f"/api/jobs/{job['id']}",
                            headers={"X-Workspace": "ws-jobs"}).json()
            if st["status"] in ("terminado", "error"):
                break
            time.sleep(0.25)
        assert st["status"] == "terminado"
        assert st["workspace"] == "ws-jobs"
        hist = client.get("/api/workspaces/jobs-history",
                          headers={"X-Workspace": "ws-jobs"}).json()["jobs"]
        assert any(j["id"] == job["id"] and j["status"] == "terminado" for j in hist)
        # el historial del principal no lo contiene
        hist_main = client.get("/api/workspaces/jobs-history").json()["jobs"]
        assert not any(j["id"] == job["id"] for j in hist_main)
    finally:
        client.delete("/api/workspaces/ws-jobs")


def test_las_descargas_respetan_el_workspace(client):
    client.post("/api/workspaces", json={"name": "ws-dl"})
    try:
        r = client.post("/api/datasets/upload-stream?filename=d.csv&name=dl",
                        content=_csv(), headers={"X-Workspace": "ws-dl"})
        ds = r.json()["dataset"]["id"]
        job = client.post("/api/exports/data", json={"dataset_id": ds, "format": "csv"},
                          headers={"X-Workspace": "ws-dl"}).json()
        for _ in range(40):
            st = client.get(f"/api/jobs/{job['id']}", headers={"X-Workspace": "ws-dl"}).json()
            if st["status"] in ("terminado", "error"):
                break
            time.sleep(0.25)
        url = st["result"]["download_url"]
        # con el query param del workspace baja; sin él, 404 en el principal
        assert client.get(f"{url}?workspace=ws-dl").status_code == 200
        assert client.get(url).status_code == 404
    finally:
        client.delete("/api/workspaces/ws-dl")


def test_catalogo_de_familias_en_la_api(client):
    fams = client.get("/api/automl/catalog").json()["families"]
    assert len(fams) >= 15
    assert {"knn", "mlp", "naive_bayes"} <= {f["name"] for f in fams}
