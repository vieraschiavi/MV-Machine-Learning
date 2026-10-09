"""Etapa 4: fuentes públicas reales (OMS, Banco Mundial, Google Trends), probadas sin salir a internet.

Las respuestas simuladas tienen la forma exacta de las APIs (verificada contra la
OMS y el Banco Mundial reales al escribir el importador).
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, unquote, urlparse

import pandas as pd
import pytest
from app.core import agente_mercado as A
from app.core import fuentes_publicas as F

OMS_HTA = {  # NCD_HYP_PREVALENCE_C: por sexo, sin grupo de edad
    "NCD_HYP_PREVALENCE_C": [("URY", 2018, "SEX_MLE", None, 47.0, 36.0, 58.0),
                             ("URY", 2019, "SEX_MLE", None, 48.6, 37.6, 59.9),
                             ("URY", 2019, "SEX_FMLE", None, 44.7, 34.7, 55.1),
                             ("URY", 2019, "SEX_BTSX", None, 46.6, 39.3, 54.0)],
    "NCD_HYP_DIAGNOSIS_C": [("URY", 2019, "SEX_MLE", None, 63.0, 48.8, 76.1),
                            ("URY", 2019, "SEX_FMLE", None, 75.2, 60.6, 86.2)],
    "NCD_HYP_TREATMENT_C": [("URY", 2019, "SEX_MLE", None, 49.8, 35.0, 63.0),
                            ("URY", 2019, "SEX_FMLE", None, 66.4, 52.0, 78.0)],
    "NCD_DIABETES_PREVALENCE_CRUDE": [("CHL", 2022, "SEX_MLE", "AGEGROUP_YEARS18-PLUS", 13.0, 6.6, 21.5),
                                      ("CHL", 2022, "SEX_MLE", "AGEGROUP_YEARS30-PLUS", 16.0, 9.0, 25.0)],
}


def _bm(tramo: str, sexo: str) -> list[dict]:
    base = {"MA": 100_000, "FE": 110_000}[sexo]
    return [{"countryiso3code": "URY", "date": "2025", "value": base}]


def abrir_falso(url: str) -> bytes:
    u = urlparse(url)
    if "ghoapi" in u.netloc:
        ind = u.path.rsplit("/", 1)[-1]
        filtro = unquote(parse_qs(u.query)["$filter"][0])
        filas = [{"SpatialDim": iso, "TimeDim": y, "Dim1": sx, "Dim2": d2, "Dim3": None, "NumericValue": v,
                  "Low": lo, "High": hi} for iso, y, sx, d2, v, lo, hi in OMS_HTA.get(ind, []) if iso in filtro]
        return json.dumps({"value": filas}).encode()
    if "worldbank" in u.netloc:
        ind = u.path.split("/indicator/")[1]
        _, _, tramo, sexo = ind.split(".")
        return json.dumps([{"page": 1}, _bm(tramo, sexo)]).encode()
    raise AssertionError(f"URL inesperada: {url}")


def test_la_oms_toma_el_ultimo_anio_por_pais_y_sexo_y_pasa_a_proporcion():
    df = F.oms("NCD_HYP_PREVALENCE_C", ["uy"], abrir_falso)
    hombres = df[df["sexo"] == "Hombres"].iloc[0]
    assert (hombres["anio"], hombres["valor"], hombres["bajo"]) == (2019, pytest.approx(0.486), pytest.approx(0.376))
    assert set(df["sexo"]) == {"Hombres", "Mujeres", "Total"}


def test_el_grupo_de_edad_se_respeta():
    df = F.prevalencias_oms("Diabetes", ["Chile"], abrir_falso)
    assert list(df["prevalencia"]) == [pytest.approx(0.13)] and "adultos 18+" in df["fuente"].iloc[0]


def test_la_poblacion_reparte_bien_los_tramos_de_edad():
    pob = F.poblacion_banco_mundial(["Uruguay"], abrir=abrir_falso).set_index(["sexo", "rango_edad"])["poblacion"]
    # 18-39 = 2/5 del tramo 15-19 + cuatro tramos completos; 60+ = cuatro tramos + el de 80 y más.
    assert pob[("Hombres", "18-39")] == round(100_000 * (0.4 + 4))
    assert pob[("Hombres", "60+")] == 500_000 and pob[("Mujeres", "40-59")] == 440_000


def test_los_supuestos_salen_con_intervalo_fuente_y_tratados_sobre_diagnosticados():
    s = F.supuestos_oms("Hipertensión", ["Uruguay"], abrir=abrir_falso)
    h = s[s["segmento"] == "Hombres"].set_index("parametro")
    assert h.loc["prevalencia", "minimo"] == pytest.approx(0.376) and h.loc["prevalencia", "maximo"] == pytest.approx(0.599)
    assert h.loc["tratados", "valor"] == pytest.approx(0.498 / 0.63)
    assert h.loc["poblacion", "valor"] == round(100_000 * 10)          # tramos de 30 a 79: diez de cinco años
    assert set(s["origen"]) == {"fuente pública"} and s["fuente"].str.contains("OMS|Banco Mundial").all()
    # Entra al agente de mercado como un estudio: pisa a la propuesta de la IA.
    tabla, _ = A.combinar(None, s)
    assert not tabla.empty


def test_pais_y_area_desconocidos():
    with pytest.raises(ValueError, match="ISO"):
        F.pais("Narnia")
    assert F.pais("uy") == "Uruguay" and F.pais("MEX") == "México"
    with pytest.raises(ValueError, match="Área sin indicadores"):
        F.prevalencias_oms("Dermatología", ["Uruguay"], abrir_falso)


def test_una_caida_de_red_se_informa_con_el_indicador():
    def caida(url: str) -> bytes:
        raise OSError("sin conexión")
    with pytest.raises(ValueError, match="NCD_HYP_PREVALENCE_C"):
        F.oms("NCD_HYP_PREVALENCE_C", ["Uruguay"], caida)


def test_google_trends_tal_como_lo_exporta_trends():
    csv = ("Categoría: Todas las categorías\n\nRegión,mounjaro: (1/1/25 - 1/10/25)\n"
           "Montevideo,100\nCanelones,63\nRivera,<1\nArtigas,\n")
    df = F.trends_csv(csv.encode(), "Uruguay")
    assert list(df["region"]) == ["Montevideo", "Canelones", "Rivera"]
    assert list(df["interes"]) == [100, 63, 0.5] and set(df["termino"]) == {"mounjaro"}
    with pytest.raises(ValueError, match="Google Trends"):
        F.trends_csv(b"hola", "Uruguay")


def test_api_de_fuentes_publicas_sin_red(client, monkeypatch):
    monkeypatch.setattr(F, "_abrir_red", abrir_falso)
    r = client.post("/api/relacionamiento/fuentes/publicas",
                    json={"fuente": "oms_supuestos", "area": "Cardiometabólica", "paises": ["Uruguay"]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["dataset"]["id"] and j["filas"] == 8
    r = client.post("/api/relacionamiento/fuentes/publicas", json={"fuente": "oms_prevalencias", "paises": ["Narnia"]})
    assert r.status_code == 400
    r = client.post("/api/relacionamiento/fuentes/trends", params={"pais": "Uruguay"},
                    files={"file": ("t.csv", b"Region,dolor de cabeza\nMontevideo,100\n")})
    assert r.status_code == 200 and r.json()["filas"] == 1
    assert pd.DataFrame(j["muestra"])["parametro"].isin(["poblacion", "prevalencia", "diagnosticados", "tratados"]).all()


def test_un_censo_publicado_a_lo_ancho_pasa_al_formato_largo():
    ancho = pd.DataFrame({"País": ["Uruguay"], "Ciudad": ["Montevideo"], "Barrio": ["Pocitos"],
                          "Hombres 18-39": ["12.345"], "Mujeres_60 y más": [9876], "Varones 40-59": [5000]})
    largo = F.censo_ancho_a_largo(ancho).set_index(["sexo", "rango_edad"])["poblacion"]
    assert largo[("Hombres", "18-39")] == 12345 and largo[("Mujeres", "60+")] == 9876
    assert largo[("Hombres", "40-59")] == 5000
    with pytest.raises(ValueError, match="sexo edad"):
        F.censo_ancho_a_largo(ancho.assign(Total=[1]))
    with pytest.raises(ValueError, match="identificación"):
        F.censo_ancho_a_largo(ancho.drop(columns=["Ciudad"]))
