"""Etapa 2: el libro de consentimientos (evidencia de cada sí y cada no) y el formulario de captación."""
from __future__ import annotations

import pandas as pd
import pytest
from app.core import programa_relacionamiento as PR
from app.core import registro_consentimientos as RC

V = RC.TEXTOS["es"]


def _ev(cid, finalidad, accion, fecha, version=None, canal="landing"):
    return {"id_contacto": cid, "finalidad": finalidad, "accion": accion, "fecha": fecha, "canal": canal,
            "version_texto": version if version is not None else V.get(finalidad, {}).get("version", "")}


def test_el_ultimo_evento_de_cada_finalidad_manda():
    libro, _ = RC.preparar(pd.DataFrame([
        _ev("1", "contacto", "otorga", "2026-01-01"), _ev("1", "marketing", "otorga", "2026-01-01"),
        _ev("1", "marketing", "retira", "2026-03-01"), _ev("1", "doble_optin", "confirma", "2026-01-02", ""),
    ]))
    st = RC.estado(libro).set_index("id_contacto").loc["1"]
    assert st["consiente_contacto"] and not st["consiente_marketing"] and st["doble_optin"] and not st["baja"]
    assert st["version_contacto"] == V["contacto"]["version"]


def test_una_baja_retira_todo_y_un_nuevo_si_la_levanta():
    eventos = [_ev("1", "contacto", "otorga", "2026-01-01"), _ev("1", "salud", "otorga", "2026-01-01"),
               _ev("1", "todas", "baja", "2026-02-01", "")]
    st = RC.estado(RC.preparar(pd.DataFrame(eventos))[0]).iloc[0]
    assert st["baja"] and not st["consiente_contacto"] and not st["consiente_salud"]
    eventos.append(_ev("1", "contacto", "otorga", "2026-05-01"))
    st = RC.estado(RC.preparar(pd.DataFrame(eventos))[0]).iloc[0]
    assert not st["baja"] and st["consiente_contacto"] and not st["consiente_salud"]


def test_el_orden_de_las_filas_no_importa_manda_la_fecha():
    a = RC.estado(RC.preparar(pd.DataFrame([_ev("1", "contacto", "retira", "2026-03-01"),
                                            _ev("1", "contacto", "otorga", "2026-01-01")]))[0])
    assert not a.iloc[0]["consiente_contacto"]


def test_eventos_invalidos_y_sin_version_se_avisan():
    _, avisos = RC.preparar(pd.DataFrame([_ev("1", "contacto", "otorga", "2026-01-01", version=""),
                                          _ev("1", "telepatia", "otorga", "2026-01-01"),
                                          _ev("2", "contacto", "otorga", "no-es-fecha")]))
    texto = " ".join(avisos)
    assert "2 evento(s)" in texto and "sin versión del texto" in texto
    with pytest.raises(ValueError, match="finalidad"):
        RC.preparar(pd.DataFrame([{"id_contacto": "1", "fecha": "2026-01-01"}]))


def test_el_libro_manda_sobre_la_tabla_en_el_analisis():
    contactos = pd.DataFrame([{"id_contacto": "1", "pais": "Uruguay", "consiente_contacto": "si"},
                              {"id_contacto": "2", "pais": "Uruguay", "consiente_contacto": "si"}])
    contenidos = pd.DataFrame([{"id_contenido": "A", "tipo": "concientizacion"}])
    libro = pd.DataFrame([_ev("1", "contacto", "otorga", "2026-01-01"), _ev("1", "contacto", "retira", "2026-02-01")])
    r = PR.analizar(contactos, contenidos, consentimientos=libro, politicas_guardadas=False)
    assert set(r["recomendaciones"]["id_contacto"]) == {"2"}            # el 1 retiró su consentimiento
    texto = " ".join(r["avisos"])
    assert "no respalda" in texto and "sin eventos en el libro" in texto
    t = PR.modelo(r)
    assert set(t["fact_consentimientos"]["accion"]) == {"otorga", "retira"}


def test_la_evidencia_trae_el_texto_exacto_que_se_acepto():
    libro = pd.DataFrame([_ev(1.0, "salud", "otorga", "2026-01-01T10:00:00Z")])
    ev = RC.evidencia(libro, "1")
    assert ev[0]["texto_aceptado"] == V["salud"]["texto"] and ev[0]["finalidad"] == "salud"


def test_cada_texto_tiene_su_version_y_cambiar_el_texto_cambia_la_version():
    versiones = {v["version"] for idioma in RC.TEXTOS.values() for v in idioma.values()}
    assert len(versiones) == 8
    assert RC.version(V["contacto"]["texto"] + " ") != V["contacto"]["version"]


def test_el_formulario_trae_las_cuatro_casillas_sin_marcar_y_envia_al_crm():
    html = RC.formulario_html("pt", accion="https://crm.adium.invalid/alta", aviso_privacidad="https://x/priv")
    assert html.count('type="checkbox"') == 4 and "checked" not in html
    assert 'action="https://crm.adium.invalid/alta"' in html and RC.TEXTOS["pt"]["salud"]["version"] in html
    assert 'name="consiente_contacto"' in html and "required" in html.split('name="consiente_contacto"')[1][:80]
    with pytest.raises(ValueError, match="Idioma"):
        RC.formulario_html("fr")
