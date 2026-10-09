"""API de relacionamiento: de las tablas subidas al análisis y al zip para Power BI y Fabric."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

EJEMPLOS = Path(__file__).resolve().parents[2] / "examples"
ARCHIVOS = {"contactos": "relacionamiento_contactos.csv", "contenidos": "relacionamiento_contenidos.csv",
            "interacciones": "relacionamiento_interacciones.csv", "poblacion": "censo_sintetico.csv",
            "prevalencias": "prevalencias_sinteticas.csv", "escucha": "escucha_social_sintetica.csv"}


@pytest.fixture(scope="module")
def ids(client) -> dict[str, str]:
    out = {}
    for clave, nombre in ARCHIVOS.items():
        with (EJEMPLOS / nombre).open("rb") as f:
            r = client.post("/api/datasets/upload", files={"file": (nombre, f)})
        assert r.status_code == 200, r.text
        out[f"{clave}_dataset_id"] = r.json()["dataset"]["id"]
    return out


def test_plantillas(client):
    r = client.get("/api/relacionamiento/plantilla/contactos")
    columnas = r.text.splitlines()[0].split(",")
    assert r.status_code == 200 and "consiente_salud" in columnas and "email" not in columnas
    assert client.get("/api/relacionamiento/plantilla/prevalencias").status_code == 200
    assert client.get("/api/relacionamiento/plantilla/mails").status_code == 404


def test_analizar_solo_la_base_propia(client, ids):
    body = {k: ids[k] for k in ("contactos_dataset_id", "contenidos_dataset_id", "interacciones_dataset_id")}
    r = client.post("/api/relacionamiento/analizar", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    json.dumps(j, allow_nan=False)
    assert j["resumen"]["contactos"] == 1500 and len(j["recomendaciones"]) <= 500
    assert j["cobertura"] == [] and j["escucha_menciones"] == []
    assert any(e["pais"] == "Total" for e in j["embudo"])


def test_analizar_con_fuentes_publicas_y_ajustes_de_legal(client, ids):
    r = client.post("/api/relacionamiento/analizar", json={
        **ids, "area": "Diabetes", "segmentar": ["sexo"], "por_contacto": 2,
        "ajustes": {"Uruguay": {"frecuencia_max_30d": 1, "validado_por_legal": True}}})
    assert r.status_code == 200, r.text
    j = r.json()
    json.dumps(j, allow_nan=False)
    assert j["cobertura"] and j["cobertura"][0]["area_terapeutica"] == "Diabetes" and "sexo" in j["cobertura"][0]
    assert j["escucha_menciones"] and j["farmacovigilancia"]
    uy = next(p for p in j["politicas"] if p["pais"] == "Uruguay")
    assert uy["frecuencia_max_30d"] == 1 and uy["validado_por_legal"] is True


def test_errores_de_entrada(client, ids):
    base = {"contactos_dataset_id": ids["contactos_dataset_id"], "contenidos_dataset_id": ids["contenidos_dataset_id"]}
    assert client.post("/api/relacionamiento/analizar", json={**base, "segmentar": ["religion"]}).status_code == 422
    assert client.post("/api/relacionamiento/analizar", json={
        **base, "ajustes": {"Uruguay": {"frecuencia_max_30d": 999}}}).status_code == 422
    assert client.post("/api/relacionamiento/analizar", json={
        **base, "contactos_dataset_id": "no-existe"}).status_code == 404
    # Las prevalencias no son una tabla de contactos: error claro, no un 500.
    r = client.post("/api/relacionamiento/analizar", json={**base, "contactos_dataset_id": ids["prevalencias_dataset_id"]})
    assert r.status_code == 400 and "id_contacto" in r.json()["detail"]


def test_exportar_el_zip_con_powerbi_y_modelo_fabric(client, ids):
    r = client.post("/api/relacionamiento/exportar", json={**ids, "formato": "csv"})
    assert r.status_code == 200, r.text
    zbytes = client.get(r.json()["download_url"]).content
    nombres = zipfile.ZipFile(io.BytesIO(zbytes)).namelist()
    assert "medidas_relacionamiento.dax" in nombres and "relacionamiento_cobertura.csv" in nombres
    assert "modelo_fabric/crear_tablas.sql" in nombres and "modelo_fabric/dim_contacto.csv" in nombres
    assert not any(n.endswith(".part") for n in nombres)
