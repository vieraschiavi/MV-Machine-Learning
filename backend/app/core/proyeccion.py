"""Proyección de series de tiempo, con el backtest adelante y no atrás.

Proyectar es fácil: cualquier modelo devuelve una línea que sigue. El problema
es que esa línea puede no valer nada y verse igual de convincente en el
gráfico. Por eso acá el orden está invertido respecto de lo habitual:

    1. se corre un **backtest walk-forward** con varios candidatos,
    2. se los ordena por MASE contra el mismo conjunto de orígenes,
    3. **recién entonces** se proyecta, con el que ganó,
    4. y se informa por cuánto ganó —o que no le ganó a nada—.

MASE compara el error contra la naive estacional del propio tramo de
entrenamiento: 1,00 es «igual que repetir el año pasado». Debajo de 1 el
modelo aporta; arriba de 1 el modelo molesta, y el programa lo dice.

Por qué estos modelos y no un modelo de fundación: se midió. Sobre series
mensuales cortas de negocio —36 meses, horizonte de 3, que es el caso de
cualquier PyME— Holt-Winters quedó en MASE 0,65 contra 0,72 de TimesFM 2.5
zero-shot, sin sumar 2,5 GB al instalador ni depender de internet. En series
largas el modelo de fundación gana, pero ése no es el caso que se vende.
Todo esto sale de statsmodels, que ya viajaba en el paquete.
"""
from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from . import storage as S

GRANOS = {"day": 7, "week": 52, "month": 12, "quarter": 4, "year": 1}
AGREGACIONES = {"sum": "sum", "avg": "avg", "count": "count", "min": "min", "max": "max"}
MIN_CICLOS = 2          # menos de dos ciclos y la estacionalidad es una ilusión
MIN_PUNTOS = 8
# Cuántos modelos se promedian para proyectar. Apostar al ganador del backtest
# parece lo obvio y mide PEOR: con 30 puntos de historia, el backtest interno
# es ruidoso y a veces corona a un modelo que ganó de casualidad. Promediar los
# tres mejores amortigua ese error de selección. Medido sobre las series de
# cobranzas del repo (36 meses, horizonte 3): combinar 3 da MASE 0,622 contra
# 0,712 de quedarse con el mejor y 0,647 de fijar Holt-Winters a mano.
COMBINAR = 3


def _q(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


# ═══════════════════════════════════════════════════════════════ métricas ════
def _escala(train, m: int) -> float:
    """Denominador del MASE: cuánto erraría repetir el período anterior.

    En una serie perfectamente periódica ese error es CERO y el MASE queda
    indefinido — justo en la serie más predecible de todas, que es cuando el
    usuario más espera un número. Ahí se cae a la variación media de la serie,
    que sigue siendo una unidad honesta para escalar el error.
    """
    train = np.asarray(train, float)
    k = m if (m > 1 and len(train) > m) else 1
    e = float(np.mean(np.abs(train[k:] - train[:-k]))) if len(train) > k else 0.0
    if np.isfinite(e) and e > 0:
        return e
    e = float(np.mean(np.abs(np.diff(train)))) if len(train) > 1 else 0.0
    if np.isfinite(e) and e > 0:
        return e
    e = float(np.mean(np.abs(train - np.mean(train)))) if len(train) else 0.0
    return e if np.isfinite(e) and e > 0 else float("nan")


def mase(real, pred, train, m: int) -> float:
    """Error escalado por la naive estacional del entrenamiento."""
    escala = _escala(train, m)
    if not np.isfinite(escala):
        return float("nan")
    return float(np.mean(np.abs(np.asarray(real, float) - np.asarray(pred, float))) / escala)


def smape(real, pred) -> float:
    real, pred = np.asarray(real, float), np.asarray(pred, float)
    den = (np.abs(real) + np.abs(pred)) / 2
    ok = den > 0
    return float(np.mean(np.abs(real[ok] - pred[ok]) / den[ok]) * 100) if ok.any() else float("nan")


# ════════════════════════════════════════════════════════════════ modelos ════
def _naive_estacional(train, h: int, m: int):
    train = np.asarray(train, float)
    if m > 1 and len(train) >= m:
        ult = train[-m:]
        return np.array([ult[i % m] for i in range(h)])
    return np.repeat(train[-1], h)


def _media_movil(train, h: int, m: int):
    train = np.asarray(train, float)
    v = int(min(max(m, 3), len(train)))
    return np.repeat(float(np.mean(train[-v:])), h)


def _media_historica(train, h: int, m: int):
    """Predecir siempre el promedio de todo lo visto. El piso absoluto."""
    return np.repeat(float(np.mean(np.asarray(train, float))), h)


def _deriva(train, h: int, m: int):
    """Última observación más la pendiente media de toda la serie."""
    train = np.asarray(train, float)
    if len(train) < 2:
        return np.repeat(train[-1], h)
    paso = (train[-1] - train[0]) / (len(train) - 1)
    return train[-1] + paso * np.arange(1, h + 1)


def _ets(tendencia: str | None, estacional: str | None) -> Callable:
    def modelo(train, h: int, m: int):
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        y = np.asarray(train, float)
        usa_est = estacional is not None and m > 1 and len(y) >= MIN_CICLOS * m + 4
        # Holt-Winters multiplicativo necesita valores estrictamente positivos.
        if usa_est and estacional == "mul" and np.any(y <= 0):
            return _naive_estacional(train, h, m)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                f = ExponentialSmoothing(
                    y, trend=tendencia,
                    seasonal=estacional if usa_est else None,
                    seasonal_periods=m if usa_est else None,
                    initialization_method="estimated").fit()
                p = np.asarray(f.forecast(h), float)
            except Exception:
                return _naive_estacional(train, h, m)
        return p if np.all(np.isfinite(p)) else _naive_estacional(train, h, m)

    return modelo


# Los "triviales" no aprenden ningún patrón: repiten, promedian o siguen la
# recta. Si el ganador sale de acá, la serie no tiene estructura que valga la
# pena modelar, y el veredicto lo dice en vez de disfrazarlo de proyección.
TRIVIALES = {"naive estacional", "media móvil", "media histórica"}

MODELOS: dict[str, Callable] = {
    "naive estacional": _naive_estacional,
    "media histórica": _media_historica,
    "media móvil": _media_movil,
    "deriva": _deriva,
    "tendencia (Holt)": _ets("add", None),
    "estacional (Holt-Winters)": _ets("add", "add"),
    "estacional multiplicativo": _ets("add", "mul"),
}


# ═══════════════════════════════════════════════════════════════ la serie ════
def serie(ds_id: str, columna_tiempo: str, columna_valor: str, grano: str = "month",
          agregacion: str = "sum", filtro: dict[str, str] | None = None) -> dict[str, Any]:
    """Agrupa el dataset por período y devuelve la serie lista para proyectar."""
    if grano not in GRANOS:
        raise ValueError(f"Grano no soportado: {grano!r}. Usá uno de {sorted(GRANOS)}.")
    if agregacion not in AGREGACIONES:
        raise ValueError(f"Agregación no soportada: {agregacion!r}.")

    meta = S.load_meta(ds_id)
    tipos = {c["name"]: str(c.get("arrow_type", "")).lower() for c in meta.columns}
    for col in (columna_tiempo, columna_valor):
        if col not in tipos:
            raise ValueError(f"La columna «{col}» no existe en el dataset.")
    if not any(t in tipos[columna_tiempo] for t in ("timestamp", "date")):
        raise ValueError(f"«{columna_tiempo}» no es una fecha "
                         f"(es {tipos[columna_tiempo]}): no se puede agrupar por período.")

    qt, qv = _q(columna_tiempo), _q(columna_valor)
    where = [f"{qt} IS NOT NULL"]
    params: list[Any] = []
    if filtro:
        for col, val in filtro.items():
            if col in tipos:
                where.append(f"CAST({_q(col)} AS VARCHAR) = ?")
                params.append(str(val))
    agg = "count(*)" if agregacion == "count" else f"{agregacion}({qv})"

    con = S.connect()
    try:
        df = con.execute(
            f"SELECT date_trunc('{grano}', {qt}) AS p, {agg} AS v "
            f"FROM {S.glob_expr(ds_id)} WHERE {' AND '.join(where)} "
            f"GROUP BY 1 ORDER BY 1", params).df()
    finally:
        con.close()

    df = df.dropna()
    return {
        "periodos": [pd.Timestamp(p).strftime("%Y-%m-%d") for p in df["p"]],
        "valores": [float(v) for v in df["v"]],
        "grano": grano, "estacionalidad": GRANOS[grano],
        "columna_tiempo": columna_tiempo, "columna_valor": columna_valor,
        "agregacion": agregacion,
    }


# ══════════════════════════════════════════════════════════════ backtest ═════
def _origenes(n: int, h: int, m: int, n_origenes: int) -> list[int]:
    """Cortes donde se evalúa. Cada uno deja `h` puntos reales por delante."""
    minimo = max(MIN_PUNTOS, m + h if m > 1 else 2 * h)
    ultimo = n - h
    if ultimo < minimo:
        return []
    return sorted({int(t) for t in np.linspace(minimo, ultimo, n_origenes)})


def backtest(valores, m: int, h: int, modelos: dict[str, Callable] | None = None,
             n_origenes: int = 6) -> list[dict[str, Any]]:
    """Walk-forward: en cada corte el modelo ve SÓLO el pasado.

    Devuelve una fila por (modelo, origen). Todos los modelos reciben los
    mismos cortes: comparar un modelo en meses fáciles contra otro en meses
    difíciles no es una comparación, es elegir el resultado.
    """
    y = np.asarray(valores, float)
    modelos = modelos or MODELOS
    filas: list[dict[str, Any]] = []
    for t in _origenes(len(y), h, m, n_origenes):
        train, real = y[:t], y[t:t + h]
        for nombre, f in modelos.items():
            try:
                pred = np.asarray(f(train, h, m), float)[:h]
            except Exception:
                continue
            if len(pred) < h or not np.all(np.isfinite(pred)):
                continue
            filas.append({"modelo": nombre, "origen": int(t),
                          "MASE": mase(real, pred, train, m), "sMAPE": smape(real, pred)})
    return filas


def _resumen(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not filas:
        return []
    df = pd.DataFrame(filas)
    g = (df.groupby("modelo")
           .agg(MASE=("MASE", "mean"), sMAPE=("sMAPE", "mean"), origenes=("MASE", "size"))
           .reset_index().sort_values("MASE"))
    return [{"modelo": r.modelo, "MASE": round(float(r.MASE), 4),
             "sMAPE": round(float(r.sMAPE), 2), "origenes": int(r.origenes)}
            for r in g.itertuples() if np.isfinite(r.MASE)]


# ═══════════════════════════════════════════════════════════ la proyección ═══
def _siguientes(ultimo: str, grano: str, h: int) -> list[str]:
    paso = {"day": pd.DateOffset(days=1), "week": pd.DateOffset(weeks=1),
            "month": pd.DateOffset(months=1), "quarter": pd.DateOffset(months=3),
            "year": pd.DateOffset(years=1)}[grano]
    t = pd.Timestamp(ultimo)
    return [(t + paso * (i + 1)).strftime("%Y-%m-%d") for i in range(h)]


def _veredicto(mejor: dict[str, Any] | None, piso: dict[str, Any] | None) -> dict[str, str]:
    """Qué tan en serio tomar la proyección.

    La vara NO es sólo la naive estacional: es el MEJOR de los modelos
    triviales —repetir el año pasado, el promedio de siempre, el promedio
    reciente—. La diferencia importa: sobre ruido puro, el promedio le gana
    holgadamente a repetir el año pasado, así que medir sólo contra la naive
    daría un MASE de 0,7 y un veredicto tranquilizador para una serie que no
    tiene absolutamente nada que aprender. Comparando contra el mejor trivial,
    el ruido se delata: el ganador ES un trivial.
    """
    if mejor is None:
        return {"nivel": "alerta",
                "texto": "No se pudo evaluar ningún modelo sobre esta serie. La proyección "
                         "que se muestra es sólo la continuación de lo último observado."}
    mase_mejor = mejor["MASE"]

    if mejor["modelo"] in TRIVIALES:
        return {"nivel": "alerta",
                "texto": f"Lo que mejor funciona en esta serie es «{mejor['modelo']}», que no "
                         f"aprende ningún patrón: se limita a repetir o promediar lo ya visto. "
                         f"Ningún modelo con estacionalidad ni tendencia le ganó, así que la "
                         f"serie no tiene una forma aprovechable. Tomá la proyección como "
                         f"referencia gruesa, no como número de presupuesto."}
    ref = piso["MASE"] if piso else None
    if mase_mejor >= 1:
        return {"nivel": "alerta",
                "texto": f"El mejor modelo quedó en MASE {mase_mejor:.2f}, y 1,00 significa "
                         f"errar lo mismo que repetir el período anterior. No hay señal que "
                         f"aprovechar en esta serie."}
    if ref is not None and mase_mejor > ref * 0.95:
        return {"nivel": "revisar",
                "texto": f"«{mejor['modelo']}» quedó apenas mejor que lo trivial "
                         f"({mase_mejor:.2f} contra {ref:.2f} de «{piso['modelo']}»). La "
                         f"ganancia es chica: mirá la banda tanto como la línea."}
    mejora = (1 - mase_mejor / ref) * 100 if ref else (1 - mase_mejor) * 100
    return {"nivel": "ok",
            "texto": f"«{mejor['modelo']}» erró {mejora:.0f}% menos que el mejor método trivial "
                     f"en las pruebas hacia atrás (MASE {mase_mejor:.2f} contra {ref:.2f}). "
                     f"La banda muestra el rango razonable, no sólo la línea."}


def proyectar_serie(s: dict[str, Any], horizonte: int = 6,
                    n_origenes: int = 6) -> dict[str, Any]:
    """Backtestea, elige el mejor y proyecta con él."""
    y = np.asarray(s["valores"], float)
    m = int(s.get("estacionalidad", 12))
    n = len(y)
    if horizonte < 1:
        raise ValueError("El horizonte tiene que ser al menos 1 período.")
    if n < MIN_PUNTOS:
        raise ValueError(f"La serie es demasiado corta: {n} períodos. Hacen falta al menos "
                         f"{MIN_PUNTOS} para medir algo, y {MIN_CICLOS * m} para aprovechar "
                         f"la estacionalidad.")
    if horizonte > n // 2:
        raise ValueError(f"Un horizonte de {horizonte} períodos sobre {n} de historia es "
                         f"adivinar, no proyectar. El tope es {n // 2}.")

    filas = backtest(y, m=m, h=horizonte, n_origenes=n_origenes)
    tabla = _resumen(filas)
    mejor = tabla[0] if tabla else None
    naive = next((f for f in tabla if f["modelo"].startswith("naive")), None)
    # El piso contra el que se juzga: el mejor de los métodos que no aprenden nada.
    piso = next((f for f in tabla if f["modelo"] in TRIVIALES), None)

    elegidos = [f["modelo"] for f in tabla[:COMBINAR]] or ["naive estacional"]
    nombre = (elegidos[0] if len(elegidos) == 1
              else "combinación de " + ", ".join(f"«{e}»" for e in elegidos))
    pred = np.mean([np.asarray(MODELOS[e](y, horizonte, m), float)[:horizonte]
                    for e in elegidos], axis=0)

    # La banda sale del error real que cometió ESE modelo en el backtest, no
    # de un supuesto de normalidad: es el rango en el que se equivocó antes.
    errores = [f["MASE"] for f in filas
               if f["modelo"] in elegidos and np.isfinite(f["MASE"])]
    k = m if (m > 1 and n > m) else 1
    escala = float(np.mean(np.abs(y[k:] - y[:-k]))) if n > k else float(np.std(y))
    margen = float(np.median(errores) if errores else 1.0) * escala
    # El error se ensancha con la distancia: el mes 6 es más incierto que el 1.
    ensanche = np.sqrt(np.arange(1, horizonte + 1))

    periodos = _siguientes(s["periodos"][-1], s["grano"], horizonte)
    proyeccion = [{"periodo": p, "valor": round(float(v), 4),
                   "inferior": round(float(v - margen * e), 4),
                   "superior": round(float(v + margen * e), 4)}
                  for p, v, e in zip(periodos, pred, ensanche, strict=False)]

    return {
        "serie": {k2: s[k2] for k2 in ("periodos", "valores", "grano", "estacionalidad")},
        "columna_valor": s.get("columna_valor"), "columna_tiempo": s.get("columna_tiempo"),
        "horizonte": horizonte, "proyeccion": proyeccion,
        "modelo_elegido": nombre, "modelos_combinados": elegidos, "backtest": tabla,
        "mejor_mase": mejor["MASE"] if mejor else None,
        "mase_baseline": naive["MASE"] if naive else None,
        "veredicto": _veredicto(mejor, piso),
        "mase_piso_trivial": piso["MASE"] if piso else None,
        "modelo_piso_trivial": piso["modelo"] if piso else None,
        "origenes_evaluados": len({f["origen"] for f in filas}),
    }


def proyectar(ds_id: str, columna_tiempo: str, columna_valor: str, horizonte: int = 6,
              grano: str = "month", agregacion: str = "sum",
              filtro: dict[str, str] | None = None) -> dict[str, Any]:
    """Del dataset a la proyección, en una sola llamada."""
    s = serie(ds_id, columna_tiempo, columna_valor, grano, agregacion, filtro)
    out = proyectar_serie(s, horizonte)
    out["agregacion"] = agregacion
    return out
