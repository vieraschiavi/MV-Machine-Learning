"""Agente de mercado: propone supuestos con IA, los estudios mandan, y la lectura no miente.

Ninguna prueba sale a internet: el motor de IA se reemplaza por una respuesta
fija. Lo que se fija es el comportamiento del agente alrededor de esa
respuesta: qué acepta, qué descarta, cómo marca el origen de cada número y qué
recomienda.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest
from app.core import agente_mercado as A
from app.core import ai
from app.core import mercado as M

CTX = A.Contexto(area_terapeutica="Cardiometabólica", molecula="Antihipertensivo X",
                 enfermedad="Hipertensión arterial", presentacion="40 mg, 1 comprimido por día",
                 paises=("AR", "UY"), segmentos=("Hombres", "Mujeres"))


def _respuesta(paises=("AR", "UY"), extra=None) -> str:
    sup = []
    for p in paises:
        for seg, diag in (("Hombres", 0.45), ("Mujeres", 0.65)):
            sup += [
                {"pais": p, "segmento": seg, "parametro": "poblacion", "valor": 1_000_000,
                 "fuente": "censo 2022"},
                {"pais": p, "segmento": seg, "parametro": "prevalencia", "valor": 35, "minimo": 30,
                 "maximo": 40, "fuente": "encuesta nacional de salud 2019"},
                {"pais": p, "segmento": seg, "parametro": "diagnosticados", "valor": diag,
                 "minimo": diag - 0.1, "maximo": diag + 0.1},
                {"pais": p, "segmento": seg, "parametro": "tratados", "valor": 0.7},
                {"pais": p, "segmento": seg, "parametro": "clase", "valor": 0.3},
                {"pais": p, "segmento": seg, "parametro": "precio_unidad", "valor": 0.4},
            ]
    sup += extra or []
    return "```json\n" + json.dumps({
        "supuestos": sup,
        "casuistica": [{"tema": "Subdiagnóstico", "lectura": "los hombres consultan menos"}],
        "latente": [{"pais": "AR", "segmento": "Hombres", "motivo": "no consultan"}],
        "advertencias": ["prevalencia autorreportada"],
    }) + "\n```"


class _IAFalsa(list):
    """Guarda las consignas recibidas; `texto` es lo que responde."""
    texto = ""


@pytest.fixture
def ia_falsa(monkeypatch):
    llamadas = _IAFalsa()
    llamadas.texto = _respuesta()

    def chat(provider, prompt, system=None, model=None, max_tokens=1200, **kw):
        llamadas.append(prompt)
        return {"ok": True, "text": llamadas.texto, "provider": "falso", "model": "m"}

    monkeypatch.setattr(ai, "chat", chat)
    return llamadas


# ── proponer ─────────────────────────────────────────────────────────────────

def test_la_consigna_cubre_la_casuistica_y_pide_no_inventar_citas(ia_falsa):
    A.proponer(CTX)
    prompt = ia_falsa[0]
    assert "Hipertensión arterial" in prompt and "40 mg" in prompt
    assert "síntomas y no consulta" in prompt
    assert "No inventes citas" in prompt


def test_todo_lo_propuesto_queda_marcado_como_ia_a_validar(ia_falsa):
    r = A.proponer(CTX)
    assert {s["origen"] for s in r["supuestos"]} == {A.ORIGEN_IA}
    assert r["avisos"][0] == A.AVISO_IA
    assert r["casuistica"][0]["tema"] == "Subdiagnóstico"


def test_las_tasas_que_vienen_en_porcentaje_se_corrigen(ia_falsa):
    r = A.proponer(CTX)
    prev = [s for s in r["supuestos"] if s["parametro"] == "prevalencia"]
    assert all(0 < s["valor"] < 1 for s in prev)


def test_lo_que_no_se_pidio_se_descarta(ia_falsa):
    ia_falsa.texto = _respuesta(extra=[
        {"pais": "BR", "segmento": "Hombres", "parametro": "prevalencia", "valor": 0.3},
        {"pais": "AR", "segmento": "Niños", "parametro": "prevalencia", "valor": 0.01}])
    r = A.proponer(CTX)
    assert {s["pais"] for s in r["supuestos"]} == {"AR", "UY"}
    assert {s["segmento"] for s in r["supuestos"]} == {"Hombres", "Mujeres"}


def test_una_respuesta_que_no_es_json_da_un_error_claro(ia_falsa):
    ia_falsa.texto = "No tengo datos para eso."
    with pytest.raises(A.AgenteError, match="JSON"):
        A.proponer(CTX)


def test_sin_supuestos_para_los_paises_pedidos_no_se_inventa_nada(ia_falsa):
    ia_falsa.texto = _respuesta(paises=("BR",))
    with pytest.raises(A.AgenteError, match="países y segmentos"):
        A.proponer(CTX)


def test_sin_motor_de_ia_configurado_el_error_lo_dice(monkeypatch):
    def chat(*a, **k):
        raise ai.AIError("No hay ningún proveedor de IA configurado.")
    monkeypatch.setattr(ai, "chat", chat)
    with pytest.raises(A.AgenteError, match="proveedor"):
        A.proponer(CTX)


# ── combinar: el estudio manda ───────────────────────────────────────────────

def test_el_estudio_de_mercado_pisa_lo_propuesto_por_la_ia(ia_falsa):
    prop = pd.DataFrame(A.proponer(CTX)["supuestos"])
    estudio = pd.DataFrame([{"pais": "AR", "segmento": "Hombres", "parametro": "diagnosticados",
                             "valor": 0.38, "fuente": "estudio propio 2026"}])
    tabla, avisos = A.combinar(prop, estudio)
    f = tabla[(tabla["pais"] == "AR") & (tabla["segmento"] == "Hombres")
              & (tabla["parametro"] == "diagnosticados")].iloc[0]
    assert f["valor"] == pytest.approx(0.38)
    assert f["origen"] == A.ORIGEN_ESTUDIO
    assert any("reemplazado" in a for a in avisos)
    assert len(tabla) == len(prop)


def test_el_nivel_de_evidencia_cuenta_lo_que_falta_validar(ia_falsa):
    prop = pd.DataFrame(A.proponer(CTX)["supuestos"])
    assert A.nivel_de_evidencia(prop)["nivel"] == "solo IA"
    est = prop.assign(origen=A.ORIGEN_ESTUDIO)
    assert A.nivel_de_evidencia(est)["nivel"] == "estudios"
    mixta, _ = A.combinar(prop, est.head(3).drop(columns="origen"))
    ev = A.nivel_de_evidencia(mixta)
    assert ev["nivel"] == "mixta" and ev["de_estudios"] == 3


def test_sin_nada_cargado_combinar_lo_dice():
    with pytest.raises(M.SupuestosInvalidos, match="estudio de mercado"):
        A.combinar(None, None)


# ── analizar ─────────────────────────────────────────────────────────────────

def test_el_analisis_lee_cada_pais_y_recomienda_que_validar(ia_falsa):
    sup = pd.DataFrame(A.proponer(CTX)["supuestos"])
    r = A.analizar(sup, plan=M.Lanzamiento(pico=0.1, meses_al_pico=12, horizonte=12),
                   inicio="2027-01", n_sim=300)
    assert [x["pais"] for x in r["lecturas"]] == ["AR", "UY"]
    assert r["medida_sensibilidad"] == "valor_clase"
    assert r["evidencia"]["nivel"] == "solo IA"
    assert any("validar" in x for x in r["recomendaciones"])
    assert any("hipótesis" in x for x in r["recomendaciones"])
    assert len([x for x in r["lanzamiento"] if x["pais"] == "Total"]) == 12
    assert "no de un backtest" in r["lanzamiento_nota"]


def test_mucho_subdiagnostico_lleva_a_desarrollar_y_nombra_el_segmento(ia_falsa):
    sup = pd.DataFrame(A.proponer(CTX)["supuestos"])
    lectura = A.analizar(sup, n_sim=100)["lecturas"][0]
    assert lectura["accion"] == "desarrollar"
    assert lectura["segmento_mas_latente"] == "Hombres"
    assert "Hombres" in lectura["lectura"]


def test_mercado_ya_tratado_lleva_a_proteger():
    filas = [{"pais": "CL", "segmento": "Total", "parametro": k, "valor": v} for k, v in
             {"poblacion": 1e6, "prevalencia": 0.2, "diagnosticados": 0.95, "tratados": 0.9}.items()]
    r = A.analizar(pd.DataFrame(filas), n_sim=50)
    assert r["lecturas"][0]["accion"] == "proteger"


def test_diagnosticados_sin_tratar_lleva_a_acelerar():
    filas = [{"pais": "PE", "segmento": "Total", "parametro": k, "valor": v} for k, v in
             {"poblacion": 1e6, "prevalencia": 0.2, "diagnosticados": 0.8, "tratados": 0.5}.items()]
    r = A.analizar(pd.DataFrame(filas), n_sim=50)
    assert r["lecturas"][0]["accion"] == "acelerar"


def test_el_analisis_incluye_el_contraste_con_lo_vendido(ia_falsa):
    sup = pd.DataFrame(A.proponer(CTX)["supuestos"])
    obs = pd.DataFrame({"pais": ["AR"], "unidades": [1e12]})
    r = A.analizar(sup, observado=obs, n_sim=50)
    assert r["contraste"][0]["estado"] == "imposible"


def test_la_narracion_usa_la_consigna_de_mercado(monkeypatch, ia_falsa):
    sup = pd.DataFrame(A.proponer(CTX)["supuestos"])
    r = A.analizar(sup, n_sim=50)
    ia_falsa.texto = "Lectura ejecutiva."
    out = A.narrar(r)
    assert out["text"] == "Lectura ejecutiva."
    assert "latente" in ia_falsa[-1] and "hipótesis" in ia_falsa[-1]
