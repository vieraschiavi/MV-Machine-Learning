"""La base propia contra la población: dónde está el mercado que todavía no alcanzamos.

Cruza la base de relacionamiento con datos **públicos y agregados**: el censo
(población por país, ciudad, barrio, sexo, rango de edad y nivel
socioeconómico) y las encuestas de salud (prevalencia por sexo y edad). El
cruce es por el territorio que la persona **declaró**, nunca por la persona:
a un contacto de Pocitos se le asigna el nivel socioeconómico *de Pocitos*
(``nse_zona``), no uno inferido para él.

Lo que publica está agregado y con **supresión de celdas chicas**: una zona con
menos de ``K_MINIMO`` contactos muestra «menos de K» y no el número, para que
nadie se pueda reidentificar cruzando tablas.

Tablas de entrada:

* **poblacion** — ``pais``, ``ciudad``, opcional ``barrio``, ``sexo``,
  ``rango_edad``, opcional ``nse``, y ``poblacion``. Fuentes: INE, INDEC,
  INEGI (AGEB), IBGE (setor censitário), DANE (estrato), INE Chile.
* **prevalencias** — ``pais``, ``area_terapeutica``, ``sexo``, ``rango_edad``,
  ``prevalencia`` (0 a 1), opcional ``fuente``. Fuentes: ENSANUT, ENFR, PNS,
  ENS, STEPS-OMS, GBD. Se puede usar «Total» en sexo o rango de edad.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .consentimiento import _clave

K_MINIMO = 10
TOTAL = "total"


def _normalizar(df: pd.DataFrame, nombre: str, obligatorias: tuple[str, ...]) -> pd.DataFrame:
    d = df.copy()
    d.columns = [_clave(c).replace(" ", "_") for c in d.columns]
    faltan = [c for c in obligatorias if c not in d.columns]
    if faltan:
        raise ValueError(f"A la tabla de {nombre} le faltan columnas: {', '.join(faltan)}.")
    for c in ("pais", "ciudad", "barrio", "sexo", "rango_edad", "nse", "area_terapeutica"):
        if c in d.columns:
            d[c] = d[c].fillna("").astype(str)
            d[f"{c}_k"] = d[c].map(_clave)
    return d


def preparar_poblacion(df: pd.DataFrame) -> pd.DataFrame:
    d = _normalizar(df, "población", ("pais", "ciudad", "poblacion"))
    d["poblacion"] = pd.to_numeric(d["poblacion"], errors="coerce").fillna(0).clip(lower=0)
    for c in ("barrio", "sexo", "rango_edad", "nse"):
        if c not in d.columns:
            d[c], d[f"{c}_k"] = "", ""
    return d


def preparar_prevalencias(df: pd.DataFrame) -> pd.DataFrame:
    d = _normalizar(df, "prevalencias", ("pais", "area_terapeutica", "prevalencia"))
    d["prevalencia"] = pd.to_numeric(d["prevalencia"], errors="coerce")
    malas = ~d["prevalencia"].between(0, 1)
    if malas.any():
        raise ValueError(f"{int(malas.sum())} prevalencia(s) fuera de 0–1: van como proporción (8 % = 0,08).")
    for c in ("sexo", "rango_edad"):
        if c not in d.columns:
            d[c], d[f"{c}_k"] = "Total", TOTAL
        d[f"{c}_k"] = d[f"{c}_k"].replace("", TOTAL)
    return d


def _zona(d: pd.DataFrame, por_barrio: bool) -> list[str]:
    return ["pais_k", "ciudad_k", "barrio_k"] if por_barrio else ["pais_k", "ciudad_k"]


def nse_por_zona(poblacion: pd.DataFrame) -> pd.DataFrame:
    """El nivel socioeconómico predominante de cada zona (barrio si lo hay, si no ciudad)."""
    p = poblacion[poblacion["nse_k"] != ""]
    if p.empty:
        return pd.DataFrame(columns=["pais_k", "ciudad_k", "barrio_k", "nse_zona"])
    g = p.groupby(["pais_k", "ciudad_k", "barrio_k", "nse"])["poblacion"].sum().reset_index()
    g = g.sort_values("poblacion", ascending=False).drop_duplicates(["pais_k", "ciudad_k", "barrio_k"])
    return g.rename(columns={"nse": "nse_zona"})[["pais_k", "ciudad_k", "barrio_k", "nse_zona"]]


def enriquecer(contactos: pd.DataFrame, poblacion: pd.DataFrame) -> pd.DataFrame:
    """Agrega a cada contacto el `nse_zona` de su barrio (o de su ciudad) declarado."""
    d = contactos.copy()
    vacio = pd.Series("", index=d.index)
    pais, ciudad, barrio = (d[c].map(_clave) if c in d.columns else vacio for c in ("pais", "ciudad", "barrio"))
    z = nse_por_zona(poblacion)
    por_barrio = {(r.pais_k, r.ciudad_k, r.barrio_k): r.nse_zona for r in z[z["barrio_k"] != ""].itertuples()}
    p = poblacion[poblacion["nse_k"] != ""]
    g = p.groupby(["pais_k", "ciudad_k", "nse"])["poblacion"].sum().reset_index()
    g = g.sort_values("poblacion", ascending=False).drop_duplicates(["pais_k", "ciudad_k"])
    por_ciudad = {(r.pais_k, r.ciudad_k): r.nse for r in g.itertuples()}
    nse = [por_barrio.get((p_, c, b)) or por_ciudad.get((p_, c))
           for p_, c, b in zip(pais, ciudad, barrio, strict=True)]
    nuevo = pd.Series(nse, index=d.index, dtype=object)
    # Si la zona no está en el censo, queda lo que ya traía la base.
    d["nse_zona"] = nuevo.fillna(d["nse_zona"]) if "nse_zona" in d.columns else nuevo
    return d


def _casos(poblacion: pd.DataFrame, prevalencias: pd.DataFrame, area: str) -> pd.DataFrame:
    """Casos estimados por zona: población × prevalencia por sexo y edad (o la total del país)."""
    pv = prevalencias[prevalencias["area_terapeutica_k"] == _clave(area)]
    if pv.empty:
        raise ValueError(f"No hay prevalencias para el área «{area}».")
    p = poblacion.copy()
    exacta = pv[(pv["sexo_k"] != TOTAL) & (pv["rango_edad_k"] != TOTAL)]
    total = pv[(pv["sexo_k"] == TOTAL) & (pv["rango_edad_k"] == TOTAL)][["pais_k", "prevalencia"]]
    p = p.merge(exacta[["pais_k", "sexo_k", "rango_edad_k", "prevalencia"]], how="left",
                on=["pais_k", "sexo_k", "rango_edad_k"])
    p = p.merge(total.rename(columns={"prevalencia": "prev_total"}), how="left", on="pais_k")
    p["prevalencia"] = p["prevalencia"].fillna(p["prev_total"])
    p["casos"] = p["poblacion"] * p["prevalencia"]
    return p


SEGMENTOS = {"sexo": "sexo", "rango_edad": "rango_edad", "nse": "nse_zona"}  # censo → contacto


def cobertura(contactos: pd.DataFrame, poblacion: pd.DataFrame, prevalencias: pd.DataFrame,
              area: str, *, por_barrio: bool = False, segmentar: tuple[str, ...] = (),
              k_minimo: int = K_MINIMO) -> pd.DataFrame:
    """Por zona (y por sexo, edad o NSE si se pide): casos estimados, captados del área y la brecha.

    Sólo cuentan como captadas del área las personas que la declararon y
    consintieron el uso de datos de salud (lo mismo que exige el motor).
    """
    raros = sorted(set(segmentar) - set(SEGMENTOS))
    if raros:
        raise ValueError(f"No se puede segmentar por {', '.join(raros)}: usá {', '.join(SEGMENTOS)}.")
    p = _casos(poblacion, prevalencias, area)
    nombres = {"pais_k": "pais", "ciudad_k": "ciudad", "barrio_k": "barrio",
               **{f"{s}_k": s for s in segmentar}}
    grupo = _zona(p, por_barrio) + [f"{s}_k" for s in segmentar]
    casos = p.groupby(grupo).agg(poblacion=("poblacion", "sum"), casos_estimados=("casos", "sum"),
                                 **{v: (v, "first") for k, v in nombres.items() if k in grupo}).reset_index()
    c = contactos.copy()
    for col in ("pais", "ciudad", "barrio"):
        c[f"{col}_k"] = c[col].map(_clave) if col in c.columns else ""
    for seg in segmentar:
        origen = SEGMENTOS[seg]
        c[f"{seg}_k"] = c[origen].map(_clave) if origen in c.columns else ""
    area_k = _clave(area)
    c["del_area"] = c["areas_interes"].map(lambda s: area_k in s) & c["consiente_salud"].astype(bool)
    base = c.groupby(grupo).agg(en_base=("id_contacto", "size"), captados_area=("del_area", "sum")).reset_index()
    t = casos.merge(base, how="left", on=grupo).fillna({"en_base": 0, "captados_area": 0})
    t["penetracion"] = t["captados_area"] / t["casos_estimados"].where(t["casos_estimados"] > 0)
    t["brecha"] = (t["casos_estimados"] - t["captados_area"]).clip(lower=0).round()
    t["casos_estimados"] = t["casos_estimados"].round()
    # Celdas chicas: no se publica el número (se podría reidentificar a alguien cruzando tablas).
    chica = t["en_base"] < k_minimo
    for col in ("en_base", "captados_area"):
        t[col] = t[col].astype(int).astype(object).where(~chica, f"<{k_minimo}")
    t.loc[chica, "penetracion"] = np.nan
    # La brecha tampoco puede delatar a los captados (casos − brecha): en una celda chica es el techo.
    t.loc[chica, "brecha"] = t.loc[chica, "casos_estimados"]
    t["celda_suprimida"] = chica
    t["area_terapeutica"] = area
    t = t.sort_values("brecha", ascending=False).drop(columns=grupo)
    cols = ["area_terapeutica", *[nombres[k] for k in grupo], "poblacion", "casos_estimados", "en_base",
            "captados_area", "penetracion", "brecha", "celda_suprimida"]
    return t[cols].reset_index(drop=True)


def resumen(cob: pd.DataFrame, top: int = 5) -> dict[str, Any]:
    """Las zonas con más casos sin alcanzar: candidatas a concientización sin marca."""
    if cob.empty:
        return {"zonas": [], "texto": "Sin zonas para comparar."}
    z = cob.head(top)
    partes = [c for c in ("sexo", "rango_edad", "nse", "barrio", "ciudad", "pais") if c in z]
    nombres = [", ".join(str(r[c]) for c in partes if r.get(c)) for r in z.to_dict("records")]
    return {"zonas": nombres,
            "texto": ("Donde más casos estimados quedan fuera de la base: " + "; ".join(nombres)
                      + ". Ahí conviene concientización sin marca y captación con consentimiento.")}


__all__ = ["K_MINIMO", "SEGMENTOS", "cobertura", "enriquecer", "nse_por_zona", "preparar_poblacion",
           "preparar_prevalencias", "resumen"]
