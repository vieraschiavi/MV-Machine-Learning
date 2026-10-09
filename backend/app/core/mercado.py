"""Mercado actual y mercado latente: el embudo epidemiológico de un producto.

Una proyección que sólo mira la historia de ventas no ve a la gente que
todavía no está en la historia: el que tiene síntomas y no consulta, el que
tiene el diagnóstico y no se trata. Ese es el mercado *latente*, y para un
lanzamiento —donde no hay historia— es casi todo el mercado.

El embudo, por país y segmento (sexo, edad, lo que se cargue):

    población → prevalentes → diagnosticados → tratados → en la clase → en la marca
                    │               │
                    │               └─ diagnosticados sin tratamiento (latente)
                    └─ sin diagnóstico: síntomas sin consulta (latente)

Cada tasa del embudo se carga como un **supuesto** con valor, mínimo, máximo,
origen y fuente (`plantilla()` arma la tabla vacía). El motor no inventa
números: lo que falta y es obligatorio se reclama; lo que falta y tiene un
valor razonable por defecto (dosis 1/día, 365 días, adherencia 100 %) se usa
y **se avisa** en `por_defecto`, porque inflar el mercado callado es la forma
más fácil de vender una proyección que no se cumple.

La incertidumbre sale de simular los supuestos (triangular entre mínimo,
valor y máximo, independientes entre sí) y se reporta como P10–P90. Ese rango
mide cuánto se mueve el resultado con lo que se cargó; **no** es el error de
un modelo medido contra la realidad. Cuando hay historia, `contrastar()` pone
el embudo contra las ventas observadas para ver si los supuestos cierran.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

TASA, CANTIDAD = "tasa", "cantidad"


@dataclass(frozen=True)
class Parametro:
    tipo: str
    requerido: bool
    defecto: float | None
    descripcion: str


PARAMETROS: dict[str, Parametro] = {
    "poblacion": Parametro(CANTIDAD, True, None, "personas del segmento (adultos, por ejemplo)"),
    "prevalencia": Parametro(TASA, True, None, "fracción de la población con la enfermedad"),
    "diagnosticados": Parametro(TASA, True, None, "fracción de los prevalentes con diagnóstico"),
    "tratados": Parametro(TASA, True, None, "fracción de los diagnosticados con tratamiento"),
    "clase": Parametro(TASA, False, 1.0, "fracción de los tratados que usa la clase o molécula"),
    "participacion": Parametro(TASA, False, None, "participación de la marca dentro de la clase"),
    "dosis_dia": Parametro(CANTIDAD, False, 1.0, "unidades por día de tratamiento"),
    "dias_tratamiento": Parametro(CANTIDAD, False, 365.0, "días de tratamiento por año"),
    "adherencia": Parametro(TASA, False, 1.0, "fracción de los días que el paciente efectivamente toma"),
    "precio_unidad": Parametro(CANTIDAD, False, None, "precio por unidad (moneda del informe)"),
    "diagnosticados_objetivo": Parametro(TASA, False, None, "diagnóstico alcanzable con campañas"),
    "tratados_objetivo": Parametro(TASA, False, None, "tratamiento alcanzable con activación médica"),
}
# Los que se asumen si faltan: se usan, pero se listan en `por_defecto`.
AVISAR_SI_FALTA = ("dosis_dia", "dias_tratamiento", "adherencia")
COLUMNAS = ["pais", "segmento", "parametro", "valor", "minimo", "maximo", "origen", "fuente"]
FORMAS = {"rapida": (0.03, 0.55), "media": (0.012, 0.35), "lenta": (0.005, 0.2)}
DIAS_MES = 365.0 / 12


class SupuestosInvalidos(ValueError):
    """La tabla de supuestos no alcanza para armar el embudo."""


# ── tabla de supuestos ──────────────────────────────────────────────────────
def plantilla(paises: list[str], segmentos: list[str] | None = None,
              parametros: list[str] | None = None) -> pd.DataFrame:
    """Tabla vacía para completar a mano o con un estudio de mercado."""
    segs = segmentos or ["Total"]
    params = parametros or list(PARAMETROS)
    filas = [{"pais": p, "segmento": s, "parametro": k, "valor": None, "minimo": None,
              "maximo": None, "origen": "", "fuente": ""}
             for p in paises for s in segs for k in params]
    return pd.DataFrame(filas, columns=COLUMNAS)


def _numero(x: Any) -> float | None:
    try:
        v = float(str(x).replace(",", ".")) if isinstance(x, str) else float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else v


def _normalizar_fila(f: dict[str, Any], problemas: list[str]) -> dict[str, Any] | None:
    nombre = str(f.get("parametro") or "").strip().lower()
    if nombre not in PARAMETROS:
        problemas.append(f"Parámetro desconocido «{f.get('parametro')}» ({f.get('pais')}): se ignora.")
        return None
    valor = _numero(f.get("valor"))
    if valor is None:
        return None
    lo, hi = _numero(f.get("minimo")), _numero(f.get("maximo"))
    lo = valor if lo is None else lo
    hi = valor if hi is None else hi
    lo, hi = min(lo, valor, hi), max(lo, valor, hi)
    donde = f"{f['pais']} / {f['segmento']} / {nombre}"
    if PARAMETROS[nombre].tipo == TASA:
        if max(abs(lo), abs(hi)) > 1 and max(abs(lo), abs(hi)) <= 100:
            problemas.append(f"{donde}: vino en porcentaje; se pasó a fracción.")
            valor, lo, hi = valor / 100, lo / 100, hi / 100
        if lo < 0 or hi > 1:
            problemas.append(f"{donde}: una tasa tiene que estar entre 0 y 1; se recortó.")
            valor, lo, hi = (float(np.clip(v, 0, 1)) for v in (valor, lo, hi))
    elif lo < 0:
        problemas.append(f"{donde}: una cantidad no puede ser negativa; se puso en 0.")
        valor, lo, hi = max(valor, 0.0), max(lo, 0.0), max(hi, 0.0)
    return {"pais": str(f["pais"]).strip(), "segmento": str(f["segmento"]).strip(),
            "parametro": nombre, "valor": valor, "minimo": lo, "maximo": hi,
            "origen": str(f.get("origen") or "").strip(), "fuente": str(f.get("fuente") or "").strip()}


def normalizar(supuestos: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Valida y limpia la tabla larga de supuestos. Devuelve `(tabla, avisos)`."""
    df = supuestos.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    faltan = [c for c in ("pais", "parametro", "valor") if c not in df.columns]
    if faltan:
        raise SupuestosInvalidos(f"A la tabla de supuestos le faltan columnas: {', '.join(faltan)}.")
    if "segmento" not in df.columns:
        df["segmento"] = "Total"
    df["segmento"] = df["segmento"].fillna("Total").replace("", "Total")
    df = df.dropna(subset=["pais"])
    problemas: list[str] = []
    filas = [r for f in df.to_dict("records") if (r := _normalizar_fila(f, problemas))]
    if not filas:
        raise SupuestosInvalidos("La tabla de supuestos no tiene ningún valor cargado.")
    out = pd.DataFrame(filas, columns=COLUMNAS)
    dup = out.duplicated(["pais", "segmento", "parametro"], keep="last")
    if dup.any():
        problemas.append(f"{int(dup.sum())} supuesto(s) repetido(s): vale el último cargado.")
    return out[~dup].reset_index(drop=True), problemas


def _por_fila(tabla: pd.DataFrame) -> list[dict[str, Any]]:
    """Una entrada por país y segmento, con sus parámetros y lo que falta."""
    filas = []
    for (pais, seg), g in tabla.groupby(["pais", "segmento"], sort=False):
        params = {r["parametro"]: (r["valor"], r["minimo"], r["maximo"]) for r in g.to_dict("records")}
        faltan = [k for k, p in PARAMETROS.items() if p.requerido and k not in params]
        if faltan:
            raise SupuestosInvalidos(
                f"{pais} / {seg}: faltan supuestos obligatorios: {', '.join(faltan)}. "
                "Cargalos de un estudio de mercado o pedile una propuesta al agente.")
        defecto = [k for k in AVISAR_SI_FALTA if k not in params]
        for k in defecto:
            v = PARAMETROS[k].defecto
            params[k] = (v, v, v)
        if "clase" not in params:
            params["clase"] = (1.0, 1.0, 1.0)
        filas.append({"pais": pais, "segmento": seg, "params": params, "por_defecto": defecto})
    return filas


# ── el embudo ───────────────────────────────────────────────────────────────
def _calcular(p: dict[str, Any]) -> dict[str, Any]:
    """Todas las salidas del embudo. Acepta escalares o vectores de simulación."""
    prev = p["poblacion"] * p["prevalencia"]
    diag = prev * p["diagnosticados"]
    trat = diag * p["tratados"]
    clase = trat * p["clase"]
    por_paciente = p["dosis_dia"] * p["dias_tratamiento"] * p["adherencia"]
    out = {"prevalentes": prev, "sin_diagnostico": prev - diag, "diagnosticados": diag,
           "sin_tratamiento": diag - trat, "tratados": trat, "en_clase": clase,
           "latente": prev - trat, "unidades_clase": clase * por_paciente}
    precio = p.get("precio_unidad")
    if precio is not None:
        out["valor_clase"] = out["unidades_clase"] * precio
        out["valor_latente"] = out["latente"] * p["clase"] * por_paciente * precio
    if p.get("participacion") is not None:
        out["pacientes_marca"] = clase * p["participacion"]
        out["unidades_marca"] = out["unidades_clase"] * p["participacion"]
        if precio is not None:
            out["valor_marca"] = out["valor_clase"] * p["participacion"]
    if p.get("diagnosticados_objetivo") is not None or p.get("tratados_objetivo") is not None:
        d_obj = p.get("diagnosticados_objetivo", p["diagnosticados"])
        t_obj = p.get("tratados_objetivo", p["tratados"])
        out["en_clase_alcanzable"] = prev * np.maximum(d_obj, p["diagnosticados"]) \
            * np.maximum(t_obj, p["tratados"]) * p["clase"]
        out["incremento_alcanzable"] = out["en_clase_alcanzable"] - clase
    return out


def embudo(supuestos: pd.DataFrame) -> pd.DataFrame:
    """El embudo con los valores centrales: una fila por país y segmento."""
    tabla, _ = normalizar(supuestos)
    filas = []
    for f in _por_fila(tabla):
        base = {k: v[0] for k, v in f["params"].items()}
        r = _calcular(base)
        filas.append({"pais": f["pais"], "segmento": f["segmento"],
                      **{k: float(v) for k, v in r.items()},
                      "por_defecto": ", ".join(f["por_defecto"])})
    return pd.DataFrame(filas)


def _simular(params: dict[str, tuple], n: int, rng: np.random.Generator) -> dict[str, Any]:
    p = {}
    for k, (v, lo, hi) in params.items():
        p[k] = rng.triangular(lo, v, hi, n) if hi > lo else np.full(n, v)
    return _calcular(p)


def _cuantiles(x: np.ndarray) -> dict[str, float]:
    q = np.percentile(x, [10, 50, 90])
    return {"p10": float(q[0]), "p50": float(q[1]), "p90": float(q[2])}


def potencial(supuestos: pd.DataFrame, n_sim: int = 2000, semilla: int = 42) -> dict[str, Any]:
    """Mercado actual, latente y alcanzable por país, con rango P10–P90."""
    tabla, avisos = normalizar(supuestos)
    filas = _por_fila(tabla)
    rng = np.random.default_rng(semilla)
    por_pais: dict[str, dict[str, np.ndarray]] = {}
    for f in filas:
        sim = _simular(f["params"], n_sim, rng)
        acc = por_pais.setdefault(f["pais"], {})
        for k, v in sim.items():
            acc[k] = acc.get(k, 0) + v
    total: dict[str, np.ndarray] = {}
    for acc in por_pais.values():
        for k, v in acc.items():
            total[k] = total.get(k, 0) + v
    rango = [{"pais": pais, "medida": k, **_cuantiles(v)}
             for pais, acc in [*por_pais.items(), ("Total", total)] for k, v in acc.items()]
    defecto = sorted({k for f in filas for k in f["por_defecto"]})
    if defecto:
        avisos.append("Se asumió por falta de dato: " + ", ".join(
            f"{k} = {PARAMETROS[k].defecto:g}" for k in defecto)
            + ". Cargá el valor real: cambia el mercado en la misma proporción.")
    return {"embudo": embudo(tabla).to_dict("records"), "rango": rango,
            "supuestos": tabla.to_dict("records"), "avisos": avisos,
            "por_defecto": defecto, "simulaciones": n_sim,
            "nota": ("El rango P10–P90 mide cuánto se mueve el resultado con la incertidumbre "
                     "de los supuestos cargados, tomados como independientes. No es el error "
                     "de un modelo medido contra ventas reales.")}


def sensibilidad(supuestos: pd.DataFrame, medida: str = "en_clase") -> pd.DataFrame:
    """Tornado: cuánto se mueve `medida` llevando cada supuesto a su mínimo y a su máximo."""
    tabla, _ = normalizar(supuestos)
    filas = _por_fila(tabla)

    def total(sobre: str | None = None, extremo: int = 0) -> float:
        acc = 0.0
        for f in filas:
            p = {k: (v[extremo] if k == sobre else v[0]) for k, v in f["params"].items()}
            r = _calcular(p)
            if medida not in r:
                raise SupuestosInvalidos(f"La medida «{medida}» necesita supuestos que no están cargados.")
            acc += float(r[medida])
        return acc

    base = total()
    nombres = sorted({k for f in filas for k, v in f["params"].items() if v[2] > v[1]})
    out = [{"parametro": k, "bajo": total(k, 1), "alto": total(k, 2), "base": base} for k in nombres]
    df = pd.DataFrame(out, columns=["parametro", "bajo", "alto", "base"])
    df["oscilacion"] = (df["alto"] - df["bajo"]).abs()
    return df.sort_values("oscilacion", ascending=False).reset_index(drop=True)


# ── lanzamiento ─────────────────────────────────────────────────────────────
def _bass(t: np.ndarray, p: float, q: float) -> np.ndarray:
    e = np.exp(-(p + q) * t)
    return (1 - e) / (1 + (q / p) * e)


def adopcion(meses: int, meses_al_pico: int, forma: str = "media") -> np.ndarray:
    """Fracción del pico alcanzada cada mes (difusión de Bass): 90 % en `meses_al_pico`."""
    if forma not in FORMAS:
        raise ValueError(f"Forma de curva desconocida «{forma}». Opciones: {', '.join(FORMAS)}.")
    if meses_al_pico < 1:
        raise ValueError("Los meses al pico tienen que ser al menos 1.")
    p, q = FORMAS[forma]
    x = 0.1 / (1 + 0.9 * q / p)          # e^{-(p+q)t} cuando F(t) = 0,9
    t90 = -np.log(x) / (p + q)
    t = np.arange(1, meses + 1) * (t90 / meses_al_pico)
    return _bass(t, p, q)


@dataclass(frozen=True)
class Lanzamiento:
    pico: float                       # participación de la marca dentro de la clase al pico
    meses_al_pico: int = 24
    horizonte: int = 36
    forma: str = "media"
    crecimiento_anual: float = 0.0    # crecimiento de la clase tratada (activación del latente)
    pico_min: float | None = None
    pico_max: float | None = None


def lanzamiento(supuestos: pd.DataFrame, plan: Lanzamiento, inicio: str | None = None,
                n_sim: int = 1000, semilla: int = 42) -> pd.DataFrame:
    """Proyección mensual de un lanzamiento por país, con P10–P90 de supuestos."""
    if not 0 < plan.pico <= 1:
        raise ValueError("La participación al pico va entre 0 y 1 (por ejemplo 0,15 = 15 %).")
    tabla, _ = normalizar(supuestos)
    filas = _por_fila(tabla)
    rng = np.random.default_rng(semilla)
    curva = adopcion(plan.horizonte, plan.meses_al_pico, plan.forma)
    meses = np.arange(1, plan.horizonte + 1)
    crece = (1 + plan.crecimiento_anual) ** (meses / 12)
    lo, hi = plan.pico_min or plan.pico, plan.pico_max or plan.pico
    pico = rng.triangular(min(lo, plan.pico), plan.pico, max(hi, plan.pico), n_sim) \
        if hi > lo else np.full(n_sim, plan.pico)
    acumulado: dict[str, dict[str, np.ndarray]] = {}
    for f in filas:
        sim = _simular(f["params"], n_sim, rng)
        por_paciente_mes = sim["unidades_clase"] / np.where(sim["en_clase"] > 0, sim["en_clase"], 1) / 12
        pacientes = np.outer(sim["en_clase"] * pico, curva * crece)          # (n_sim, meses)
        unidades = pacientes * por_paciente_mes[:, None]
        acc = acumulado.setdefault(f["pais"], {"pacientes": 0, "unidades": 0, "valor": 0})
        acc["pacientes"] = acc["pacientes"] + pacientes
        acc["unidades"] = acc["unidades"] + unidades
        # Sin precio en algún segmento, el valor del país queda sin calcular:
        # sumar sólo los segmentos con precio daría un total que parece completo.
        if "valor_clase" in sim and acc["valor"] is not None:
            precio = sim["valor_clase"] / np.where(sim["unidades_clase"] > 0, sim["unidades_clase"], 1)
            acc["valor"] = acc["valor"] + unidades * precio[:, None]
        else:
            acc["valor"] = None
    return _tabla_lanzamiento(acumulado, meses, inicio)


def _tabla_lanzamiento(acumulado: dict, meses: np.ndarray, inicio: str | None) -> pd.DataFrame:
    total = {k: sum(a[k] for a in acumulado.values()) if all(a[k] is not None for a in acumulado.values())
             else None for k in ("pacientes", "unidades", "valor")}
    periodos = (pd.period_range(pd.Period(inicio, "M"), periods=len(meses), freq="M").astype(str)
                if inicio else [None] * len(meses))
    filas = []
    for pais, acc in [*acumulado.items(), ("Total", total)]:
        for i, m in enumerate(meses):
            fila = {"pais": pais, "mes": int(m), "periodo": periodos[i],
                    "pacientes": float(np.median(acc["pacientes"][:, i]))}
            for k in ("unidades", "valor"):
                if acc[k] is not None:
                    q = _cuantiles(acc[k][:, i])
                    fila.update({f"{k}_p10": q["p10"], f"{k}_p50": q["p50"], f"{k}_p90": q["p90"]})
            filas.append(fila)
    return pd.DataFrame(filas)


# ── contraste con la historia ───────────────────────────────────────────────
def contrastar(supuestos: pd.DataFrame, observado: pd.DataFrame,
               tolerancia: float = 0.3) -> pd.DataFrame:
    """Pone el embudo contra lo que se vende de verdad, por país.

    `observado` trae `pais` y `unidades` (anuales); opcionalmente `proyectado`
    (unidades anuales que dice la proyección por historia). Sirve para dos
    cosas: ver si los supuestos cierran con la realidad, y ver si una
    proyección por historia se sale del techo que permite el mercado tratado.
    """
    obs = observado.copy()
    obs.columns = [str(c).strip().lower() for c in obs.columns]
    if not {"pais", "unidades"} <= set(obs.columns):
        raise SupuestosInvalidos("Para contrastar hacen falta las columnas «pais» y «unidades».")
    emb = embudo(supuestos).groupby("pais", sort=False).sum(numeric_only=True)
    filas = []
    for r in obs.to_dict("records"):
        pais = str(r["pais"]).strip()
        if pais not in emb.index:
            filas.append({"pais": pais, "estado": "sin supuestos",
                          "lectura": "No hay embudo cargado para este país."})
            continue
        e = emb.loc[pais]
        filas.append(_contraste_pais(pais, e, float(r["unidades"]), _numero(r.get("proyectado")),
                                     tolerancia))
    return pd.DataFrame(filas)


def _contraste_pais(pais: str, e: pd.Series, vendido: float, proyectado: float | None,
                    tol: float) -> dict[str, Any]:
    techo = float(e["unidades_clase"])
    implicito = float(e["unidades_marca"]) if "unidades_marca" in e and e["unidades_marca"] else None
    part = vendido / techo if techo > 0 else None
    fila = {"pais": pais, "vendido": vendido, "techo_clase": techo, "esperado_marca": implicito,
            "participacion_implicita": part}
    if part is not None and part > 1:
        fila.update(estado="imposible", lectura=(
            "Se vende más de lo que consume todo el mercado tratado con estos supuestos: "
            "prevalencia, diagnóstico, tratamiento o dosis están subestimados, o hay ventas "
            "fuera del embudo (canal institucional, exportación)."))
    elif implicito:
        ratio = vendido / implicito
        ok = 1 - tol <= ratio <= 1 + tol
        fila.update(ratio=ratio, estado="coherente" if ok else "revisar", lectura=(
            "Los supuestos explican lo que se vende." if ok else
            f"Lo vendido es {ratio:.0%} de lo que dicen los supuestos: revisá la participación "
            "o las tasas del embudo antes de proyectar con ellos."))
    else:
        fila.update(estado="sin participacion", lectura=(
            f"Sin participación cargada; lo vendido equivale a {part:.1%} del mercado tratado."
            if part is not None else "El mercado tratado da cero con estos supuestos."))
    if proyectado is not None and techo > 0:
        fila["proyectado"] = proyectado
        fila["proyectado_sobre_techo"] = proyectado / techo
        if proyectado > techo:
            fila["estado"] = "proyeccion fuera de techo"
            fila["lectura"] += (" La proyección por historia supera todo el mercado tratado: "
                                "no puede cumplirse sin activar mercado latente.")
    return fila
