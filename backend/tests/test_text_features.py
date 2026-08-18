"""Texto libre como feature: detección, vectorización y protocolo completo."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.core import automl as A
from app.core import etl, profiling, storage
from app.core.features import Preprocessor, base_column, looks_like_text

POS = ["cliente conforme promete pagar la cuota completa este mes",
       "acordamos plan de pagos con muy buena disposicion al contacto",
       "confirma la transferencia realizada y envia el comprobante"]
NEG = ["no atiende el telefono y el numero esta fuera de servicio",
       "se niega a pagar y dice que va a iniciar un reclamo legal",
       "sin respuesta a los mensajes y direccion desconocida"]


@pytest.fixture(scope="module")
def frame_texto():
    rng = np.random.default_rng(3)
    n = 1200
    y = rng.binomial(1, 0.4, n)
    return pd.DataFrame({
        "ruido": rng.normal(0, 1, n),
        "observaciones": [f"{(POS if v else NEG)[rng.integers(3)]} expediente {i}"
                          for i, v in enumerate(y)],
        "region": rng.choice(["norte", "sur"], n),
        "objetivo": y,
    })


def test_deteccion_de_texto_vs_categorica(frame_texto):
    assert looks_like_text(frame_texto.observaciones) is True
    assert looks_like_text(frame_texto.region) is False
    assert looks_like_text(pd.Series(["A"] * 100)) is False


def test_el_preprocesador_clasifica_y_vectoriza(frame_texto):
    pre = Preprocessor().fit(frame_texto.drop(columns=["objetivo"]).head(800))
    assert pre.text == ["observaciones"]
    assert pre.categorical == ["region"]
    Xt = pre.transform_tree(frame_texto.drop(columns=["objetivo"]))
    txt = [c for c in Xt.columns if "__txt" in c]
    assert len(txt) >= 5
    assert np.isfinite(Xt[txt].to_numpy()).all()
    # la matriz lineal lleva las mismas componentes
    assert pre.transform_linear(frame_texto.drop(columns=["objetivo"])).shape[1] \
        == len(pre.feature_names_linear)


def test_base_column_mapea_componentes_a_la_columna_madre():
    assert base_column("observaciones__txt7") == "observaciones"
    assert base_column("monto__log") == "monto"
    assert base_column("region=norte") == "region"


def test_columna_ausente_en_score_no_rompe(frame_texto):
    pre = Preprocessor().fit(frame_texto.drop(columns=["objetivo"]))
    sin = pre.transform_tree(frame_texto.drop(columns=["objetivo", "observaciones"]))
    assert len(sin) == len(frame_texto)


def test_el_etl_declara_el_texto_y_no_lo_destruye(tmp_root, frame_texto):
    path = tmp_root / "texto.csv"
    frame_texto.to_csv(path, index=False)
    meta = storage.ingest_file(path, "texto")

    prof = profiling.profile(meta.id)
    col = {c["name"]: c for c in prof["columns"]}
    assert col["observaciones"].get("is_text") is True
    codes = {i["code"] for i in prof["quality"]["issues"]}
    assert "text" in codes

    plan = etl.propose(meta.id, target="objetivo")
    ops = {(s["op"], s["column"]) for s in plan["steps"]}
    assert ("text_column", "observaciones") in ops
    assert ("drop_column", "observaciones") not in ops
    assert ("group_rare", "observaciones") not in ops

    r = etl.execute(meta.id, plan)
    assert "observaciones" in [c["name"] for c in r["dataset"]["columns"]]


def test_entrenamiento_con_senal_solo_en_el_texto(frame_texto):
    """Si el TF-IDF no entrara al modelo, el AUC sería ~0,5: la única señal es el texto."""
    res = A.train(frame_texto, A.TrainConfig(target="objetivo", budget_seconds=8,
                                             max_models=2, shap=False))
    r = res["report"]
    assert r["champion"]["holdout"]["auc"] > 0.9
    top = [x["column"] for x in r["features"]["ranking"][:3]]
    assert any(c.startswith("observaciones") for c in top)


def test_prediccion_guardada_con_texto(frame_texto, tmp_root):
    from app.core import registry

    res = A.train(frame_texto, A.TrainConfig(target="objetivo", budget_seconds=5,
                                             max_models=1, shap=False,
                                             permutation_importance=False))
    path = tmp_root / "texto_score.csv"
    frame_texto.to_csv(path, index=False)
    meta = storage.ingest_file(path, "texto para scoring")
    card = registry.save(res["bundle"], res["report"], "con texto", meta.id)
    out = registry.score_dataset(card["id"], meta.id)
    assert out["rows"] == len(frame_texto)
