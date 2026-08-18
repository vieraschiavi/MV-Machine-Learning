"""Pruebas de extremo a extremo sobre la API HTTP."""
from __future__ import annotations

import io
import time

import pytest


def _esperar(client, job_id, timeout=180):
    """Espera a que un trabajo en segundo plano termine."""
    limite = time.time() + timeout
    while time.time() < limite:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("terminado", "error", "cancelado"):
            return job
        time.sleep(0.25)
    raise AssertionError(f"El trabajo {job_id} no terminó en {timeout}s")


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["version"]
    assert "lightgbm" in body["engines"]


def test_capabilities_declara_lo_que_el_producto_promete(client):
    caps = client.get("/api/capabilities").json()
    assert ".csv" in caps["file_formats"] and ".xlsx" in caps["file_formats"]
    ids = {e["id"] for e in caps["sql_engines"]}
    assert {"sqlserver", "postgresql", "mysql", "sqlite"} <= ids
    proveedores = {p["id"] for p in caps["ai_providers"]}
    assert {"openai", "anthropic", "xai", "google", "copilot"} <= proveedores
    assert caps["languages"] == ["es", "en", "pt"]


def test_docs_disponibles(client):
    assert client.get("/api/openapi.json").status_code == 200


def test_la_interfaz_se_sirve(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "MV AutoML Studio" in r.text
    for ruta in ["/assets/css/app.css", "/assets/js/app.js", "/assets/i18n/es.json",
                 "/assets/i18n/en.json", "/assets/i18n/pt.json"]:
        assert client.get(ruta).status_code == 200, ruta


@pytest.fixture(scope="module")
def subido(client, frame_binary):
    buf = io.BytesIO()
    frame_binary.to_csv(buf, sep=";", index=False, decimal=",", encoding="utf-8")
    r = client.post("/api/datasets/upload-stream?filename=api.csv&name=desde%20api",
                    content=buf.getvalue())
    assert r.status_code == 200, r.text
    return r.json()["dataset"]


def test_subida_por_streaming(subido, frame_binary):
    assert subido["rows"] == len(frame_binary)
    assert subido["n_columns"] == frame_binary.shape[1]


def test_subida_multipart(client, frame_regression):
    buf = io.BytesIO()
    frame_regression.head(100).to_csv(buf, index=False)
    r = client.post("/api/datasets/upload", files={"file": ("m.csv", buf.getvalue(), "text/csv")})
    assert r.status_code == 200
    assert r.json()["dataset"]["rows"] == 100


def test_archivo_vacio_da_400(client):
    r = client.post("/api/datasets/upload-stream?filename=vacio.csv", content=b"")
    assert r.status_code == 400
    assert "detail" in r.json()


def test_extension_invalida_da_400(client):
    r = client.post("/api/datasets/upload-stream?filename=x.exe", content=b"MZ...")
    assert r.status_code == 400


def test_dataset_inexistente_da_404(client):
    assert client.get("/api/datasets/ds_no_existe").status_code == 404


def test_preview_perfil_y_correlaciones(client, subido):
    p = client.get(f"/api/datasets/{subido['id']}/preview?limit=5").json()
    assert len(p["rows"]) == 5
    prof = client.get(f"/api/datasets/{subido['id']}/profile").json()
    assert prof["rows"] == subido["rows"]
    assert 0 <= prof["quality"]["score"] <= 100
    corr = client.get(f"/api/datasets/{subido['id']}/correlations").json()
    assert "columns" in corr


def test_consulta_sql_libre_solo_lectura(client, subido):
    ok = client.post(f"/api/datasets/{subido['id']}/query",
                     json={"sql": "SELECT count(*) AS n FROM {t}", "limit": 10})
    assert ok.status_code == 200
    assert ok.json()["rows"][0]["n"] == subido["rows"]
    malo = client.post(f"/api/datasets/{subido['id']}/query",
                       json={"sql": "DROP TABLE x", "limit": 10})
    assert malo.status_code == 400


def test_flujo_completo_etl_entrenamiento_y_exportacion(client, subido):
    # 1. proponer el ETL
    plan = client.post("/api/etl/propose",
                       json={"dataset_id": subido["id"], "target": "objetivo"}).json()
    assert plan["steps"] and plan["sql"]

    # 2. ejecutarlo
    job = client.post("/api/etl/execute",
                      json={"dataset_id": subido["id"], "plan": plan}).json()
    resultado = _esperar(client, job["id"])
    assert resultado["status"] == "terminado", resultado.get("error")
    limpio = resultado["result"]["dataset"]

    # 3. entrenar
    job = client.post("/api/automl/train", json={
        "dataset_id": limpio["id"], "target": "objetivo",
        "budget_seconds": 8, "max_models": 2, "shap": False,
        "permutation_importance": False, "name": "modelo api",
    }).json()
    entrenado = _esperar(client, job["id"], timeout=300)
    assert entrenado["status"] == "terminado", entrenado.get("error")
    informe = entrenado["result"]["report"]
    model_id = entrenado["result"]["model_id"]
    assert informe["champion"]["holdout"]["auc"] > 0.5
    assert informe["split"]["holdout"] > 0

    # 4. ficha del modelo
    ficha = client.get(f"/api/automl/models/{model_id}").json()
    assert ficha["target"] == "objetivo"

    # 5. predicción puntual
    fila = client.get(f"/api/datasets/{limpio['id']}/preview?limit=2").json()["rows"]
    pred = client.post("/api/automl/predict", json={"model_id": model_id, "rows": fila})
    assert pred.status_code == 200
    assert len(pred.json()["predictions"]) == 2

    # 6. scoring del dataset completo
    job = client.post("/api/automl/score",
                      json={"model_id": model_id, "dataset_id": limpio["id"]}).json()
    scoring = _esperar(client, job["id"])
    assert scoring["status"] == "terminado"
    assert scoring["result"]["rows"] == limpio["rows"]

    # 7. informe en Excel
    job = client.post("/api/exports/excel", json={
        "dataset_id": limpio["id"], "model_id": model_id, "data_limit": 100,
    }).json()
    excel = _esperar(client, job["id"])
    assert excel["status"] == "terminado", excel.get("error")
    assert "Resumen Ejecutivo" in excel["result"]["sheets"]
    descarga = client.get(excel["result"]["download_url"])
    assert descarga.status_code == 200
    assert len(descarga.content) > 5000

    # 8. datos en CSV
    job = client.post("/api/exports/data",
                      json={"dataset_id": limpio["id"], "format": "csv"}).json()
    csv = _esperar(client, job["id"])
    assert csv["status"] == "terminado"
    assert csv["result"]["rows"] == limpio["rows"]


def test_entrenar_con_objetivo_inexistente_da_400(client, subido):
    r = client.post("/api/automl/train",
                    json={"dataset_id": subido["id"], "target": "no_existe"})
    assert r.status_code == 400


def test_estado_de_los_proveedores_de_ia(client):
    body = client.get("/api/ai/status").json()
    ids = {p["provider"] for p in body["providers"]}
    assert {"openai", "anthropic", "xai", "google", "copilot"} <= ids
    for p in body["providers"]:
        assert "api_key" not in p


def test_sugerencia_de_objetivo_funciona_sin_ia(client, subido):
    r = client.post("/api/ai/suggest-target",
                    json={"dataset_id": subido["id"], "objective": "el objetivo del cliente"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.parametrize("ruta", [
    "/api/exports/download/..%2F..%2Fetc%2Fpasswd",
    "/api/exports/download/no_existe.xlsx",
    "/api/inventado",
])
def test_rutas_invalidas_devuelven_json_y_no_la_interfaz(client, ruta):
    r = client.get(ruta)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "<html" not in r.text.lower()


def test_trabajo_inexistente_da_404(client):
    assert client.get("/api/jobs/job_no_existe").status_code == 404


def test_listado_de_trabajos(client):
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert isinstance(r.json()["jobs"], list)
