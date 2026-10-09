"""Salida para Power BI del tablero «Portafolio y mercado».

Se fija que las tablas salgan con las columnas que usan las medidas DAX y la
especificación de burbujas del kit, que cada área tenga su matriz propia
(contribuciones que suman uno dentro del área) y que el kit viaje junto.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pandas as pd
import pytest
from app.core import agente_mercado as A
from app.core import contribucion as C
from app.core import mercado as M
from app.core import powerbi_portafolio as P

EJEMPLOS = Path(__file__).resolve().parents[2] / "examples"
CFG = C.Config(entidad="pais", valor="ventas_usd", mix="presentacion",
               grupo="area_terapeutica", periodo="periodo")


@pytest.fixture(scope="module")
def salida(tmp_path_factory):
    df = pd.read_csv(EJEMPLOS / "portafolio_sintetico.csv")
    est = pd.read_csv(EJEMPLOS / "estudios_mercado_sintetico.csv")
    an = A.analizar(est, plan=M.Lanzamiento(pico=0.1, meses_al_pico=12, horizonte=18),
                    observado=pd.DataFrame({"pais": ["Chile"], "unidades": [5e6]}), n_sim=200)
    carpeta = tmp_path_factory.mktemp("pbi")
    return carpeta, P.escribir(carpeta, C.calcular_por_grupo(df, CFG), an)


def test_salen_todas_las_tablas_y_el_kit(salida):
    _, out = salida
    for t in ("portafolio_entidades", "portafolio_mix", "portafolio_kpis", "portafolio_lectura",
              "portafolio_grupos", "mercado_embudo", "mercado_potencial", "mercado_lecturas",
              "mercado_sensibilidad", "mercado_lanzamiento", "mercado_supuestos", "mercado_contraste"):
        assert out[t].exists(), t
    for k in P.KIT:
        assert out[k].exists(), k


def test_cada_area_tiene_su_matriz_y_suma_uno(salida):
    _, out = salida
    ent = pd.read_parquet(out["portafolio_entidades"])
    assert set(ent["grupo"]) == {"Todas", "Cardiometabólica", "Respiratoria", "Sistema nervioso central"}
    assert ent.groupby("grupo")["contribucion"].sum().round(9).eq(1).all()


def test_las_columnas_que_usa_el_kit_existen_en_las_tablas(salida):
    carpeta, out = salida
    columnas = {n: set(pd.read_parquet(out[n]).columns) for n in out
                if Path(out[n]).suffix not in (".json", ".dax")}
    dax = (carpeta / "medidas_portafolio.dax").read_text(encoding="utf-8")
    usadas = set(re.findall(r"(\w+)\[(\w+)\]", dax))
    for tabla, col in usadas:
        assert col in columnas[tabla], f"{tabla}[{col}] no existe"
    spec = json.loads((carpeta / "burbujas_contribucion.vl.json").read_text(encoding="utf-8"))
    campos = set(re.findall(r'"field":\s*"(\w+)"', json.dumps(spec)))
    propios = {"x0", "x1", "y", "color", "franja", "etiqueta"}
    assert campos - propios <= columnas["portafolio_entidades"]


def test_el_tema_es_un_json_de_tema_valido(salida):
    carpeta, _ = salida
    tema = json.loads((carpeta / "tema_portafolio.json").read_text(encoding="utf-8"))
    assert tema["name"] and len(tema["dataColors"]) >= 3
    assert all(re.fullmatch(r"#[0-9A-F]{6}", c) for c in tema["dataColors"])


def test_el_embudo_va_en_formato_largo_y_ordenado(salida):
    _, out = salida
    emb = pd.read_parquet(out["mercado_embudo"])
    orden = emb.drop_duplicates("etapa").sort_values("orden")["etapa"].tolist()
    assert orden == ["prevalentes", "diagnosticados", "tratados", "en_clase", "pacientes_marca"]


def test_en_csv_tambien_sale(tmp_path):
    df = pd.read_csv(EJEMPLOS / "portafolio_sintetico.csv")
    out = P.escribir(tmp_path, C.calcular_por_grupo(df, CFG), formato="csv", kit=False)
    assert out["portafolio_entidades"].suffix == ".csv"
    assert not (tmp_path / "tema_portafolio.json").exists()


def test_sin_nada_para_escribir_o_con_formato_raro_se_explica(tmp_path):
    with pytest.raises(ValueError, match="nada para escribir"):
        P.escribir(tmp_path)
    with pytest.raises(ValueError, match="parquet o csv"):
        P.escribir(tmp_path, mercado={}, formato="xlsx")


def test_el_zip_lleva_todo(salida, tmp_path):
    carpeta, out = salida
    z = P.empaquetar(carpeta, tmp_path / "pbi.zip")
    assert set(zipfile.ZipFile(z).namelist()) == {p.name for p in out.values()}
