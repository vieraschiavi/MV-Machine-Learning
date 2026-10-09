"""Fuentes públicas reales, agregadas: OMS (GHO), Banco Mundial y Google Trends.

Nada de esto identifica a nadie: son tasas y conteos por país, sexo y edad.

* **OMS — Global Health Observatory** (``ghoapi.azureedge.net``): prevalencia
  de hipertensión, diabetes y obesidad por país y sexo, con su intervalo de
  confianza; para hipertensión, además, la cobertura de diagnóstico y de
  tratamiento. Es el embudo del agente de mercado, medido.
* **Banco Mundial** (``api.worldbank.org``): población por sexo y tramos de
  5 años, para llevar las tasas a personas.
* **Google Trends**: no tiene API pública; se carga la exportación CSV de
  «interés por región» (0–100). Es búsqueda agregada, no de personas.

Salidas en los formatos que ya usa el programa:

* ``prevalencias_oms`` → la tabla de prevalencias de ``territorio``;
* ``supuestos_oms`` → los supuestos del agente de mercado (población,
  prevalencia, diagnosticados, tratados), con mínimo y máximo del intervalo y
  la fuente citada: un estudio de verdad que pisa a la propuesta de la IA;
* ``poblacion_banco_mundial`` → la tabla de población por país, sexo y edad.

La red se inyecta (``abrir``) para probar sin salir a internet.
"""
from __future__ import annotations

import io
import json
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

import pandas as pd

from .consentimiento import _clave, politica

GHO = "https://ghoapi.azureedge.net/api"
BM = "https://api.worldbank.org/v2"
ISO3 = {"Argentina": "ARG", "Bolivia": "BOL", "Brasil": "BRA", "Chile": "CHL", "Colombia": "COL",
        "Costa Rica": "CRI", "Ecuador": "ECU", "El Salvador": "SLV", "Guatemala": "GTM", "Honduras": "HND",
        "México": "MEX", "Nicaragua": "NIC", "Panamá": "PAN", "Paraguay": "PRY", "Perú": "PER",
        "República Dominicana": "DOM", "Uruguay": "URY", "Venezuela": "VEN"}
_POR_CLAVE = {_clave(k): k for k in ISO3} | {_clave(v): k for k, v in ISO3.items()}
SEXOS = {"SEX_BTSX": "Total", "SEX_MLE": "Hombres", "SEX_FMLE": "Mujeres"}
# área: indicadores de la OMS y el tramo de edad al que se refieren
AREAS = {
    "Cardiometabólica": {"enfermedad": "Hipertensión", "edad": (30, 79),
                         "prevalencia": "NCD_HYP_PREVALENCE_C", "diagnostico": "NCD_HYP_DIAGNOSIS_C",
                         "tratamiento": "NCD_HYP_TREATMENT_C"},
    # La OMS no publica cobertura de diagnóstico de diabetes: sólo la prevalencia entra al embudo.
    "Diabetes": {"enfermedad": "Diabetes", "edad": (18, None), "grupo_edad": "18-PLUS",
                 "prevalencia": "NCD_DIABETES_PREVALENCE_CRUDE"},
    "Obesidad": {"enfermedad": "Obesidad", "edad": (18, None), "grupo_edad": "18-PLUS", "prevalencia": "NCD_BMI_30C"},
}
TIMEOUT = 30

Abrir = Callable[[str], bytes]


def _abrir_red(url: str, intentos: int = 3) -> bytes:
    """GET con reintento: la API del Banco Mundial a veces tarda en contestar una de las llamadas."""
    req = urllib.request.Request(url, headers={"User-Agent": "MV-AutoML-Studio"})
    for i in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - sólo URLs https armadas acá
                return r.read()
        except (TimeoutError, OSError):
            if i == intentos - 1:
                raise
            time.sleep(2 ** i)
    raise OSError("sin respuesta")


def pais(nombre: str) -> str:
    """Nombre canónico del país (acepta ISO3, sin tildes, en minúsculas)."""
    k = _POR_CLAVE.get(_clave(nombre)) or _POR_CLAVE.get(_clave(politica(nombre).pais))
    if not k:
        raise ValueError(f"País sin código ISO conocido: «{nombre}». Disponibles: {', '.join(ISO3)}.")
    return k


# ── OMS ─────────────────────────────────────────────────────────────────────
def oms(indicador: str, paises: list[str], abrir: Abrir | None = None,
        grupo_edad: str | None = None) -> pd.DataFrame:
    """El último año disponible de un indicador de la OMS, por país y sexo, como proporción (0–1).

    Algunos indicadores vienen además por grupo de edad (``18-PLUS``, ``30-PLUS``):
    se toma el pedido; los que no lo traen se toman sin desagregar.
    """
    grupo = f"AGEGROUP_YEARS{grupo_edad}" if grupo_edad else None
    abrir = abrir or _abrir_red
    nombres = [pais(p) for p in paises]
    filtro = " or ".join(f"SpatialDim eq '{ISO3[n]}'" for n in nombres)
    url = f"{GHO}/{indicador}?" + urllib.parse.urlencode({"$filter": f"({filtro})"})
    try:
        datos = json.loads(abrir(url))["value"]
    except (OSError, ValueError, KeyError) as exc:
        raise ValueError(f"No se pudo leer el indicador {indicador} de la OMS: {exc}") from exc
    a_nombre = {ISO3[n]: n for n in nombres}
    filas = [{"pais": a_nombre.get(d["SpatialDim"]), "indicador": indicador, "anio": int(d["TimeDim"]),
              "sexo": SEXOS.get(d.get("Dim1"), "Total"), "valor": d.get("NumericValue"),
              "bajo": d.get("Low"), "alto": d.get("High")}
             for d in datos if d.get("NumericValue") is not None and d.get("SpatialDim") in a_nombre
             and (d.get("Dim2") or None) == grupo and d.get("Dim3") in (None, "")]
    if not filas:
        return pd.DataFrame(columns=["pais", "indicador", "anio", "sexo", "valor", "bajo", "alto"])
    df = pd.DataFrame(filas)
    for c in ("valor", "bajo", "alto"):
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100
    df = df.sort_values("anio").drop_duplicates(["pais", "sexo"], keep="last")
    return df.sort_values(["pais", "sexo"]).reset_index(drop=True)


def _area(area: str) -> dict[str, Any]:
    for k, v in AREAS.items():
        if _clave(k) == _clave(area) or _clave(v["enfermedad"]) == _clave(area):
            return {"area": k, **v}
    raise ValueError(f"Área sin indicadores de la OMS: «{area}». Disponibles: {', '.join(AREAS)}.")


def _cita(indicador: str, anio: int, extra: str = "") -> str:
    return f"OMS, Global Health Observatory, {indicador} ({anio}){extra}"


def prevalencias_oms(area: str, paises: list[str], abrir: Abrir | None = None) -> pd.DataFrame:
    """Tabla de prevalencias (formato de ``territorio``) con la OMS como fuente citada."""
    a = _area(area)
    df = oms(a["prevalencia"], paises, abrir, a.get("grupo_edad"))
    edad = f"{a['edad'][0]}-{a['edad'][1]}" if a["edad"][1] else f"{a['edad'][0]}+"
    return pd.DataFrame({
        "pais": df["pais"], "area_terapeutica": a["area"], "sexo": df["sexo"], "rango_edad": "Total",
        "prevalencia": df["valor"],
        "fuente": [_cita(a["prevalencia"], y, f", adultos {edad}") for y in df["anio"]]})


# ── Banco Mundial ───────────────────────────────────────────────────────────
_TRAMOS = ["0004", "0509", "1014", "1519", "2024", "2529", "3034", "3539", "4044", "4549", "5054", "5559",
           "6064", "6569", "7074", "7579", "80UP"]


def _peso_tramo(tramo: str, desde: int, hasta: int | None) -> float:
    """Qué parte de un tramo de 5 años cae en [desde, hasta] (suponiendo edades parejas dentro del tramo)."""
    ini = int(tramo[:2])
    fin = 100 if tramo == "80UP" else int(tramo[2:])
    hi = hasta if hasta is not None else 100
    cubre = max(0, min(fin, hi) - max(ini, desde) + 1)
    return cubre / (fin - ini + 1)


def poblacion_por_tramos(paises: list[str], abrir: Abrir | None = None) -> pd.DataFrame:
    """Población por país, sexo y tramo de 5 años (último año con dato) del Banco Mundial."""
    abrir = abrir or _abrir_red
    nombres = [pais(p) for p in paises]
    codigos = ";".join(ISO3[n] for n in nombres)
    a_nombre = {ISO3[n]: n for n in nombres}
    filas = []
    for tramo in _TRAMOS:
        for sx, sexo in (("MA", "Hombres"), ("FE", "Mujeres")):
            ind = f"SP.POP.{tramo}.{sx}"
            url = f"{BM}/country/{codigos}/indicator/{ind}?format=json&mrnev=1&per_page=100"
            try:
                cuerpo = json.loads(abrir(url))
            except (OSError, ValueError) as exc:
                raise ValueError(f"No se pudo leer {ind} del Banco Mundial: {exc}") from exc
            for d in (cuerpo[1] if len(cuerpo) > 1 and cuerpo[1] else []):
                if d.get("value") is not None and d.get("countryiso3code") in a_nombre:
                    filas.append({"pais": a_nombre[d["countryiso3code"]], "sexo": sexo, "tramo": tramo,
                                  "anio": int(d["date"]), "poblacion": float(d["value"])})
    return pd.DataFrame(filas, columns=["pais", "sexo", "tramo", "anio", "poblacion"])


RANGOS = {"18-39": (18, 39), "40-59": (40, 59), "60+": (60, None)}


def poblacion_banco_mundial(paises: list[str], rangos: dict[str, tuple[int, int | None]] | None = None,
                            abrir: Abrir | None = None) -> pd.DataFrame:
    """Población adulta por país, sexo y rango de edad: la tabla de población de ``territorio`` (nivel país)."""
    t = poblacion_por_tramos(paises, abrir)
    filas = []
    for (p, sexo), g in t.groupby(["pais", "sexo"]):
        for rango, (desde, hasta) in (rangos or RANGOS).items():
            n = sum(r.poblacion * _peso_tramo(r.tramo, desde, hasta) for r in g.itertuples())
            filas.append({"pais": p, "ciudad": "(total país)", "barrio": "", "sexo": sexo, "rango_edad": rango,
                          "nse": "", "poblacion": round(n), "fuente": f"Banco Mundial, SP.POP ({int(g['anio'].max())})"})
    return pd.DataFrame(filas)


def _adultos(t: pd.DataFrame, desde: int, hasta: int | None) -> pd.DataFrame:
    t = t.assign(n=[r.poblacion * _peso_tramo(r.tramo, desde, hasta) for r in t.itertuples()])
    g = t.groupby(["pais", "sexo"]).agg(poblacion=("n", "sum"), anio=("anio", "max")).reset_index()
    total = g.groupby("pais").agg(poblacion=("poblacion", "sum"), anio=("anio", "max")).reset_index()
    return pd.concat([g, total.assign(sexo="Total")], ignore_index=True)


# ── supuestos del agente de mercado ─────────────────────────────────────────
def supuestos_oms(area: str, paises: list[str], segmentos: tuple[str, ...] = ("Hombres", "Mujeres"),
                  abrir: Abrir | None = None) -> pd.DataFrame:
    """Población, prevalencia, diagnosticados y tratados por país y sexo, con intervalo y fuente.

    La OMS mide la cobertura de diagnóstico y de tratamiento sobre **todos** los
    que tienen la enfermedad; el embudo del agente mide «tratados» sobre los
    diagnosticados, así que se convierte: tratados = tratamiento / diagnóstico.
    """
    a = _area(area)
    pob = _adultos(poblacion_por_tramos(paises, abrir), *a["edad"])
    edad = f"{a['edad'][0]}-{a['edad'][1]}" if a["edad"][1] else f"{a['edad'][0]}+"
    datos = {k: oms(a[k], paises, abrir, a.get("grupo_edad")) for k in ("prevalencia", "diagnostico", "tratamiento") if k in a}
    filas: list[dict[str, Any]] = []
    for p in [pais(x) for x in paises]:
        for seg in segmentos:
            filas += _supuestos_segmento(a, p, seg, pob, datos, edad)
    return pd.DataFrame(filas, columns=["pais", "segmento", "parametro", "valor", "minimo", "maximo", "origen",
                                        "fuente"])


def _dato(datos: dict[str, pd.DataFrame], k: str, p: str, seg: str) -> pd.Series | None:
    d = datos.get(k)
    if d is None or d.empty:
        return None
    s = d[(d["pais"] == p) & (d["sexo"] == seg)]
    return s.iloc[0] if len(s) else None


def _supuestos_segmento(a: dict[str, Any], p: str, seg: str, pob: pd.DataFrame,
                        datos: dict[str, pd.DataFrame], edad: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def fila(param: str, valor: Any, mn: Any = None, mx: Any = None, fuente: str = "") -> None:
        if valor is not None and pd.notna(valor):
            out.append({"pais": p, "segmento": seg, "parametro": param, "valor": float(valor),
                        "minimo": None if mn is None or pd.isna(mn) else float(mn),
                        "maximo": None if mx is None or pd.isna(mx) else float(mx),
                        "origen": "fuente pública", "fuente": fuente})

    pp = pob[(pob["pais"] == p) & (pob["sexo"] == seg)]
    if len(pp):
        fila("poblacion", round(pp["poblacion"].iloc[0]),
             fuente=f"Banco Mundial, SP.POP ({int(pp['anio'].iloc[0])}), {seg.lower()} {edad}")
    prev, diag, trat = (_dato(datos, k, p, seg) for k in ("prevalencia", "diagnostico", "tratamiento"))
    if prev is not None:
        fila("prevalencia", prev["valor"], prev["bajo"], prev["alto"], _cita(a["prevalencia"], prev["anio"]))
    if diag is not None:
        fila("diagnosticados", diag["valor"], diag["bajo"], diag["alto"], _cita(a["diagnostico"], diag["anio"]))
    if trat is not None and diag is not None and diag["valor"]:
        fila("tratados", min(trat["valor"] / diag["valor"], 1.0),
             fuente=_cita(a["tratamiento"], trat["anio"], f" ÷ {a['diagnostico']}: tratados sobre diagnosticados"))
    return out


# ── censos publicados «a lo ancho» ──────────────────────────────────────────
_SEXO = {"hombres": "Hombres", "hombre": "Hombres", "varones": "Hombres", "masculino": "Hombres", "h": "Hombres",
         "m": "Mujeres", "mujeres": "Mujeres", "mujer": "Mujeres", "femenino": "Mujeres",
         "homens": "Hombres", "mulheres": "Mujeres"}
_COL = re.compile(r"^(?P<sexo>[a-z]+)[\s_\-]+(?P<edad>\d+\s*(?:-\s*\d+|\+|\s*y\s*mas|\s*e\s*mais))$")


def censo_ancho_a_largo(df: pd.DataFrame, id_cols: list[str] | None = None) -> pd.DataFrame:
    """Una tabla de censo con una columna por sexo y edad («Hombres 18-39», «Mujeres_60+») al formato largo.

    Las columnas de identificación (país, ciudad, barrio, nse) se toman por nombre;
    el resto tiene que ser «sexo edad».
    """
    d = df.copy()
    d.columns = [_clave(c) for c in d.columns]
    ids = [_clave(c) for c in (id_cols or [c for c in ("pais", "ciudad", "barrio", "nse") if c in d.columns])]
    faltan = [c for c in ("pais", "ciudad") if c not in ids]
    if faltan:
        raise ValueError(f"Al censo le faltan columnas de identificación: {', '.join(faltan)}.")
    valores, raras = {}, []
    for c in d.columns:
        if c in ids:
            continue
        m = _COL.match(c)
        if not m or m["sexo"] not in _SEXO:
            raras.append(c)
            continue
        edad = re.sub(r"\s*(y\s*mas|e\s*mais)$", "+", re.sub(r"\s+", "", m["edad"]))
        valores[c] = (_SEXO[m["sexo"]], edad)
    if raras:
        raise ValueError(f"Columnas que no son «sexo edad»: {', '.join(raras[:6])}. Ej.: «Hombres 18-39».")
    largo = d.melt(id_vars=ids, value_vars=list(valores), var_name="columna", value_name="poblacion")
    largo["sexo"] = largo["columna"].map(lambda c: valores[c][0])
    largo["rango_edad"] = largo["columna"].map(lambda c: valores[c][1])
    largo["poblacion"] = pd.to_numeric(largo["poblacion"].astype(str).str.replace(".", "", regex=False)
                                       .str.replace(",", ".", regex=False), errors="coerce")
    if (largo["poblacion"] < 0).any():
        raise ValueError("Hay poblaciones negativas en el censo.")
    for c in ("barrio", "nse"):
        if c not in largo.columns:
            largo[c] = ""
    return largo[["pais", "ciudad", "barrio", "sexo", "rango_edad", "nse", "poblacion"]].dropna(subset=["poblacion"])


# ── Google Trends ───────────────────────────────────────────────────────────
def trends_csv(contenido: bytes | str, pais_: str, termino: str | None = None) -> pd.DataFrame:
    """La exportación «Interés por subregión» de Google Trends, en formato largo (región · término · interés).

    Acepta el CSV tal como lo baja Trends (líneas de encabezado incluidas) y
    «<1» como 0,5. El interés es relativo (100 = la región con más búsquedas).
    """
    texto = contenido.decode("utf-8-sig") if isinstance(contenido, bytes) else contenido
    lineas = [ln for ln in texto.splitlines() if ln.strip()]
    inicio = next((i for i, ln in enumerate(lineas) if "," in ln and not ln.lower().startswith("category")
                   and not ln.lower().startswith("categoría")), None)
    if inicio is None:
        raise ValueError("No parece una exportación de Google Trends: no hay tabla de región e interés.")
    df = pd.read_csv(io.StringIO("\n".join(lineas[inicio:])))
    if df.shape[1] < 2:
        raise ValueError("La exportación de Google Trends tiene que tener región y al menos un término.")
    region = df.columns[0]
    largo = df.melt(id_vars=[region], var_name="termino", value_name="interes")
    largo["termino"] = largo["termino"].map(lambda t: termino or re.sub(r":\s*\(.*\)$", "", str(t)).strip())
    largo["interes"] = largo["interes"].map(lambda v: 0.5 if str(v).strip() == "<1" else pd.to_numeric(v, errors="coerce"))
    largo = largo.dropna(subset=["interes"]).rename(columns={region: "region"})
    largo.insert(0, "pais", pais(pais_))
    return largo[["pais", "region", "termino", "interes"]].reset_index(drop=True)


__all__ = ["AREAS", "ISO3", "censo_ancho_a_largo", "oms", "pais", "poblacion_banco_mundial", "poblacion_por_tramos", "prevalencias_oms",
           "supuestos_oms", "trends_csv"]
