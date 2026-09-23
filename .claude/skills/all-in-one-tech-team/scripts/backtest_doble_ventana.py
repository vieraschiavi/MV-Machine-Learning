#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
===============================================================================
 BACKTEST DE DOBLE VENTANA — motor generico de proyeccion de series
===============================================================================
 Que hace:
   - Walk-forward expansivo h=1 con refit en cada paso.
   - Parte las ventanas en SELECCION (elegis aca) y HOLDOUT CIEGO (medis aca).
   - Compara dos politicas: elegir campeon por serie vs combinar un pool fijo.
   - Skill score vs naive -> declara series NO PROYECTABLES.
   - Umbrales de semaforo calibrados por percentiles del error real de la serie.

 Generico: cualquier panel de series. Sin dependencias de negocio.

 Entrada: DataFrame/CSV largo con columnas [serie_id, fecha, valor]
          (nombres configurables) o un dict {id: pd.Series indexada por fecha}.

 Uso:
   python backtest_doble_ventana.py datos.csv --id serie --fecha ds --valor y
   python backtest_doble_ventana.py --demo
===============================================================================
"""
from __future__ import annotations
import argparse, sys, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")

SEASON = 12          # periodicidad; 12=mensual, 7=diario-semanal, 4=trimestral
VENTANAS = [0, 6, 9, 12, 18, 24]     # 0 = toda la historia


# ------------------------------------------------------------------ metodos
def m_naive(h):    return float(h[-1])
def m_media3(h):   return float(np.mean(h[-3:]))
def m_media6(h):   return float(np.mean(h[-6:]))
def m_mediana3(h): return float(np.median(h[-3:]))


def m_ewma(h, a=.5):
    k = min(6, len(h)); w = np.array([a ** i for i in range(k)])[::-1]; w /= w.sum()
    return float(np.dot(h[-k:], w))


def m_drift(h, k=SEASON):
    if len(h) < 4: return float(h[-1])
    k = min(k, len(h) - 1)
    return float(h[-1] + (h[-1] - h[-1 - k]) / k)


def m_lin(h, n=6):
    if len(h) < n: return m_media3(h)
    return float(np.polyval(np.polyfit(np.arange(n), h[-n:], 1), n))


def m_snaive(h):
    return float(h[-SEASON]) if len(h) >= SEASON else float(h[-1])


def m_seas_adj(h):
    if len(h) < SEASON + 4: return m_media3(h)
    ref = np.mean(h[-SEASON - 2:-SEASON + 1])
    fac = h[-SEASON] / ref if ref else 1.0
    return float(np.mean(h[-3:]) * float(np.clip(fac, .7, 1.4)))


def m_holt(h):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    if len(h) < 8: return m_media3(h)
    try:
        return float(ExponentialSmoothing(h, trend="add", damped_trend=True,
                     initialization_method="estimated").fit().forecast(1)[0])
    except Exception:
        return m_media3(h)


def m_theta(h):
    if len(h) < 8: return m_media3(h)
    n = len(h); b, a = np.polyfit(np.arange(n), h, 1)
    return float(.5 * (a + b * n) + .5 * m_ewma(h, .6))


def m_arima(h):
    from statsmodels.tsa.arima.model import ARIMA
    if len(h) < 8: return m_media3(h)
    try: return float(ARIMA(h, order=(1, 1, 0)).fit().forecast(1)[0])
    except Exception: return m_media3(h)


METODOS = {"Naive": m_naive, "Media3": m_media3, "Media6": m_media6, "Mediana3": m_mediana3,
           "EWMA": m_ewma, "Drift": m_drift, "Lin6": lambda h: m_lin(h, 6),
           "Lin9": lambda h: m_lin(h, 9), "SNaive": m_snaive, "SeasAdj": m_seas_adj,
           "Holt": m_holt, "Theta": m_theta, "ARIMA110": m_arima}
MIN_OBS = {"Naive": 1, "Media3": 3, "Media6": 6, "Mediana3": 3, "EWMA": 3, "Drift": 4,
           "Lin6": 6, "Lin9": 9, "SNaive": SEASON, "SeasAdj": SEASON + 4, "Holt": 8,
           "Theta": 8, "ARIMA110": 8}

# Pools por tipo de serie. La eleccion es ESTRUCTURAL, no por metrica.
POOL_FLUJO = ["Media3@0", "Media3@12", "EWMA@0", "Mediana3@0", "Naive@0",
              "Holt@12", "Theta@12", "SeasAdj@0", "Lin6@12"]
POOL_STOCK = ["Holt@12", "Holt@24", "Holt@0", "Drift@12", "Drift@24",
              "Lin6@12", "Lin9@12", "ARIMA110@0"]


def predecir(nombre, h):
    base, ven = nombre.split("@"); ven = int(ven)
    h = np.asarray(h, float)
    hh = h if ven == 0 else h[-ven:]
    if len(hh) < MIN_OBS.get(base, 3): return np.nan
    try:
        v = METODOS[base](hh)
        return float(v) if np.isfinite(v) else np.nan
    except Exception:
        return np.nan


def todos_los_modelos():
    return [f"{m}@{v}" for m in METODOS for v in VENTANAS]


# ----------------------------------------------------------------- metricas
def wmape(r, p):
    r, p = np.asarray(r, float), np.asarray(p, float)
    ok = np.isfinite(r) & np.isfinite(p); r, p = r[ok], p[ok]
    den = np.abs(r).sum()
    return float(np.abs(r - p).sum() / den * 100) if den else np.inf


def metricas(r, p):
    r, p = np.asarray(r, float), np.asarray(p, float)
    ok = np.isfinite(r) & np.isfinite(p); r, p = r[ok], p[ok]
    if len(r) == 0: return dict(wmape=np.inf, mape=np.inf, r2=np.nan, diracc=np.nan, n=0)
    m = r != 0
    mape = float(np.mean(np.abs(r[m] - p[m]) / np.abs(r[m])) * 100) if m.any() else np.inf
    sst = np.sum((r - r.mean()) ** 2)
    da = float(np.mean(np.sign(np.diff(r)) == np.sign(np.diff(p))) * 100) if len(r) > 1 else np.nan
    return dict(wmape=wmape(r, p), mape=mape,
                r2=float(1 - np.sum((r - p) ** 2) / sst) if sst > 0 else np.nan,
                diracc=da, n=int(len(r)))


# ------------------------------------------------------------------- motor
def backtest(series: dict, n_windows=18, n_seleccion=12, pool=None, tipo="flujo"):
    """series: {id: pd.Series indexada por fecha, ordenada}."""
    modelos = todos_los_modelos()
    pool = pool or (POOL_STOCK if tipo == "stock" else POOL_FLUJO)
    pool = [p for p in pool if p in modelos]

    filas = []
    for uid, s in series.items():
        s = s.sort_index(); v = s.values.astype(float)
        objetivos = list(range(max(len(v) - n_windows, 8), len(v)))
        for t in objetivos:
            row = dict(serie=uid, ds=s.index[t], y=float(v[t]))
            for mname in modelos:
                row[mname] = predecir(mname, v[:t])
            row["POOL"] = float(np.nanmean([row[m] for m in pool])) \
                if np.isfinite([row[m] for m in pool]).any() else np.nan
            filas.append(row)
    cv = pd.DataFrame(filas)

    fechas = sorted(cv.ds.unique())
    f_sel, f_hold = fechas[:n_seleccion], fechas[n_seleccion:]
    if not f_hold:
        raise ValueError("No queda holdout: bajá n_seleccion o subí n_windows")

    def evaluar(fs, cols):
        out = []
        sub = cv[cv.ds.isin(fs)]
        for uid, g in sub.groupby("serie"):
            for m in cols:
                d = metricas(g.y.values, g[m].values)
                if d["n"]: d.update(serie=uid, modelo=m); out.append(d)
        return pd.DataFrame(out)

    cols = modelos + ["POOL"]
    ev_sel, ev_hold = evaluar(f_sel, cols), evaluar(f_hold, cols)

    # politica A: campeon elegido en SELECCION, medido en HOLDOUT
    camp = (ev_sel[np.isfinite(ev_sel.wmape) & (ev_sel.modelo != "POOL")]
            .sort_values("wmape").groupby("serie").first().reset_index()
            [["serie", "modelo", "wmape"]].rename(columns={"modelo": "campeon",
                                                           "wmape": "wmape_sel_campeon"}))
    hold = ev_hold.rename(columns={"modelo": "campeon", "wmape": "wmape_hold_campeon"})
    camp = camp.merge(hold[["serie", "campeon", "wmape_hold_campeon"]],
                      on=["serie", "campeon"], how="left")
    # politica B: pool fijo
    pl = ev_hold[ev_hold.modelo == "POOL"][["serie", "wmape", "mape", "r2", "diracc"]] \
        .rename(columns={"wmape": "wmape_hold_pool"})
    nv = ev_hold[ev_hold.modelo == "Naive@0"][["serie", "wmape"]] \
        .rename(columns={"wmape": "wmape_naive"})
    R = camp.merge(pl, on="serie", how="outer").merge(nv, on="serie", how="left")
    R["skill_pool"] = (1 - R.wmape_hold_pool / R.wmape_naive) * 100
    R["calidad"] = np.where(R.wmape_hold_pool <= 8, "ALTA",
                    np.where(R.wmape_hold_pool <= 15, "MEDIA",
                    np.where(R.wmape_hold_pool <= 30, "BAJA", "NO PROYECTABLE")))
    # Un skill bajo con error bajo NO es una serie imposible: es una serie facil,
    # donde el naive ya alcanza. Solo se degrada a NO PROYECTABLE si ademas el
    # error absoluto es alto: ahi el modelo no aporta Y encima falla.
    R.loc[(R.skill_pool <= 0) & (R.wmape_hold_pool > 15), "calidad"] = "NO PROYECTABLE"
    R["nota"] = np.where((R.skill_pool <= 0) & (R.wmape_hold_pool <= 15),
                         "naive alcanza: no complicar el modelo", "")

    # umbrales de semaforo por percentiles del error real de cada serie
    umb = {}
    for uid in series:
        g = cv[cv.serie == uid]
        e = np.abs((g["POOL"] - g.y) / g.y.replace(0, np.nan)) * 100
        e = e[np.isfinite(e)]
        umb[uid] = (float(np.percentile(e, 50)), float(np.percentile(e, 80))) if len(e) >= 5 else (10., 20.)
    return cv, R, umb, (f_sel, f_hold)


def resumen(R):
    print("\n" + "=" * 74)
    print("POLITICA A (elegir campeon)  vs  POLITICA B (combinar pool fijo)")
    print("=" * 74)
    a, b = R.wmape_hold_campeon, R.wmape_hold_pool
    ok = np.isfinite(a) & np.isfinite(b)
    print(f"  WMAPE mediana en HOLDOUT   campeon={a[ok].median():6.2f}%   pool={b[ok].median():6.2f}%")
    print(f"  WMAPE media   en HOLDOUT   campeon={a[ok].mean():6.2f}%   pool={b[ok].mean():6.2f}%")
    print(f"  Brecha del campeon (seleccion -> holdout): "
          f"{R.wmape_sel_campeon.median():.2f}% -> {a[ok].median():.2f}%")
    print(f"  El pool gana en {(b < a)[ok].sum()}/{ok.sum()} series")
    print(f"\n  GANA: {'COMBINAR (pool fijo)' if b[ok].median() < a[ok].median() else 'ELEGIR CAMPEON'}")
    print("\nCalidad por serie:"); print(R.calidad.value_counts().to_string())
    return R


def demo():
    rng = np.random.default_rng(42)
    idx = pd.date_range("2023-01-01", periods=36, freq="MS")
    series = {}
    for nm, base, tend, vol, phi in [("flujo_grande", 800e6, -2e6, .06, .55),
                                     ("flujo_chico", 40e6, 0, .18, .35),
                                     ("stock", 3e9, 130e6, .01, .80),
                                     ("ruidosa", 5e6, 0, .55, .05)]:
        est = 1 + .08 * np.sin(np.arange(36) / 12 * 2 * np.pi)
        e = np.zeros(36)                      # ruido AR(1): las series reales
        for i in range(1, 36):                # tienen memoria, el ruido iid no
            e[i] = phi * e[i - 1] + rng.normal(0, vol)
        v = (base + tend * np.arange(36)) * est * (1 + e)
        series[nm] = pd.Series(np.clip(v, 0, None), index=idx)
    print("DEMO: 4 series x 36 meses\n")
    cv, R, umb, (fs, fh) = backtest(series, n_windows=18, n_seleccion=12)
    print(f"SELECCION {pd.Timestamp(fs[0]):%Y-%m}..{pd.Timestamp(fs[-1]):%Y-%m} | "
          f"HOLDOUT {pd.Timestamp(fh[0]):%Y-%m}..{pd.Timestamp(fh[-1]):%Y-%m}")
    print(R[["serie", "campeon", "wmape_sel_campeon", "wmape_hold_campeon",
             "wmape_hold_pool", "skill_pool", "calidad", "nota"]].round(2).to_string(index=False))
    resumen(R)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?"); ap.add_argument("--id", default="serie")
    ap.add_argument("--fecha", default="ds"); ap.add_argument("--valor", default="y")
    ap.add_argument("--ventanas", type=int, default=18)
    ap.add_argument("--seleccion", type=int, default=12)
    ap.add_argument("--tipo", default="flujo", choices=["flujo", "stock"])
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    if a.demo or not a.csv:
        demo()
    else:
        d = pd.read_csv(a.csv)
        d[a.fecha] = pd.to_datetime(d[a.fecha])
        series = {k: g.set_index(a.fecha)[a.valor].sort_index() for k, g in d.groupby(a.id)}
        cv, R, umb, _ = backtest(series, a.ventanas, a.seleccion, tipo=a.tipo)
        print(R.round(2).to_string(index=False)); resumen(R)
        R.to_csv("performance_doble_ventana.csv", index=False)
        print("\n-> performance_doble_ventana.csv")
