#!/usr/bin/env python3
"""Backtest del motor de proyecciones. Reproducible con lo que trae el repo.

    python scripts/backtest_proyeccion.py

Corre walk-forward por origen sobre series públicas (statsmodels) y sobre las
series de negocio de `examples/`, y compara el motor del producto contra los
métodos triviales. Sin dependencias extra: usa lo mismo que viaja en el .exe.

Si además hay `timesfm` y `torch` instalados —que NO viajan en el producto—,
agrega TimesFM 2.5 a la comparación con `--con-timesfm`. Así se puede
reverificar la decisión de no empaquetar un modelo de fundación en vez de
tener que creerle a un documento.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
warnings.filterwarnings("ignore")

from app.core import proyeccion as P  # noqa: E402


def motor(train, h, m):
    """El motor tal como proyecta en la aplicación: mide y combina los mejores."""
    filas, _ = P.backtest(np.asarray(train, float), m=m, h=h, n_origenes=5)
    tabla, _parciales, _comunes = P._resumen(filas)
    elegidos = [f["modelo"] for f in tabla[:P.COMBINAR]] or ["naive estacional"]
    return np.mean([np.asarray(P.MODELOS[e](train, h, m), float)[:h] for e in elegidos], axis=0)


def series_publicas():
    import statsmodels.api as sm

    out = []
    co2 = sm.datasets.co2.load_pandas().data["co2"].resample("MS").mean().dropna()
    out.append(("CO2 Mauna Loa (mensual)", co2.to_numpy(float), 12, 12))
    mac = sm.datasets.macrodata.load_pandas().data
    out.append(("PBI real EE.UU. (trimestral)", mac["realgdp"].to_numpy(float), 4, 8))
    out.append(("Desempleo EE.UU. (trimestral)", mac["unemp"].to_numpy(float), 4, 8))
    out.append(("Inflación EE.UU. (trimestral)", mac["infl"].to_numpy(float), 4, 8))
    out.append(("Manchas solares (anual)",
                sm.datasets.sunspots.load_pandas().data["SUNACTIVITY"].to_numpy(float), 11, 6))
    out.append(("Caudal del Nilo (anual)",
                sm.datasets.nile.load_pandas().data["volume"].to_numpy(float), 1, 6))
    return out


def series_de_negocio():
    """Las del repo: mensuales y cortas, el perfil del cliente real."""
    f = RAIZ / "examples" / "cobranzas_panel.xlsx"
    if not f.exists():
        return []
    d = pd.read_excel(f)
    out = [("Cobranzas TOTAL",
            d.groupby("FechaObs")["TotalCobrado"].sum().sort_index().to_numpy(float), 12, 3)]
    for tramo, g in d.groupby("TramoDeuda"):
        out.append((f"Cobranzas tramo {tramo}",
                    g.groupby("FechaObs")["TotalCobrado"].sum().sort_index().to_numpy(float), 12, 3))
    return out


def evaluar(pares, arranque_fijo=None, n_origenes=8, con_timesfm=False):
    tfm = None
    if con_timesfm:
        import timesfm
        import torch

        torch.set_float32_matmul_precision("high")
        tfm = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
        tfm.compile(timesfm.ForecastConfig(
            max_context=1024, max_horizon=64, normalize_inputs=True,
            use_continuous_quantile_head=True, force_flip_invariance=True,
            infer_is_positive=True, fix_quantile_crossing=True))

    filas = []
    for nombre, y, m, h in pares:
        n = len(y)
        if arranque_fijo:
            cortes = range(arranque_fijo, n - h + 1)
        else:
            minimo = max(3 * m + h, 40)
            if n < minimo + n_origenes:
                continue
            cortes = sorted({int(t) for t in np.linspace(minimo, n - h, n_origenes)})
        for t in cortes:
            train, real = y[:t], y[t:t + h]
            if len(real) < h:
                continue
            candidatos = {
                "naive estacional": P.MODELOS["naive estacional"](train, h, m),
                "media histórica": P.MODELOS["media histórica"](train, h, m),
                "Holt-Winters fijo": P.MODELOS["estacional (Holt-Winters)"](train, h, m),
                "MOTOR MV": motor(train, h, m),
            }
            if tfm is not None:
                candidatos["TimesFM 2.5"] = np.asarray(
                    tfm.forecast(horizon=h, inputs=[np.asarray(train, float)])[0][0][:h], float)
            for modelo, pred in candidatos.items():
                filas.append({"serie": nombre, "origen": int(t), "modelo": modelo,
                              "MASE": P.mase(real, np.asarray(pred, float)[:h], train, m)})
    return pd.DataFrame(filas)


def informar(titulo, df):
    print(f"\n{'=' * 74}\n{titulo}\n{'=' * 74}")
    if df.empty:
        print("(sin series suficientes)")
        return
    g = (df.groupby("modelo")["MASE"]
           .agg(MASE_medio="mean", MASE_mediana="median", evaluaciones="size")
           .sort_values("MASE_medio"))
    print(g.round(3).to_string())
    anc = df.pivot_table(index=["serie", "origen"], columns="modelo", values="MASE").dropna()
    if not anc.empty:
        print(f"\nGanador por corte ({len(anc)} cortes):")
        print(anc.idxmin(axis=1).value_counts().to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--con-timesfm", action="store_true",
                    help="agrega TimesFM 2.5 (requiere timesfm y torch instalados aparte)")
    args = ap.parse_args()

    informar("A) SERIES DE NEGOCIO — mensuales y cortas, el caso del cliente",
             evaluar(series_de_negocio(), arranque_fijo=24, con_timesfm=args.con_timesfm))
    informar("B) SERIES PÚBLICAS LARGAS — CO2, PBI, desempleo, inflación, manchas, Nilo",
             evaluar(series_publicas(), con_timesfm=args.con_timesfm))
    print("\nMASE 1,00 = errar lo mismo que repetir el período anterior.")


if __name__ == "__main__":
    main()
