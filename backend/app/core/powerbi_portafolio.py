"""Tablas y kit de Power BI para el tablero «Portafolio y mercado».

Deja en una carpeta (la del Lakehouse en Fabric, o una común) las tablas que
el informe lee directo, más el kit para armar la página con el formato de la
lámina de contribución:

* ``tema_portafolio.json`` — el tema (Vista → Temas → Buscar temas).
* ``medidas_portafolio.dax`` — las medidas de tarjetas, lectura y banda de acciones.
* ``burbujas_contribucion.vl.json`` — la matriz de burbujas para el visual
  Deneb, con las zonas de mix de fondo y las líneas de 3 % y 10 %.

Tablas (Parquet o CSV), una por archivo:

| tabla | una fila por |
|---|---|
| portafolio_entidades | área · entidad (país, molécula o marca) |
| portafolio_mix | área · entidad · presentación |
| portafolio_kpis | área · indicador |
| portafolio_lectura | área · bloque (escala, dirección, diversidad) |
| portafolio_grupos | área terapéutica |
| mercado_embudo | país · segmento · etapa del embudo |
| mercado_potencial | país · medida, con P10/P50/P90 |
| mercado_lecturas | país: proteger, acelerar o desarrollar |
| mercado_sensibilidad | supuesto (tornado) |
| mercado_lanzamiento | país · mes |
| mercado_supuestos | país · segmento · parámetro, con origen y fuente |
| mercado_contraste | país: embudo contra lo vendido |
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

RECURSOS = Path(__file__).resolve().parents[1] / "recursos" / "powerbi"
KIT = ("tema_portafolio.json", "medidas_portafolio.dax", "burbujas_contribucion.vl.json")
FORMATOS = ("parquet", "csv")
ETAPAS = ("prevalentes", "diagnosticados", "tratados", "en_clase", "pacientes_marca")


def tablas_contribucion(por_grupo: dict[str, dict[str, Any]]) -> dict[str, pd.DataFrame]:
    """Aplana la matriz de cada área en tablas con la columna `grupo`."""
    t: dict[str, list[pd.DataFrame]] = {k: [] for k in ("entidades", "mix", "kpis", "lectura")}
    grupos = None
    for g, r in por_grupo.items():
        t["entidades"].append(pd.DataFrame(r["entidades"]).assign(grupo=g, eje_x=r["eje_x"]))
        if r.get("mix"):
            t["mix"].append(pd.DataFrame(r["mix"]).assign(grupo=g))
        t["kpis"].append(pd.DataFrame(r["kpis"]).assign(grupo=g))
        lectura = pd.DataFrame(r["lectura"]).assign(grupo=g)
        lectura.insert(0, "orden", range(1, len(lectura) + 1))
        t["lectura"].append(lectura)
        if r.get("grupos"):
            grupos = pd.DataFrame(r["grupos"])
    out = {f"portafolio_{k}": pd.concat(v, ignore_index=True) for k, v in t.items() if v}
    if grupos is not None:
        out["portafolio_grupos"] = grupos
    return out


def tablas_mercado(analisis: dict[str, Any]) -> dict[str, pd.DataFrame]:
    """Las tablas del análisis de mercado del agente."""
    emb = pd.DataFrame(analisis["embudo"])
    etapas = [e for e in ETAPAS if e in emb.columns]
    largo = emb.melt(id_vars=["pais", "segmento"], value_vars=etapas,
                     var_name="etapa", value_name="pacientes")
    largo["orden"] = largo["etapa"].map({e: i for i, e in enumerate(etapas, 1)})
    out = {"mercado_embudo": largo,
           "mercado_potencial": pd.DataFrame(analisis["rango"]),
           "mercado_lecturas": pd.DataFrame(analisis["lecturas"]),
           "mercado_sensibilidad": pd.DataFrame(analisis["sensibilidad"]),
           "mercado_supuestos": pd.DataFrame(analisis["supuestos"])}
    for clave in ("lanzamiento", "contraste"):
        if analisis.get(clave):
            out[f"mercado_{clave}"] = pd.DataFrame(analisis[clave])
    return out


def _escribir(df: pd.DataFrame, carpeta: Path, nombre: str, formato: str) -> Path:
    destino = carpeta / f"{nombre}.{formato}"
    # Columnas de texto con algún nulo: Parquet las quiere de un solo tipo.
    limpio = df.copy()
    for c in limpio.columns:
        if limpio[c].dtype == object:
            limpio[c] = limpio[c].map(lambda v: v if v is None or isinstance(v, str) else str(v))
    if formato == "parquet":
        limpio.to_parquet(destino, index=False)
    else:
        limpio.to_csv(destino, index=False, encoding="utf-8")
    return destino


def escribir(carpeta: str | Path, contribucion: dict[str, dict[str, Any]] | None = None,
             mercado: dict[str, Any] | None = None, formato: str = "parquet",
             kit: bool = True) -> dict[str, Path]:
    """Escribe las tablas (y el kit) en `carpeta`. Devuelve nombre → archivo."""
    if formato not in FORMATOS:
        raise ValueError(f"formato «{formato}» desconocido: usá {' o '.join(FORMATOS)}.")
    if contribucion is None and mercado is None:
        raise ValueError("No hay nada para escribir: pasá la matriz de contribución, el análisis "
                         "de mercado o los dos.")
    ruta = Path(carpeta).expanduser()
    ruta.mkdir(parents=True, exist_ok=True)
    tablas: dict[str, pd.DataFrame] = {}
    if contribucion is not None:
        tablas.update(tablas_contribucion(contribucion))
    if mercado is not None:
        tablas.update(tablas_mercado(mercado))
    salida = {n: _escribir(df, ruta, n, formato) for n, df in tablas.items()}
    if kit:
        for archivo in KIT:
            salida[archivo] = Path(shutil.copy2(RECURSOS / archivo, ruta / archivo))
    return salida


def empaquetar(carpeta: Path, destino_zip: Path) -> Path:
    """Un zip con todo lo de `carpeta`, para bajar desde la pantalla."""
    with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(carpeta.iterdir()):
            if p.is_file():
                z.write(p, p.name)
    return destino_zip
