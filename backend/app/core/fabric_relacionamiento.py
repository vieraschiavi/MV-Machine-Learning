"""Etapa 5: el modelo de relacionamiento conectado a Fabric, con cargas incrementales.

El modelo estrella (``modelo_fabric``) ya sale con claves estables. Esto agrega
lo que hace falta para que viva en Fabric y se actualice sin recargar todo:

* **Carga incremental (Delta MERGE)**: cada tabla tiene una estrategia.

  - *dimension* — MERGE por su clave: lo que cambió se actualiza y lo nuevo se
    agrega (un contacto que pidió la baja queda con la baja, sin duplicarse).
  - *reemplazo* — se reemplaza la porción que trae la carga: los días de
    interacciones o de consentimientos que vienen en el archivo, la foto de
    recomendaciones del día, la población de las zonas que se recargan. Cada
    carga trae los días o zonas **completos** que cubre; así una carga repetida
    no duplica nada y un evento que se repite el mismo día no se pierde.

  ``fusionar`` es la misma lógica en pandas: los tests la prueban y el notebook
  de Spark la repite paso por paso.

* **Modelo semántico en TMDL** (Direct Lake sobre el Lakehouse): tablas,
  columnas, medidas DAX y relaciones, en la carpeta que entiende la integración
  de Fabric con Git (``Relacionamiento.SemanticModel``). ``verificar_tmdl``
  revisa que cada relación y cada medida apunten a algo que existe.

* **Notebook de Fabric** (``.ipynb``): parámetros, carga incremental, control de
  claves huérfanas y OPTIMIZE.

Nada de esto se conecta a Fabric por su cuenta: se genera y lo corre quien
tenga permiso en el workspace.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

ESTRATEGIAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "dim_geografia": ("dimension", ("geo_key",)),
    "dim_area": ("dimension", ("area_key",)),
    "dim_producto": ("dimension", ("producto_key",)),
    "dim_contenido": ("dimension", ("contenido_key",)),
    "dim_contacto": ("dimension", ("contacto_key",)),
    "dim_fecha": ("dimension", ("fecha_key",)),
    "puente_contacto_area": ("reemplazo", ("contacto_key",)),
    "fact_interacciones": ("reemplazo", ("fecha_key",)),
    "fact_consentimientos": ("reemplazo", ("fecha_key",)),
    "fact_recomendaciones": ("reemplazo", ("fecha_key",)),
    "fact_poblacion": ("reemplazo", ("geo_key",)),
    "fact_prevalencia": ("reemplazo", ("geo_key", "area_key")),
    "fact_escucha": ("reemplazo", ("geo_key", "fecha_key")),
    "fact_cobertura": ("reemplazo", ("geo_key", "area_key")),
    "fact_busquedas": ("reemplazo", ("geo_key",)),
}
#: Con las dos activas, de un contenido a su área habría dos caminos (directo y por el producto): Power BI no
#: acepta la ambigüedad. Queda activa la directa; la del producto se usa con USERELATIONSHIP.
INACTIVAS = {("dim_producto", "area_key")}
ESQUEMA = "relacionamiento"
_NS = uuid.UUID("6f1c2a3e-7d4b-4e1a-9c55-3b0e2d8f4a10")


def estrategia(tabla: str) -> tuple[str, tuple[str, ...]]:
    if tabla not in ESTRATEGIAS:
        raise ValueError(f"Tabla «{tabla}» sin estrategia de carga: agregala a ESTRATEGIAS.")
    return ESTRATEGIAS[tabla]


def _orden(tablas: Any) -> list[str]:
    """Dimensiones primero, después el puente y los hechos: así una relación nunca apunta a algo que no se cargó."""
    return sorted(tablas, key=lambda t: (0 if t.startswith("dim_") else 1 if t.startswith("puente_") else 2, t))


def _claves_de(df: pd.DataFrame, claves: tuple[str, ...]) -> pd.Series:
    """Una tupla por fila con las claves, donde un nulo es igual a otro nulo (como `<=>` en Spark)."""
    faltan = [k for k in claves if k not in df.columns]
    if faltan:
        raise ValueError(f"Faltan las claves {', '.join(faltan)}.")
    return pd.Series(list(zip(*[df[k].astype(object).where(df[k].notna(), None) for k in claves], strict=True)),
                     index=df.index, dtype=object) if len(df) else pd.Series([], dtype=object)


def fusionar(actual: pd.DataFrame | None, nuevo: pd.DataFrame, tabla: str) -> pd.DataFrame:
    """Lo que queda en la tabla Delta después de cargar `nuevo` encima de `actual` (la misma lógica que el MERGE)."""
    modo, claves = estrategia(tabla)
    if actual is None:
        return nuevo.reset_index(drop=True)
    k_nuevo = _claves_de(nuevo, claves)
    if modo == "dimension":
        nuevo = nuevo[~k_nuevo.duplicated(keep="last")]
        k_nuevo = _claves_de(nuevo, claves)
    queda = actual[~_claves_de(actual, claves).isin(set(k_nuevo))]
    columnas = list(dict.fromkeys([*actual.columns, *nuevo.columns]))       # columnas nuevas: se agregan
    partes = [p.reindex(columns=columnas) for p in (queda, nuevo) if len(p)]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=columnas)


# ── modelo semántico (TMDL) ─────────────────────────────────────────────────
def _guid(*partes: str) -> str:
    return str(uuid.uuid5(_NS, "|".join(partes)))


def tipo_tmdl(serie: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(serie):
        return "boolean"
    if pd.api.types.is_integer_dtype(serie):
        return "int64"
    if pd.api.types.is_float_dtype(serie):
        return "double"
    if pd.api.types.is_datetime64_any_dtype(serie):
        return "dateTime"
    return "string"


def _nombre(n: str) -> str:
    return n if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n) else "'" + n.replace("'", "''") + "'"


def _conteo(tabla: str, filtro: str) -> str:
    return f"CALCULATE(COUNTROWS({tabla}), {filtro})"


def medidas(tablas: dict[str, pd.DataFrame]) -> dict[str, list[tuple[str, str, str]]]:
    """Las medidas DAX de cada tabla (nombre, expresión, formato), sólo con las columnas que existen."""
    m: dict[str, list[tuple[str, str, str]]] = {}
    entero, pct = "#,0", "0.0%"
    cols = {t: set(df.columns) for t, df in tablas.items()}
    if "dim_contacto" in tablas:
        c = cols["dim_contacto"]
        m["dim_contacto"] = [("Contactos", "COUNTROWS(dim_contacto)", entero)]
        if {"consiente_contacto", "baja"} <= c:
            m["dim_contacto"] += [
                ("Contactables", "CALCULATE([Contactos], dim_contacto[consiente_contacto] = TRUE(), "
                                 "dim_contacto[baja] = FALSE())", entero),
                ("% contactables", "DIVIDE([Contactables], [Contactos])", pct)]
        for col, nombre in (("consiente_marketing", "Con permiso de marketing"),
                            ("consiente_salud", "Con permiso de salud"), ("doble_optin", "Con doble opt-in")):
            if col in c:
                m["dim_contacto"].append((nombre, f"CALCULATE([Contactos], dim_contacto[{col}] = TRUE())", entero))
    if "fact_interacciones" in tablas:
        f = "fact_interacciones"
        eventos = [("Envíos", "envio"), ("Aperturas", "apertura"), ("Clics", "clic"), ("Inscripciones", "inscripcion"),
                   ("Canjes", "canje"), ("Bajas", "baja"), ("Quejas", "queja")]
        m[f] = [("Interacciones", f"COUNTROWS({f})", entero)]
        m[f] += [(n, _conteo(f, f'{f}[evento] = "{e}"'), entero) for n, e in eventos]
        m[f] += [("Conversiones", "[Inscripciones] + [Canjes]", entero),
                 ("Contactos alcanzados", f'CALCULATE(DISTINCTCOUNT({f}[contacto_key]), {f}[evento] = "envio")', entero),
                 ("Tasa de apertura", "DIVIDE([Aperturas], [Envíos])", pct),
                 ("Tasa de clic", "DIVIDE([Clics], [Envíos])", pct),
                 ("Tasa de conversión", "DIVIDE([Conversiones], [Envíos])", pct),
                 ("Tasa de baja", "DIVIDE([Bajas], [Envíos])", pct)]
    if "fact_recomendaciones" in tablas:
        f = "fact_recomendaciones"
        m[f] = [("Recomendaciones", f"COUNTROWS({f})", entero),
                ("Contactos con recomendación", f"DISTINCTCOUNT({f}[contacto_key])", entero)]
        if "personalizado" in cols[f]:
            m[f].append(("% personalizadas", f"DIVIDE({_conteo(f, f'{f}[personalizado] = TRUE()')}, "
                                             "[Recomendaciones])", pct))
    if "fact_consentimientos" in tablas:
        f = "fact_consentimientos"
        m[f] = [(n, _conteo(f, f'{f}[accion] = "{a}"'), entero)
                for n, a in (("Consentimientos otorgados", "otorga"), ("Consentimientos retirados", "retira"),
                             ("Bajas registradas", "baja"))]
    if "fact_poblacion" in tablas:
        m["fact_poblacion"] = [("Población", "SUM(fact_poblacion[poblacion])", entero)]
    if "fact_prevalencia" in tablas:
        m["fact_prevalencia"] = [("Prevalencia promedio", "AVERAGE(fact_prevalencia[prevalencia])", pct)]
    if "fact_cobertura" in tablas:
        f, c = "fact_cobertura", cols["fact_cobertura"]
        m[f] = [(n, f"SUM({f}[{col}])", entero) for col, n in
                (("casos_estimados", "Casos estimados"), ("captados_area", "Captados del área"), ("brecha", "Brecha"))
                if col in c]
        if {"casos_estimados", "captados_area"} <= c:
            m[f].append(("Penetración", "DIVIDE([Captados del área], [Casos estimados])", pct))
    if "fact_escucha" in tablas:
        f = "fact_escucha"
        m[f] = [("Menciones", f"SUM({f}[menciones])", entero),
                ("Sentimiento neto", f"DIVIDE(SUM({f}[positivas]) - SUM({f}[negativas]), [Menciones])", pct)]
    if "fact_busquedas" in tablas:
        m["fact_busquedas"] = [("Interés de búsqueda", "AVERAGE(fact_busquedas[interes])", "0.0")]
    return {t: v for t, v in m.items() if v}


def _tabla_tmdl(nombre: str, df: pd.DataFrame, med: list[tuple[str, str, str]], esquema: str) -> str:
    lineas = [f"table {nombre}", f"\tlineageTag: {_guid('tabla', nombre)}", ""]
    for n, expr, fmt in med:
        lineas += [f"\tmeasure {_nombre(n)} = {expr}", f"\t\tformatString: {fmt}",
                   f"\t\tlineageTag: {_guid('medida', nombre, n)}", ""]
    es_hecho = not nombre.startswith("dim_")
    for col in df.columns:
        tipo = tipo_tmdl(df[col])
        clave = col.endswith("_key")
        resumen = "sum" if tipo in ("int64", "double") and not clave and col not in ("anio", "mes", "semana_iso",
                                                                                      "rango") else "none"
        lineas += [f"\tcolumn {_nombre(col)}", f"\t\tdataType: {tipo}"]
        if clave and es_hecho:
            lineas.append("\t\tisHidden")
        if tipo == "dateTime":
            lineas.append("\t\tformatString: yyyy-mm-dd")
        lineas += [f"\t\tlineageTag: {_guid('columna', nombre, col)}", f"\t\tsummarizeBy: {resumen}",
                   f"\t\tsourceColumn: {col}", ""]
    lineas += [f"\tpartition {nombre} = entity", "\t\tmode: directLake", "\t\tsource",
               f"\t\t\tentityName: {nombre}", f"\t\t\tschemaName: {esquema or 'dbo'}",
               "\t\t\texpressionSource: DatabaseQuery", ""]
    return "\n".join(lineas)


def tmdl(tablas: dict[str, pd.DataFrame], *, servidor: str = "SERVIDOR_SQL_DEL_LAKEHOUSE",
         lakehouse: str = "NOMBRE_DEL_LAKEHOUSE", esquema: str = ESQUEMA,
         nombre: str = "Relacionamiento") -> dict[str, str]:
    """Los archivos del modelo semántico, por ruta relativa a la carpeta ``<nombre>.SemanticModel``."""
    from .modelo_fabric import RELACIONES

    if not tablas:
        raise ValueError("No hay tablas para el modelo semántico.")
    med = medidas(tablas)
    orden = _orden(tablas)
    archivos = {
        ".platform": json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/"
                       "2.0.0/schema.json",
            "metadata": {"type": "SemanticModel", "displayName": nombre},
            "config": {"version": "2.0", "logicalId": _guid("modelo", nombre)}}, indent=2),
        "definition.pbism": json.dumps({"version": "4.0", "settings": {}}, indent=2),
        "definition/database.tmdl": "database\n\tcompatibilityLevel: 1604\n",
        "definition/model.tmdl": "\n".join(
            ["model Model", "\tculture: es-AR", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: es-AR", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull",
             "", *[f"ref table {t}" for t in orden], ""]),
        "definition/expressions.tmdl": "\n".join(
            ["expression DatabaseQuery =", "\t\tlet", f'\t\t    database = Sql.Database("{servidor}", "{lakehouse}")',
             "\t\tin", "\t\t    database", f"\tlineageTag: {_guid('expresion', 'DatabaseQuery')}", "",
             "\tannotation PBI_IncludeFutureArtifacts = False", ""]),
    }
    rel = []
    for a, b, c, d in RELACIONES:
        if a in tablas and c in tablas and b in tablas[a].columns and d in tablas[c].columns:
            rel += [f"relationship {_guid('relacion', a, b, c, d)}"]
            if (a, b) in INACTIVAS:
                rel.append("\tisActive: false")
            rel += [f"\tfromColumn: {a}.{b}", f"\ttoColumn: {c}.{d}", ""]
    archivos["definition/relationships.tmdl"] = "\n".join(rel)
    for t in orden:
        archivos[f"definition/tables/{t}.tmdl"] = _tabla_tmdl(t, tablas[t], med.get(t, []), esquema)
    return archivos


def verificar_tmdl(archivos: dict[str, str]) -> list[str]:
    """Los problemas del modelo: relaciones a columnas que no existen, medidas que citan algo inexistente,
    tablas sin partición o declaradas sin archivo. Vacío = listo para abrir."""
    problemas: list[str] = []
    columnas: dict[str, set[str]] = {}
    nombres_medidas: set[str] = set()
    expresiones: list[tuple[str, str, str]] = []
    for ruta, texto in archivos.items():
        if not ruta.startswith("definition/tables/"):
            continue
        tabla = re.search(r"^table (\S+)", texto, re.M)
        if not tabla:
            problemas.append(f"{ruta}: no declara la tabla.")
            continue
        t = tabla.group(1)
        columnas[t] = set(re.findall(r"^\tcolumn (\S+)", texto, re.M))
        for n, expr in re.findall(r"^\tmeasure ('(?:[^']|'')+'|\S+) = (.+)$", texto, re.M):
            n = n.strip("'").replace("''", "'")
            nombres_medidas.add(n)
            expresiones.append((t, n, expr))
        if "\tpartition " not in texto:
            problemas.append(f"{t}: sin partición (no lee nada del Lakehouse).")
    for t in re.findall(r"^ref table (\S+)", archivos.get("definition/model.tmdl", ""), re.M):
        if t not in columnas:
            problemas.append(f"model.tmdl referencia la tabla {t}, que no tiene archivo.")
    for lado, t, c in re.findall(r"^\t(fromColumn|toColumn): (\w+)\.(\w+)$",
                                 archivos.get("definition/relationships.tmdl", ""), re.M):
        if c not in columnas.get(t, set()):
            problemas.append(f"Relación ({lado}) a {t}.{c}, que no existe.")
    for t, n, expr in expresiones:
        for tt, cc in re.findall(r"(\w+)\[([^\]]+)\]", expr):
            if cc not in columnas.get(tt, set()):
                problemas.append(f"Medida «{n}» ({t}) usa {tt}[{cc}], que no existe.")
        for ref in re.findall(r"(?<![\w\]])\[([^\]]+)\]", expr):
            if ref not in nombres_medidas:
                problemas.append(f"Medida «{n}» ({t}) usa la medida [{ref}], que no existe.")
    return problemas


# ── carga incremental en Spark ──────────────────────────────────────────────
CODIGO_MERGE = '''# MV AutoML Studio · carga incremental del modelo de relacionamiento en un Lakehouse de Fabric.
# Dimensiones: MERGE por su clave (actualiza y agrega). Hechos y puente: se reemplaza la porción que trae
# la carga (los días, zonas o contactos del archivo). Repetir la misma carga no duplica nada.
from delta.tables import DeltaTable
from pyspark.sql import functions as F

CARPETA = "{carpeta}"
ESQUEMA = "{esquema}"          # "" si el Lakehouse no tiene esquemas habilitados
FORMATO = "{formato}"
TABLAS = {tablas}
RELACIONES = {relaciones}

spark.conf.set("spark.databricks.delta.schema.autoMerge.enabled", "true")   # columnas nuevas: se agregan
if ESQUEMA:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {{ESQUEMA}}")


def nombre(t):
    return f"{{ESQUEMA}}.{{t}}" if ESQUEMA else t


def leer(t):
    ruta = f"{{CARPETA}}/{{t}}.{{FORMATO}}"
    if FORMATO == "parquet":
        return spark.read.parquet(ruta)
    return spark.read.option("header", True).option("inferSchema", True).csv(ruta)


def cargar(t, estrategia, claves):
    df, destino = leer(t), nombre(t)
    if not spark.catalog.tableExists(destino):
        df.write.format("delta").saveAsTable(destino)
        return "creada", df.count()
    delta = DeltaTable.forName(spark, destino)
    cond = " AND ".join(f"t.`{{k}}` <=> s.`{{k}}`" for k in claves)       # <=>: un nulo es igual a otro nulo
    if estrategia == "dimension":
        fuente = df.dropDuplicates(list(claves))
        delta.alias("t").merge(fuente.alias("s"), cond).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
        return "actualizada", fuente.count()
    porciones = df.select(*claves).distinct()
    delta.alias("t").merge(porciones.alias("s"), cond).whenMatchedDelete().execute()
    df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(destino)
    return "reemplazada", df.count()


resumen = []
for t, (estrategia, claves) in TABLAS.items():
    accion, filas = cargar(t, estrategia, claves)
    resumen.append((t, accion, filas))
    print(f"{{t:<24}} {{accion:<12}} {{filas:>10,}} filas")


def huerfanas():
    """Claves de un hecho que no están en su dimensión: el modelo semántico las mostraría en blanco."""
    malas = []
    for desde, col, hacia, col2 in RELACIONES:
        a, b = spark.table(nombre(desde)).alias("a"), spark.table(nombre(hacia)).alias("b")
        n = (a.where(F.col(f"a.{{col}}").isNotNull())
              .join(b, F.col(f"a.{{col}}") == F.col(f"b.{{col2}}"), "left_anti").count())
        if n:
            malas.append((desde, col, hacia, n))
            print(f"⚠ {{desde}}[{{col}}] → {{hacia}}: {{n:,}} claves sin dimensión")
    return malas
'''

CODIGO_CONTROL = '''malas = huerfanas()
print("Sin claves huérfanas." if not malas else f"{len(malas)} relación(es) con claves huérfanas: revisá la carga.")
'''

CODIGO_OPTIMIZE = '''for t in TABLAS:
    spark.sql(f"OPTIMIZE {nombre(t)}")
print("Tablas compactadas. Refrescá el modelo semántico (Direct Lake toma los datos nuevos solo).")
'''


def codigo_merge(tablas: dict[str, pd.DataFrame], *, carpeta: str = "Files/mv/relacionamiento_modelo",
                 esquema: str = ESQUEMA, formato: str = "parquet") -> str:
    from .modelo_fabric import RELACIONES

    orden = _orden(tablas)
    tab = "{\n" + "".join(f"    {t!r}: ({estrategia(t)[0]!r}, {estrategia(t)[1]!r}),\n" for t in orden) + "}"
    rel = [r for r in RELACIONES if r[0] in tablas and r[2] in tablas and r[1] in tablas[r[0]].columns]
    relaciones = "[\n" + "".join(f"    {r!r},\n" for r in rel) + "]"
    return CODIGO_MERGE.format(carpeta=carpeta, esquema=esquema, formato=formato, tablas=tab, relaciones=relaciones)


def _celda(tipo: str, texto: str, etiquetas: list[str] | None = None) -> dict[str, Any]:
    fuente = texto.splitlines(keepends=True)
    if tipo == "markdown":
        return {"cell_type": "markdown", "metadata": {}, "source": fuente}
    return {"cell_type": "code", "execution_count": None, "outputs": [],
            "metadata": {"tags": etiquetas} if etiquetas else {}, "source": fuente}


def notebook(tablas: dict[str, pd.DataFrame], *, carpeta: str = "Files/mv/relacionamiento_modelo",
             esquema: str = ESQUEMA, formato: str = "parquet") -> dict[str, Any]:
    """El notebook de Fabric de punta a punta: parámetros, carga incremental, control y OPTIMIZE."""
    codigo = codigo_merge(tablas, carpeta=carpeta, esquema=esquema, formato=formato)
    parametros, _, resto = codigo.partition('TABLAS = ')
    cabecera, _, params = parametros.partition("CARPETA = ")
    celdas = [
        _celda("markdown", "# Relacionamiento · carga incremental en el Lakehouse\n\n"
               "1. Subí la carpeta `modelo_fabric` a **Files/** del Lakehouse (o ajustá `CARPETA`).\n"
               "2. Corré todo. La primera vez crea las tablas Delta; las siguientes hacen MERGE.\n"
               "3. El modelo semántico (`Relacionamiento.SemanticModel`, Direct Lake) toma los datos nuevos solo.\n\n"
               "Ninguna tabla tiene mail, teléfono ni nombre: el contacto es un id seudónimo y lo demás vive en "
               "el CRM."),
        _celda("code", "CARPETA = " + params.rstrip() + "\n", ["parameters"]),
        _celda("code", cabecera + "TABLAS = " + resto),
        _celda("code", CODIGO_CONTROL),
        _celda("code", CODIGO_OPTIMIZE),
    ]
    return {"cells": celdas, "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
                         "language_info": {"name": "python"}}}


def escribir(carpeta: str | Path, tablas: dict[str, pd.DataFrame], *, formato: str = "parquet",
             esquema: str = ESQUEMA, nombre: str = "Relacionamiento") -> dict[str, Path]:
    """Deja al lado de las tablas el MERGE, el notebook y el modelo semántico."""
    ruta = Path(carpeta)
    salida: dict[str, Path] = {}
    (ruta / "merge_incremental.py").write_text(codigo_merge(tablas, esquema=esquema, formato=formato) + "\n"
                                               + CODIGO_CONTROL, encoding="utf-8")
    salida["merge_incremental.py"] = ruta / "merge_incremental.py"
    nb = ruta / "notebook_relacionamiento.ipynb"
    nb.write_text(json.dumps(notebook(tablas, esquema=esquema, formato=formato), ensure_ascii=False, indent=1),
                  encoding="utf-8")
    salida[nb.name] = nb
    archivos = tmdl(tablas, esquema=esquema, nombre=nombre)
    problemas = verificar_tmdl(archivos)
    if problemas:
        raise ValueError("El modelo semántico no cierra: " + " ".join(problemas[:5]))
    for rel, texto in archivos.items():
        destino = ruta / f"{nombre}.SemanticModel" / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        salida[f"{nombre}.SemanticModel/{rel}"] = destino
    return salida


__all__ = ["ESQUEMA", "ESTRATEGIAS", "INACTIVAS", "codigo_merge", "escribir", "estrategia", "fusionar", "medidas",
           "notebook", "tipo_tmdl", "tmdl", "verificar_tmdl"]
