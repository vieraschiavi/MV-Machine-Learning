"""Monitoreo de deriva: ¿los datos de hoy se parecen a los que el modelo aprendió?

Un modelo no se rompe con un error: se pone viejo en silencio. Sigue devolviendo
probabilidades con el mismo aspecto, pero los clientes, los precios o el canal
cambiaron y el número dejó de valer. Nadie lo nota hasta que la campaña rinde
la mitad de lo previsto.

Este módulo lo mide con el **PSI** (índice de estabilidad poblacional), el
estándar de la industria de riesgo crediticio:

    PSI = Σ (actual − referencia) · ln(actual / referencia)

sobre la proporción de filas en cada tramo. Los umbrales son los de siempre:
menos de 0,10 estable, hasta 0,25 moderada, arriba de 0,25 fuerte.

Tres decisiones que importan:

  * **La referencia se guarda al entrenar**, dentro del modelo: las variables se
    perfilan sobre la ventana de entrenamiento —lo que el modelo aprendió— y la
    predicción sobre el holdout, fuera de muestra. Un modelo guardado viaja con
    su referencia; no hace falta volver a tener los datos de entrenamiento.
  * **Los vacíos son un tramo más.** Una columna que pasó de 0 % a 40 % de
    vacíos cambió aunque los valores que quedan sean los de siempre, y es el
    caso más común de «se rompió la carga».
  * **El veredicto pesa la importancia.** Una variable que el modelo casi no
    usa puede moverse sin que haga falta reentrenar; una de las que sostienen
    el modelo, no. Por eso se vigila distinto una que otra.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

UMBRAL_MODERADA = 0.10
UMBRAL_FUERTE = 0.25
MIN_FILAS = 100                 # con menos, el PSI mide ruido y no población
N_TRAMOS = 10                   # deciles de la referencia
MAX_CATEGORIAS = 30             # el resto va al tramo «otras»
MAX_CONOCIDAS = 5_000           # tope de categorías recordadas para contar las nuevas
MAX_FILAS_PERFIL = 200_000      # los cuantiles no cambian por perfilar más filas
IMPORTANCIA_MINIMA = 0.05       # participación para contar como «variable que importa»
TOP_IMPORTANTES = 5
_EPS = 1e-4                     # evita log(0) en tramos vacíos, como es estándar

_ORDEN = {"falta": 5, "fuerte": 4, "moderada": 3, "estable": 2, "no_aplica": 1}


# ─────────────────────────────────────────────────────────────── perfiles ────
def _es_numerica(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def _props_numericas(x: np.ndarray, cortes: np.ndarray, n_total: int) -> list[float]:
    """Proporción por tramo, sobre TODAS las filas: el último tramo son los vacíos."""
    tramos = len(cortes) + 1
    if n_total == 0:
        return [0.0] * (tramos + 1)
    cuenta = np.bincount(np.searchsorted(cortes, x, side="right"), minlength=tramos)
    return (np.append(cuenta, n_total - len(x)) / n_total).tolist()


def _props_categoricas(valores: pd.Series, categorias: list[str], n_total: int) -> list[float]:
    """Proporción por categoría, más «otras» y «vacío», sobre todas las filas."""
    if n_total == 0:
        return [0.0] * (len(categorias) + 2)
    frec = valores.value_counts()
    conocidas = [int(frec.get(c, 0)) for c in categorias]
    otras = len(valores) - sum(conocidas)
    return (np.array([*conocidas, otras, n_total - len(valores)]) / n_total).tolist()


def perfilar_columna(s: pd.Series) -> dict[str, Any]:
    """Cómo se distribuía la columna en la referencia, en tramos comparables."""
    n = len(s)
    nulos = float(s.isna().mean()) if n else 0.0
    if _es_numerica(s):
        x = s.dropna().to_numpy(dtype=float)
        cortes = (np.unique(np.quantile(x, np.linspace(0, 1, N_TRAMOS + 1)[1:-1]))
                  if len(x) else np.array([]))
        return {"tipo": "numerica", "cortes": cortes.tolist(),
                "props": _props_numericas(x, cortes, n), "nulos": nulos, "n": n}

    valores = s.dropna().astype(str)
    distintos = int(valores.nunique())
    # Un código de factura o un documento cambia en cada fila nueva: medirle la
    # deriva daría «fuerte» siempre y taparía lo que sí importa.
    if distintos > MAX_CATEGORIAS and distintos > 0.5 * max(len(valores), 1):
        return {"tipo": "identificador", "nulos": nulos, "n": n}
    categorias = valores.value_counts().index[:MAX_CATEGORIAS].tolist()
    conocidas = valores.unique().tolist() if distintos <= MAX_CONOCIDAS else None
    return {"tipo": "categorica", "categorias": categorias, "conocidas": conocidas,
            "props": _props_categoricas(valores, categorias, n), "nulos": nulos, "n": n}


# ──────────────────────────────────────────────────────────────────── PSI ────
def psi(referencia: list[float], actual: list[float]) -> float:
    r = np.clip(np.asarray(referencia, dtype=float), _EPS, None)
    a = np.clip(np.asarray(actual, dtype=float), _EPS, None)
    return float(np.sum((a - r) * np.log(a / r)))


def nivel(valor: float) -> str:
    if valor >= UMBRAL_FUERTE:
        return "fuerte"
    return "moderada" if valor >= UMBRAL_MODERADA else "estable"


def comparar(perfil: dict[str, Any], s: pd.Series | None) -> dict[str, Any]:
    """Una columna nueva contra su perfil de referencia."""
    out: dict[str, Any] = {"tipo": perfil["tipo"], "psi": None, "nulos_ref": perfil["nulos"],
                           "nulos_nuevos": None, "categorias_nuevas": None}
    if s is None:
        return {**out, "nivel": "falta"}
    n = len(s)
    if perfil["tipo"] == "numerica":
        x = pd.to_numeric(s, errors="coerce")
        out["nulos_nuevos"] = float(x.isna().mean()) if n else 0.0
        cortes = np.asarray(perfil["cortes"], dtype=float)
        actual = _props_numericas(x.dropna().to_numpy(dtype=float), cortes, n)
    else:
        out["nulos_nuevos"] = float(s.isna().mean()) if n else 0.0
        if perfil["tipo"] == "identificador":
            return {**out, "nivel": "no_aplica"}
        valores = s.dropna().astype(str)
        actual = _props_categoricas(valores, perfil["categorias"], n)
        if perfil.get("conocidas") is not None and n:
            out["categorias_nuevas"] = float((~valores.isin(perfil["conocidas"])).sum() / n)
    out["psi"] = round(psi(perfil["props"], actual), 6)
    return {**out, "nivel": nivel(out["psi"])}


# ───────────────────────────────────────────────────────────── referencia ────
def serie_prediccion(pred: pd.DataFrame) -> pd.Series:
    """La columna que resume la salida del modelo, sea cual sea la tarea.

    Binaria: la probabilidad de la clase positiva (es lo que se usa para
    ordenar). Multiclase y regresión: la predicción.
    """
    probs = [c for c in pred.columns if str(c).startswith("prob_")]
    col = probs[0] if len(probs) == 1 else "prediccion"
    return pred[col].rename(col)


def referencia(datos: pd.DataFrame, prediccion: pd.Series | None,
               importancias: dict[str, float] | None = None) -> dict[str, Any]:
    """Lo que se guarda dentro del modelo para comparar después."""
    if len(datos) > MAX_FILAS_PERFIL:
        datos = datos.sample(n=MAX_FILAS_PERFIL, random_state=42)
    if prediccion is not None and len(prediccion) > MAX_FILAS_PERFIL:
        prediccion = prediccion.sample(n=MAX_FILAS_PERFIL, random_state=42)
    positivas = {str(k): max(float(v or 0.0), 0.0) for k, v in (importancias or {}).items()}
    total = sum(positivas.values())
    return {
        "version": 1,
        "creada": time.time(),
        "filas": int(len(datos)),
        "variables": {str(c): perfilar_columna(datos[c]) for c in datos.columns},
        "prediccion": perfilar_columna(prediccion) if prediccion is not None else None,
        "columna_prediccion": getattr(prediccion, "name", None),
        "importancias": ({k: v / total for k, v in positivas.items()} if total > 0 else {}),
    }


def _importantes(ref: dict[str, Any]) -> set[str]:
    """Las variables que sostienen el modelo. Sin importancias, todas lo son."""
    imp = ref.get("importancias") or {}
    if not imp:
        return set(ref["variables"])
    orden = sorted(imp.items(), key=lambda kv: -kv[1])
    return {k for k, v in orden[:TOP_IMPORTANTES] if v >= IMPORTANCIA_MINIMA}


# ──────────────────────────────────────────────────────────────── informe ────
def _coma(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _describir(filas: list[dict[str, Any]]) -> str:
    partes = []
    for v in filas[:3]:
        partes.append(f"«{v['variable']}» falta en los datos nuevos" if v["nivel"] == "falta"
                      else f"«{v['variable']}» (PSI {_coma(v['psi'])})")
    return ", ".join(partes)


def _veredicto(variables: list[dict[str, Any]], pred: dict[str, Any] | None,
               n: int) -> dict[str, str]:
    if n < MIN_FILAS:
        return {"nivel": "insuficiente",
                "texto": f"Con {n} filas el PSI mide ruido, no población: hacen falta al "
                         f"menos {MIN_FILAS} para opinar."}
    graves = ("fuerte", "falta")
    criticas = [v for v in variables if v["importante"] and v["nivel"] in graves]
    pred_nivel = (pred or {}).get("nivel")
    if criticas or pred_nivel == "fuerte":
        motivos = []
        if criticas:
            motivos.append(f"cambiaron variables que sostienen el modelo: {_describir(criticas)}")
        if pred_nivel == "fuerte":
            motivos.append(f"la predicción se corrió (PSI {_coma(pred['psi'])})")
        return {"nivel": "fuerte",
                "texto": "Reentrenar: " + "; ".join(motivos) + ". El modelo está midiendo "
                         "una población distinta de la que aprendió."}
    vigilar = ([v for v in variables if v["importante"] and v["nivel"] == "moderada"]
               + [v for v in variables if not v["importante"] and v["nivel"] in graves])
    if vigilar or pred_nivel == "moderada":
        detalle = _describir(vigilar) if vigilar else "la distribución de la predicción"
        return {"nivel": "moderada",
                "texto": f"Vigilar: se movió {detalle}. Todavía no hace falta reentrenar; "
                         "si en el próximo control sigue igual o peor, sí."}
    return {"nivel": "estable",
            "texto": "Los datos nuevos se parecen a los de entrenamiento: el modelo sigue "
                     "midiendo la misma población."}


def informe(ref: dict[str, Any] | None, datos: pd.DataFrame,
            prediccion: pd.Series | None) -> dict[str, Any]:
    """El control completo: cada variable, la predicción y qué hacer."""
    if not ref:
        return {"disponible": False,
                "motivo": "Este modelo se entrenó antes de que existiera el monitoreo de deriva: "
                          "reentrenalo una vez y queda activado para siempre."}
    importantes = _importantes(ref)
    imp = ref.get("importancias") or {}
    variables = []
    for col, perfil in ref["variables"].items():
        fila = comparar(perfil, datos[col] if col in datos.columns else None)
        variables.append({"variable": col, **fila, "importancia": imp.get(col),
                          "importante": col in importantes})
    variables.sort(key=lambda v: (-_ORDEN[v["nivel"]], -(v["psi"] or 0.0)))

    pred = None
    if ref.get("prediccion") is not None and prediccion is not None:
        pred = {"variable": "(predicción)", **comparar(ref["prediccion"], prediccion)}

    conteo = {k: sum(v["nivel"] == k for v in variables)
              for k in ("estable", "moderada", "fuerte", "falta", "no_aplica")}
    return {
        "disponible": True,
        "filas_referencia": ref.get("filas"),
        "filas_nuevas": int(len(datos)),
        "umbrales": {"moderada": UMBRAL_MODERADA, "fuerte": UMBRAL_FUERTE},
        "variables": variables,
        "prediccion": pred,
        "conteo": conteo,
        "veredicto": _veredicto(variables, pred, len(datos)),
    }
