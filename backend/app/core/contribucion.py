"""Matriz de contribución y mix: quién sostiene el negocio y hacia dónde evoluciona.

Es la lámina de «una plataforma regional, con motores de crecimiento
diferentes por mercado», hecha cálculo:

* **eje Y — contribución**: qué parte de las ventas explica cada entidad
  (un país, una molécula, una marca), en tres niveles: alta (>10 %), media
  (3–10 %) y baja (<3 %). Los umbrales se configuran.
* **eje X — evolución del mix**: qué tan avanzada está la entidad en la
  escalera de presentaciones (monoterapia → combinaciones dobles → triples).
  Es un índice de 0 a 1: 0 es todo en el primer escalón, 1 todo en el último.
  Sin columna de mix, el eje X pasa a ser el crecimiento contra el período
  anterior.
* **tamaño de la burbuja**: la contribución.

Encima va la lectura que en la lámina se escribe a mano —escala, dirección y
diversidad— y la banda de abajo: qué **proteger** (contribución alta), qué
**acelerar** (media) y qué **desarrollar** (baja). Para cada entidad se dice
además cuál es su **siguiente motor**: el primer escalón del mix donde está
por debajo de la región. La idea de la lámina es esa —no uniformar el mix,
sino activar el motor que sigue en cada mercado— y acá sale de los datos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

NOMBRES_NIVEL = {1: "monoterapia", 2: "combinaciones dobles", 3: "triple terapia"}
ACCIONES = {"Alta": "proteger", "Media": "acelerar", "Baja": "desarrollar"}
PREGUNTAS = {"proteger": "¿Qué debemos proteger?", "acelerar": "¿Qué debemos acelerar?",
             "desarrollar": "¿Qué debemos desarrollar?"}
_SEPARADORES = re.compile(r"\s*(?:/|\+|\bcon\b|\by\b)\s*", re.IGNORECASE)


@dataclass(frozen=True)
class Config:
    entidad: str                                 # país, molécula o marca
    valor: str                                   # ventas
    mix: str | None = None                       # presentación o combinación
    niveles_mix: dict[str, int] | None = None    # presentación -> escalón (1 = mono)
    grupo: str | None = None                     # área terapéutica
    periodo: str | None = None                   # para el crecimiento (último vs anterior)
    umbral_alta: float = 0.10
    umbral_media: float = 0.03
    top: int = 3
    etiqueta: str = "mercados"                   # cómo se nombra a las entidades en la lectura


def nivel_por_nombre(presentacion: str) -> int:
    """Escalón de una presentación por su nombre: «A/B» es doble, «A/B/C» triple."""
    s = str(presentacion).lower()
    for palabra, n in (("triple", 3), ("doble", 2), ("mono", 1)):
        if palabra in s:
            return n
    return len([p for p in _SEPARADORES.split(s) if p.strip()]) or 1


def _nivel(contribucion: float, cfg: Config) -> str:
    if contribucion > cfg.umbral_alta:
        return "Alta"
    return "Media" if contribucion >= cfg.umbral_media else "Baja"


def _preparar(df: pd.DataFrame, cfg: Config, grupo_valor: str | None) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Valida columnas, filtra el grupo y separa período actual y anterior."""
    usadas = [c for c in (cfg.entidad, cfg.valor, cfg.mix, cfg.grupo, cfg.periodo) if c]
    faltan = [c for c in usadas if c not in df.columns]
    if faltan:
        raise ValueError(f"El dataset no tiene las columnas: {', '.join(faltan)}.")
    if not cfg.mix and not cfg.periodo:
        raise ValueError("Para la matriz hace falta la columna de mix (presentación o combinación) "
                         "o la de período, para medir el crecimiento.")
    d = df[usadas].copy()
    d[cfg.valor] = pd.to_numeric(d[cfg.valor], errors="coerce").fillna(0.0)
    d[cfg.entidad] = d[cfg.entidad].astype(str).str.strip()
    if cfg.grupo and grupo_valor is not None:
        d = d[d[cfg.grupo].astype(str) == str(grupo_valor)]
    if d.empty or d[cfg.valor].sum() <= 0:
        raise ValueError("No hay ventas positivas para calcular contribuciones con ese filtro.")
    if not cfg.periodo:
        return d, None
    periodos = sorted(d[cfg.periodo].dropna().unique())
    actual = d[d[cfg.periodo] == periodos[-1]]
    anterior = d[d[cfg.periodo] == periodos[-2]] if len(periodos) > 1 else None
    return actual, anterior


def _mix(d: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, dict[str, int]]:
    """Ventas y participación por entidad y presentación, más el total regional."""
    niveles = {str(s): (cfg.niveles_mix or {}).get(str(s)) or nivel_por_nombre(s)
               for s in d[cfg.mix].dropna().unique()}
    g = d.groupby([cfg.entidad, cfg.mix], sort=False)[cfg.valor].sum().reset_index()
    g.columns = ["entidad", "segmento", "ventas"]
    reg = g.groupby("segmento", sort=False)["ventas"].sum().reset_index().assign(entidad="Total")
    largo = pd.concat([g, reg[["entidad", "segmento", "ventas"]]], ignore_index=True)
    largo["segmento"] = largo["segmento"].astype(str)
    tot = largo.groupby("entidad")["ventas"].transform("sum")
    largo["participacion"] = np.where(tot > 0, largo["ventas"] / tot, 0.0)
    largo["nivel_mix"] = largo["segmento"].map(niveles)
    return largo, niveles


def _indice(m: pd.DataFrame, kmax: int) -> float:
    if kmax <= 1:
        return 0.0
    return float((m["participacion"] * (m["nivel_mix"] - 1)).sum() / (kmax - 1))


def _etapa(indice: float, kmax: int) -> str:
    nombre = lambda k: NOMBRES_NIVEL.get(k, f"escalón {k}")  # noqa: E731
    if indice < 1 / 3:
        return f"Mayor dependencia en {nombre(1)}"
    if indice < 2 / 3 or kmax < 3:
        return f"Mix centrado en {nombre(min(2, kmax))}"
    return f"Plataforma diversificada (incluye {nombre(kmax)})"


def _siguiente_motor(m: pd.DataFrame, region: pd.DataFrame, kmax: int) -> str:
    """El primer escalón (desde el 2) donde la entidad está por debajo de la región."""
    propia = dict(zip(m["segmento"], m["participacion"], strict=False))
    for k in range(2, kmax + 1):
        del_nivel = region[region["nivel_mix"] == k]
        # «por debajo» = menos del 80 % de lo que pesa esa presentación en la región
        brechas = [(r["participacion"] - propia.get(r["segmento"], 0.0), r["segmento"])
                   for r in del_nivel.to_dict("records")
                   if propia.get(r["segmento"], 0.0) < 0.8 * r["participacion"]]
        if brechas:
            seg = max(brechas)[1]
            return f"Activar {NOMBRES_NIVEL.get(k, f'escalón {k}')} ({seg})"
    return "Consolidar el mix actual"


def calcular(df: pd.DataFrame, cfg: Config, grupo_valor: str | None = None) -> dict[str, Any]:
    """La matriz completa: burbujas, mix, KPIs, lectura estratégica y acciones."""
    actual, anterior = _preparar(df, cfg, grupo_valor)
    ventas = actual.groupby(cfg.entidad, sort=False)[cfg.valor].sum()
    total = float(ventas.sum())
    ent = pd.DataFrame({"entidad": ventas.index, "ventas": ventas.values})
    ent["contribucion"] = ent["ventas"] / total
    ent["nivel"] = [_nivel(c, cfg) for c in ent["contribucion"]]
    ent["accion"] = ent["nivel"].map(ACCIONES)
    if anterior is not None:
        prev = anterior.groupby(cfg.entidad)[cfg.valor].sum()
        base = ent["entidad"].map(prev)
        ent["crecimiento"] = np.where(base > 0, ent["ventas"] / base - 1, np.nan)
    largo, kmax = None, 1
    if cfg.mix:
        largo, niveles = _mix(actual, cfg)
        kmax = max(niveles.values())
        region = largo[largo["entidad"] == "Total"]
        por = dict(list(largo.groupby("entidad")))
        ent["indice_mix"] = [_indice(por[e], kmax) for e in ent["entidad"]]
        ent["etapa_mix"] = [_etapa(i, kmax) for i in ent["indice_mix"]]
        ent["siguiente_motor"] = [_siguiente_motor(por[e], region, kmax) for e in ent["entidad"]]
    ent = ent.sort_values("contribucion", ascending=False).reset_index(drop=True)
    eje = "mix" if cfg.mix else "crecimiento"
    out = {"entidades": _registros(ent), "eje_x": eje, "zonas_x": _zonas(eje, kmax),
           "total": total, "kpis": _kpis(ent, largo, cfg, total),
           "acciones": {a: ent.loc[ent["accion"] == a, "entidad"].tolist() for a in PREGUNTAS},
           "preguntas": PREGUNTAS, "umbrales": {"alta": cfg.umbral_alta, "media": cfg.umbral_media},
           "grupo": grupo_valor}
    out["lectura"] = _lectura(ent, out["kpis"], cfg)
    if largo is not None:
        out["mix"] = _registros(largo)
        out["indice_mix_region"] = _indice(largo[largo["entidad"] == "Total"], kmax)
        if kmax == 1:
            out["aviso"] = ("No se pudo distinguir el escalón de las presentaciones por el nombre: "
                            "pasá `niveles_mix` (presentación → 1, 2, 3) para que el eje X tenga sentido.")
    if cfg.grupo and grupo_valor is None:
        out["grupos"] = _grupos(df, cfg)
    return out


def _registros(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in r.items()}
            for r in df.to_dict("records")]


def _zonas(eje: str, kmax: int) -> list[str]:
    if eje == "mix":
        return [_etapa(0.0, kmax), _etapa(0.5, kmax), _etapa(1.0, kmax)]
    return ["Cae", "Estable", "Crece"]


def _kpis(ent: pd.DataFrame, largo: pd.DataFrame | None, cfg: Config, total: float) -> list[dict[str, Any]]:
    top = ent.head(cfg.top)
    kpis = [{"kpi": "ventas_total", "valor": total, "texto": "Ventas del período"},
            {"kpi": "concentracion_top", "valor": float(top["contribucion"].sum()),
             "texto": f"Lo explican {len(top)} {cfg.etiqueta}: {', '.join(top['entidad'])}"},
            {"kpi": "entidades", "valor": float(len(ent)), "texto": f"{cfg.etiqueta} con ventas"}]
    if largo is not None:
        reg = largo[largo["entidad"] == "Total"]
        comb = float(reg.loc[reg["nivel_mix"] > 1, "participacion"].sum())
        segs = reg.loc[reg["nivel_mix"] > 1, "segmento"].tolist()
        kpis.append({"kpi": "combinaciones", "valor": comb,
                     "texto": "Combinaciones del negocio total" + (f": {' + '.join(segs)}" if segs else "")})
    return kpis


def _lectura(ent: pd.DataFrame, kpis: list[dict[str, Any]], cfg: Config) -> list[dict[str, str]]:
    k = {x["kpi"]: x for x in kpis}
    top = ent.head(cfg.top)
    out = [{"bloque": "ESCALA", "titulo": f"{len(top)} {cfg.etiqueta} explican "
            f"~{k['concentracion_top']['valor']:.0%} del negocio",
            "texto": f"{', '.join(top['entidad'])} son los principales motores de escala."}]
    if "combinaciones" in k:
        c = k["combinaciones"]["valor"]
        out.append({"bloque": "DIRECCIÓN",
                    "titulo": ("Las combinaciones ya son el centro de gravedad" if c >= 0.5 else
                               f"La {NOMBRES_NIVEL[1]} sigue siendo la base"),
                    "texto": f"Las combinaciones representan ~{c:.0%} del negocio."})
        i = ent["indice_mix"]
        lo, hi = ent.loc[i.idxmin()], ent.loc[i.idxmax()]
        out.append({"bloque": "DIVERSIDAD", "titulo": "El mix muestra distintos niveles de desarrollo",
                    "texto": f"El índice de mix va de {_coma(lo['indice_mix'])} ({lo['entidad']}) a "
                             f"{_coma(hi['indice_mix'])} ({hi['entidad']}): cada {cfg.etiqueta[:-1]} "
                             "necesita activar un motor distinto."})
    elif "crecimiento" in ent:
        crecen = ent[ent["crecimiento"] > 0]
        out.append({"bloque": "DIRECCIÓN", "titulo": f"{len(crecen)} de {len(ent)} crecen",
                    "texto": "Los que más crecen: " + ", ".join(
                        crecen.sort_values("crecimiento", ascending=False)["entidad"].head(3))})
    return out


def _coma(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _grupos(df: pd.DataFrame, cfg: Config) -> list[dict[str, Any]]:
    """Contribución de cada grupo (área terapéutica) y sus principales entidades."""
    d, _ = _preparar(df, cfg, None)
    total = float(d[cfg.valor].sum())
    out = []
    for g, sub in d.groupby(cfg.grupo, sort=False):
        v = sub.groupby(cfg.entidad)[cfg.valor].sum().sort_values(ascending=False)
        out.append({"grupo": str(g), "ventas": float(v.sum()), "contribucion": float(v.sum()) / total,
                    "principales": ", ".join(f"{e} {x / v.sum():.0%}" for e, x in v.head(cfg.top).items())})
    return sorted(out, key=lambda r: -r["ventas"])


TODAS = "Todas"


def calcular_por_grupo(df: pd.DataFrame, cfg: Config) -> dict[str, dict[str, Any]]:
    """La matriz para el total y para cada grupo (área terapéutica) por separado.

    En Power BI el segmentador de área elige una de estas matrices: las
    contribuciones se calculan dentro del área, no se recalculan filtrando
    el total (que daría porcentajes que no suman uno).
    """
    out = {TODAS: calcular(df, cfg)}
    if cfg.grupo:
        for g in df[cfg.grupo].dropna().astype(str).unique():
            try:
                out[g] = calcular(df, cfg, grupo_valor=g)
            except ValueError:
                continue                     # un área sin ventas positivas no tiene matriz
    return out
