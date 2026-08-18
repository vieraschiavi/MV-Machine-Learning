"""Motor de ETL: propuesta, compilación, ejecución y auditoría de fuga."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.core import etl, storage


@pytest.fixture(scope="module")
def plan(dataset_binary):
    return etl.propose(dataset_binary.id, target="objetivo")


def _ops(plan, op):
    return [s["column"] for s in plan["steps"] if s["op"] == op]


def test_descarta_constante_identificador_y_columna_vacia(plan):
    dropped = _ops(plan, "drop_column")
    assert "constante" in dropped
    assert "casi_vacia" in dropped
    assert "id" in dropped
    assert "objetivo" not in dropped


def test_no_descarta_la_fecha_como_identificador(plan):
    """Una fecha tiene un valor por fila; sin detección de tipo se perdería."""
    assert "fecha" not in _ops(plan, "drop_column")
    assert "fecha" in _ops(plan, "parse_datetime")
    assert "fecha" in _ops(plan, "expand_datetime")


def test_convierte_texto_numerico_con_simbolo_y_coma_decimal(plan):
    assert "monto_texto" in _ops(plan, "cast_numeric")
    paso = next(s for s in plan["steps"] if s["op"] == "cast_numeric")
    assert paso["params"]["decimal_comma"] is True


def test_imputa_y_marca_faltantes(plan):
    assert "ingreso" in _ops(plan, "impute_numeric")
    paso = next(s for s in plan["steps"] if s["op"] == "impute_numeric")
    assert np.isfinite(paso["params"]["value"])


def test_cada_paso_trae_su_motivo(plan):
    for s in plan["steps"]:
        assert s["reason"] and len(s["reason"]) > 10
        assert s["op"] and "id" in s


def test_sql_compilado_es_una_sola_sentencia(plan):
    sql = plan["sql"]
    assert sql.strip().upper().startswith("SELECT")
    assert sql.count(";") == 0
    assert "{t}" in sql


def test_ejecucion_produce_dataset_derivado(dataset_binary, plan):
    r = etl.execute(dataset_binary.id, plan, name="derivado")
    assert r["rows_out"] > 0
    assert r["columns_out"] < r["columns_in"] + 8
    meta = storage.load_meta(r["dataset"]["id"])
    assert meta.parent_id == dataset_binary.id
    nombres = [c["name"] for c in meta.columns]
    assert "constante" not in nombres
    assert "fecha__year" in nombres
    assert "ingreso__faltante" in nombres
    df = storage.load_frame(meta.id)
    assert df["ingreso"].isna().sum() == 0
    assert pd.api.types.is_numeric_dtype(df["monto_texto"])


def test_pasos_desactivados_no_se_aplican(dataset_binary, plan):
    plan2 = {**plan, "steps": [dict(s) for s in plan["steps"]]}
    for s in plan2["steps"]:
        if s["op"] == "drop_column" and s["column"] == "constante":
            s["enabled"] = False
    plan2["sql"] = etl.compile_sql(dataset_binary.id, plan2)
    assert '"constante"' in plan2["sql"]


def test_auditoria_detecta_una_columna_que_contiene_la_respuesta(tmp_root):
    rng = np.random.default_rng(3)
    n = 800
    df = pd.DataFrame({"x": rng.normal(0, 1, n), "ruido": rng.normal(0, 1, n)})
    df["objetivo"] = (df.x > 0).astype(int)
    df["copia_del_objetivo"] = df.objetivo          # fuga evidente
    path = tmp_root / "fuga.csv"
    df.to_csv(path, index=False)
    meta = storage.ingest_file(path, "fuga")

    hallazgos = etl.audit_leakage(meta.id, "objetivo")
    bloqueadas = {h["column"] for h in hallazgos if h["blocked"]}
    assert "copia_del_objetivo" in bloqueadas
    assert "ruido" not in bloqueadas

    plan = etl.propose(meta.id, target="objetivo")
    assert "copia_del_objetivo" in _ops(plan, "drop_column")


def test_auditoria_no_marca_columnas_inocentes(dataset_binary):
    hallazgos = etl.audit_leakage(dataset_binary.id, "objetivo")
    assert not [h for h in hallazgos if h["blocked"]]
