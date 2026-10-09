"""Etapa 1: las reglas por país que valida legal, con firma, historial y planilla."""
from __future__ import annotations

import io
import uuid

import pandas as pd
import pytest
from app.core import politicas_legales as PL
from app.core import programa_relacionamiento as PR
from app.core import workspace


@pytest.fixture()
def ws():
    """Cada prueba en su propio workspace: lo que valida una no le cambia las reglas a otra."""
    nombre = f"legal-{uuid.uuid4().hex[:8]}"
    workspace.create(nombre)
    token = workspace.activate(nombre)
    yield nombre
    workspace.deactivate(token)


def test_sin_validar_se_usan_los_valores_conservadores(ws):
    uy = next(p for p in PL.vigentes() if p["pais"] == "Uruguay")
    assert (uy["promocion_receta_a_publico"], uy["validado_por_legal"], uy["validado_por"]) == (False, False, None)
    assert {"Argentina", "Brasil", "México"} <= {p["pais"] for p in PL.vigentes()}


def test_validar_un_pais_guarda_firma_y_historial(ws):
    r = PL.guardar("uy", {"frecuencia_max_30d": 2, "doble_optin_obligatorio": "sí"},
                   validado_por="Dra. Pérez (Legal)", norma="Ley 18.331, art. 9")
    assert (r["pais"], r["frecuencia_max_30d"], r["doble_optin_obligatorio"]) == ("Uruguay", 2, True)
    assert r["validado_por_legal"] and r["validado_por"] == "Dra. Pérez (Legal)" and r["fecha_validacion"]
    h = PL.historial()[0]
    assert h["pais"] == "Uruguay" and {c["campo"] for c in h["cambios"]} == {"frecuencia_max_30d", "doble_optin_obligatorio"}
    assert next(c for c in h["cambios"] if c["campo"] == "frecuencia_max_30d") == {
        "campo": "frecuencia_max_30d", "antes": 4, "despues": 2}


def test_relajar_una_regla_sin_firma_se_rechaza(ws):
    with pytest.raises(ValueError, match="firma de legal"):
        PL.guardar("Argentina", {"promocion_receta_a_publico": True})
    with pytest.raises(ValueError, match="firma de legal"):
        PL.guardar("Argentina", {"frecuencia_max_30d": 10})
    # Endurecer sí se puede sin firma (bajar el tope es más prudente).
    assert PL.guardar("Argentina", {"frecuencia_max_30d": 2})["frecuencia_max_30d"] == 2


def test_valores_invalidos(ws):
    with pytest.raises(ValueError, match="entre 0 y 30"):
        PL.guardar("Chile", {"frecuencia_max_30d": 99}, validado_por="x")
    with pytest.raises(ValueError, match="no es sí ni no"):
        PL.guardar("Chile", {"doble_optin_obligatorio": "quizás"}, validado_por="x")
    with pytest.raises(ValueError, match="Campo desconocido"):
        PL.guardar("Chile", {"pais": "Narnia"}, validado_por="x")


def test_el_analisis_usa_lo_validado_en_su_workspace(ws):
    contactos = pd.DataFrame([{"id_contacto": "1", "pais": "Uruguay", "consiente_contacto": "si", "doble_optin": "no"}])
    contenidos = pd.DataFrame([{"id_contenido": "A", "tipo": "concientizacion"}])
    assert len(PR.analizar(contactos, contenidos)["recomendaciones"]) == 1
    PL.guardar("Uruguay", {"doble_optin_obligatorio": True}, validado_por="Legal")
    r = PR.analizar(contactos, contenidos)
    assert r["recomendaciones"].empty
    assert r["politicas"].set_index("pais").loc["Uruguay", "validado_por_legal"]
    # Un escenario del pedido se suma encima sin tocar lo guardado.
    r = PR.analizar(contactos, contenidos, ajustes={"Uruguay": {"doble_optin_obligatorio": False}})
    assert len(r["recomendaciones"]) == 1
    assert PL.ajustes()["Uruguay"]["doble_optin_obligatorio"] is True


def test_la_planilla_va_y_vuelve_y_solo_aplica_lo_firmado(ws):
    df = pd.read_excel(io.BytesIO(PL.planilla(["Uruguay", "Chile"])), sheet_name="Validación legal", dtype=object)
    assert set(df["pais"]) == {"Uruguay", "Chile"} and len(df) == 2 * len(PL.CAMPOS)
    df = df.astype(object)
    uy = (df["pais"] == "Uruguay") & (df["regla"] == "frecuencia_max_30d")
    df.loc[uy, ["valor_validado", "validado_por", "norma_o_fuente"]] = [3, "Legal UY", "Ley 18.331"]
    cl = (df["pais"] == "Chile") & (df["regla"] == "frecuencia_max_30d")
    df.loc[cl, "valor_validado"] = 9                     # sin firma: no se aplica
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name="Validación legal", index=False)
    r = PL.importar_planilla(buf.getvalue())
    assert r["aplicadas"] == [{"pais": "Uruguay", "validado_por": "Legal UY", "reglas": 1}]
    assert r["sin_firma"] == len(df) - 1 and not r["errores"]
    vig = {p["pais"]: p for p in PL.vigentes(["Uruguay", "Chile"])}
    assert vig["Uruguay"]["frecuencia_max_30d"] == 3 and vig["Uruguay"]["norma"] == "Ley 18.331"
    assert vig["Chile"]["frecuencia_max_30d"] == 4


def test_una_planilla_que_no_es_la_de_validacion_se_rechaza(ws):
    buf = io.BytesIO()
    pd.DataFrame({"a": [1]}).to_excel(buf, index=False)
    with pytest.raises(ValueError, match="Validación legal"):
        PL.importar_planilla(buf.getvalue())


def test_api_de_politicas(client):
    nombre = f"legal-api-{uuid.uuid4().hex[:6]}"
    h = {"X-Workspace": nombre}
    assert client.post("/api/workspaces", json={"name": nombre}).status_code in (200, 201)
    r = client.put("/api/relacionamiento/politicas/México", json={"cambios": {"promocion_receta_a_publico": True}},
                   headers=h)
    assert r.status_code == 400 and "firma" in r.json()["detail"]
    r = client.put("/api/relacionamiento/politicas/México", json={"cambios": {"frecuencia_max_30d": 2},
                                                                   "validado_por": "Legal MX"}, headers=h)
    assert r.status_code == 200 and r.json()["frecuencia_max_30d"] == 2
    j = client.get("/api/relacionamiento/politicas", headers=h).json()
    assert j["historial"][0]["pais"] == "México"
    x = client.get("/api/relacionamiento/politicas/planilla", headers=h)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    r = client.post("/api/relacionamiento/politicas/planilla", headers=h,
                    files={"file": ("p.xlsx", x.content)})
    assert r.status_code == 200 and r.json()["aplicadas"] == []
