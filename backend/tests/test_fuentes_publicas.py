"""Fuentes públicas y agregadas: censo y prevalencias por territorio, escucha social y el modelo para Fabric."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from app.core import consentimiento as K
from app.core import escucha as S
from app.core import modelo_fabric as F
from app.core import relacionamiento as R
from app.core import territorio as T

EJEMPLOS = Path(__file__).resolve().parents[2] / "examples"


def _censo() -> pd.DataFrame:
    filas = []
    for barrio, nse in (("Pocitos", "alto"), ("Cerro", "bajo")):
        for sexo in ("Mujeres", "Hombres"):
            filas.append({"pais": "Uruguay", "ciudad": "Montevideo", "barrio": barrio, "sexo": sexo,
                          "rango_edad": "40-59", "nse": nse, "poblacion": 1000})
            filas.append({"pais": "Uruguay", "ciudad": "Montevideo", "barrio": barrio, "sexo": sexo,
                          "rango_edad": "40-59", "nse": "medio", "poblacion": 100})
    return pd.DataFrame(filas)


def _contactos(n_pocitos: int, n_cerro: int) -> pd.DataFrame:
    filas = [{"id_contacto": f"P{i}", "pais": "Uruguay", "ciudad": "Montevideo", "barrio": "Pocitos",
              "sexo": "Mujeres", "rango_edad": "40-59", "consiente_contacto": "si", "consiente_salud": "si",
              "areas_interes": "Cardio"} for i in range(n_pocitos)]
    filas += [{"id_contacto": f"C{i}", "pais": "Uruguay", "ciudad": "Montevideo", "barrio": "cerro",
               "sexo": "Hombres", "rango_edad": "40-59", "consiente_contacto": "si", "consiente_salud": "no",
               "areas_interes": "Cardio"} for i in range(n_cerro)]
    return K.preparar_contactos(pd.DataFrame(filas))[0]


PREV = pd.DataFrame([{"pais": "Uruguay", "area_terapeutica": "Cardio", "sexo": "Total", "rango_edad": "Total",
                      "prevalencia": 0.3},
                     {"pais": "Uruguay", "area_terapeutica": "Cardio", "sexo": "Mujeres", "rango_edad": "40-59",
                      "prevalencia": 0.2}])


# ── territorio ──────────────────────────────────────────────────────────────
def test_el_nse_es_el_de_la_zona_declarada_no_uno_inferido_para_la_persona():
    ct = T.enriquecer(_contactos(1, 1), T.preparar_poblacion(_censo()))
    assert ct.set_index("id_contacto")["nse_zona"].to_dict() == {"P0": "alto", "C0": "bajo"}


def test_sin_zona_en_el_censo_queda_lo_que_traia_la_base():
    ct = _contactos(1, 0).assign(nse_zona="medio", barrio="Narnia", ciudad="Otra")
    assert T.enriquecer(ct, T.preparar_poblacion(_censo()))["nse_zona"].iloc[0] == "medio"


def test_cobertura_usa_la_prevalencia_por_sexo_y_edad_y_si_no_la_total():
    cob = T.cobertura(_contactos(12, 12), T.preparar_poblacion(_censo()), T.preparar_prevalencias(PREV),
                      "cardio", por_barrio=True, segmentar=("sexo",)).set_index(["barrio", "sexo"])
    assert cob.loc[("Pocitos", "Mujeres"), "casos_estimados"] == 220        # 1100 × 0,20
    assert cob.loc[("Pocitos", "Hombres"), "casos_estimados"] == 330        # 1100 × 0,30 (total)
    assert cob.loc[("Pocitos", "Mujeres"), "captados_area"] == 12
    # Sin consentimiento de salud no se cuentan como captados del área (el dato se borró al prepararlos).
    assert cob.loc[("Cerro", "Hombres"), "captados_area"] == 0


def test_las_celdas_chicas_no_se_publican_ni_por_la_brecha():
    cob = T.cobertura(_contactos(3, 0), T.preparar_poblacion(_censo()), T.preparar_prevalencias(PREV),
                      "Cardio", por_barrio=True).set_index("barrio")
    fila = cob.loc["Pocitos"]
    assert fila["en_base"] == "<10" and fila["captados_area"] == "<10" and pd.isna(fila["penetracion"])
    assert fila["brecha"] == fila["casos_estimados"] and fila["celda_suprimida"]


def test_errores_claros_de_territorio():
    with pytest.raises(ValueError, match="0–1"):
        T.preparar_prevalencias(PREV.assign(prevalencia=30))
    with pytest.raises(ValueError, match="No hay prevalencias"):
        T.cobertura(_contactos(1, 0), T.preparar_poblacion(_censo()), T.preparar_prevalencias(PREV), "Ojos")
    with pytest.raises(ValueError, match="segmentar"):
        T.cobertura(_contactos(1, 0), T.preparar_poblacion(_censo()), T.preparar_prevalencias(PREV), "Cardio",
                    segmentar=("religion",))
    with pytest.raises(ValueError, match="poblacion"):
        T.preparar_poblacion(pd.DataFrame([{"pais": "UY", "ciudad": "Mvd"}]))


# ── escucha ─────────────────────────────────────────────────────────────────
def test_limpiar_borra_lo_que_identifica():
    s = S.limpiar("hola @juan escribime a juan@x.com o al +598 99 123 456, mirá https://x.com/p/1")
    assert "@juan" not in s and "juan@x.com" not in s and "123 456" not in s and "https" not in s


@pytest.mark.parametrize("texto,esperado", [("excelente, me ayudo mucho", 1), ("horrible y caro", -1),
                                            ("no funciona", -1), ("tomo la pastilla a la noche", 0)])
def test_sentimiento(texto, esperado):
    assert S.sentimiento(texto) == esperado


def test_la_escucha_sale_agregada_sin_autores_y_con_celdas_chicas_suprimidas():
    posts = pd.DataFrame({"fecha": ["2026-07-06"] * 6 + ["2026-07-07"],
                          "pais": ["Uruguay"] * 6 + ["Chile"],
                          "texto": ["la presión alta es un problema"] * 3 + ["controlar la presión me ayudó"] * 3
                          + ["presión alta"],
                          "autor": [f"@u{i}" for i in range(7)], "url": ["https://x"] * 7})
    r = S.agregar(posts, {"Hipertensión": ["presión alta", "presión"]})
    m = r["menciones"]
    assert list(m.columns) == ["pais", "semana", "tema", "menciones", "positivas", "negativas", "sentimiento_neto"]
    assert len(m) == 1 and m["menciones"].iloc[0] == 6 and m["pais"].iloc[0] == "Uruguay"   # Chile: 1 < 5
    assert (m["positivas"].iloc[0], m["negativas"].iloc[0]) == (3, 3)
    texto = " ".join(r["avisos"])
    assert "autor" in texto and "menos de 5" in texto
    assert "texto" not in m.columns


def test_farmacovigilancia_cuenta_posibles_eventos_adversos_de_productos_propios():
    posts = pd.DataFrame({"fecha": ["2026-07-06"] * 2, "texto": ["Vasotril me dio náuseas", "Vasotril anda bien"]})
    # El producto se repite en el catálogo (varios contenidos): se cuenta una vez por publicación.
    r = S.agregar(posts, {"Vasotril": ["vasotril"]}, productos=["Vasotril", "vasotril", "Vasotril"], k_minimo=1)
    assert r["farmacovigilancia"].to_dict("records") == [{"producto": "vasotril", "menciones_posible_evento_adverso": 1}]
    assert any("farmacovigilancia" in a for a in r["avisos"])


def test_sin_temas_no_hay_escucha():
    with pytest.raises(ValueError, match="tema"):
        S.agregar(pd.DataFrame({"fecha": ["2026-01-01"], "texto": ["x"]}), {})
    with pytest.raises(ValueError, match="texto"):
        S.preparar(pd.DataFrame({"fecha": ["2026-01-01"]}))


# ── modelo para Fabric ──────────────────────────────────────────────────────
def _modelo() -> dict[str, pd.DataFrame]:
    E = EJEMPLOS
    pob = T.preparar_poblacion(pd.read_csv(E / "censo_sintetico.csv"))
    pv = T.preparar_prevalencias(pd.read_csv(E / "prevalencias_sinteticas.csv"))
    ct = T.enriquecer(K.preparar_contactos(pd.read_csv(E / "relacionamiento_contactos.csv"))[0], pob)
    co = K.preparar_contenidos(pd.read_csv(E / "relacionamiento_contenidos.csv"))
    inter = R.preparar_interacciones(pd.read_csv(E / "relacionamiento_interacciones.csv"))[0]
    esc = S.agregar(pd.read_csv(E / "escucha_social_sintetica.csv"), S.temas_del_catalogo(co))["menciones"]
    return F.construir(contactos=ct, contenidos=co, interacciones=inter, poblacion=pob, prevalencias=pv,
                       escucha=esc, cobertura=T.cobertura(ct, pob, pv, "Diabetes"), hoy="2026-10-01")


def test_las_claves_son_estables_y_no_dependen_de_tildes_ni_mayusculas():
    assert F.clave("México", "Ciudad de México") == F.clave("mexico", "CIUDAD DE MEXICO")
    assert F.clave("Uruguay") != F.clave("Paraguay")
    assert 0 < F.clave("x") < 2**63


def test_el_modelo_no_tiene_huerfanos_ni_datos_que_identifiquen():
    t = _modelo()
    for a, b, c, d in F.RELACIONES:
        if a in t and c in t:
            fk = t[a][b].dropna()
            assert fk.isin(set(t[c][d])).all(), f"{a}[{b}] → {c}[{d}] tiene claves huérfanas"
    columnas = {c for df in t.values() for c in df.columns}
    assert not columnas & {"email", "telefono", "nombre", "texto", "autor", "url"}


def test_escribir_el_modelo_deja_ddl_esquema_y_carga(tmp_path):
    t = _modelo()
    out = F.escribir(tmp_path / "m", t, formato="parquet")
    assert (tmp_path / "m" / "dim_contacto.parquet").exists()
    ddl = (tmp_path / "m" / "crear_tablas.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS relacionamiento.fact_interacciones" in ddl and "USING DELTA" in ddl
    esq = json.loads((tmp_path / "m" / "modelo.json").read_text(encoding="utf-8"))
    assert {"desde": "fact_escucha[geo_key]", "hacia": "dim_geografia[geo_key]",
            "cardinalidad": "muchos a uno"} in esq["relaciones"]
    assert "saveAsTable" in out["cargar_en_lakehouse.py"].read_text(encoding="utf-8")
    assert pd.read_parquet(out["dim_contenido"])["area_key"].dtype == "Int64"


def test_modelo_vacio_o_formato_raro():
    with pytest.raises(ValueError, match="No hay tablas"):
        F.escribir("/tmp/no-se-usa", {})
    with pytest.raises(ValueError, match="formato"):
        F.escribir("/tmp/no-se-usa", {"x": pd.DataFrame()}, formato="xlsx")


# ── bordes que encontró la revisión ─────────────────────────────────────────
def test_supresion_complementaria_y_de_captados_chicos():
    # 10 mujeres y 2 hombres en Pocitos: suprimir sólo a los hombres se despejaría restando del total.
    ct = pd.concat([_contactos(10, 0), _contactos(0, 2).assign(barrio="Pocitos")], ignore_index=True)
    cob = T.cobertura(ct, T.preparar_poblacion(_censo()), T.preparar_prevalencias(PREV), "Cardio",
                      por_barrio=True, segmentar=("sexo",)).set_index(["barrio", "sexo"])
    assert cob.loc[("Pocitos", "Hombres"), "celda_suprimida"] and cob.loc[("Pocitos", "Mujeres"), "celda_suprimida"]
    # 12 personas pero sólo 3 con el área declarada: el dato de salud chico tampoco se publica.
    ct = pd.concat([_contactos(3, 0), _contactos(9, 0).assign(areas_interes=[frozenset()] * 9)], ignore_index=True)
    fila = T.cobertura(ct, T.preparar_poblacion(_censo()), T.preparar_prevalencias(PREV), "Cardio",
                       por_barrio=True).set_index("barrio").loc["Pocitos"]
    assert fila["captados_area"] == "<10"


def test_prevalencias_parciales_y_repetidas():
    prev = pd.DataFrame([{"pais": "Uruguay", "area_terapeutica": "Cardio", "sexo": "Total", "rango_edad": "40-59",
                          "prevalencia": 0.2},
                         {"pais": "Uruguay", "area_terapeutica": "Cardio", "sexo": "Total", "rango_edad": "40-59",
                          "prevalencia": 0.4}])
    cob = T.cobertura(_contactos(1, 0), T.preparar_poblacion(_censo()),
                      T.preparar_prevalencias(prev), "Cardio")
    assert cob["poblacion"].iloc[0] == 4400 and cob["casos_estimados"].iloc[0] == 1320   # 4400 × 0,30


def test_profesionales_y_bajas_no_son_captados_del_area():
    ct = _contactos(12, 0)
    ct.loc[:5, "tipo"] = "profesional"
    ct.loc[6:7, "baja"] = True
    fila = T.cobertura(ct, T.preparar_poblacion(_censo()), T.preparar_prevalencias(PREV), "Cardio",
                       por_barrio=True, k_minimo=1).set_index("barrio").loc["Pocitos"]
    assert fila["en_base"] == 12 and fila["captados_area"] == 4


def test_el_modelo_sale_de_lo_que_uso_el_motor():
    from app.core import programa_relacionamiento as PR
    ct = pd.DataFrame([{"id_contacto": "1", "pais": "Uruguay", "consiente_contacto": "si"}])
    co = pd.DataFrame([{"id_contenido": "A", "tipo": "concientizacion"}])
    inter = pd.DataFrame([{"id_contacto": "1", "id_contenido": "A", "fecha": "2026-09-01", "evento": "baja"},
                          {"id_contacto": "SUPRIMIDO", "id_contenido": "A", "fecha": "2026-09-01", "evento": "envio"}])
    t = PR.modelo(PR.analizar(ct, co, inter, hoy="2026-10-01"))
    assert bool(t["dim_contacto"]["baja"].iloc[0])
    assert "SUPRIMIDO" not in set(t["fact_interacciones"]["contacto_key"])


def test_escucha_sin_temas_se_saltea_con_aviso():
    from app.core import programa_relacionamiento as PR
    ct = pd.DataFrame([{"id_contacto": "1", "pais": "Uruguay", "consiente_contacto": "si"}])
    co = pd.DataFrame([{"id_contenido": "A", "tipo": "concientizacion"}])
    r = PR.analizar(ct, co, escucha=pd.DataFrame({"fecha": ["2026-01-01"], "texto": ["hola"]}))
    assert any("escucha se salteó" in a for a in r["avisos"])
