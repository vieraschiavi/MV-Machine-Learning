"""Matriz de contribución y mix: la lámina de «motores de crecimiento por mercado», calculada.

Se arma un portafolio chico con números a mano para que cada cifra de la
matriz se pueda verificar sin calculadora: contribuciones, niveles, el índice
de mix (eje X), el siguiente motor de cada mercado y la lectura estratégica.
"""
from __future__ import annotations

import pandas as pd
import pytest
from app.core import contribucion as C

MONO, DOBLE_A, DOBLE_B, TRIPLE = "Alfa", "Alfa/Diurético", "Alfa/Calcio", "Alfa/Calcio/Diurético"


def _portafolio() -> pd.DataFrame:
    filas = {
        # país: {presentación: ventas}
        "MX": {MONO: 100, DOBLE_A: 100, DOBLE_B: 50, TRIPLE: 50},       # 300 → 50 %
        "CL": {MONO: 30, DOBLE_A: 60, DOBLE_B: 30, TRIPLE: 0},          # 120 → 20 %
        "AR": {MONO: 100, DOBLE_A: 0, DOBLE_B: 0, TRIPLE: 0},           # 100 → 16,7 %
        "PE": {MONO: 40, DOBLE_A: 20, DOBLE_B: 0, TRIPLE: 0},           #  60 → 10 %
        "BO": {MONO: 10, DOBLE_A: 0, DOBLE_B: 0, TRIPLE: 10},           #  20 → 3,3 %
    }
    out = [{"pais": p, "presentacion": s, "ventas": v, "area": "Cardio"}
           for p, d in filas.items() for s, v in d.items()]
    out.append({"pais": "MX", "presentacion": "Beta", "ventas": 400, "area": "SNC"})
    return pd.DataFrame(out)


CFG = C.Config(entidad="pais", valor="ventas", mix="presentacion", grupo="area")


def _ent(r):
    return {e["entidad"]: e for e in r["entidades"]}


def test_la_contribucion_suma_uno_y_se_ordena_de_mayor_a_menor():
    r = C.calcular(_portafolio(), CFG, grupo_valor="Cardio")
    contrib = [e["contribucion"] for e in r["entidades"]]
    assert sum(contrib) == pytest.approx(1.0)
    assert contrib == sorted(contrib, reverse=True)
    assert r["total"] == pytest.approx(600)


def test_los_niveles_y_las_acciones_siguen_los_umbrales_de_la_lamina():
    e = _ent(C.calcular(_portafolio(), CFG, grupo_valor="Cardio"))
    assert (e["MX"]["nivel"], e["MX"]["accion"]) == ("Alta", "proteger")
    assert (e["PE"]["nivel"], e["PE"]["accion"]) == ("Media", "acelerar")     # 10 % justo no es alta
    assert (e["BO"]["nivel"], e["BO"]["accion"]) == ("Media", "acelerar")     # 3,3 %
    r = C.calcular(_portafolio(), C.Config(**{**CFG.__dict__, "umbral_media": 0.05}), "Cardio")
    assert _ent(r)["BO"]["accion"] == "desarrollar"


def test_el_escalon_sale_del_nombre_de_la_presentacion():
    assert C.nivel_por_nombre("Olmesartán") == 1
    assert C.nivel_por_nombre("Olmesartán/HCTZ") == 2
    assert C.nivel_por_nombre("Olmesartán + Amlodipina + HCTZ") == 3
    assert C.nivel_por_nombre("Triple terapia") == 3


def test_el_indice_de_mix_va_de_cero_a_uno_y_ordena_la_evolucion():
    e = _ent(C.calcular(_portafolio(), CFG, grupo_valor="Cardio"))
    assert e["AR"]["indice_mix"] == pytest.approx(0.0)            # todo monoterapia
    # MX: (100·0 + 150·1 + 50·2) / 300 / 2
    assert e["MX"]["indice_mix"] == pytest.approx(250 / 300 / 2)
    assert e["AR"]["etapa_mix"].startswith("Mayor dependencia en monoterapia")
    assert e["AR"]["indice_mix"] < e["PE"]["indice_mix"] < e["CL"]["indice_mix"]


def test_el_siguiente_motor_es_el_primer_escalon_donde_se_esta_por_debajo_de_la_region():
    e = _ent(C.calcular(_portafolio(), CFG, grupo_valor="Cardio"))
    assert e["AR"]["siguiente_motor"] == f"Activar combinaciones dobles ({DOBLE_A})"
    assert e["CL"]["siguiente_motor"] == f"Activar triple terapia ({TRIPLE})"
    assert e["MX"]["siguiente_motor"] == "Consolidar el mix actual"


def test_los_kpis_traen_la_concentracion_y_el_peso_de_las_combinaciones():
    r = C.calcular(_portafolio(), CFG, grupo_valor="Cardio")
    k = {x["kpi"]: x for x in r["kpis"]}
    assert k["concentracion_top"]["valor"] == pytest.approx((300 + 120 + 100) / 600)
    assert "MX, CL, AR" in k["concentracion_top"]["texto"]
    assert k["combinaciones"]["valor"] == pytest.approx((180 + 80 + 60) / 600)


def test_la_lectura_estrategica_trae_escala_direccion_y_diversidad():
    r = C.calcular(_portafolio(), CFG, grupo_valor="Cardio")
    bloques = [x["bloque"] for x in r["lectura"]]
    assert bloques == ["ESCALA", "DIRECCIÓN", "DIVERSIDAD"]
    assert "~87%" in r["lectura"][0]["titulo"]
    # BO mezcla mitad monoterapia y mitad triple: índice 0,5, el más alto
    assert "0,00 (AR)" in r["lectura"][2]["texto"] and "0,50 (BO)" in r["lectura"][2]["texto"]


def test_la_banda_de_acciones_agrupa_proteger_acelerar_desarrollar():
    r = C.calcular(_portafolio(), CFG, grupo_valor="Cardio")
    assert r["acciones"]["proteger"] == ["MX", "CL", "AR"]
    assert set(r["preguntas"]) == {"proteger", "acelerar", "desarrollar"}


def test_sin_filtro_de_grupo_sale_la_contribucion_por_area_terapeutica():
    r = C.calcular(_portafolio(), CFG)
    g = {x["grupo"]: x for x in r["grupos"]}
    assert g["SNC"]["contribucion"] == pytest.approx(400 / 1000)
    assert g["Cardio"]["principales"].startswith("MX 50%")


def test_sin_mix_el_eje_x_es_el_crecimiento_contra_el_periodo_anterior():
    df = pd.DataFrame({"marca": ["A", "B", "A", "B"], "ventas": [100, 100, 150, 50],
                       "anio": [2025, 2025, 2026, 2026]})
    r = C.calcular(df, C.Config(entidad="marca", valor="ventas", periodo="anio", etiqueta="marcas"))
    e = _ent(r)
    assert r["eje_x"] == "crecimiento" and r["zonas_x"] == ["Cae", "Estable", "Crece"]
    assert e["A"]["crecimiento"] == pytest.approx(0.5) and e["B"]["crecimiento"] == pytest.approx(-0.5)
    assert e["A"]["contribucion"] == pytest.approx(0.75)     # se mide sobre el último período
    assert r["lectura"][1]["titulo"] == "1 de 2 crecen"


def test_sin_mix_ni_periodo_se_explica_que_falta():
    with pytest.raises(ValueError, match="mix .*período"):
        C.calcular(_portafolio(), C.Config(entidad="pais", valor="ventas"))


def test_una_columna_inexistente_se_nombra():
    with pytest.raises(ValueError, match="no_existe"):
        C.calcular(_portafolio(), C.Config(entidad="no_existe", valor="ventas", mix="presentacion"))


def test_presentaciones_sin_escalon_reconocible_avisan_que_pasen_niveles():
    df = _portafolio().assign(presentacion=lambda d: d["presentacion"].str.replace("/", " "))
    r = C.calcular(df, CFG, grupo_valor="Cardio")
    assert "niveles_mix" in r["aviso"]
    cfg = C.Config(**{**CFG.__dict__, "niveles_mix": {"Alfa Diurético": 2, "Alfa Calcio": 2,
                                                      "Alfa Calcio Diurético": 3}})
    assert "aviso" not in C.calcular(df, cfg, grupo_valor="Cardio")
