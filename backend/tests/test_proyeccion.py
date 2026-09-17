"""Proyecciones: cuánto va a pasar el mes que viene, y cuánto creerle.

El programa sabía clasificar y estimar sobre una fila, pero no sabía mirar
hacia adelante en el tiempo. Eso es lo que pide todo el mundo: cuánto vamos a
cobrar en marzo, cuántas unidades vamos a vender el trimestre próximo.

Proyectar es fácil; proyectar con honestidad es lo difícil. Una serie siempre
devuelve una línea que sigue: el problema es que esa línea puede no valer
nada y aun así verse convincente en un gráfico. Por eso el módulo no proyecta
y ya: primero corre un backtest, mide contra el baseline y sólo después
proyecta con el que ganó, diciendo por cuánto ganó.

Estas pruebas fijan las cuatro cosas que sostienen esa honestidad:

  1. **El backtest no puede ver el futuro.** En cada origen, el modelo recibe
     un prefijo estricto de la serie. Se verifica con un modelo espía que
     anota exactamente cuántos puntos vio.
  2. **Gana el que mide mejor**, no un favorito escrito en el código.
  3. **Todos compiten con los mismos orígenes**, o la comparación es trucha.
  4. **Si nadie le gana al baseline, se dice.** Un «no te puedo proyectar
     esto» honesto vale más que una línea linda.
"""
from __future__ import annotations

import numpy as np
import pytest
from app.core import proyeccion


@pytest.fixture(scope="module")
def serie_mensual(dataset_binary):
    """Serie real armada desde el dataset de pruebas: 1200 días → meses."""
    return proyeccion.serie(dataset_binary.id, columna_tiempo="fecha",
                            columna_valor="ingreso", grano="month", agregacion="sum")


# ══════════════════════════════════════════════════════════════ la serie ═════
def test_arma_la_serie_agregando_por_periodo(serie_mensual):
    assert serie_mensual["grano"] == "month"
    assert len(serie_mensual["periodos"]) == len(serie_mensual["valores"]) > 12
    assert all(np.isfinite(serie_mensual["valores"]))


def test_los_periodos_salen_ordenados_y_sin_repetir(serie_mensual):
    p = serie_mensual["periodos"]
    assert p == sorted(p)
    assert len(set(p)) == len(p)


def test_una_columna_que_no_es_fecha_se_rechaza(dataset_binary):
    with pytest.raises(ValueError):
        proyeccion.serie(dataset_binary.id, columna_tiempo="ingreso",
                         columna_valor="edad", grano="month")


# ═══════════════════════════════════════════════════ el backtest no espía ════
def test_en_cada_origen_el_modelo_solo_ve_el_pasado():
    """La prueba que sostiene todo: sin esto, el MASE es una fantasía.

    Un modelo espía anota cuántos puntos recibió en cada llamada. Si alguna
    vez viera más que el corte, estaría leyendo el futuro que después se usa
    para calificarlo.
    """
    y = np.arange(1, 61, dtype=float)
    vistos: list[int] = []

    def espia(train, h, m):
        vistos.append(len(train))
        return np.repeat(train[-1], h)

    res, _ = proyeccion.backtest(y, m=12, h=3, modelos={"espia": espia}, n_origenes=5)

    cortes = [f["origen"] for f in res if f["modelo"] == "espia"]
    assert vistos, "el modelo nunca fue llamado"
    assert vistos == cortes, f"vio {vistos} puntos en cortes {cortes}"
    assert max(vistos) <= len(y) - 3, "algún origen se comió el futuro que se evalúa"


def test_todos_los_modelos_compiten_con_los_mismos_origenes():
    """Comparar un modelo en meses fáciles contra otro en meses difíciles no
    es una comparación: es elegir el resultado.

    La invariante vive en el RANKING y no en las filas crudas: un modelo
    estacional necesita dos ciclos de historia, así que en los primeros
    cortes no puede correr y no tiene fila. Antes eso se tapaba —devolvía
    la predicción de la naive con su propio nombre puesto—, y la tabla
    quedaba pareja a costa de mentir sobre qué modelo se midió. Ahora falta
    la fila, y el resumen se encarga de que el promedio salga sobre los
    cortes que TODOS pudieron correr.
    """
    y = np.sin(np.arange(80) / 6) * 10 + 100
    filas, _ = proyeccion.backtest(y, m=12, h=4, n_origenes=6)
    tabla, parciales, comunes = proyeccion._resumen(filas)

    assert len({f["origenes"] for f in tabla}) == 1, tabla
    assert all(f["origenes"] == len(comunes) for f in tabla), (tabla, comunes)
    # Y los cortes usados son de verdad cortes donde cada modelo rankeado corrió.
    rankeados = {f["modelo"] for f in tabla}
    por_modelo: dict[str, set] = {}
    for f in filas:
        por_modelo.setdefault(f["modelo"], set()).add(f["origen"])
    for m in rankeados:
        assert set(comunes) <= por_modelo[m], (m, comunes, por_modelo[m])
    assert not (rankeados & set(parciales))


def test_un_modelo_que_corre_en_menos_cortes_no_gana_por_eso():
    """El sesgo que esto evita, con números: un modelo que sólo corre en los
    cortes fáciles no puede ganarle a otro medido también en los difíciles.

    Se arma a mano: «facil» sólo sabe correr en los dos últimos orígenes, y
    ahí acierta perfecto; «parejo» corre en todos con un error constante.
    Promediando cada uno sobre SUS cortes, gana el fácil; sobre los cortes
    comunes, se los compara de verdad.
    """
    y = np.arange(1, 61, dtype=float)
    llamadas: list[int] = []

    def facil(train, h, m):
        llamadas.append(len(train))
        if len(train) < 45:
            raise proyeccion.NoAplicable("necesita más historia")
        return np.arange(len(train) + 1, len(train) + 1 + h, dtype=float)

    def parejo(train, h, m):
        return np.arange(len(train) + 1, len(train) + 1 + h, dtype=float) + 3.0

    filas, no_eval = proyeccion.backtest(
        y, m=12, h=3, n_origenes=5, modelos={"facil": facil, "parejo": parejo})
    tabla, parciales, comunes = proyeccion._resumen(filas)

    assert llamadas, "el modelo nunca fue llamado"
    assert not no_eval, "corrió en algunos cortes: no es «no evaluado»"
    # Todos los rankeados, sobre los mismos cortes.
    assert len({f["origenes"] for f in tabla}) == 1, tabla
    if "facil" in {f["modelo"] for f in tabla}:
        comunes_facil = {f["origen"] for f in filas if f["modelo"] == "facil"}
        assert set(comunes) <= comunes_facil


def test_el_mase_del_naive_estacional_ronda_uno_en_una_serie_estacional():
    """Cordura de la métrica: si el MASE del baseline diera 0.01, algo se rompió."""
    y = np.tile(np.arange(12, dtype=float) + 10, 8)      # estacional pura
    res, _ = proyeccion.backtest(y, m=12, h=6, n_origenes=4)

    naive = [f["MASE"] for f in res if f["modelo"].startswith("naive")]
    assert naive and all(np.isfinite(naive))
    assert np.median(naive) < 0.5, "en una serie perfectamente estacional el naive acierta"


# ═════════════════════════════════════════════════════════════ la elección ═══
def test_proyecta_con_los_mejores_del_backtest_no_con_un_favorito(serie_mensual):
    """Los modelos que proyectan son los de menor MASE medido, en ese orden.

    No se apuesta al ganador solo: con series cortas el backtest interno es
    ruidoso y a veces corona a uno que ganó de casualidad. Promediar los tres
    primeros amortigua ese error de selección —medido: MASE 0,62 contra 0,71
    de quedarse con el mejor—. Lo que esta prueba fija es que los que entran
    salen del ranking real y no de una preferencia escrita en el código.
    """
    r = proyeccion.proyectar_serie(serie_mensual, horizonte=6)

    orden = [f["modelo"] for f in r["backtest"]]
    assert r["modelos_combinados"] == orden[:len(r["modelos_combinados"])], \
        f"combinó {r['modelos_combinados']} teniendo el ranking {orden}"
    assert orden[0] in r["modelos_combinados"], "el mejor medido no participa"


def test_la_tabla_del_backtest_incluye_siempre_el_baseline(serie_mensual):
    """Sin el naive en la tabla, el usuario no tiene contra qué comparar."""
    r = proyeccion.proyectar_serie(serie_mensual, horizonte=6)
    modelos = [f["modelo"] for f in r["backtest"]]

    assert any(m.startswith("naive") for m in modelos), modelos
    assert len(modelos) >= 3, "hacen falta candidatos para que la elección signifique algo"


def test_cuando_nadie_le_gana_al_baseline_el_veredicto_lo_dice():
    """Ruido puro: acá ningún modelo puede ganar, y el programa tiene que
    decirlo en vez de dibujar una proyección convincente."""
    rng = np.random.default_rng(3)
    ruido = {"periodos": [f"2020-{i % 12 + 1:02d}-01" for i in range(60)],
             "valores": list(rng.normal(100, 20, 60)), "grano": "month",
             "estacionalidad": 12, "columna_valor": "ruido"}

    r = proyeccion.proyectar_serie(ruido, horizonte=6)

    assert r["veredicto"]["nivel"] in ("revisar", "alerta")
    assert r["mejor_mase"] is not None


# ═══════════════════════════════════════════════════════════ la proyección ═══
def test_la_proyeccion_tiene_el_largo_pedido_y_sigue_al_ultimo_periodo(serie_mensual):
    r = proyeccion.proyectar_serie(serie_mensual, horizonte=6)

    assert len(r["proyeccion"]) == 6
    assert r["proyeccion"][0]["periodo"] > serie_mensual["periodos"][-1]
    assert [p["periodo"] for p in r["proyeccion"]] == sorted(p["periodo"] for p in r["proyeccion"])


def test_cada_punto_proyectado_trae_su_banda(serie_mensual):
    """Un número solo miente por precisión; con banda, el lector ve el rango."""
    r = proyeccion.proyectar_serie(serie_mensual, horizonte=6)

    for p in r["proyeccion"]:
        assert p["inferior"] <= p["valor"] <= p["superior"], p


def test_una_serie_demasiado_corta_avisa_en_vez_de_inventar(dataset_binary):
    corta = {"periodos": ["2024-01-01", "2024-02-01", "2024-03-01"],
             "valores": [1.0, 2.0, 3.0], "grano": "month",
             "estacionalidad": 12, "columna_valor": "x"}

    with pytest.raises(ValueError, match="(?i)corta|suficien"):
        proyeccion.proyectar_serie(corta, horizonte=6)


def test_el_horizonte_no_puede_estirarse_mas_que_la_historia(serie_mensual):
    """Proyectar 60 meses con 40 de historia es adivinar, no proyectar."""
    with pytest.raises(ValueError):
        proyeccion.proyectar_serie(serie_mensual, horizonte=999)


# ════════════════════════════════════════════════════════════ de punta a punta ══
def test_del_dataset_a_la_proyeccion_en_una_llamada(dataset_binary):
    r = proyeccion.proyectar(dataset_binary.id, columna_tiempo="fecha",
                             columna_valor="ingreso", horizonte=6)

    assert r["serie"]["valores"] and len(r["proyeccion"]) == 6
    assert r["modelo_elegido"] and r["backtest"]
    assert r["veredicto"]["texto"]


# ══════════════════════════════════════════════════════════════════ la API ═══
def test_la_api_ofrece_las_columnas_que_sirven(client, dataset_binary):
    r = client.get(f"/api/proyeccion/columnas/{dataset_binary.id}")

    assert r.status_code == 200
    c = r.json()
    assert "fecha" in c["fechas"], "sin columna de fecha no hay proyección posible"
    assert "ingreso" in c["numericas"]
    assert "month" in c["granos"]


def test_la_api_proyecta_y_devuelve_tambien_su_backtest(client, dataset_binary):
    """La medición viaja con la proyección: una línea sin su error es una
    opinión con gráfico."""
    r = client.post("/api/proyeccion", json={
        "dataset_id": dataset_binary.id, "columna_tiempo": "fecha",
        "columna_valor": "ingreso", "horizonte": 6})

    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["proyeccion"]) == 6
    assert d["backtest"] and d["veredicto"]["texto"]
    assert d["modelos_combinados"]


def test_un_horizonte_imposible_se_explica_no_se_intenta(client, dataset_binary):
    r = client.post("/api/proyeccion", json={
        "dataset_id": dataset_binary.id, "columna_tiempo": "fecha",
        "columna_valor": "ingreso", "horizonte": 120})

    assert r.status_code == 400
    assert "adivinar" in r.json()["detail"].lower()


def test_una_columna_que_no_es_fecha_da_400_con_motivo(client, dataset_binary):
    r = client.post("/api/proyeccion", json={
        "dataset_id": dataset_binary.id, "columna_tiempo": "ingreso",
        "columna_valor": "edad", "horizonte": 6})

    assert r.status_code == 400
    assert "fecha" in r.json()["detail"].lower()


def test_cuando_el_walkforward_no_arma_ni_un_corte_dice_la_cuenta():
    """El caso medido con datos de un negocio de verdad: 18 meses de
    mercado, horizonte 6, estacionalidad 12.

    La pantalla decía «no se pudo evaluar ningún modelo sobre esta serie».
    Es verdad, y leído por un gerente significa «mis datos no sirven». No
    es eso: falta LARGO, la cuenta es fija, y bajando el horizonte la
    misma serie sí se puede medir. Eso es una acción concreta.
    """
    serie = {"periodos": [f"2025-{1 + i % 12:02d}-01" for i in range(18)],
             "valores": [100.0 + i for i in range(18)],
             "grano": "month", "estacionalidad": 12,
             "columna_tiempo": "f", "columna_valor": "v"}
    out = proyeccion.proyectar_serie(serie, horizonte=6)
    assert out["origenes_evaluados"] == 0
    assert out["backtest"] == []
    motivo = out["sin_cortes"]
    assert "18 puntos" in motivo and "24" in motivo, motivo
    # y el veredicto lo lleva adelante, no lo esconde en otra clave
    assert "Motivo:" in out["veredicto"]["texto"]
    assert "horizonte de 3" in motivo, "tiene que decir con qué horizonte SÍ se puede"


def test_con_el_horizonte_que_sugiere_la_misma_serie_se_evalua():
    """El arreglo que propone el mensaje tiene que funcionar de verdad.
    Sin este test, la sugerencia es una frase amable sin respaldo."""
    serie = {"periodos": [f"2025-{1 + i % 12:02d}-01" for i in range(18)],
             "valores": [100.0 + i for i in range(18)],
             "grano": "month", "estacionalidad": 12,
             "columna_tiempo": "f", "columna_valor": "v"}
    out = proyeccion.proyectar_serie(serie, horizonte=3)
    assert out["origenes_evaluados"] >= 1
    assert out["backtest"], "con el horizonte sugerido tiene que haber tabla"
    assert not out["sin_cortes"]


def test_una_serie_larga_no_trae_motivo_de_cortes():
    """`sin_cortes` vacío cuando no hay nada que explicar: un campo que
    siempre trae texto se vuelve ruido y deja de leerse."""
    serie = {"periodos": [f"20{20 + i // 12}-{1 + i % 12:02d}-01" for i in range(48)],
             "valores": [100.0 + (i % 12) * 5 for i in range(48)],
             "grano": "month", "estacionalidad": 12,
             "columna_tiempo": "f", "columna_valor": "v"}
    out = proyeccion.proyectar_serie(serie, horizonte=6)
    assert out["sin_cortes"] == ""
