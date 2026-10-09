"""El «siguiente mejor contenido» dentro de lo permitido, los KPIs, la auditoría y los derechos."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from app.core import relacionamiento as R

EJEMPLOS = Path(__file__).resolve().parents[2] / "examples"


def _ct(i: str, **kw) -> dict:
    base = {"id_contacto": i, "pais": "Uruguay", "tipo": "paciente", "consiente_contacto": "si",
            "consiente_marketing": "si", "consiente_salud": "si", "consiente_perfilado": "si",
            "doble_optin": "si", "baja": "no", "areas_interes": "Cardio", "productos_recetados": "Vasotril"}
    return {**base, **kw}


CONTENIDOS = pd.DataFrame([
    {"id_contenido": "A", "titulo": "Presión", "tipo": "concientizacion", "area_terapeutica": "Cardio"},
    {"id_contenido": "B", "titulo": "Programa", "tipo": "programa_paciente", "area_terapeutica": "Cardio",
     "producto": "Vasotril", "condicion_venta": "receta"},
    {"id_contenido": "C", "titulo": "Marca Rx", "tipo": "promocion_marca", "area_terapeutica": "Cardio",
     "producto": "Vasotril", "condicion_venta": "receta"},
    {"id_contenido": "D", "titulo": "Caminar", "tipo": "concientizacion"},
])


def _ev(c: str, k: str, fecha: str, *eventos: str) -> list[dict]:
    return [{"id_contacto": c, "id_contenido": k, "fecha": fecha, "evento": e} for e in eventos]


def test_nunca_recomienda_lo_que_no_se_puede_enviar():
    r = R.analizar(pd.DataFrame([_ct("1"), _ct("2", consiente_salud="no")]), CONTENIDOS, hoy="2026-10-01")
    rec = r["recomendaciones"]
    assert "C" not in set(rec["id_contenido"])          # promoción Rx a un paciente
    assert set(rec.loc[rec["id_contacto"] == "2", "id_contenido"]) == {"D"}   # sin salud: sólo lo general
    assert rec.loc[rec["id_contacto"] == "1", "id_contenido"].iloc[0] == "B"  # el programa pesa más


def test_no_repite_lo_enviado_hace_poco_ni_lo_ya_convertido_ni_lo_que_genero_queja():
    inter = pd.DataFrame(_ev("1", "A", "2026-09-20", "envio") + _ev("1", "B", "2026-03-01", "envio", "inscripcion")
                         + _ev("1", "D", "2026-01-01", "envio", "queja"))
    r = R.analizar(pd.DataFrame([_ct("1")]), CONTENIDOS, inter, hoy="2026-10-01")
    assert r["recomendaciones"].empty
    # Pasada la ventana de 30 días, «A» vuelve a ser candidato.
    r = R.analizar(pd.DataFrame([_ct("1")]), CONTENIDOS, inter, hoy="2026-11-15")
    assert list(r["recomendaciones"]["id_contenido"]) == ["A"]


def test_respeta_el_tope_de_frecuencia_del_pais():
    inter = pd.DataFrame(_ev("1", "X1", "2026-09-25", "envio") + _ev("1", "X2", "2026-09-26", "envio"))
    r = R.analizar(pd.DataFrame([_ct("1")]), CONTENIDOS, inter, hoy="2026-10-01",
                   ajustes={"Uruguay": {"frecuencia_max_30d": 3}})
    assert len(r["recomendaciones"]) == 1


def test_una_baja_registrada_en_un_envio_se_respeta_aunque_el_crm_no_la_tenga():
    inter = pd.DataFrame(_ev("1", "A", "2026-05-01", "envio", "baja"))
    r = R.analizar(pd.DataFrame([_ct("1")]), CONTENIDOS, inter, hoy="2026-10-01")
    assert r["recomendaciones"].empty
    assert any("registrarla en el CRM" in a for a in r["avisos"])
    # Lo enviado antes de la baja estaba bien: no es un envío irregular.
    assert r["envios_no_elegibles"].empty


def test_la_auditoria_marca_lo_enviado_que_hoy_no_cumple():
    inter = pd.DataFrame(_ev("1", "C", "2026-09-01", "envio"))
    r = R.analizar(pd.DataFrame([_ct("1")]), CONTENIDOS, inter, hoy="2026-10-01")
    aud = r["envios_no_elegibles"]
    assert list(aud["motivo"]) == ["receta_al_publico"] and aud["envios"].iloc[0] == 1
    assert any("compliance" in a for a in r["avisos"])


def test_el_filtrado_colaborativo_solo_personaliza_con_consentimiento_de_perfilado():
    # A cuatro personas que abrieron «A» también les interesó «D»: patrón «a quienes les interesó…».
    otros = [_ct(str(i)) for i in range(10, 14)]
    inter = []
    for c in otros:
        inter += _ev(c["id_contacto"], "A", "2026-06-01", "envio", "clic")
        inter += _ev(c["id_contacto"], "D", "2026-06-02", "envio", "clic")
    inter += _ev("1", "A", "2026-06-01", "envio", "clic") + _ev("2", "A", "2026-06-01", "envio", "clic")
    gente = pd.DataFrame([*otros, _ct("1"), _ct("2", consiente_perfilado="no")])
    rec = R.analizar(gente, CONTENIDOS, pd.DataFrame(inter), hoy="2026-10-01")["recomendaciones"]
    d1 = rec[(rec["id_contacto"] == "1") & (rec["id_contenido"] == "D")].iloc[0]
    d2 = rec[(rec["id_contacto"] == "2") & (rec["id_contenido"] == "D")].iloc[0]
    assert "a quienes les interesó «Presión»" in d1["motivo"] and d1["personalizado"]
    assert "a quienes les interesó" not in d2["motivo"] and not d2["personalizado"]
    assert d1["puntaje"] > d2["puntaje"]


def test_embudo_y_kpis_por_contenido():
    inter = pd.DataFrame(_ev("1", "A", "2026-09-01", "envio", "apertura", "clic")
                         + _ev("2", "A", "2026-09-01", "envio") + _ev("1", "B", "2026-09-02", "envio", "inscripcion"))
    r = R.analizar(pd.DataFrame([_ct("1"), _ct("2"), _ct("3", consiente_contacto="no", pais="Chile")]),
                   CONTENIDOS, inter, hoy="2026-10-01")
    tot = r["embudo"].set_index("pais").loc["Total"]
    assert (tot["captados"], tot["contactables"], tot["alcanzados"], tot["activos"], tot["convertidos"]) == (3, 2, 2, 1, 1)
    k = r["contenidos"].set_index("id_contenido")
    assert k.loc["A", "envios"] == 2 and k.loc["A", "ctr"] == pytest.approx(0.5)
    assert k.loc["B", "tasa_conversion"] == pytest.approx(1.0)
    assert pd.isna(k.loc["C", "ctr"])            # sin envíos no hay tasa, ni infinito ni error


def test_interacciones_invalidas_y_de_contactos_suprimidos_se_avisan():
    inter = pd.DataFrame(_ev("1", "A", "2026-09-01", "envio", "like") + _ev("1", "A", "no-es-fecha", "envio")
                         + _ev("99", "A", "2026-09-01", "envio"))
    r = R.analizar(pd.DataFrame([_ct("1")]), CONTENIDOS, inter, hoy="2026-10-01")
    texto = " ".join(r["avisos"])
    assert "eventos desconocidos" in texto and "sin fecha" in texto and "no están en la base" in texto


def test_tope_de_tamano():
    with pytest.raises(ValueError, match="Partí la base"):
        R.analizar(pd.DataFrame([_ct(str(i)) for i in range(5)]), CONTENIDOS, max_celdas=10)


def test_suprimir_y_acceso():
    ct = pd.DataFrame([_ct("1"), _ct("2")])
    inter = R.preparar_interacciones(pd.DataFrame(_ev("1", "A", "2026-09-01", "envio")))[0]
    from app.core import consentimiento as K
    ctp = K.preparar_contactos(ct)[0]
    a = R.acceso(ctp, inter, "1")
    assert a["datos"]["areas_interes"] == ["cardio"] and len(a["interacciones"]) == 1
    ct2, in2, lista = R.suprimir(ctp, inter, ["1"])
    assert list(ct2["id_contacto"]) == ["2"] and in2.empty
    assert lista == [R.huella("1")] and len(lista[0]) == 64
    with pytest.raises(KeyError):
        R.acceso(ct2, in2, "1")


def test_el_ejemplo_sintetico_corre_entero_y_sale_a_json():
    r = R.analizar(pd.read_csv(EJEMPLOS / "relacionamiento_contactos.csv"),
                   pd.read_csv(EJEMPLOS / "relacionamiento_contenidos.csv"),
                   pd.read_csv(EJEMPLOS / "relacionamiento_interacciones.csv"))
    rec = r["recomendaciones"]
    assert not rec.empty and rec.groupby("id_contacto").size().max() <= 3
    # Ningún paciente recibe promoción de un producto bajo receta.
    rx = set(r["contenidos"].query("tipo == 'promocion_marca'")["id_contenido"]) & {"K-07"}
    pacientes = set(pd.read_csv(EJEMPLOS / "relacionamiento_contactos.csv").query("tipo != 'profesional'")["id_contacto"])
    assert rec[rec["id_contenido"].isin(rx) & rec["id_contacto"].isin(pacientes)].empty
    j = R.a_json(r, max_recomendaciones=50)
    assert len(j["recomendaciones"]) == 50 and isinstance(j["embudo"], list)
    assert all(v is None or v == v for f in j["contenidos"] for v in f.values())   # sin NaN
