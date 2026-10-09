"""Modelo estrella de relacionamiento, listo para un Lakehouse de Fabric.

Junta en un solo modelo lo propio (contactos seudónimos, contenidos,
interacciones, recomendaciones) con lo público y agregado (población del
censo, prevalencias de encuestas de salud, escucha social, cobertura). Las
dimensiones son **conformadas**: país, área terapéutica y producto llevan una
columna ``*_clave`` normalizada (sin tildes, en minúsculas) para relacionarse
con las mismas dimensiones del modelo corporativo (Analysis Services o el
data warehouse) sin depender de cómo se escribió cada nombre.

Las claves sustitutas salen de un hash de la clave natural: son **estables**
entre cargas, así que una carga incremental (MERGE en Delta) o una migración
de entorno no rompe relaciones.

Ningún dato que identifique a la persona entra al modelo: el contacto es un id
seudónimo; el mail y el teléfono viven en el CRM.

Además de las tablas escribe:

* ``modelo.json`` — tablas, columnas, tipos y relaciones (para armar el modelo
  semántico o un TMDL);
* ``crear_tablas.sql`` — el DDL de Spark SQL para crear las tablas Delta en el
  Lakehouse;
* ``cargar_en_lakehouse.py`` — la celda de notebook que lee los archivos y los
  guarda como tablas Delta.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .consentimiento import _clave
from .powerbi_portafolio import FORMATOS, _escribir

RELACIONES = [  # (desde tabla, columna) → (hacia dimensión, columna): muchos a uno
    ("dim_contacto", "geo_key", "dim_geografia", "geo_key"),
    ("dim_contenido", "area_key", "dim_area", "area_key"),
    ("dim_contenido", "producto_key", "dim_producto", "producto_key"),
    ("dim_producto", "area_key", "dim_area", "area_key"),
    ("puente_contacto_area", "contacto_key", "dim_contacto", "contacto_key"),
    ("puente_contacto_area", "area_key", "dim_area", "area_key"),
    ("fact_interacciones", "contacto_key", "dim_contacto", "contacto_key"),
    ("fact_interacciones", "contenido_key", "dim_contenido", "contenido_key"),
    ("fact_interacciones", "fecha_key", "dim_fecha", "fecha_key"),
    ("fact_recomendaciones", "contacto_key", "dim_contacto", "contacto_key"),
    ("fact_recomendaciones", "contenido_key", "dim_contenido", "contenido_key"),
    ("fact_recomendaciones", "fecha_key", "dim_fecha", "fecha_key"),
    ("fact_poblacion", "geo_key", "dim_geografia", "geo_key"),
    ("fact_prevalencia", "geo_key", "dim_geografia", "geo_key"),
    ("fact_prevalencia", "area_key", "dim_area", "area_key"),
    ("fact_escucha", "geo_key", "dim_geografia", "geo_key"),
    ("fact_escucha", "fecha_key", "dim_fecha", "fecha_key"),
    ("fact_cobertura", "geo_key", "dim_geografia", "geo_key"),
    ("fact_cobertura", "area_key", "dim_area", "area_key"),
    ("fact_consentimientos", "contacto_key", "dim_contacto", "contacto_key"),
    ("fact_consentimientos", "fecha_key", "dim_fecha", "fecha_key"),
]
_SQL = {"int64": "BIGINT", "Int64": "BIGINT", "int32": "INT", "float64": "DOUBLE", "bool": "BOOLEAN",
        "datetime64[ns]": "DATE", "object": "STRING", "string": "STRING"}


def clave(*partes: Any) -> int:
    """Clave sustituta estable: el mismo nombre (con o sin tildes) da siempre la misma clave."""
    texto = "|".join(_clave(p) for p in partes)
    return int(hashlib.sha1(texto.encode()).hexdigest()[:15], 16)


def _col(df: pd.DataFrame | None, c: str) -> pd.Series:
    if df is None:
        return pd.Series(dtype=object)
    return df[c].fillna("").astype(str) if c in df.columns else pd.Series("", index=df.index)


def _geo(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["pais", "ciudad", "barrio"])
    return pd.DataFrame({c: _col(df, c) for c in ("pais", "ciudad", "barrio")})


def _claves(valores: Any) -> pd.Series:
    """Claves de una columna que puede venir vacía: Int64 con nulos (un float perdería dígitos)."""
    return pd.Series([clave(v) if _clave(v) else None for v in valores], dtype="Int64")


def _con_geo(df: pd.DataFrame) -> pd.Series:
    return pd.Series([clave(p, c, b) for p, c, b in zip(_col(df, "pais"), _col(df, "ciudad"),
                                                          _col(df, "barrio"), strict=True)], index=df.index, dtype="int64")


def _fecha_key(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.strftime("%Y%m%d").astype("Int64")


def dim_fecha(*series: pd.Series) -> pd.DataFrame:
    fechas = pd.concat([pd.to_datetime(s, errors="coerce") for s in series if s is not None and len(s)])
    fechas = fechas.dropna()
    if fechas.empty:
        return pd.DataFrame(columns=["fecha_key", "fecha", "anio", "mes", "anio_mes", "semana_iso"])
    rango = pd.date_range(fechas.min().normalize(), fechas.max().normalize(), freq="D")
    return pd.DataFrame({"fecha_key": rango.strftime("%Y%m%d").astype(int), "fecha": rango,
                         "anio": rango.year, "mes": rango.month, "anio_mes": rango.strftime("%Y-%m"),
                         "semana_iso": rango.isocalendar().week.astype(int).values})


def construir(*, contactos: pd.DataFrame | None = None, contenidos: pd.DataFrame | None = None,
              interacciones: pd.DataFrame | None = None, recomendaciones: pd.DataFrame | None = None,
              poblacion: pd.DataFrame | None = None, prevalencias: pd.DataFrame | None = None,
              escucha: pd.DataFrame | None = None, cobertura: pd.DataFrame | None = None,
              consentimientos: pd.DataFrame | None = None, hoy: Any = None) -> dict[str, pd.DataFrame]:
    """Arma las dimensiones y los hechos con lo que haya. Las tablas preparadas por cada módulo."""
    t: dict[str, pd.DataFrame] = {}
    geo = pd.concat([_geo(contactos), _geo(poblacion), _geo(prevalencias), _geo(escucha), _geo(cobertura)])
    geo = geo.drop_duplicates().reset_index(drop=True)
    if not geo.empty:
        geo.insert(0, "geo_key", _con_geo(geo))
        geo["pais_clave"] = geo["pais"].map(_clave)
        geo["nivel"] = geo.apply(lambda r: "barrio" if r["barrio"] else "ciudad" if r["ciudad"] else "pais", axis=1)
        t["dim_geografia"] = geo.drop_duplicates("geo_key")
    areas = pd.concat([_col(x, "area_terapeutica") for x in (contenidos, prevalencias, cobertura)]
                      + ([pd.Series([a for s in contactos["areas_interes"] for a in s])]
                         if contactos is not None and "areas_interes" in contactos else []))
    areas = sorted({a for a in areas if _clave(a)}, key=_clave)
    vistos: dict[str, str] = {}
    for a in areas:
        vistos.setdefault(_clave(a), a)
    if vistos:
        t["dim_area"] = pd.DataFrame({"area_key": [clave(k) for k in vistos], "area_terapeutica": list(vistos.values()),
                                      "area_clave": list(vistos)})
    if contenidos is not None:
        t.update(_catalogo(contenidos))
    if contactos is not None:
        t.update(_contactos(contactos))
    if interacciones is not None and not interacciones.empty:
        t["fact_interacciones"] = pd.DataFrame({
            "contacto_key": interacciones["id_contacto"].astype(str), "contenido_key": interacciones["id_contenido"].astype(str),
            "fecha_key": _fecha_key(interacciones["fecha"]), "evento": interacciones["evento"], "cantidad": 1})
    if recomendaciones is not None and not recomendaciones.empty:
        r = recomendaciones.copy()
        r["fecha_key"] = int(pd.Timestamp(hoy or pd.Timestamp.today()).strftime("%Y%m%d"))
        t["fact_recomendaciones"] = r.rename(columns={"id_contacto": "contacto_key", "id_contenido": "contenido_key"})[
            ["contacto_key", "contenido_key", "fecha_key", "rango", "puntaje", "personalizado", "motivo"]]
    if consentimientos is not None and not consentimientos.empty:
        c = consentimientos
        t["fact_consentimientos"] = pd.DataFrame({
            "contacto_key": c["id_contacto"].astype(str), "fecha_key": _fecha_key(c["fecha"]),
            "finalidad": c["finalidad"], "accion": c["accion"], "canal": c["canal"],
            "version_texto": c["version_texto"]})
    t.update(_publicos(poblacion, prevalencias, escucha, cobertura))
    fechas = [x["fecha_key"].astype(str) for x in t.values() if "fecha_key" in x.columns and len(x)]
    if fechas:
        t["dim_fecha"] = dim_fecha(*[pd.to_datetime(f, format="%Y%m%d", errors="coerce") for f in fechas])
    return t


def _catalogo(contenidos: pd.DataFrame) -> dict[str, pd.DataFrame]:
    c = contenidos
    out = {"dim_contenido": pd.DataFrame({
        "contenido_key": c["id_contenido"].astype(str), "titulo": _col(c, "titulo"), "tipo": _col(c, "tipo"),
        "area_key": _claves(_col(c, "area_terapeutica")).values,
        "producto_key": _claves(_col(c, "producto")).values,
        "condicion_venta": _col(c, "condicion_venta"), "audiencia": _col(c, "audiencia"), "canal": _col(c, "canal")})}
    prod = c[_col(c, "producto").map(_clave) != ""].drop_duplicates("producto")
    if not prod.empty:
        out["dim_producto"] = pd.DataFrame({
            "producto_key": [clave(p) for p in prod["producto"]], "producto": prod["producto"].values,
            "producto_clave": prod["producto"].map(_clave).values,
            "area_key": _claves(_col(prod, "area_terapeutica")).values,
            "condicion_venta": _col(prod, "condicion_venta").values}).drop_duplicates("producto_key")
    return out


def _contactos(contactos: pd.DataFrame) -> dict[str, pd.DataFrame]:
    c = contactos
    dim = pd.DataFrame({"contacto_key": c["id_contacto"].astype(str), "geo_key": _con_geo(c)})
    for col in ("tipo", "sexo", "rango_edad", "nse_zona", "canal_captacion", "canal_preferido", "especialidad"):
        if col in c.columns:
            dim[col] = c[col].values
    if "fecha_alta" in c.columns:
        dim["fecha_alta"] = pd.to_datetime(c["fecha_alta"], errors="coerce").values
    for col in ("consiente_contacto", "consiente_marketing", "consiente_salud", "consiente_perfilado",
                "doble_optin", "baja"):
        if col in c.columns:
            dim[col] = c[col].astype(bool).values
    puente = [(i, clave(a)) for i, s in zip(c["id_contacto"].astype(str), c.get("areas_interes", []), strict=False)
              for a in s]
    return {"dim_contacto": dim,
            "puente_contacto_area": pd.DataFrame(puente, columns=["contacto_key", "area_key"])}


def _publicos(poblacion: pd.DataFrame | None, prevalencias: pd.DataFrame | None,
              escucha: pd.DataFrame | None, cobertura: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
    out = {}
    if poblacion is not None and not poblacion.empty:
        out["fact_poblacion"] = pd.DataFrame({"geo_key": _con_geo(poblacion), "sexo": _col(poblacion, "sexo"),
                                              "rango_edad": _col(poblacion, "rango_edad"),
                                              "nse": _col(poblacion, "nse"), "poblacion": poblacion["poblacion"]})
    if prevalencias is not None and not prevalencias.empty:
        out["fact_prevalencia"] = pd.DataFrame({
            "geo_key": _con_geo(prevalencias), "area_key": [clave(a) for a in prevalencias["area_terapeutica"]],
            "sexo": _col(prevalencias, "sexo"), "rango_edad": _col(prevalencias, "rango_edad"),
            "prevalencia": prevalencias["prevalencia"], "fuente": _col(prevalencias, "fuente")})
    if escucha is not None and not escucha.empty:
        out["fact_escucha"] = pd.DataFrame({
            "geo_key": _con_geo(escucha), "fecha_key": _fecha_key(escucha["semana"]), "tema": escucha["tema"],
            "menciones": escucha["menciones"], "positivas": escucha["positivas"], "negativas": escucha["negativas"]})
    if cobertura is not None and not cobertura.empty:
        cob = cobertura.copy()
        cob.insert(0, "geo_key", _con_geo(cob))
        cob.insert(1, "area_key", [clave(a) for a in cob["area_terapeutica"]])
        # Las celdas suprimidas («<10») quedan vacías en el modelo: un número no puede ser texto.
        for col in ("en_base", "captados_area"):
            cob[col] = pd.to_numeric(cob[col], errors="coerce").astype("Int64")
        out["fact_cobertura"] = cob.drop(columns=[c for c in ("pais", "ciudad", "barrio", "area_terapeutica")
                                                  if c in cob.columns])
    return out


def _tipo_sql(serie: pd.Series) -> str:
    return _SQL.get(str(serie.dtype), "STRING")


def esquema(tablas: dict[str, pd.DataFrame]) -> dict[str, Any]:
    rel = [{"desde": f"{a}[{b}]", "hacia": f"{c}[{d}]", "cardinalidad": "muchos a uno"}
           for a, b, c, d in RELACIONES if a in tablas and c in tablas]
    return {"tablas": {n: [{"columna": c, "tipo": _tipo_sql(df[c])} for c in df.columns] for n, df in tablas.items()},
            "relaciones": rel}


def ddl(tablas: dict[str, pd.DataFrame], esquema_lakehouse: str = "relacionamiento") -> str:
    partes = [f"-- Tablas Delta del modelo de relacionamiento (MV AutoML Studio).\n"
              f"CREATE SCHEMA IF NOT EXISTS {esquema_lakehouse};\n"]
    for n, df in tablas.items():
        cols = ",\n".join(f"  `{c}` {_tipo_sql(df[c])}" for c in df.columns)
        partes.append(f"CREATE TABLE IF NOT EXISTS {esquema_lakehouse}.{n} (\n{cols}\n) USING DELTA;\n")
    return "\n".join(partes)


CARGA = '''# Celda de notebook de Fabric: carga las tablas del modelo de relacionamiento como Delta.
# Subí la carpeta a Files/ del Lakehouse y ajustá CARPETA.
CARPETA = "Files/mv/relacionamiento_modelo"
TABLAS = {tablas}
for t in TABLAS:
    df = {lector}
    # Primera carga: overwrite. Las siguientes, con claves estables, pueden ser MERGE por la clave de cada tabla.
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(t)
'''


def escribir(carpeta: str | Path, tablas: dict[str, pd.DataFrame], formato: str = "parquet") -> dict[str, Path]:
    if formato not in FORMATOS:
        raise ValueError(f"formato «{formato}» desconocido: usá {' o '.join(FORMATOS)}.")
    if not tablas:
        raise ValueError("No hay tablas para el modelo: pasá al menos contactos o datos públicos.")
    ruta = Path(carpeta).expanduser()
    ruta.mkdir(parents=True, exist_ok=True)
    salida = {n: _escribir(df, ruta, n, formato) for n, df in tablas.items()}
    (ruta / "modelo.json").write_text(json.dumps(esquema(tablas), ensure_ascii=False, indent=2), encoding="utf-8")
    (ruta / "crear_tablas.sql").write_text(ddl(tablas), encoding="utf-8")
    lector = ('spark.read.parquet(f"{CARPETA}/{t}.parquet")' if formato == "parquet" else
              'spark.read.option("header", True).option("inferSchema", True).csv(f"{CARPETA}/{t}.csv")')
    (ruta / "cargar_en_lakehouse.py").write_text(CARGA.format(tablas=sorted(tablas), lector=lector),
                                                 encoding="utf-8")
    for extra in ("modelo.json", "crear_tablas.sql", "cargar_en_lakehouse.py"):
        salida[extra] = ruta / extra
    return salida


__all__ = ["RELACIONES", "clave", "construir", "ddl", "dim_fecha", "escribir", "esquema"]
