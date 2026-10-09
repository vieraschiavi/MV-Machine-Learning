"""Etapa 5: el modelo de relacionamiento en Fabric — carga incremental, modelo semántico (TMDL) y notebook."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest
from app.core import consentimiento as K
from app.core import escucha as S
from app.core import fabric_relacionamiento as FR
from app.core import modelo_fabric as F
from app.core import relacionamiento as R
from app.core import territorio as T

EJEMPLOS = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture(scope="module")
def modelo() -> dict[str, pd.DataFrame]:
    """El modelo completo con los ejemplos sintéticos: propios, públicos, consentimientos y búsquedas."""
    E = EJEMPLOS
    pob = T.preparar_poblacion(pd.read_csv(E / "censo_sintetico.csv"))
    pv = T.preparar_prevalencias(pd.read_csv(E / "prevalencias_sinteticas.csv"))
    ct = T.enriquecer(K.preparar_contactos(pd.read_csv(E / "relacionamiento_contactos.csv"))[0], pob)
    co = K.preparar_contenidos(pd.read_csv(E / "relacionamiento_contenidos.csv"))
    inter = R.preparar_interacciones(pd.read_csv(E / "relacionamiento_interacciones.csv"))[0]
    esc = S.agregar(pd.read_csv(E / "escucha_social_sintetica.csv"), S.temas_del_catalogo(co))["menciones"]
    libro = pd.DataFrame({"id_contacto": ["C-00001", "C-00001"], "fecha": ["2026-05-01", "2026-06-01"],
                          "finalidad": ["contacto", "contacto"], "accion": ["otorga", "retira"],
                          "canal": ["landing", "landing"], "version_texto": ["v-1", "v-1"]})
    bus = pd.DataFrame({"pais": ["Uruguay"], "region": ["Montevideo"], "termino": ["presión alta"], "interes": [100]})
    return F.construir(contactos=ct, contenidos=co, interacciones=inter, poblacion=pob, prevalencias=pv,
                       escucha=esc, cobertura=T.cobertura(ct, pob, pv, "Diabetes"), consentimientos=libro,
                       busquedas=bus, hoy="2026-10-01")


# ── carga incremental ───────────────────────────────────────────────────────
def test_cada_tabla_del_modelo_tiene_estrategia_y_sus_claves_existen(modelo):
    assert set(modelo) <= set(FR.ESTRATEGIAS)
    for t, df in modelo.items():
        _, claves = FR.estrategia(t)
        assert set(claves) <= set(df.columns), t
    with pytest.raises(ValueError, match="sin estrategia"):
        FR.estrategia("fact_inventada")


def test_una_dimension_se_actualiza_y_agrega_sin_duplicar():
    actual = pd.DataFrame({"contacto_key": ["a", "b"], "baja": [False, False]})
    nuevo = pd.DataFrame({"contacto_key": ["b", "c", "c"], "baja": [True, False, True],
                          "especialidad": ["", "", "cardio"]})
    r = FR.fusionar(actual, nuevo, "dim_contacto").set_index("contacto_key")
    assert list(r.index) == ["a", "b", "c"]
    assert not r.loc["a", "baja"] and r.loc["b", "baja"] and r.loc["c", "baja"]       # gana la última fila
    assert "especialidad" in r.columns and pd.isna(r.loc["a", "especialidad"])     # columna nueva: se agrega
    assert FR.fusionar(r.reset_index(), nuevo, "dim_contacto").equals(FR.fusionar(actual, nuevo, "dim_contacto"))


def test_los_hechos_reemplazan_los_dias_que_trae_la_carga():
    actual = pd.DataFrame({"contacto_key": ["a", "a", "b"], "contenido_key": ["K1"] * 3,
                           "fecha_key": [20260101, 20260102, 20260102], "evento": ["envio", "envio", "envio"]})
    # La carga trae el 2 de enero completo: dos clics iguales del mismo día son dos clics, no uno.
    nuevo = pd.DataFrame({"contacto_key": ["a", "a", "a"], "contenido_key": ["K1"] * 3,
                          "fecha_key": [20260102] * 3, "evento": ["envio", "clic", "clic"]})
    r = FR.fusionar(actual, nuevo, "fact_interacciones")
    assert len(r[r["fecha_key"] == 20260101]) == 1                          # lo que no vino, queda
    assert sorted(r.loc[r["fecha_key"] == 20260102, "evento"]) == ["clic", "clic", "envio"]
    assert len(FR.fusionar(r, nuevo, "fact_interacciones")) == len(r)       # repetir la carga no duplica


def test_una_clave_nula_es_una_porcion_mas():
    actual = pd.DataFrame({"fecha_key": pd.array([None, 20260101], dtype="Int64"), "accion": ["otorga", "otorga"]})
    nuevo = pd.DataFrame({"fecha_key": pd.array([None], dtype="Int64"), "accion": ["retira"]})
    r = FR.fusionar(actual, nuevo, "fact_consentimientos")
    assert sorted(r["accion"]) == ["otorga", "retira"] and len(r) == 2
    assert FR.fusionar(None, nuevo, "fact_consentimientos").equals(nuevo)


# ── modelo semántico ────────────────────────────────────────────────────────
def test_el_modelo_semantico_cierra_y_es_direct_lake(modelo):
    a = FR.tmdl(modelo, servidor="x.datawarehouse.fabric.microsoft.com", lakehouse="LH_Relacionamiento")
    assert FR.verificar_tmdl(a) == []
    assert set(a) >= {".platform", "definition.pbism", "definition/model.tmdl", "definition/expressions.tmdl",
                      "definition/relationships.tmdl", "definition/tables/dim_contacto.tmdl"}
    assert json.loads(a["definition.pbism"])["version"] == "4.0"
    assert json.loads(a[".platform"])["metadata"]["type"] == "SemanticModel"
    assert 'Sql.Database("x.datawarehouse.fabric.microsoft.com", "LH_Relacionamiento")' in a["definition/expressions.tmdl"]
    for t in modelo:
        txt = a[f"definition/tables/{t}.tmdl"]
        assert "mode: directLake" in txt and f"entityName: {t}" in txt and "schemaName: relacionamiento" in txt
    rel = a["definition/relationships.tmdl"]
    assert rel.count("relationship ") == sum(1 for x, _, y, _ in F.RELACIONES if x in modelo and y in modelo)
    inactiva = rel.split("fromColumn: dim_producto.area_key")[0].rsplit("relationship ", 1)[1]
    assert "isActive: false" in inactiva                                   # sin caminos ambiguos
    assert a == FR.tmdl(modelo, servidor="x.datawarehouse.fabric.microsoft.com", lakehouse="LH_Relacionamiento")


def test_las_medidas_salen_de_las_columnas_que_hay(modelo):
    m = {t: {n for n, _, _ in v} for t, v in FR.medidas(modelo).items()}
    assert {"Contactos", "Contactables", "% contactables", "Con doble opt-in"} <= m["dim_contacto"]
    assert {"Envíos", "Tasa de apertura", "Tasa de conversión", "Contactos alcanzados"} <= m["fact_interacciones"]
    assert {"Consentimientos otorgados", "Consentimientos retirados"} <= m["fact_consentimientos"]
    assert {"Casos estimados", "Penetración"} <= m["fact_cobertura"] and "Sentimiento neto" in m["fact_escucha"]
    solo = FR.medidas({"dim_contacto": pd.DataFrame({"contacto_key": ["a"]})})
    assert [n for n, _, _ in solo["dim_contacto"]] == ["Contactos"]          # sin consentimientos, sin esas medidas
    txt = FR.tmdl(modelo)["definition/tables/fact_interacciones.tmdl"]
    assert "\tmeasure 'Tasa de apertura' = DIVIDE([Aperturas], [Envíos])" in txt and "formatString: 0.0%" in txt
    assert "\tcolumn contacto_key\n\t\tdataType: string\n\t\tisHidden" in txt          # claves ocultas en hechos


def test_el_verificador_encuentra_lo_que_no_cierra(modelo):
    a = FR.tmdl({"dim_area": modelo["dim_area"], "fact_prevalencia": modelo["fact_prevalencia"]})
    a["definition/relationships.tmdl"] += "relationship x\n\tfromColumn: fact_prevalencia.no_existe\n\ttoColumn: dim_area.area_key\n"
    a["definition/tables/fact_prevalencia.tmdl"] = a["definition/tables/fact_prevalencia.tmdl"].replace(
        "AVERAGE(fact_prevalencia[prevalencia])", "AVERAGE(fact_prevalencia[nada]) + [Fantasma]")
    a["definition/model.tmdl"] += "ref table dim_fantasma\n"
    texto = " ".join(FR.verificar_tmdl(a))
    assert "fact_prevalencia.no_existe" in texto and "fact_prevalencia[nada]" in texto and "[Fantasma]" in texto
    assert "dim_fantasma" in texto
    with pytest.raises(ValueError):
        FR.tmdl({})


def test_tipos_del_modelo():
    df = pd.DataFrame({"b": [True], "i": pd.array([1], dtype="Int64"), "f": [1.5],
                       "d": pd.to_datetime(["2026-01-01"]), "s": ["x"]})
    assert [FR.tipo_tmdl(df[c]) for c in df] == ["boolean", "int64", "double", "dateTime", "string"]
    assert "`d` DATE" in F.ddl({"t": df}) and "`s` STRING" in F.ddl({"t": df})


# ── notebook y archivos ─────────────────────────────────────────────────────
def test_el_notebook_y_el_merge_son_python_valido_con_las_mismas_estrategias(modelo):
    codigo = FR.codigo_merge(modelo, esquema="", formato="csv")
    arbol = ast.parse(codigo)
    tablas = next(ast.literal_eval(n.value) for n in arbol.body
                  if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "TABLAS")
    assert {t: (e, tuple(k)) for t, (e, k) in tablas.items()} == {t: FR.ESTRATEGIAS[t] for t in modelo}
    orden = list(tablas)
    assert max(orden.index(t) for t in orden if t.startswith("dim_")) < min(
        orden.index(t) for t in orden if t.startswith("fact_"))                        # dimensiones primero
    assert 'ESQUEMA = ""' in codigo and 'FORMATO = "csv"' in codigo and "<=>" in codigo
    nb = FR.notebook(modelo)
    assert nb["nbformat"] == 4 and nb["metadata"]["kernelspec"]["name"] == "synapse_pyspark"
    codigo_nb = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert codigo_nb[0]["metadata"]["tags"] == ["parameters"] and "CARPETA = " in "".join(codigo_nb[0]["source"])
    ast.parse("\n".join("".join(c["source"]) for c in codigo_nb))                      # el notebook entero compila


def test_escribir_deja_el_merge_el_notebook_y_el_modelo_semantico(modelo, tmp_path):
    out = F.escribir(tmp_path / "m", modelo, formato="csv")
    base = tmp_path / "m"
    assert (base / "merge_incremental.py").exists() and (base / "notebook_relacionamiento.ipynb").exists()
    sm = base / "Relacionamiento.SemanticModel"
    assert (sm / "definition.pbism").exists() and (sm / "definition" / "tables" / "fact_busquedas.tmdl").exists()
    assert "Relacionamiento.SemanticModel/definition/relationships.tmdl" in out
    json.loads((base / "notebook_relacionamiento.ipynb").read_text(encoding="utf-8"))
    ast.parse((base / "merge_incremental.py").read_text(encoding="utf-8"))
    columnas = {c for df in modelo.values() for c in df.columns}
    assert not columnas & {"email", "telefono", "nombre"}
