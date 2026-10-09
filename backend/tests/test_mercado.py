"""Mercado actual y latente: el embudo epidemiológico que alimenta la proyección.

Lo que se fija acá es que las cuentas del embudo sean exactas (son
multiplicaciones: si fallan, fallan en silencio y en grande), que lo que falta
se reclame en vez de inventarse, que lo asumido por defecto quede a la vista,
y que la curva de lanzamiento y el contraste con la historia digan la verdad
sobre lo que miden.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.core import mercado as M


def _fila(pais, seg, param, valor, lo=None, hi=None, origen="estudio", fuente="sintético"):
    return {"pais": pais, "segmento": seg, "parametro": param, "valor": valor,
            "minimo": lo, "maximo": hi, "origen": origen, "fuente": fuente}


def _supuestos(con_rango: bool = False, precio: bool = True) -> pd.DataFrame:
    """Un país, dos segmentos: los hombres consultan menos (menos diagnóstico)."""
    r = (lambda v, d: (v - d, v + d)) if con_rango else (lambda v, d: (None, None))
    filas = []
    for seg, diag in (("Hombres", 0.5), ("Mujeres", 0.7)):
        filas += [
            _fila("AR", seg, "poblacion", 1_000_000),
            _fila("AR", seg, "prevalencia", 0.3, *r(0.3, 0.05)),
            _fila("AR", seg, "diagnosticados", diag, *r(diag, 0.1)),
            _fila("AR", seg, "tratados", 0.6),
            _fila("AR", seg, "clase", 0.4),
            _fila("AR", seg, "participacion", 0.1),
            _fila("AR", seg, "dosis_dia", 1),
            _fila("AR", seg, "dias_tratamiento", 365),
            _fila("AR", seg, "adherencia", 0.8),
        ]
        if precio:
            filas.append(_fila("AR", seg, "precio_unidad", 0.5))
    return pd.DataFrame(filas)


# ── el embudo: cuentas exactas ───────────────────────────────────────────────

def test_el_embudo_separa_mercado_actual_y_latente_con_cuentas_exactas():
    e = M.embudo(_supuestos()).set_index("segmento")
    h = e.loc["Hombres"]
    assert h["prevalentes"] == pytest.approx(300_000)
    assert h["sin_diagnostico"] == pytest.approx(150_000)
    assert h["sin_tratamiento"] == pytest.approx(60_000)
    assert h["tratados"] == pytest.approx(90_000)
    assert h["en_clase"] == pytest.approx(36_000)
    assert h["latente"] == pytest.approx(210_000)
    assert h["unidades_clase"] == pytest.approx(36_000 * 365 * 0.8)
    assert h["valor_clase"] == pytest.approx(36_000 * 365 * 0.8 * 0.5)
    assert h["unidades_marca"] == pytest.approx(36_000 * 365 * 0.8 * 0.1)


def test_el_segmento_que_consulta_menos_tiene_mas_mercado_latente():
    e = M.embudo(_supuestos()).set_index("segmento")
    assert e.loc["Hombres", "sin_diagnostico"] > e.loc["Mujeres", "sin_diagnostico"]
    assert e.loc["Hombres", "en_clase"] < e.loc["Mujeres", "en_clase"]


def test_el_latente_es_prevalentes_menos_tratados():
    e = M.embudo(_supuestos())
    assert np.allclose(e["latente"], e["sin_diagnostico"] + e["sin_tratamiento"])
    assert np.allclose(e["latente"], e["prevalentes"] - e["tratados"])


# ── lo que falta se reclama; lo asumido se avisa ─────────────────────────────

def test_si_falta_un_supuesto_obligatorio_se_dice_cual_y_donde():
    df = _supuestos()
    df = df[~((df["segmento"] == "Mujeres") & (df["parametro"] == "prevalencia"))]
    with pytest.raises(M.SupuestosInvalidos, match="Mujeres.*prevalencia"):
        M.embudo(df)


def test_lo_asumido_por_defecto_queda_avisado_y_no_callado():
    df = _supuestos()
    df = df[~df["parametro"].isin(["adherencia", "dosis_dia"])]
    r = M.potencial(df, n_sim=200)
    assert set(r["por_defecto"]) == {"adherencia", "dosis_dia"}
    assert any("adherencia = 1" in a for a in r["avisos"])


def test_las_tasas_en_porcentaje_se_pasan_a_fraccion_y_se_avisa():
    df = _supuestos()
    df.loc[df["parametro"] == "prevalencia", "valor"] = 30
    tabla, avisos = M.normalizar(df)
    assert tabla.loc[tabla["parametro"] == "prevalencia", "valor"].max() == pytest.approx(0.3)
    assert any("porcentaje" in a for a in avisos)


def test_minimo_y_maximo_desordenados_se_acomodan_alrededor_del_valor():
    df = pd.DataFrame([_fila("CL", "Total", "prevalencia", 0.2, 0.3, 0.1)])
    tabla, _ = M.normalizar(df)
    f = tabla.iloc[0]
    assert f["minimo"] <= f["valor"] <= f["maximo"]


def test_un_parametro_desconocido_se_ignora_con_aviso():
    df = pd.concat([_supuestos(), pd.DataFrame([_fila("AR", "Hombres", "magia", 3)])])
    _, avisos = M.normalizar(df)
    assert any("magia" in a for a in avisos)


def test_la_plantilla_trae_todos_los_parametros_por_pais_y_segmento():
    p = M.plantilla(["AR", "UY"], ["Hombres", "Mujeres"])
    assert len(p) == 2 * 2 * len(M.PARAMETROS)
    assert list(p.columns) == M.COLUMNAS


# ── incertidumbre ────────────────────────────────────────────────────────────

def test_sin_rango_el_p10_y_el_p90_coinciden_con_el_valor_central():
    r = M.potencial(_supuestos(), n_sim=300)
    tot = {x["medida"]: x for x in r["rango"] if x["pais"] == "Total"}
    assert tot["en_clase"]["p10"] == pytest.approx(tot["en_clase"]["p90"])
    assert tot["en_clase"]["p50"] == pytest.approx(36_000 + 0.3e6 * 0.7 * 0.6 * 0.4)


def test_con_rango_el_intervalo_se_abre_y_contiene_al_central():
    r = M.potencial(_supuestos(con_rango=True), n_sim=2000)
    tot = {x["medida"]: x for x in r["rango"] if x["pais"] == "Total"}["en_clase"]
    assert tot["p10"] < tot["p50"] < tot["p90"]
    assert "no es el error" in r["nota"].lower()


def test_la_simulacion_es_reproducible_con_la_misma_semilla():
    a = M.potencial(_supuestos(con_rango=True), n_sim=500, semilla=7)["rango"]
    b = M.potencial(_supuestos(con_rango=True), n_sim=500, semilla=7)["rango"]
    assert a == b


def test_el_tornado_ordena_por_cuanto_mueve_cada_supuesto():
    t = M.sensibilidad(_supuestos(con_rango=True))
    assert list(t["parametro"]) == ["diagnosticados", "prevalencia"]
    assert (t["bajo"] < t["base"]).all() and (t["alto"] > t["base"]).all()


# ── lanzamiento ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("forma", list(M.FORMAS))
def test_la_curva_llega_al_noventa_por_ciento_del_pico_en_los_meses_pedidos(forma):
    c = M.adopcion(48, 18, forma)
    assert c[17] == pytest.approx(0.9, abs=1e-6)
    assert np.all(np.diff(c) > 0) and c[-1] < 1


def test_una_forma_de_curva_desconocida_se_rechaza_con_las_opciones():
    with pytest.raises(ValueError, match="rapida"):
        M.adopcion(12, 6, "exponencial")


def test_el_lanzamiento_crece_hacia_el_pico_y_trae_rango():
    plan = M.Lanzamiento(pico=0.15, meses_al_pico=12, horizonte=24, pico_min=0.1, pico_max=0.2)
    df = M.lanzamiento(_supuestos(con_rango=True), plan, inicio="2027-01", n_sim=400)
    tot = df[df["pais"] == "Total"].reset_index(drop=True)
    assert tot["periodo"].iloc[0] == "2027-01" and len(tot) == 24
    assert tot["unidades_p50"].is_monotonic_increasing
    assert (tot["unidades_p10"] <= tot["unidades_p50"]).all()
    assert (tot["unidades_p50"] <= tot["unidades_p90"]).all()
    assert "valor_p50" in tot


def test_el_lanzamiento_al_pico_respeta_la_participacion_sobre_la_clase():
    plan = M.Lanzamiento(pico=0.2, meses_al_pico=6, horizonte=6)
    df = M.lanzamiento(_supuestos(), plan, n_sim=50)
    ultimo = df[(df["pais"] == "Total") & (df["mes"] == 6)].iloc[0]
    en_clase = M.embudo(_supuestos())["en_clase"].sum()
    assert ultimo["pacientes"] == pytest.approx(en_clase * 0.2 * 0.9, rel=1e-6)


def test_sin_precio_el_lanzamiento_no_inventa_valor():
    df = M.lanzamiento(_supuestos(precio=False), M.Lanzamiento(pico=0.1), n_sim=50)
    assert "valor_p50" not in df.columns
    assert "unidades_p50" in df.columns


def test_un_pico_fuera_de_rango_se_rechaza():
    with pytest.raises(ValueError, match="entre 0 y 1"):
        M.lanzamiento(_supuestos(), M.Lanzamiento(pico=15))


# ── contraste con la historia ────────────────────────────────────────────────

def test_ventas_que_cierran_con_los_supuestos_dan_coherente():
    esperado = M.embudo(_supuestos())["unidades_marca"].sum()
    r = M.contrastar(_supuestos(), pd.DataFrame({"pais": ["AR"], "unidades": [esperado * 1.1]}))
    assert r.iloc[0]["estado"] == "coherente"


def test_vender_mas_que_todo_el_mercado_tratado_es_imposible():
    techo = M.embudo(_supuestos())["unidades_clase"].sum()
    r = M.contrastar(_supuestos(), pd.DataFrame({"pais": ["AR"], "unidades": [techo * 2]}))
    assert r.iloc[0]["estado"] == "imposible"
    assert "subestimados" in r.iloc[0]["lectura"]


def test_una_proyeccion_por_historia_por_encima_del_techo_se_marca():
    e = M.embudo(_supuestos())
    obs = pd.DataFrame({"pais": ["AR"], "unidades": [e["unidades_marca"].sum()],
                        "proyectado": [e["unidades_clase"].sum() * 1.5]})
    r = M.contrastar(_supuestos(), obs).iloc[0]
    assert r["estado"] == "proyeccion fuera de techo"
    assert r["proyectado_sobre_techo"] == pytest.approx(1.5)


def test_un_pais_sin_supuestos_no_rompe_el_contraste():
    r = M.contrastar(_supuestos(), pd.DataFrame({"pais": ["PE"], "unidades": [10]}))
    assert r.iloc[0]["estado"] == "sin supuestos"
