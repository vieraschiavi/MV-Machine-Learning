"""Genera `cobranzas_panel.xlsx`: panel mensual de cobranzas sintético.

Dos decisiones que importan para que el ejemplo sirva:

* **Tramos de atraso** (`0-30`, `31-60`, …) en vez de estados internos: es la
  forma en que se mira una cartera en cualquier financiera, se ordena sola y
  cualquiera entiende el gráfico sin conocer la nomenclatura de una empresa.
* **Montos de una cartera chica** —el mes cierra alrededor de doce millones,
  no de cuatrocientos—: un ejemplo con cifras infladas distrae y no representa
  a quien lo va a probar.

El panel mantiene a propósito varias columnas que son componentes contables
del total, para que la auditoría de fuga tenga trabajo de verdad.

Los datos son inventados. No hay ninguna cifra real acá.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MESES = 36
SEMILLA = 20260819

# tramo → (peso en la cartera, tasa de cobro típica)
TRAMOS = {
    "0-30": (0.34, 0.82),
    "31-60": (0.22, 0.61),
    "61-90": (0.15, 0.44),
    "91-180": (0.14, 0.29),
    "181-360": (0.09, 0.17),
    "+360": (0.06, 0.08),
}
TIPOS = {"Consumo": 0.52, "Tarjeta": 0.31, "Prendario": 0.17}


def generar(meses: int = MESES, semilla: int = SEMILLA) -> pd.DataFrame:
    r = np.random.default_rng(semilla)
    fechas = pd.date_range("2023-06-01", periods=meses, freq="MS")
    filas = []

    for i, f in enumerate(fechas):
        # la cartera crece despacio y tiene estacionalidad de fin de año
        base = 11_800_000 * (1 + 0.004 * i) * (1.09 if f.month == 12 else 1.0)
        for tramo, (peso, tasa) in TRAMOS.items():
            for tipo, peso_tipo in TIPOS.items():
                del_mes = base * peso * peso_tipo * r.normal(1, 0.06)
                vencido = del_mes * (0.10 if tramo == "0-30" else 1.45) * r.normal(1, 0.08)
                acumulado = del_mes + vencido

                efectiva = np.clip(tasa * r.normal(1, 0.09), 0.02, 0.97)
                del_mes_cob = del_mes * np.clip(tasa * 1.05 * r.normal(1, 0.07), 0.02, 0.98)
                atrasadas_cob = vencido * efectiva * 0.55
                futuras_cob = del_mes * 0.04 * r.normal(1, 0.2)
                moratorios = (atrasadas_cob + del_mes_cob) * 0.021 * r.normal(1, 0.15)
                compensatorios = -(del_mes_cob * 0.006) * r.normal(1, 0.2)

                total = del_mes_cob + atrasadas_cob + futuras_cob + moratorios + compensatorios
                socios_acum = int(acumulado / r.normal(41_000, 3_500))

                filas.append({
                    "FechaObs": f,
                    "Año": f.year,
                    "Mes": f.month,
                    "TramoDeuda": tramo,
                    "TipoCliente": tipo,
                    "MontoACobrarDelMes": round(del_mes, 2),
                    "MontoACobrarVencido": round(vencido, 2),
                    "MontoACobrarAcumulado": round(acumulado, 2),
                    "CuotasFuturasCobradas": round(futuras_cob, 2),
                    "CuotasAtrasadasCobradas": round(atrasadas_cob, 2),
                    "CuotasDelMesCobradas": round(del_mes_cob, 2),
                    "MoratorioYMultas": round(moratorios, 2),
                    "CompensatoriosYDevoluciones": round(compensatorios, 2),
                    "TotalCobrado": round(total, 2),
                    "PorcentajeTotalCobradoSobreAcumulado": round(100 * total / acumulado, 2),
                    "PorcentajeCobradoAtrasadoSobreVencido": round(100 * atrasadas_cob / vencido, 2),
                    "PorcentajeTotalCobradoSobreMes": round(100 * total / del_mes, 2),
                    "SociosACobrarAcumulado": socios_acum,
                    "SociosACobrarVencidos": int(socios_acum * vencido / acumulado),
                    "SociosACobrarDelMes": int(socios_acum * del_mes / acumulado),
                    "SociosCobrados": int(socios_acum * efectiva * 0.6),
                    "SociosAtrasadosCobrados": int(socios_acum * efectiva * 0.26),
                    "SociosDelMesCobrados": int(socios_acum * efectiva * 0.34),
                })
    return pd.DataFrame(filas)


if __name__ == "__main__":
    df = generar()
    salida = Path(__file__).resolve().parent / "cobranzas_panel.xlsx"
    df.to_excel(salida, index=False)
    mensual = df.groupby("FechaObs")["TotalCobrado"].sum()
    print(f"{len(df)} filas → {salida}")
    print(f"cobro mensual: entre {mensual.min():,.0f} y {mensual.max():,.0f}"
          .replace(",", "."))
