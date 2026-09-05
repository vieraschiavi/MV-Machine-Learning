"""La bitácora: qué le pasó a los datos, en orden, contado dos veces.

El programa ya sabía todo esto —el plan de ETL guarda el motivo de cada paso,
la ficha del modelo guarda la partición y el veredicto—, pero repartido en
cinco pantallas y en jerga. Un gerente que pregunta «¿qué le hicieron a mis
datos?» no tenía dónde mirar, y un programador que audita el pipeline tenía
que reconstruirlo a mano.

Estas pruebas fijan las tres garantías que hacen útil a la bitácora:

  1. **Orden secuencial real.** Los pasos salen en el orden en que ocurrieron,
     del archivo crudo al veredicto, no agrupados por tipo ni alfabéticos.
  2. **Dos lecturas de lo mismo.** Cada paso trae su versión técnica y su
     versión criolla, y la criolla no puede ser la técnica con otro nombre:
     se le exige que no arrastre la jerga.
  3. **Nada inventado.** Cada número de la bitácora tiene que existir en el
     linaje del dataset o en la ficha del modelo. Un informe que un gerente
     firma no puede tener cifras que no salgan de ningún lado.
"""
from __future__ import annotations

import pytest
from app.core import bitacora, etl, storage


@pytest.fixture(scope="module")
def derivado(dataset_binary):
    """Un dataset pasado por el ETL de verdad: el linaje que lee la bitácora."""
    plan = etl.propose(dataset_binary.id, target="objetivo")
    return etl.execute(dataset_binary.id, plan, name="binario · ETL")


@pytest.fixture(scope="module")
def libro(derivado):
    return bitacora.construir(dataset_id=derivado["dataset"]["id"])


@pytest.fixture(scope="module")
def modelo_entrenado(frame_binary, dataset_binary):
    """Un modelo guardado de verdad: la bitácora lee su ficha, no un simulacro."""
    from app.core import automl, registry

    df = frame_binary.drop(columns=["id", "constante", "casi_vacia", "fecha", "monto_texto"])
    cfg = automl.TrainConfig(target="objetivo", budget_seconds=8, max_models=2,
                             shap=False, permutation_importance=False)
    out = automl.train(df, cfg)
    return registry.save(out["bundle"], out["report"], "modelo de prueba", dataset_binary.id)


# ═════════════════════════════════════════════════════════ orden y cobertura ══
def test_arranca_en_la_ingesta_y_no_saltea_el_etl(libro):
    etapas = [p["etapa"] for p in libro["pasos"]]

    assert etapas[0] == "ingesta", f"la bitácora empieza en {etapas[0]!r}"
    assert "etl" in etapas, "el ETL no aparece: es justamente lo que hay que contar"


def test_los_pasos_estan_numerados_en_secuencia_sin_huecos(libro):
    """El orden es el mensaje: si se desordena, deja de ser una bitácora."""
    ordenes = [p["orden"] for p in libro["pasos"]]

    assert ordenes == list(range(1, len(ordenes) + 1))


def test_el_etl_va_despues_de_la_ingesta_y_nunca_antes(libro):
    etapas = [p["etapa"] for p in libro["pasos"]]

    assert etapas.index("ingesta") < etapas.index("etl")


def test_cada_paso_dice_que_se_hizo_por_que_y_como_repercute(libro):
    """Las cuatro preguntas que el usuario pidió responder en cada paso."""
    for p in libro["pasos"]:
        for campo in ("titulo", "tecnico", "criollo", "porque", "impacto"):
            assert p.get(campo), f"el paso {p['orden']} ({p['etapa']}) no trae {campo}"


# ═══════════════════════════════════════════════════════════ las dos lecturas ══
JERGA = ["nan", "null", "dtype", "cast", "parse", "imputa", "cardinalidad",
         "one-hot", "holdout", "varianza", "outlier", "timestamp"]


def test_la_version_criolla_no_repite_la_tecnica(libro):
    for p in libro["pasos"]:
        assert p["criollo"].strip().lower() != p["tecnico"].strip().lower(), \
            f"el paso {p['orden']} dice lo mismo dos veces"


def test_la_version_criolla_esta_libre_de_jerga(libro):
    """El texto para el jefe no puede tener las palabras que él no usa."""
    sucios = [(p["orden"], j) for p in libro["pasos"]
              for j in JERGA if j in p["criollo"].lower()]

    assert not sucios, f"jerga en la lectura criolla: {sucios}"


def test_la_version_tecnica_nombra_la_columna_que_toco(derivado, libro):
    """Un programador audita por columna: sin el nombre, no sirve de nada."""
    pasos_etl = [p for p in libro["pasos"] if p["etapa"] == "etl"]
    tocadas = {s["column"] for s in derivado["applied"] if s.get("column")}
    nombradas = " ".join(p["tecnico"] + " " + str(p.get("detalle", "")) for p in pasos_etl)

    faltan = [c for c in tocadas if c not in nombradas]
    assert not faltan, f"columnas transformadas que la bitácora no nombra: {faltan}"


# ═════════════════════════════════════════════════════════════════ evidencia ══
def test_la_ingesta_declara_las_filas_y_columnas_que_entraron(libro, dataset_binary):
    ingesta = next(p for p in libro["pasos"] if p["etapa"] == "ingesta")
    valores = " ".join(str(e["valor"]) for e in ingesta["evidencia"])

    assert f"{dataset_binary.rows:,}".replace(",", ".") in valores, \
        f"las filas reales ({dataset_binary.rows}) no figuran: {valores}"


def test_el_resumen_cuadra_con_el_linaje_real(libro, derivado):
    """Las cifras del encabezado son las del dataset, no un cálculo aparte."""
    r = libro["resumen"]

    assert r["filas_inicio"] == derivado["rows_in"]
    assert r["filas_fin"] == derivado["rows_out"]
    assert r["columnas_inicio"] == derivado["columns_in"]
    assert r["columnas_fin"] == derivado["columns_out"]


def test_todas_las_operaciones_aplicadas_tienen_su_paso(libro, derivado):
    """Si el ETL hizo algo que la bitácora no cuenta, la bitácora miente."""
    hechas = {s["op"] for s in derivado["applied"]}
    contadas = {op for p in libro["pasos"] for op in p.get("ops", [])}

    assert hechas <= contadas, f"operaciones sin contar: {hechas - contadas}"


def test_el_sql_ejecutado_queda_a_la_vista_para_auditar(libro):
    """La promesa del ETL es que se puede auditar; la bitácora la sostiene."""
    assert any("SELECT" in str(p.get("detalle", "")).upper()
               for p in libro["pasos"] if p["etapa"] == "etl")


# ════════════════════════════════════════════════════════ dataset sin historia ══
def test_un_dataset_recien_subido_igual_produce_bitacora(dataset_binary):
    """Sin ETL todavía no hay nada que contar, pero no puede reventar."""
    libro = bitacora.construir(dataset_id=dataset_binary.id)

    assert libro["pasos"], "un dataset crudo también tiene su paso de ingesta"
    assert all(p["etapa"] != "etl" for p in libro["pasos"])


def test_pide_al_menos_un_dataset_o_un_modelo():
    with pytest.raises(ValueError):
        bitacora.construir()


def test_dataset_inexistente_avisa_en_vez_de_romper():
    """El mismo error tipado que usa el resto del programa, no uno nuevo.

    `storage.IngestError` es el que la API ya traduce a un mensaje legible;
    inventar otra excepción acá lo devolvería como un 500 sin explicación.
    """
    with pytest.raises(storage.IngestError):
        bitacora.construir(dataset_id="ds_que_no_existe")


# ════════════════════════════════════════════════════════════════ con modelo ══
def test_el_modelo_agrega_particion_entrenamiento_y_veredicto(modelo_entrenado):
    libro = bitacora.construir(model_id=modelo_entrenado["id"])
    etapas = [p["etapa"] for p in libro["pasos"]]

    for esperada in ("particion", "entrenamiento", "evaluacion"):
        assert esperada in etapas, f"falta la etapa {esperada}: {etapas}"


def test_la_particion_explica_por_que_el_holdout_queda_afuera(modelo_entrenado):
    """Es el punto que más cuesta explicar y el que sostiene el número final."""
    libro = bitacora.construir(model_id=modelo_entrenado["id"])
    paso = next(p for p in libro["pasos"] if p["etapa"] == "particion")

    assert paso["porque"], "sin motivo, la partición parece un capricho"
    assert any("holdout" in str(e["valor"]).lower() or "ciego" in str(e["clave"]).lower()
               or e["clave"].lower().startswith("holdout") for e in paso["evidencia"])


def test_las_filas_del_modelo_salen_de_la_ficha_no_de_una_cuenta_propia(modelo_entrenado):
    libro = bitacora.construir(model_id=modelo_entrenado["id"])
    rep = modelo_entrenado["report"]
    paso = next(p for p in libro["pasos"] if p["etapa"] == "particion")
    valores = " ".join(str(e["valor"]) for e in paso["evidencia"])

    assert f"{rep['split']['holdout']:,}".replace(",", ".") in valores
