"""Excel de varias hojas y fechas escondidas: el caso «no tiene columna de fecha».

Un usuario subió un libro con un diccionario de datos en la primera hoja y las
tablas de hechos (recetas, mercado) después. La ingesta tomaba la hoja 0 a
ciegas, el dataset quedaba con puro texto, y Proyecciones decía «este dataset
no tiene una columna de fecha» sobre un archivo lleno de fechas. Además, una
fecha escrita como texto (``2024-01-31``, ``31/01/2024``, ``2024-01``) o un
período ``202401`` no contaban como fecha porque sólo se miraba el tipo.

El libro de acá es sintético, con la misma forma que el real y valores
inventados.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from app.core import fechas, storage


def _libro(path: Path, fechas_como_texto: bool = False) -> Path:
    rng = np.random.default_rng(3)
    meses = pd.date_range("2023-01-01", periods=24, freq="MS")
    productos = [f"P{i:03d}" for i in range(1, 5)]
    mercado = pd.DataFrame([
        {"Fecha": m, "ProductoID": p, "Corporacion": "Corp A" if i % 2 else "Corp B",
         "Unidades": int(rng.integers(800, 1200)),
         "VentasUSD": round(float(rng.gamma(20, 2000)), 2)}
        for m in meses for i, p in enumerate(productos)])
    recetas = pd.DataFrame({
        "ID": [f"T{i:05d}" for i in range(300)],
        "Fecha": rng.choice(meses, 300),
        "MedicoID": [f"M{int(i):03d}" for i in rng.integers(1, 40, 300)],
        "ProductoID": rng.choice(productos, 300),
        "PXs": rng.integers(1, 60, 300),
        "Especialidad": rng.choice(["Cardiología", "Neurología"], 300),
    })
    if fechas_como_texto:
        mercado["Fecha"] = mercado["Fecha"].dt.strftime("%Y-%m-%d")
        recetas["Fecha"] = pd.to_datetime(recetas["Fecha"]).dt.strftime("%d/%m/%Y")
    diccionario = pd.DataFrame({
        "Tabla": ["Recetas", "Recetas", "Mercado", "Mercado"],
        "Campo": ["Fecha", "PXs", "Fecha", "VentasUSD"],
        "Tipo": ["Fecha", "Entero", "Fecha", "Decimal"],
        "Descripción": ["Mes de la receta", "Prescripciones", "Mes", "Ventas"],
    })
    medico = pd.DataFrame({"ID": [f"M{i:03d}" for i in range(1, 40)],
                           "Especialidad": "Cardiología"})
    with pd.ExcelWriter(path) as xw:
        diccionario.to_excel(xw, sheet_name="Diccionario", index=False)
        medico.to_excel(xw, sheet_name="Medico", index=False)
        recetas.to_excel(xw, sheet_name="Recetas", index=False)
        pd.DataFrame().to_excel(xw, sheet_name="Vacia", index=False)
        mercado.to_excel(xw, sheet_name="Mercado", index=False)
    return path


# ═════════════════════════════════════════════════ selección de la hoja ══════
def test_cada_hoja_es_un_dataset_y_la_activa_es_la_de_hechos(tmp_path):
    metas = storage.ingest_workbook(_libro(tmp_path / "bases.xlsx"), "bases")
    hojas = [m.origin["sheet"] for m in metas]

    assert hojas[0] == "Mercado", "la hoja con fecha y más medidas va primero"
    assert set(hojas) == {"Diccionario", "Medico", "Recetas", "Mercado"}, \
        "todas las hojas con datos quedan accesibles; la vacía se saltea"
    assert metas[0].name == "bases · Mercado"
    assert len({m.origin["libro"] for m in metas}) == 1


def test_pidiendo_una_hoja_se_carga_esa_y_una_inexistente_se_dice(tmp_path):
    libro = _libro(tmp_path / "bases.xlsx")
    [meta] = storage.ingest_workbook(libro, "recetas", opts={"sheet": "Recetas"})
    assert meta.rows == 300

    with pytest.raises(storage.IngestError, match="Hojas: Diccionario"):
        storage.ingest_file(libro, "x", opts={"sheet": "NoExiste"})


def test_la_subida_devuelve_las_hojas_y_activa_la_util(client, tmp_path):
    libro = _libro(tmp_path / "bases.xlsx")
    with libro.open("rb") as f:
        r = client.post("/api/datasets/upload", files={"file": ("bases.xlsx", f)})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["dataset"]["origin"]["sheet"] == "Mercado"
    assert [h["sheet"] for h in body["hojas"]][0] == "Mercado"
    assert {"Recetas", "Diccionario"} <= {h["sheet"] for h in body["hojas"]}
    assert client.get("/api/datasets/active").json()["id"] == body["dataset"]["id"]


# ════════════════════════════════════════════════ fechas por contenido ═══════
@pytest.mark.parametrize(("valores", "nombre", "esperado"), [
    (["2024-01-31", "2024-02-29", "2024-03-31"], "x", "ymd"),
    (["2024-01-31 00:00:00", "2024-02-29 10:30:00", "2024-03-31 00:00:00"], "x", "ymd"),
    (["31/01/2024", "29/02/2024", "15/03/2024"], "x", "dmy"),
    (["01/31/2024", "02/29/2024", "03/15/2024"], "x", "mdy"),
    (["2024-01", "2024-02", "2024-12"], "x", "ym"),
    (["202401", "202402", "202412"], "periodo", "yyyymm"),
])
def test_texto_con_forma_de_fecha_es_fecha(valores, nombre, esperado):
    assert fechas.detectar(pd.Series(valores), nombre) == esperado


@pytest.mark.parametrize(("valores", "nombre"), [
    (["M001", "M002", "M003"], "MedicoID"),
    (["1.234-5", "2.345-6", "9.876-5"], "codigo"),
    (["202401", "202402", "202412"], "codigo"),       # aaaamm sin nombre de fecha
    (["2024-13", "2024-14", "2024-15"], "x"),         # mes imposible
    (["Enero", "Febrero", "Marzo"], "Mes"),
])
def test_codigos_y_textos_no_son_fechas(valores, nombre):
    assert fechas.detectar(pd.Series(valores), nombre) is None


def test_los_numeros_solo_son_fecha_si_la_columna_se_llama_como_una():
    aaaamm = pd.Series([202401.0, 202402.0, 202403.0])
    assert fechas.detectar(aaaamm, "AnioMes") == "yyyymm"
    assert fechas.detectar(aaaamm, "VentasUSD") is None
    assert fechas.detectar(pd.Series([1.0, 2.0, 3.0]), "periodo") is None


def test_fechas_en_texto_se_clasifican_y_se_proyectan(tmp_path):
    """Un parquet con la fecha guardada como texto (dataset ya ingerido)."""
    rng = np.random.default_rng(1)
    meses = pd.date_range("2022-01-01", periods=30, freq="MS")
    frames = pd.DataFrame({
        "periodo": [int(m.strftime("%Y%m")) for m in meses],
        "fecha_texto": [m.strftime("%d/%m/%Y") for m in meses],
        "codigo": [f"C{i}" for i in range(30)],
        "monto": rng.gamma(10, 100, 30),
    })
    frames["fecha_texto"] = frames["fecha_texto"].astype("string")
    meta = storage.ingest_frames(iter([frames]), "texto", source="derived")
    c = storage.clasificar_columnas(meta.id)

    assert c["fechas"] == ["periodo", "fecha_texto"]
    assert c["formatos"] == {"periodo": "yyyymm", "fecha_texto": "dmy"}
    assert c["numericas"] == ["monto"], "el aaaamm deja de contarse como medida"

    from app.core import proyeccion
    for col in ("periodo", "fecha_texto"):
        s = proyeccion.serie(meta.id, col, "monto", grano="month")
        assert len(s["periodos"]) == 30, col
        assert s["periodos"][0] == "2022-01-01"


def test_se_prefiere_la_columna_que_se_llama_fecha():
    df = pd.DataFrame({"alta": ["2024-01-01"] * 5, "Fecha": ["2024-02-01"] * 5,
                       "v": [1.0, 2.0, 3.0, 4.0, 5.0]})
    meta = storage.ingest_frames(iter([df]), "pref", source="derived")
    assert storage.clasificar_columnas(meta.id)["fechas"][0] == "Fecha"


def test_excel_con_fechas_como_texto_llega_con_fechas(tmp_path):
    metas = storage.ingest_workbook(_libro(tmp_path / "t.xlsx", fechas_como_texto=True), "t")
    por_hoja = {m.origin["sheet"]: m for m in metas}
    for hoja in ("Mercado", "Recetas"):
        assert storage.clasificar_columnas(por_hoja[hoja].id)["fechas"] == ["Fecha"], hoja


# ═════════════════════════════════════════════════ de punta a punta ══════════
def test_proyeccion_de_punta_a_punta_sobre_el_libro(client, tmp_path):
    libro = _libro(tmp_path / "bases.xlsx", fechas_como_texto=True)
    with libro.open("rb") as f:
        up = client.post("/api/datasets/upload", files={"file": ("bases.xlsx", f)}).json()
    por_hoja = {h["sheet"]: h["id"] for h in up["hojas"]}

    # sin dataset_id: el activo, que es Mercado; columnas elegidas solas
    r = client.post("/api/proyeccion", json={"horizonte": 3})
    assert r.status_code == 200, r.text
    assert r.json()["columna_tiempo"] == "Fecha"
    assert len(r.json()["proyeccion"]) == 3

    r = client.post("/api/proyeccion", json={
        "dataset_id": por_hoja["Recetas"], "columna_tiempo": "Fecha",
        "columna_valor": "PXs", "horizonte": 2})
    assert r.status_code == 200, r.text

    # el diccionario no tiene fecha: se dice, y se dice qué hoja sí
    col = client.get(f"/api/proyeccion/columnas/{por_hoja['Diccionario']}").json()
    assert col["fechas"] == []
    assert {o["sheet"] for o in col["otras_hojas"]} >= {"Mercado", "Recetas"}
    r = client.post("/api/proyeccion", json={"dataset_id": por_hoja["Diccionario"]})
    assert r.status_code == 400
    assert "Mercado" in r.json()["detail"] and "Recetas" in r.json()["detail"]
