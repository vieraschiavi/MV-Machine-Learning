"""API de portafolio y mercado: de la pantalla al motor y de vuelta, sin 500 ni JSON roto."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from app.core import ai

EJEMPLOS = Path(__file__).resolve().parents[2] / "examples"


def _subir(client, nombre: str) -> str:
    with (EJEMPLOS / nombre).open("rb") as f:
        r = client.post("/api/datasets/upload", files={"file": (nombre, f)})
    assert r.status_code == 200, r.text
    return r.json()["dataset"]["id"]


@pytest.fixture(scope="module")
def portafolio(client):
    return _subir(client, "portafolio_sintetico.csv")


@pytest.fixture(scope="module")
def estudios(client):
    return _subir(client, "estudios_mercado_sintetico.csv")


CONTRIB = {"entidad": "pais", "valor": "ventas_usd", "mix": "presentacion",
           "grupo": "area_terapeutica", "periodo": "periodo"}


def test_las_columnas_del_portafolio_se_clasifican(client, portafolio):
    r = client.get(f"/api/portafolio/columnas/{portafolio}").json()
    assert "pais" in r["categoricas"] and "ventas_usd" in r["numericas"]


def test_la_matriz_sale_por_area_y_ofrece_las_areas(client, portafolio):
    r = client.post("/api/portafolio/contribucion", json={
        **CONTRIB, "dataset_id": portafolio, "grupo_valor": "Cardiometabólica"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["grupo"] == "Cardiometabólica"
    assert "Respiratoria" in j["grupos_disponibles"]
    assert sum(e["contribucion"] for e in j["entidades"]) == pytest.approx(1)
    assert [x["bloque"] for x in j["lectura"]] == ["ESCALA", "DIRECCIÓN", "DIVERSIDAD"]


def test_una_columna_mal_elegida_da_400_con_motivo(client, portafolio):
    r = client.post("/api/portafolio/contribucion", json={
        "dataset_id": portafolio, "entidad": "pais", "valor": "no_existe", "mix": "presentacion"})
    assert r.status_code == 400 and "no_existe" in r.json()["detail"]


def test_la_plantilla_baja_como_csv_con_todos_los_parametros(client):
    r = client.get("/api/mercado/plantilla", params={"paises": "Chile,Perú"})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    df = pd.read_csv(io.StringIO(r.text))
    assert set(df["pais"]) == {"Chile", "Perú"} and set(df["segmento"]) == {"Hombres", "Mujeres"}


def test_el_analisis_con_estudios_cargados_devuelve_json_valido(client, estudios):
    r = client.post("/api/mercado/analizar", json={
        "estudios_dataset_id": estudios, "n_sim": 300, "inicio": "2027-01",
        "lanzamiento": {"pico": 0.1, "meses_al_pico": 12, "horizonte": 24},
        "observado": [{"pais": "Chile", "unidades": 3_000_000}, {"pais": "Perú", "unidades": 5}]})
    assert r.status_code == 200, r.text
    j = json.loads(r.text)                         # sin NaN: JSON estándar
    assert {x["pais"] for x in j["lecturas"]} == {"México", "Ecuador", "Chile"}
    assert j["evidencia"]["nivel"] == "estudios"
    assert len([x for x in j["lanzamiento"] if x["pais"] == "Total"]) == 24
    assert {x["estado"] for x in j["contraste"]} >= {"sin supuestos"}


def test_supuestos_incompletos_dan_400_explicado(client):
    r = client.post("/api/mercado/analizar", json={"supuestos": [
        {"pais": "Chile", "segmento": "Total", "parametro": "poblacion", "valor": 1000}]})
    assert r.status_code == 400 and "prevalencia" in r.json()["detail"]


def test_proponer_sin_motor_de_ia_da_400_y_no_500(client, monkeypatch):
    def chat(*a, **k):
        raise ai.AIError("No hay ningún proveedor de IA configurado.")
    monkeypatch.setattr(ai, "chat", chat)
    r = client.post("/api/mercado/proponer", json={
        "area_terapeutica": "Cardio", "molecula": "X", "enfermedad": "HTA", "paises": ["Chile"]})
    assert r.status_code == 400 and "proveedor" in r.json()["detail"]


def test_el_paquete_para_powerbi_trae_tablas_y_kit(client, portafolio, estudios):
    r = client.post("/api/portafolio/powerbi", json={
        "contribucion": {**CONTRIB, "dataset_id": portafolio},
        "mercado": {"estudios_dataset_id": estudios, "n_sim": 200}})
    assert r.status_code == 200, r.text
    z = client.get(r.json()["download_url"])
    nombres = set(zipfile.ZipFile(io.BytesIO(z.content)).namelist())
    assert {"portafolio_entidades.csv", "mercado_embudo.csv", "tema_portafolio.json",
            "medidas_portafolio.dax", "burbujas_contribucion.vl.json"} <= nombres
    assert not any(n.endswith(".part") for n in nombres)


def test_demasiados_paises_en_un_analisis_se_rechazan_con_motivo(client):
    filas = [{"pais": f"P{i}", "segmento": "Total", "parametro": k, "valor": v}
             for i in range(200) for k, v in (("poblacion", 1000), ("prevalencia", 0.1),
                                              ("diagnosticados", 0.5), ("tratados", 0.5))]
    r = client.post("/api/mercado/analizar", json={"supuestos": filas})
    assert r.status_code == 400 and "máximo" in r.json()["detail"]


def test_el_paquete_powerbi_sale_solo_con_el_mercado(client, estudios):
    r = client.post("/api/portafolio/powerbi", json={"mercado": {"estudios_dataset_id": estudios, "n_sim": 100}})
    assert r.status_code == 200, r.text
