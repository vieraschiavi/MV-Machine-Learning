"""Fechas escondidas: columnas que son fechas aunque el tipo diga otra cosa.

El tipo de Arrow sólo dice «fecha» cuando la fecha llegó como fecha. En la
práctica llega de muchas otras formas: texto ``2024-01-31`` o ``31/01/2024``
porque la celda de Excel estaba formateada como texto, ``2024-01`` porque el
período es un mes, o un entero ``202401`` porque así lo guarda el ERP. Si sólo
se mira el tipo, un dataset lleno de fechas queda «sin columna de fecha» y la
pantalla de Proyecciones dice que no se puede proyectar, que es mentira.

La detección mira el CONTENIDO, y es estricta a propósito:

* texto: casi todos los valores (95%) tienen que tener forma de fecha **y**
  poder leerse como tal. Un código como ``M001`` o ``1.234-5`` no pasa.
* números: jamás por el valor solo. Un ``202401`` es indistinguible de un ID o
  de un importe, así que un número es fecha únicamente si la columna SE LLAMA
  como una fecha (``periodo``, ``aniomes``, ``fecha``…) y todos sus valores son
  ``aaaamm`` válidos.

Este módulo es puro (pandas y texto SQL): no toca el disco ni el almacén, así
que lo usan tanto la ingesta como la proyección sin dependencias circulares.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

UMBRAL = 0.95
MUESTRA = 500

# formatos que se reconocen, del más específico al más laxo
_HORA = r"([ T]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?)?"
_YMD_RE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}" + _HORA + r"$")
_DMY_RE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})" + _HORA + r"$")
_YM_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})$")
_YYYYMM_RE = re.compile(r"^(\d{4})(\d{2})$")

# nombres que anuncian una fecha (para preferirla y para aceptar un aaaamm)
_NOMBRE_FECHA = {"fecha", "date", "periodo", "period", "aniomes", "anomes",
                 "yyyymm", "aaaamm", "mesanio", "datetime", "timestamp", "dia", "day"}
_PREFERIDAS = ("fecha", "date", "periodo", "period")
# partes de una fecha: una columna «Anio» o «MesNumero» es numérica pero no es
# una medida que valga la pena proyectar
_PARTES_DE_FECHA = {"anio", "ano", "year", "mes", "month", "dia", "day", "semana",
                    "week", "trimestre", "quarter", "hora", "hour", "id"}


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def tokens(nombre: str) -> list[str]:
    """``DiaSemanaNumero`` → ``[dia, semana, numero]``; ``fecha_alta`` → ``[fecha, alta]``."""
    s = _sin_acentos(str(nombre))
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    return [t for t in re.split(r"[^A-Za-z0-9]+", s.lower()) if t]


def nombre_de_fecha(nombre: str) -> bool:
    ts = tokens(nombre)
    return any(t in _NOMBRE_FECHA for t in ts) or "".join(ts) in _NOMBRE_FECHA


def es_parte_de_fecha(nombre: str) -> bool:
    return any(t in _PARTES_DE_FECHA for t in tokens(nombre))


def preferencia(nombre: str) -> int:
    """0 si la columna se llama fecha/date/periodo; 1 si no. Para ordenar."""
    ts = tokens(nombre)
    return 0 if ts and ts[0] in _PREFERIDAS else 1


def _proporcion(muestra: pd.Series, patron: re.Pattern) -> float:
    return float(muestra.map(lambda v: bool(patron.match(v))).mean())


def _aaaamm_validos(muestra: pd.Series) -> bool:
    ok = 0
    for v in muestra:
        m = _YYYYMM_RE.match(v)
        if m and 1900 <= int(m.group(1)) <= 2100 and 1 <= int(m.group(2)) <= 12:
            ok += 1
    return ok / len(muestra) >= UMBRAL


def detectar(valores: pd.Series, nombre: str = "") -> str | None:
    """Formato de fecha de una columna, o ``None`` si no es una fecha.

    Devuelve ``ymd`` (2024-01-31), ``dmy`` (31/01/2024), ``mdy`` (01/31/2024),
    ``ym`` (2024-01) o ``yyyymm`` (202401). Las columnas ya tipadas como fecha
    no pasan por acá: esas son ``nativa`` y las resuelve quien llama.
    """
    s = valores.dropna()
    if pd.api.types.is_bool_dtype(s):
        return None
    if pd.api.types.is_numeric_dtype(s):
        # un número sólo es fecha si la columna lo dice con su nombre
        if not nombre_de_fecha(nombre) or len(s) < 3:
            return None
        s = s.head(MUESTRA)
        if not (s == s.round()).all():
            return None
        return "yyyymm" if _aaaamm_validos(s.astype("int64").astype(str)) else None

    muestra = s.astype(str).str.strip()
    muestra = muestra[muestra != ""].head(MUESTRA)
    if len(muestra) < 3:
        return None

    if _proporcion(muestra, _YMD_RE) >= UMBRAL:
        leidas = pd.to_datetime(muestra, errors="coerce", format="mixed", yearfirst=True)
        return "ymd" if leidas.notna().mean() >= UMBRAL else None

    if _proporcion(muestra, _DMY_RE) >= UMBRAL:
        partes = [m for m in (_DMY_RE.match(v) for v in muestra) if m]
        dia_primero = True                     # la convención de acá, si nada lo contradice
        if max(int(m.group(1)) for m in partes) > 12:
            dia_primero = True
        elif max(int(m.group(2)) for m in partes) > 12:
            dia_primero = False
        leidas = pd.to_datetime(muestra, errors="coerce", dayfirst=dia_primero, format="mixed")
        if leidas.notna().mean() >= UMBRAL:
            return "dmy" if dia_primero else "mdy"
        return None

    if _proporcion(muestra, _YM_RE) >= UMBRAL:
        meses = [int(m.group(2)) for m in (_YM_RE.match(v) for v in muestra) if m]
        if meses and sum(1 <= x <= 12 for x in meses) / len(muestra) >= UMBRAL:
            return "ym"
        return None

    if nombre_de_fecha(nombre) and _proporcion(muestra, _YYYYMM_RE) >= UMBRAL \
            and _aaaamm_validos(muestra):
        return "yyyymm"
    return None


def _formatos(seps: str, cuerpo: str, horas: bool = True) -> list[str]:
    out = []
    for sep in seps:
        base = cuerpo.replace("-", sep)
        out.append(base)
        if horas:
            out += [base + " %H:%M:%S", base + " %H:%M", base + "T%H:%M:%S"]
    return out


def expr_sql(col_sql: str, formato: str | None) -> str:
    """Expresión DuckDB que convierte la columna en TIMESTAMP (NULL si no se lee).

    ``col_sql`` ya viene entrecomillada. Con ``try_strptime`` un valor suelto
    que no se lee queda en NULL y se descarta, en vez de tirar abajo la consulta.
    """
    if formato in (None, "nativa"):
        return col_sql
    texto = f"trim(CAST({col_sql} AS VARCHAR))"
    if formato == "ymd":
        lista = _formatos("-/.", "%Y-%m-%d")
        return (f"COALESCE(try_cast({texto} AS TIMESTAMP), "
                f"try_strptime({texto}, {lista!r}))")
    if formato in ("dmy", "mdy"):
        cuerpo = "%d-%m-" if formato == "dmy" else "%m-%d-"
        # %y primero: con %Y, «24» se leería como el año 24 d. C.
        lista = _formatos("/-.", cuerpo + "%y") + _formatos("/-.", cuerpo + "%Y")
        return f"try_strptime({texto}, {lista!r})"
    if formato == "ym":
        return f"try_strptime({texto}, ['%Y-%m', '%Y/%m', '%Y.%m'])"
    if formato == "yyyymm":
        return f"try_strptime(CAST(TRY_CAST({col_sql} AS BIGINT) AS VARCHAR), '%Y%m')"
    raise ValueError(f"Formato de fecha desconocido: {formato!r}")
