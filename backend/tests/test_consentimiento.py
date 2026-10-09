"""Reglas de la base propia: consentimiento por finalidad, minimización y leyes sanitarias por país."""
from __future__ import annotations

import pandas as pd
import pytest
from app.core import consentimiento as K


def _contacto(**kw) -> dict:
    base = {"id_contacto": "C1", "pais": "Uruguay", "tipo": "paciente", "consiente_contacto": "si",
            "consiente_marketing": "si", "consiente_salud": "si", "consiente_perfilado": "si",
            "doble_optin": "si", "baja": "no", "areas_interes": "Cardiometabólica",
            "productos_recetados": "Vasotril"}
    return {**base, **kw}


def _contenido(**kw) -> dict:
    base = {"id_contenido": "K1", "titulo": "t", "tipo": "concientizacion",
            "area_terapeutica": "Cardiometabólica", "producto": "", "condicion_venta": "",
            "audiencia": "publico", "paises": "*"}
    return {**base, **kw}


def _motivo(contacto: dict, contenido: dict, ajustes: dict | None = None) -> str:
    ct, _ = K.preparar_contactos(pd.DataFrame([contacto]))
    co = K.preparar_contenidos(pd.DataFrame([contenido]))
    return K.matriz_elegibilidad(ct, co, ajustes)["motivo"].iloc[0]


def test_un_paciente_con_todo_consentido_recibe_concientizacion_de_su_area():
    assert _motivo(_contacto(), _contenido()) == ""


def test_la_promocion_de_un_medicamento_bajo_receta_nunca_le_llega_a_un_paciente():
    rx = _contenido(tipo="promocion_marca", producto="Vasotril", condicion_venta="Rx", audiencia="todos")
    assert _motivo(_contacto(), rx) == "receta_al_publico"
    assert _motivo(_contacto(tipo="profesional"), rx) == ""


def test_la_venta_libre_si_se_puede_promocionar_al_publico_con_consentimiento_comercial():
    otc = _contenido(tipo="promocion_marca", area_terapeutica="", producto="Vitalix", condicion_venta="OTC")
    assert _motivo(_contacto(), otc) == ""
    assert _motivo(_contacto(consiente_marketing="no"), otc) == "sin_consentimiento_marketing"


def test_una_condicion_de_venta_desconocida_se_trata_como_receta():
    raro = _contenido(tipo="promocion_marca", producto="X", condicion_venta="magistral")
    assert _motivo(_contacto(), raro) == "receta_al_publico"


@pytest.mark.parametrize("valor", ["", None, "quizás", "0"])
def test_un_consentimiento_vacio_o_dudoso_no_se_presume(valor):
    assert _motivo(_contacto(consiente_contacto=valor), _contenido()) == "sin_consentimiento_contacto"


def test_la_baja_gana_a_todo_lo_demas():
    assert _motivo(_contacto(baja="si", consiente_contacto="no"), _contenido()) == "baja"


def test_no_se_infiere_un_area_que_la_persona_no_declaro():
    assert _motivo(_contacto(areas_interes="Diabetes"), _contenido()) == "area_no_declarada"


def test_el_programa_de_pacientes_exige_la_receta_declarada():
    prog = _contenido(tipo="programa_paciente", producto="Glucofin", audiencia="paciente")
    assert _motivo(_contacto(), prog) == "programa_sin_receta_declarada"
    assert _motivo(_contacto(productos_recetados="Glucofin; Vasotril"), prog) == ""


def test_un_beneficio_de_un_producto_bajo_receta_tambien_exige_la_receta_y_no_va_a_profesionales():
    ben = _contenido(tipo="beneficio", producto="Glucofin", condicion_venta="receta", audiencia="paciente")
    assert _motivo(_contacto(), ben) == "programa_sin_receta_declarada"
    assert _motivo(_contacto(tipo="profesional"), ben) == "audiencia"


def test_la_educacion_medica_es_solo_para_profesionales():
    edu = _contenido(tipo="educacion_medica", audiencia="profesional")
    assert _motivo(_contacto(), edu) == "audiencia"
    # Al profesional no se le piden datos de salud propios para recibirla.
    assert _motivo(_contacto(tipo="profesional", consiente_salud="no", areas_interes=""), edu) == ""


def test_el_doble_optin_se_exige_solo_donde_legal_lo_configuro():
    sin = _contacto(doble_optin="no")
    assert _motivo(sin, _contenido()) == ""
    assert _motivo(sin, _contenido(), {"Uruguay": {"doble_optin_obligatorio": True}}) == "sin_doble_optin"


def test_el_pais_acepta_alias_y_acentos():
    mx = _contenido(paises="MX; Brasil")
    assert _motivo(_contacto(pais="México"), mx) == ""
    assert _motivo(_contacto(pais="mexico"), mx) == ""
    assert _motivo(_contacto(pais="Uruguay"), mx) == "pais"


def test_las_columnas_que_identifican_a_la_persona_se_descartan():
    df = pd.DataFrame([_contacto(email="a@b.com", telefono="099", nombre="Ana")])
    ct, avisos = K.preparar_contactos(df)
    assert not {"email", "telefono", "nombre"} & set(ct.columns)
    assert any("id seudónimo" in a for a in avisos)


def test_los_datos_de_salud_sin_consentimiento_de_salud_no_se_usan():
    ct, avisos = K.preparar_contactos(pd.DataFrame([_contacto(consiente_salud="no")]))
    assert ct["areas_interes"].iloc[0] == frozenset()
    assert ct["productos_recetados"].iloc[0] == frozenset()
    assert any("sin consentimiento de salud" in a for a in avisos)


def test_contactos_repetidos_vale_la_ultima_fila():
    df = pd.DataFrame([_contacto(baja="no"), _contacto(baja="si")])
    ct, avisos = K.preparar_contactos(df)
    assert len(ct) == 1 and bool(ct["baja"].iloc[0])
    assert any("repetido" in a for a in avisos)


def test_faltan_columnas_obligatorias():
    with pytest.raises(ValueError, match="pais"):
        K.preparar_contactos(pd.DataFrame([{"id_contacto": "1"}]))
    with pytest.raises(ValueError, match="tipo"):
        K.preparar_contenidos(pd.DataFrame([{"id_contenido": "1"}]))
    with pytest.raises(ValueError, match="desconocidos"):
        K.preparar_contenidos(pd.DataFrame([_contenido(tipo="spam")]))


def test_politica_por_defecto_es_conservadora_y_los_ajustes_validos_se_aplican():
    p = K.politica("Argentina")
    assert (p.autoridad_sanitaria, p.promocion_receta_a_publico, p.validado_por_legal) == ("ANMAT", False, False)
    q = K.politica("ar", {"Argentina": {"frecuencia_max_30d": 2, "validado_por_legal": True, "cualquiera": 1}})
    assert (q.pais, q.frecuencia_max_30d, q.validado_por_legal) == ("Argentina", 2, True)
    otro = K.politica("Narnia")
    assert otro.pais == "Narnia" and not otro.promocion_receta_a_publico


def test_matriz_vacia_sin_contenidos():
    ct, _ = K.preparar_contactos(pd.DataFrame([_contacto()]))
    co = K.preparar_contenidos(pd.DataFrame(columns=["id_contenido", "tipo"]))
    assert K.matriz_elegibilidad(ct, co).empty


def test_las_plantillas_pasan_sus_propias_validaciones():
    t = K.plantillas()
    ct, _ = K.preparar_contactos(t["contactos"])
    co = K.preparar_contenidos(t["contenidos"])
    assert K.matriz_elegibilidad(ct, co)["motivo"].iloc[0] == ""


def test_cada_motivo_tiene_su_etiqueta_corta_en_los_tres_idiomas():
    import json
    from pathlib import Path
    i18n = Path(__file__).resolve().parents[2] / "frontend" / "assets" / "i18n"
    for lang in ("es", "en", "pt"):
        rel = json.loads((i18n / f"{lang}.json").read_text(encoding="utf-8"))["rel"]
        faltan = [m for m in K.MOTIVOS if f"mot_{m}" not in rel]
        assert not faltan, f"{lang}: faltan etiquetas para {faltan}"


# ── bordes que encontró la revisión ─────────────────────────────────────────
def test_con_producto_y_sin_condicion_de_venta_se_asume_receta():
    sin = _contenido(tipo="promocion_marca", producto="Xarelto", condicion_venta="")
    assert _motivo(_contacto(), sin) == "receta_al_publico"
    ben = _contenido(tipo="beneficio", producto="Xarelto", condicion_venta=None, audiencia="paciente")
    assert _motivo(_contacto(productos_recetados=""), ben) == "programa_sin_receta_declarada"


def test_ningun_tipo_de_contenido_nombra_un_producto_bajo_receta_al_publico():
    marca_en_concientizacion = _contenido(tipo="concientizacion", producto="Xarelto", condicion_venta="receta",
                                          area_terapeutica="")
    assert _motivo(_contacto(), marca_en_concientizacion) == "receta_al_publico"
    # La concientización sin marca sí, aunque el área tenga productos bajo receta.
    assert _motivo(_contacto(), _contenido(condicion_venta="receta")) == ""


@pytest.mark.parametrize("valor,es_baja", [(1.0, True), (1, True), (float("nan"), False), (0.0, False),
                                           ("pendiente", True), ("no", False)])
def test_la_baja_numerica_o_dudosa_se_respeta(valor, es_baja):
    ct, avisos = K.preparar_contactos(pd.DataFrame([_contacto(baja=valor)]))
    assert bool(ct["baja"].iloc[0]) is es_baja
    assert any("no se entendieron" in a for a in avisos) is (valor == "pendiente")


def test_consentimientos_numericos():
    ct, _ = K.preparar_contactos(pd.DataFrame([_contacto(consiente_contacto=1.0, consiente_marketing=0.0)]))
    assert bool(ct["consiente_contacto"].iloc[0]) and not bool(ct["consiente_marketing"].iloc[0])


def test_los_ids_se_comparan_igual_entre_tablas():
    assert list(K.normalizar_id(pd.Series([1.0, 2, "C-3", " 4 "]))) == ["1", "2", "C-3", "4"]


@pytest.mark.parametrize("clave", ["Mexico", "MX", "méxico"])
def test_el_ajuste_de_legal_vale_aunque_el_pais_se_escriba_distinto(clave):
    for pais in ("México", "MX"):
        assert _motivo(_contacto(pais=pais, doble_optin="no"), _contenido(),
                       {clave: {"doble_optin_obligatorio": True}}) == "sin_doble_optin"


def test_audiencias_con_sinonimos_y_desconocidas():
    otc_hcp = _contenido(tipo="promocion_marca", producto="Vitalix", condicion_venta="OTC", audiencia="Médicos",
                         area_terapeutica="")
    assert _motivo(_contacto(), otc_hcp) == "audiencia"
    with pytest.raises(ValueError, match="Audiencia desconocida"):
        K.preparar_contenidos(pd.DataFrame([_contenido(audiencia="marcianos")]))


def test_tablas_vacias_paises_en_blanco_y_contenidos_repetidos():
    with pytest.raises(ValueError, match="vacía"):
        K.preparar_contactos(pd.DataFrame(columns=["id_contacto", "pais"]))
    ct, _ = K.preparar_contactos(pd.DataFrame([_contacto(pais=None)]))
    assert ct["pais"].iloc[0] == "(sin país)"
    with pytest.raises(ValueError, match="repetido"):
        K.preparar_contenidos(pd.DataFrame([_contenido(), _contenido()]))
