"""Tablas y medidas de Power BI para el tablero «Relacionamiento».

Una tabla por archivo (Parquet o CSV), con el prefijo ``relacionamiento_``:

| tabla | una fila por |
|---|---|
| embudo | país · etapa (captados → contactables → … → convertidos) |
| contenidos | contenido, con envíos, aperturas, clics, conversiones, bajas, quejas y tasas |
| recomendaciones | contacto (id seudónimo) · rango: el siguiente mejor contenido y por qué |
| bloqueos | país · tipo de contacto · tipo de contenido · motivo |
| envios_no_elegibles | contenido · motivo: lo enviado que hoy no cumple las reglas |
| frecuencia_excedida | país: contactos por encima del tope de 30 días |
| politicas | país: ley, autoridad y reglas aplicadas (y si legal las validó) |
| cobertura | zona (y segmento): población, casos estimados, captados y brecha |
| escucha_menciones | país · semana · tema: menciones y sentimiento (agregado) |
| escucha_terminos | tema · término frecuente |
| farmacovigilancia | producto: menciones con lenguaje de posible evento adverso |

Más ``medidas_relacionamiento.dax``. La tabla de recomendaciones va entera
(la pantalla muestra una muestra): es la que el CRM levanta para enviar.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from .powerbi_portafolio import FORMATOS, RECURSOS, _escribir

KIT = ("medidas_relacionamiento.dax",)
ETAPAS = ("captados", "contactables", "con_marketing", "con_salud", "con_perfilado", "alcanzados",
          "activos", "convertidos")
TABLAS = ("contenidos", "recomendaciones", "bloqueos", "envios_no_elegibles", "frecuencia_excedida",
          "politicas")
OPCIONALES = ("cobertura", "escucha_menciones", "escucha_terminos", "farmacovigilancia")


def tablas(r: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Las tablas del resultado de `relacionamiento.analizar`, listas para el modelo."""
    emb = pd.DataFrame(r["embudo"])
    largo = emb.melt(id_vars=["pais"], value_vars=[e for e in ETAPAS if e in emb.columns],
                     var_name="etapa", value_name="personas")
    largo["orden"] = largo["etapa"].map({e: i for i, e in enumerate(ETAPAS, 1)})
    out = {"relacionamiento_embudo": largo}
    for k in TABLAS:
        out[f"relacionamiento_{k}"] = pd.DataFrame(r[k])
    for k in OPCIONALES:
        if r.get(k) is not None and len(r[k]):
            out[f"relacionamiento_{k}"] = pd.DataFrame(r[k])
    return out


def escribir(carpeta: str | Path, resultado: dict[str, Any], formato: str = "parquet",
             kit: bool = True) -> dict[str, Path]:
    """Escribe las tablas (y las medidas) en `carpeta`. Devuelve nombre → archivo."""
    if formato not in FORMATOS:
        raise ValueError(f"formato «{formato}» desconocido: usá {' o '.join(FORMATOS)}.")
    ruta = Path(carpeta).expanduser()
    ruta.mkdir(parents=True, exist_ok=True)
    salida = {n: _escribir(df, ruta, n, formato) for n, df in tablas(resultado).items()}
    if kit:
        for archivo in KIT:
            salida[archivo] = Path(shutil.copy2(RECURSOS / archivo, ruta / archivo))
    return salida
