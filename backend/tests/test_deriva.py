"""Monitoreo de deriva: avisar cuándo los datos nuevos ya no se parecen a los de entrenamiento.

Un modelo no se rompe con un error: se pone viejo en silencio. Sigue devolviendo
probabilidades con el mismo aspecto, pero los clientes, los precios o el canal
cambiaron y el número dejó de valer. Estas pruebas fijan que el programa lo
detecte con el PSI (índice de estabilidad poblacional), el estándar de riesgo
crediticio, y que el veredicto pese lo que importa: una variable que el modelo
casi no usa puede moverse sin que haga falta reentrenar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.core import automl as A
from app.core import deriva as D
from app.core import licensing as L
from app.core import registry, storage

# ── PSI: el número base ──────────────────────────────────────────────────────


def _normal(n: int, media: float = 0.0, semilla: int = 0) -> pd.Series:
    return pd.Series(np.random.default_rng(semilla).normal(media, 1.0, n))


def test_una_distribucion_contra_si_misma_da_psi_cero():
    s = _normal(5000)
    r = D.comparar(D.perfilar_columna(s), s)
    assert r["psi"] == pytest.approx(0.0, abs=1e-9)
    assert r["nivel"] == "estable"


def test_otra_muestra_del_mismo_proceso_queda_estable():
    r = D.comparar(D.perfilar_columna(_normal(5000, semilla=1)), _normal(5000, semilla=2))
    assert r["psi"] < D.UMBRAL_MODERADA
    assert r["nivel"] == "estable"


def test_un_corrimiento_de_una_desviacion_es_deriva_fuerte():
    r = D.comparar(D.perfilar_columna(_normal(5000)), _normal(5000, media=1.0, semilla=3))
    assert r["psi"] >= D.UMBRAL_FUERTE
    assert r["nivel"] == "fuerte"


def test_una_categoria_que_no_existia_se_cuenta_y_mueve_el_psi():
    ref = pd.Series(["norte"] * 500 + ["sur"] * 500)
    nueva = pd.Series(["norte"] * 300 + ["sur"] * 300 + ["litoral"] * 400)
    r = D.comparar(D.perfilar_columna(ref), nueva)
    assert r["categorias_nuevas"] == pytest.approx(0.40)
    assert r["nivel"] == "fuerte"


def test_un_salto_de_nulos_se_detecta_aunque_los_valores_no_cambien():
    ref = _normal(4000)
    nueva = _normal(4000, semilla=4).mask(np.arange(4000) % 5 < 2)   # 40 % vacío
    r = D.comparar(D.perfilar_columna(ref), nueva)
    assert r["nulos_ref"] == pytest.approx(0.0)
    assert r["nulos_nuevos"] == pytest.approx(0.40)
    assert r["nivel"] == "fuerte"


# ── bordes: nada de esto puede tirar el monitoreo abajo ──────────────────────


def test_una_columna_constante_no_rompe():
    s = pd.Series([7.0] * 300)
    r = D.comparar(D.perfilar_columna(s), s)
    assert r["nivel"] == "estable"


def test_una_columna_toda_vacia_no_rompe():
    s = pd.Series([np.nan] * 300)
    r = D.comparar(D.perfilar_columna(s), s)
    assert r["nivel"] == "estable"


def test_un_identificador_no_se_mide_como_deriva():
    """Cada factura trae un número nuevo: eso no es un cambio de población."""
    ref = pd.Series([f"F-{i:05d}" for i in range(1000)])
    nueva = pd.Series([f"F-{i:05d}" for i in range(5000, 6000)])
    r = D.comparar(D.perfilar_columna(ref), nueva)
    assert r["nivel"] == "no_aplica"


# ── el veredicto del modelo entero ───────────────────────────────────────────


def _referencia(n: int = 3000):
    rng = np.random.default_rng(10)
    datos = pd.DataFrame({
        "ingreso": rng.gamma(2, 20_000, n),
        "atraso": rng.integers(0, 90, n).astype(float),
        "canal": rng.choice(["web", "sucursal", "telefono"], n),
        "decorativa": rng.normal(0, 1, n),
    })
    pred = pd.Series(rng.beta(2, 5, n), name="prob_1")
    importancias = {"ingreso": 0.40, "atraso": 0.35, "canal": 0.20, "decorativa": 0.001}
    return datos, pred, D.referencia(datos, pred, importancias)


def test_los_mismos_datos_dan_veredicto_estable():
    datos, pred, ref = _referencia()
    inf = D.informe(ref, datos.sample(frac=0.5, random_state=1),
                    pred.sample(frac=0.5, random_state=1))
    assert inf["disponible"] is True
    assert inf["veredicto"]["nivel"] == "estable"


def test_si_se_corre_una_variable_importante_hay_que_reentrenar():
    datos, pred, ref = _referencia()
    nuevos = datos.assign(ingreso=datos.ingreso * 3)
    inf = D.informe(ref, nuevos, pred)
    assert inf["veredicto"]["nivel"] == "fuerte"
    assert "ingreso" in inf["veredicto"]["texto"]
    assert inf["variables"][0]["variable"] == "ingreso"      # la peor, primero


def test_si_se_corre_una_variable_que_el_modelo_no_usa_solo_se_vigila():
    datos, pred, ref = _referencia()
    nuevos = datos.assign(decorativa=datos.decorativa + 5)
    inf = D.informe(ref, nuevos, pred)
    fila = next(v for v in inf["variables"] if v["variable"] == "decorativa")
    assert fila["nivel"] == "fuerte"
    assert inf["veredicto"]["nivel"] == "moderada"


def test_si_la_prediccion_se_corre_hay_que_reentrenar():
    datos, pred, ref = _referencia()
    inf = D.informe(ref, datos, (pred + 0.4).clip(0, 1))
    assert inf["prediccion"]["nivel"] == "fuerte"
    assert inf["veredicto"]["nivel"] == "fuerte"


def test_una_variable_importante_que_falta_se_informa():
    datos, pred, ref = _referencia()
    inf = D.informe(ref, datos.drop(columns=["atraso"]), pred)
    fila = next(v for v in inf["variables"] if v["variable"] == "atraso")
    assert fila["nivel"] == "falta"
    assert inf["veredicto"]["nivel"] == "fuerte"


def test_con_pocas_filas_no_se_da_veredicto():
    datos, pred, ref = _referencia()
    inf = D.informe(ref, datos.head(30), pred.head(30))
    assert inf["veredicto"]["nivel"] == "insuficiente"


def test_un_modelo_sin_referencia_explica_que_hacer():
    inf = D.informe(None, pd.DataFrame({"x": range(200)}), None)
    assert inf["disponible"] is False
    assert "reentren" in inf["motivo"].lower()


# ── de punta a punta: entrenamiento, registro y API ──────────────────────────

EXCLUIR = ["id", "constante", "casi_vacia", "fecha", "monto_texto"]


@pytest.fixture(scope="module")
def modelo_guardado(dataset_binary):
    df = storage.load_frame(dataset_binary.id).drop(columns=EXCLUIR)
    res = A.train(df, A.TrainConfig(target="objetivo", budget_seconds=6, max_models=1,
                                    shap=False, permutation_importance=True))
    card = registry.save(res["bundle"], res["report"], "deriva", dataset_binary.id)
    return res, card


def test_el_entrenamiento_guarda_la_referencia(modelo_guardado):
    res, _ = modelo_guardado
    ref = res["bundle"]["referencia_deriva"]
    assert {"edad", "ingreso", "region", "score"} <= set(ref["variables"])
    assert ref["prediccion"] is not None
    assert res["report"]["monitoreo"]["disponible"] is True


def test_monitorear_el_mismo_dataset_da_estable(client, modelo_guardado, dataset_binary):
    _, card = modelo_guardado
    r = client.post("/api/automl/monitor",
                    json={"model_id": card["id"], "dataset_id": dataset_binary.id})
    assert r.status_code == 200, r.text
    assert r.json()["veredicto"]["nivel"] == "estable"


def test_monitorear_datos_corridos_pide_reentrenar(client, modelo_guardado, dataset_binary):
    _, card = modelo_guardado
    df = storage.load_frame(dataset_binary.id)
    corrido = df.assign(ingreso=df.ingreso * 4, edad=df.edad + 30)
    meta = storage.ingest_frames(iter([corrido]), "binario corrido", source="derived")
    r = client.post("/api/automl/monitor", json={"model_id": card["id"], "dataset_id": meta.id})
    assert r.status_code == 200, r.text
    inf = r.json()
    assert inf["veredicto"]["nivel"] == "fuerte"
    assert {v["variable"] for v in inf["variables"][:2]} == {"ingreso", "edad"}


def test_un_modelo_viejo_sin_referencia_no_rompe(client, modelo_guardado, dataset_binary):
    res, _ = modelo_guardado
    viejo = {k: v for k, v in res["bundle"].items() if k != "referencia_deriva"}
    card = registry.save(viejo, res["report"], "viejo", dataset_binary.id)
    r = client.post("/api/automl/monitor",
                    json={"model_id": card["id"], "dataset_id": dataset_binary.id})
    assert r.status_code == 200
    assert r.json()["disponible"] is False


def test_un_modelo_o_dataset_inexistente_da_404(client, modelo_guardado):
    _, card = modelo_guardado
    r = client.post("/api/automl/monitor", json={"model_id": "mdl_nada", "dataset_id": "x"})
    assert r.status_code == 404
    r = client.post("/api/automl/monitor", json={"model_id": card["id"], "dataset_id": "ds_nada"})
    assert r.status_code == 404


def test_el_monitoreo_respeta_la_licencia(client, monkeypatch):
    monkeypatch.setattr(L, "load", lambda: None)
    r = client.post("/api/automl/monitor", json={"model_id": "m", "dataset_id": "d"})
    assert r.status_code == 402
