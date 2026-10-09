"""Genera los ejemplos sintéticos de portafolio y de estudios de mercado.

Todo es inventado: marcas, moléculas propias, ventas y tasas. Sirven para
probar la matriz de contribución y el agente de mercado sin datos de nadie.
Las presentaciones combinan una molécula ficticia (vasotrilán) con dos
genéricos reales, para que el escalón del mix (mono, doble, triple) se lea
del nombre como en un portafolio de verdad.

    python examples/generar_portafolio.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
SEMILLA = 20261009

# país: (peso en el negocio, mezcla mono/doble/triple de la familia cardiometabólica)
PAISES = {
    "México": (0.30, (0.20, 0.55, 0.25)),
    "Centroamérica": (0.17, (0.25, 0.60, 0.15)),
    "Ecuador": (0.16, (0.35, 0.55, 0.10)),
    "Chile": (0.11, (0.15, 0.55, 0.30)),
    "Perú": (0.08, (0.40, 0.50, 0.10)),
    "Colombia": (0.08, (0.20, 0.55, 0.25)),
    "Argentina": (0.03, (0.85, 0.15, 0.00)),
    "Bolivia": (0.02, (0.45, 0.50, 0.05)),
    "Paraguay": (0.02, (0.10, 0.45, 0.45)),
    "Venezuela": (0.006, (0.50, 0.50, 0.00)),
}
CARDIO = [  # marca, presentación, escalón
    ("Vasotril", "Vasotrilán", 1),
    ("Vasotril HCT", "Vasotrilán/Hidroclorotiazida", 2),
    ("Vasotril AM", "Vasotrilán/Amlodipino", 2),
    ("Vasotril AM HCT", "Vasotrilán/Amlodipino/Hidroclorotiazida", 3),
]
OTRAS = [  # área, molécula, marca, presentación, peso relativo a cardio
    ("Respiratoria", "Brontelast", "Respira", "Brontelast", 0.25),
    ("Respiratoria", "Brontelast", "Respira Duo", "Brontelast/Formoterol", 0.12),
    ("Sistema nervioso central", "Zentiaprina", "Neurozen", "Zentiaprina", 0.30),
]


def portafolio(rng: np.random.Generator) -> pd.DataFrame:
    filas = []
    for periodo, factor in (("2025 YTD", 0.9), ("2026 YTD", 1.0)):
        for pais, (peso, mezcla) in PAISES.items():
            base = 54_000_000 * peso * factor * rng.uniform(0.92, 1.08)
            dobles = mezcla[1] * rng.uniform(0.85, 1.15)
            reparto = {1: mezcla[0], 2: dobles, 3: mezcla[2]}
            for marca, pres, nivel in CARDIO:
                parte = reparto[nivel] / (2 if nivel == 2 else 1)
                filas.append(_fila(periodo, pais, "Cardiometabólica", "Vasotrilán", marca, pres,
                                   base * parte * rng.uniform(0.8, 1.2)))
            for area, mol, marca, pres, rel in OTRAS:
                filas.append(_fila(periodo, pais, area, mol, marca, pres,
                                   base * rel * rng.uniform(0.6, 1.4)))
    return pd.DataFrame(filas)


def _fila(periodo, pais, area, molecula, marca, presentacion, ventas) -> dict:
    return {"periodo": periodo, "pais": pais, "area_terapeutica": area, "molecula": molecula,
            "marca": marca, "presentacion": presentacion, "ventas_usd": round(max(ventas, 0), 2)}


def estudios() -> pd.DataFrame:
    """Embudo de hipertensión para tres países, por sexo. Tasas inventadas."""
    # país: (adultos, diagnóstico en hombres, en mujeres, tratamiento de los diagnosticados)
    pob = {"México": (46_000_000, 0.45, 0.63, 0.66), "Ecuador": (6_200_000, 0.36, 0.52, 0.60),
           "Chile": (7_400_000, 0.78, 0.88, 0.62)}
    filas = []
    for pais, (adultos, diag_h, diag_m, trat) in pob.items():
        for seg, diag in (("Hombres", diag_h), ("Mujeres", diag_m)):
            valores = {
                "poblacion": (adultos, None, None),
                "prevalencia": (0.29, 0.25, 0.33),
                "diagnosticados": (diag, diag - 0.08, diag + 0.08),
                "tratados": (trat, trat - 0.08, trat + 0.08),
                "clase": (0.34, 0.28, 0.40),
                "participacion": (0.08, 0.06, 0.10),
                "dosis_dia": (1, None, None),
                "dias_tratamiento": (365, None, None),
                "adherencia": (0.62, 0.50, 0.72),
                "precio_unidad": (0.35, 0.30, 0.42),
                "diagnosticados_objetivo": (min(diag + 0.12, 0.85), None, None),
            }
            for param, (v, lo, hi) in valores.items():
                filas.append({"pais": pais, "segmento": seg, "parametro": param, "valor": v,
                              "minimo": lo, "maximo": hi, "origen": "estudio de mercado",
                              "fuente": "SINTÉTICO de ejemplo: reemplazar por el estudio real"})
    return pd.DataFrame(filas)


def main() -> None:
    rng = np.random.default_rng(SEMILLA)
    portafolio(rng).to_csv(AQUI / "portafolio_sintetico.csv", index=False, encoding="utf-8")
    estudios().to_csv(AQUI / "estudios_mercado_sintetico.csv", index=False, encoding="utf-8")


if __name__ == "__main__":
    main()
