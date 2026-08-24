"""Ingeniería de datos: claves, tiempo, relaciones entre tablas y contrato.

Lo que el perfilado ya contesta —cuántos nulos tiene cada columna, cómo se
distribuye, qué calidad tiene— responde preguntas de *análisis*. Este módulo
responde las de *ingeniería*, que son otras y llegan antes:

    ¿cuál es la clave de esta tabla?
    ¿me faltan días?  ¿está fresca?  ¿hay fechas futuras?
    ¿cómo cruzo esta tabla con la otra sin inflar filas?
    ¿cómo la creo en mi servidor y cómo verifico mañana que sigue bien?

Todo se calcula en DuckDB sobre el Parquet, igual que el resto de la
plataforma: no se trae el dataset a memoria, así que funciona con lo que entre
en disco y da lo mismo si los datos vinieron de un Excel o de una consulta a
SQL Server.

No hay un nivel de licencia propio a propósito: esto no es un producto aparte,
es parte del programa. Se aplican los topes del nivel que ya tenga el usuario.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from . import profiling
from . import storage as S

# Cruzar todos los pares de columnas de todas las tablas es cuadrático. Estos
# topes mantienen la respuesta en segundos sobre datasets grandes; están
# expuestos como parámetros para poder subirlos desde una llamada puntual.
MAX_PARES_PK = 8          # columnas candidatas a probar de a pares
MAX_TABLAS_JOIN = 8
MAX_VALORES_SOLAPE = 200_000

DIALECTOS = {
    "sqlserver": {
        "label": "Microsoft SQL Server",
        "entero": "BIGINT", "decimal": "DECIMAL(18,4)", "fecha": "DATETIME2",
        "booleano": "BIT", "texto": "NVARCHAR({n})", "texto_max": "NVARCHAR(MAX)",
        "cita": '[{}]',
    },
    "postgresql": {
        "label": "PostgreSQL",
        "entero": "BIGINT", "decimal": "NUMERIC(18,4)", "fecha": "TIMESTAMP",
        "booleano": "BOOLEAN", "texto": "VARCHAR({n})", "texto_max": "TEXT",
        "cita": '"{}"',
    },
    "mysql": {
        "label": "MySQL / MariaDB",
        "entero": "BIGINT", "decimal": "DECIMAL(18,4)", "fecha": "DATETIME",
        "booleano": "TINYINT(1)", "texto": "VARCHAR({n})", "texto_max": "TEXT",
        "cita": '`{}`',
    },
    "duckdb": {
        "label": "DuckDB",
        "entero": "BIGINT", "decimal": "DECIMAL(18,4)", "fecha": "TIMESTAMP",
        "booleano": "BOOLEAN", "texto": "VARCHAR", "texto_max": "VARCHAR",
        "cita": '"{}"',
    },
}


def _q(name: str) -> str:
    """Identificador citado para DuckDB."""
    return '"' + str(name).replace('"', '""') + '"'


def _limpio(nombre: str, tope: int = 60) -> str:
    """Nombre utilizable como identificador en cualquier motor.

    Los acentos se translitera, no se borran: tirándolos, `Año` queda como
    `A_o`, que no lo reconoce nadie. Pasándolo por su letra base queda `Ano`,
    que se lee.
    """
    base = unicodedata.normalize("NFKD", str(nombre))
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    base = base.replace("ñ", "n").replace("Ñ", "N")
    s = re.sub(r"[^0-9A-Za-z_]+", "_", base).strip("_") or "col"
    if s[0].isdigit():
        s = "c_" + s
    return s[:tope]


# ─────────────────────────────────────────────────────────────────────────────
# Claves
# ─────────────────────────────────────────────────────────────────────────────
def claves(ds_id: str, perfil: dict[str, Any] | None = None,
           max_pares: int = MAX_PARES_PK) -> dict[str, Any]:
    """Qué identifica a una fila: clave simple, compuesta, y qué apunta afuera.

    Sin clave no se puede deduplicar, ni cruzar con otra tabla sin inflar
    filas, ni saber si una carga incremental pisó algo. Es la primera pregunta
    de cualquier modelo de datos y la plataforma no la contestaba.
    """
    prof = perfil or profiling.profile(ds_id)
    filas = int(prof.get("rows") or 0)
    cols = prof.get("columns", [])

    # Se pregunta por todas las numéricas, no sólo por las que no repiten: una
    # foránea (`IdCliente`) y una mitad de clave compuesta (`Periodo`) repiten
    # muchísimo, y si no se supiera que son enteras quedarían descartadas junto
    # con los importes. Es una sola consulta con una pasada por el Parquet,
    # tenga el dataset tres columnas numéricas o trescientas.
    posibles = [c["name"] for c in cols
                if c.get("kind") == "numeric" and not c.get("constant")]
    enteras = _columnas_enteras(ds_id, posibles)

    simples, casi, constantes, foraneas = [], [], [], []
    for c in cols:
        if c.get("constant"):
            constantes.append(c["name"])
            continue
        if not _sirve_de_clave(c, enteras):
            continue
        if filas > 1 and c.get("unique_key"):
            simples.append({"columna": c["name"], "confianza": "alta",
                            "por_que": "sin nulos y sin repetidos"})
        elif filas > 50 and (c.get("distinct_pct") or 0) >= 98 and (c.get("null_pct") or 0) < 1:
            casi.append({"columna": c["name"], "confianza": "media",
                         "por_que": f"{c['distinct_pct']:.1f}% de valores distintos, "
                                    "pero hay repetidos"})
        # Candidata a foránea: identificador con pocos valores para la cantidad
        # de filas. Es lo que suele apuntar a la tabla de al lado.
        parece_id = bool(_PALABRAS_ID & _palabras(c["name"]))
        if parece_id and not c.get("unique_key") and 1 < (c.get("distinct") or 0) < filas * 0.9:
            foraneas.append({"columna": c["name"], "distintos": c.get("distinct")})

    compuestas = []
    if not simples and filas > 1:
        compuestas = _pk_compuesta(ds_id, cols, filas, max_pares, enteras)

    return {
        "dataset_id": ds_id,
        "tabla": prof.get("name"),
        "filas": filas,
        "pk_simple": simples,
        "pk_candidata": casi,
        "pk_compuesta": compuestas,
        "constantes": constantes,
        "fk_candidatas": foraneas[:12],
        "duplicados_exactos": int(prof.get("duplicate_row_groups") or 0),
        "sin_clave": not simples and not compuestas,
    }


_PALABRAS_ID = {"id", "ids", "cod", "codigo", "nro", "num", "numero", "key",
                "clave", "identificador"}


def _palabras(nombre: str) -> set[str]:
    """Las palabras de un nombre de columna, venga como venga escrito.

    `IdCliente`, `id_cliente` y `CLIENTE_ID` son la misma columna con tres
    convenciones distintas, y buscar la palabra suelta con un `_` alrededor
    sólo encuentra la segunda. El corte es por separador y por el cambio de
    minúscula a mayúscula, que es donde termina una palabra en camelCase.
    """
    partes = re.split(r"[^0-9A-Za-z]+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
                      str(nombre))
    return {p.lower() for p in partes if p}


def _sirve_de_clave(col: dict[str, Any], enteras: set[str]) -> bool:
    """Si una columna puede ser clave, más allá de que hoy no repita.

    Que no repita es necesario pero no alcanza. Un importe con decimales sobre
    tres mil filas no repite casi nunca, y proponerlo como clave primaria es
    ruido: nadie identifica una fila por lo que sale. Lo mismo un texto libre,
    que no repite porque cada uno escribió algo distinto.

    El tipo declarado no sirve para distinguirlos: la ingesta guarda todo lo
    numérico como `double`, así que un identificador entero y un importe con
    decimales llegan acá con el mismo tipo. Lo que los separa es si los valores
    son enteros, y eso se mide sobre los datos (`enteras`).
    """
    if col.get("is_text"):
        return False
    if col.get("kind") == "numeric":
        return col["name"] in enteras
    return col.get("kind") in ("categorical", "datetime", "boolean")


def _columnas_enteras(ds_id: str, nombres: list[str]) -> set[str]:
    """Cuáles de esas columnas numéricas tienen sólo valores enteros.

    Una sola consulta para todas: preguntar de a una multiplicaría las lecturas
    del Parquet sin necesidad.
    """
    if not nombres:
        return set()
    con = S.connect()
    t = S.glob_expr(ds_id)
    try:
        piezas = ", ".join(
            f"sum(CASE WHEN {_q(n)} IS NOT NULL AND {_q(n)} <> floor({_q(n)}) "
            f"THEN 1 ELSE 0 END) AS c{i}" for i, n in enumerate(nombres))
        fila = con.execute(f"SELECT {piezas} FROM {t}").fetchone()
    except Exception:
        return set()
    finally:
        con.close()
    return {n for n, con_decimales in zip(nombres, fila, strict=False)
            if not int(con_decimales or 0)}



def _pk_compuesta(ds_id: str, cols: list[dict], filas: int, max_pares: int,
                  enteras: set[str]) -> list[dict]:
    """Busca un par de columnas que juntas no repitan.

    Se prueban pares y no combinaciones de tres o más: el costo crece rápido y
    en la práctica la enorme mayoría de las claves compuestas reales son de dos
    columnas (entidad + fecha, entidad + secuencia).
    """
    candidatas = [
        c["name"] for c in cols
        if not c.get("constant") and _sirve_de_clave(c, enteras)
        and 1 < (c.get("distinct") or 0) < filas
    ][:max_pares]
    if len(candidatas) < 2:
        return []

    con = S.connect()
    t = S.glob_expr(ds_id)
    encontradas = []
    try:
        for i in range(len(candidatas)):
            for j in range(i + 1, len(candidatas)):
                a, b = candidatas[i], candidatas[j]
                try:
                    n = con.execute(
                        f"SELECT count(*) FROM (SELECT {_q(a)}, {_q(b)} FROM {t} "
                        f"GROUP BY 1,2 HAVING count(*) > 1)"
                    ).fetchone()[0]
                except Exception:
                    continue
                if int(n) == 0:
                    encontradas.append({
                        "columnas": [a, b], "confianza": "media",
                        "por_que": "juntas no repiten en ninguna fila",
                    })
                    return encontradas          # con una alcanza para proponer
    finally:
        con.close()
    return encontradas


# ─────────────────────────────────────────────────────────────────────────────
# Tiempo
# ─────────────────────────────────────────────────────────────────────────────
def tiempo(ds_id: str, columna: str | None = None,
           perfil: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Cobertura, huecos, frescura y tendencia de la columna de fecha.

    Un dataset con tres meses sin datos, o con la última carga de hace medio
    año, produce modelos y tableros que parecen sanos y no lo están. Esto lo
    dice antes de entrenar nada.
    """
    prof = perfil or profiling.profile(ds_id)
    fechas = [c["name"] for c in prof.get("columns", []) if c.get("kind") == "datetime"]
    col = columna if (columna and columna in fechas) else (fechas[0] if fechas else None)
    if not col:
        return None

    con = S.connect()
    t, q = S.glob_expr(ds_id), _q(col)
    try:
        base = con.execute(f"""
            SELECT min({q}), max({q}), count({q}),
                   count(DISTINCT CAST({q} AS DATE)),
                   sum(CASE WHEN {q} > now() THEN 1 ELSE 0 END)
            FROM {t} WHERE {q} IS NOT NULL
        """).fetchone()
        if not base or base[0] is None:
            return None
        desde, hasta, con_valor, dias_con_datos, futuras = base
        dias_rango = (hasta.date() - desde.date()).days + 1

        mensual = con.execute(f"""
            SELECT strftime(date_trunc('month', {q}), '%Y-%m') AS mes, count(*) AS n
            FROM {t} WHERE {q} IS NOT NULL GROUP BY 1 ORDER BY 1
        """).fetchall()

        # La granularidad se mide, no se supone. Un panel mensual tiene una
        # fila por mes: contarle «días faltantes» diría que le falta el 97% de
        # los datos cuando no le falta ninguno. Esa clase de falsa alarma es la
        # que hace que nadie vuelva a mirar el informe.
        distintos = con.execute(f"""
            SELECT count(DISTINCT CAST({q} AS DATE)),
                   count(DISTINCT date_trunc('week', {q})),
                   count(DISTINCT date_trunc('month', {q}))
            FROM {t} WHERE {q} IS NOT NULL
        """).fetchone()
        n_dias, n_semanas, n_meses = (int(x or 0) for x in distintos)
        if n_dias <= n_meses * 1.2:
            grano, paso, trunc = "mensual", "INTERVAL 1 MONTH", "month"
        elif n_dias <= n_semanas * 1.2:
            grano, paso, trunc = "semanal", "INTERVAL 1 WEEK", "week"
        else:
            grano, paso, trunc = "diario", "INTERVAL 1 DAY", "day"

        huecos = con.execute(f"""
            WITH calendario AS (
                SELECT unnest(generate_series(
                    date_trunc('{trunc}', CAST(? AS TIMESTAMP)),
                    date_trunc('{trunc}', CAST(? AS TIMESTAMP)), {paso})) AS d
            ), presentes AS (
                SELECT DISTINCT date_trunc('{trunc}', {q}) AS d
                FROM {t} WHERE {q} IS NOT NULL
            )
            SELECT d FROM calendario
            WHERE d NOT IN (SELECT d FROM presentes) ORDER BY d
        """, [desde, hasta]).fetchall()
        periodos_rango = con.execute(f"""
            SELECT count(*) FROM (SELECT unnest(generate_series(
                date_trunc('{trunc}', CAST(? AS TIMESTAMP)),
                date_trunc('{trunc}', CAST(? AS TIMESTAMP)), {paso})))
        """, [desde, hasta]).fetchone()[0]
        periodos_con_datos = {"mensual": n_meses, "semanal": n_semanas, "diario": n_dias}[grano]

        semana = con.execute(f"""
            SELECT dayofweek({q}) AS dow, count(*) AS n
            FROM {t} WHERE {q} IS NOT NULL GROUP BY 1 ORDER BY 1
        """).fetchall()
    finally:
        con.close()

    serie = [{"mes": m, "filas": int(n)} for m, n in mensual]
    total = sum(s["filas"] for s in serie) or 1
    nombres = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    ahora = datetime.now(UTC).replace(tzinfo=None)

    unidad = {"mensual": "meses", "semanal": "semanas", "diario": "días"}[grano]
    return {
        "columna": col,
        "granularidad": grano,
        "unidad": unidad,
        "desde": str(desde), "hasta": str(hasta),
        "dias_rango": int(dias_rango),
        "periodos_rango": int(periodos_rango or 0),
        "periodos_con_datos": int(periodos_con_datos),
        "periodos_faltantes": len(huecos),
        "cobertura_pct": (round(periodos_con_datos / int(periodos_rango) * 100, 1)
                          if periodos_rango else 0.0),
        "huecos": [str(d[0])[:10] for d in huecos[:24]],
        "frescura_dias": max(0, (ahora.date() - hasta.date()).days),
        "fechas_futuras": int(futuras or 0),
        "serie_mensual": serie[-36:],
        "tendencia": _tendencia([s["filas"] for s in serie]),
        "por_dia_semana": [
            {"dia": nombres[int(d) % 7], "pct": round(int(n) / total * 100, 1)}
            for d, n in semana
        ],
    }


def _tendencia(valores: list[int]) -> str | None:
    """Pendiente de una recta por mínimos cuadrados, sin traer numpy.

    Se compara contra el promedio y no contra cero: una pendiente de +3 filas
    por mes es ruido si el promedio son 50.000 filas, y es un cambio enorme si
    son 20.
    """
    n = len(valores)
    if n < 4:
        return None
    media_x = (n - 1) / 2
    media_y = sum(valores) / n
    den = sum((i - media_x) ** 2 for i in range(n))
    if den == 0 or media_y == 0:
        return None
    pendiente = sum((i - media_x) * (v - media_y) for i, v in enumerate(valores)) / den
    umbral = abs(media_y) * 0.02
    return "creciente" if pendiente > umbral else ("decreciente" if pendiente < -umbral else "estable")


# ─────────────────────────────────────────────────────────────────────────────
# Relaciones entre tablas
# ─────────────────────────────────────────────────────────────────────────────
def joins(ds_ids: list[str] | None = None, min_solape: float = 20.0,
          max_tablas: int = MAX_TABLAS_JOIN) -> dict[str, Any]:
    """Cómo se cruzan entre sí los datasets cargados.

    No alcanza con que dos tablas tengan una columna con el mismo nombre: eso
    empareja `id` con `id` y no significa nada. Se mide el **solapamiento real
    de valores** y se calcula la cardinalidad, porque un cruce N:N multiplica
    filas en silencio y es la forma más común de arruinar un número sin que
    salte ningún error.
    """
    disponibles = [d["id"] for d in S.list_datasets()]
    elegidos = [i for i in (ds_ids or disponibles) if i in disponibles][:max_tablas]
    if len(elegidos) < 2:
        return {"datasets": elegidos, "sugerencias": [],
                "nota": "Hacen falta al menos dos datasets cargados para buscar cruces."}

    metas = {i: S.load_meta(i) for i in elegidos}
    sugerencias = []
    con = S.connect()
    try:
        for a, b in [(x, y) for n, x in enumerate(elegidos) for y in elegidos[n + 1:]]:
            ca = {c["name"] for c in metas[a].columns}
            cb = {c["name"] for c in metas[b].columns}
            for col in sorted(ca & cb):
                s = _solape(con, a, b, col)
                if s is None or s["solape_pct"] < min_solape:
                    continue
                sugerencias.append({
                    "izquierda": metas[a].name, "izquierda_id": a,
                    "derecha": metas[b].name, "derecha_id": b,
                    "columna": col, **s,
                    "sql": (f"SELECT a.*, b.*\n"
                            f"FROM {_limpio(metas[a].name)} a\n"
                            f"LEFT JOIN {_limpio(metas[b].name)} b\n"
                            f"  ON a.{_limpio(col)} = b.{_limpio(col)};"),
                })
    finally:
        con.close()

    sugerencias.sort(key=lambda s: -s["solape_pct"])
    return {"datasets": elegidos, "sugerencias": sugerencias[:25]}


def _solape(con, a: str, b: str, col: str) -> dict[str, Any] | None:
    """Cuánto se pisan los valores de una columna entre dos datasets."""
    ta, tb, q = S.glob_expr(a), S.glob_expr(b), _q(col)
    try:
        r = con.execute(f"""
            WITH va AS (SELECT DISTINCT CAST({q} AS VARCHAR) v FROM {ta}
                        WHERE {q} IS NOT NULL LIMIT {MAX_VALORES_SOLAPE}),
                 vb AS (SELECT DISTINCT CAST({q} AS VARCHAR) v FROM {tb}
                        WHERE {q} IS NOT NULL LIMIT {MAX_VALORES_SOLAPE})
            SELECT (SELECT count(*) FROM va), (SELECT count(*) FROM vb),
                   (SELECT count(*) FROM va JOIN vb USING (v))
        """).fetchone()
    except Exception:
        return None
    na, nb, comunes = int(r[0] or 0), int(r[1] or 0), int(r[2] or 0)
    if not na or not nb:
        return None

    # Único de cada lado: define la cardinalidad y con ella el riesgo.
    def unico(t: str) -> bool:
        try:
            n = con.execute(f"SELECT count(*) FROM (SELECT {q} FROM {t} "
                            f"WHERE {q} IS NOT NULL GROUP BY 1 HAVING count(*)>1)").fetchone()[0]
            return int(n) == 0
        except Exception:
            return False

    ua, ub = unico(ta), unico(tb)
    card = "1:1" if (ua and ub) else ("1:N" if ua else ("N:1" if ub else "N:N"))
    solape = comunes / min(na, nb) * 100
    riesgo = ("alto" if card == "N:N" else ("medio" if solape < 80 else "bajo"))
    aviso = {
        "alto": "N:N — el cruce multiplica filas. Agrupá uno de los dos lados antes de unir.",
        "medio": f"Sólo coincide el {solape:.0f}% de los valores: revisá qué queda afuera.",
        "bajo": "Cruce limpio.",
    }[riesgo]
    return {"solape_pct": round(solape, 1), "valores_izquierda": na,
            "valores_derecha": nb, "valores_comunes": comunes,
            "cardinalidad": card, "riesgo": riesgo, "aviso": aviso}


# ─────────────────────────────────────────────────────────────────────────────
# Contrato: diccionario, DDL y verificaciones
# ─────────────────────────────────────────────────────────────────────────────
def _tipo_sql(col: dict[str, Any], d: dict[str, str], enteras: set[str]) -> str:
    kind = col.get("kind")
    if kind == "datetime":
        return d["fecha"]
    if kind == "boolean":
        return d["booleano"]
    if kind == "numeric":
        # Por el tipo declarado sería todo decimal: la ingesta guarda cualquier
        # número como `double`. Un año y un mes declarados DECIMAL(18,4) en el
        # servidor destino es un error que después nadie corrige.
        return d["entero"] if col["name"] in enteras else d["decimal"]
    largo = int((col.get("stats") or {}).get("max_len") or 0)
    if largo <= 0 or largo > 2000 or col.get("is_text"):
        return d["texto_max"]
    # Se deja aire: el máximo de hoy no es el máximo de mañana.
    return d["texto"].format(n=min(max(largo * 2, 20), 4000))


def contrato(ds_id: str, dialecto: str = "sqlserver",
             perfil: dict[str, Any] | None = None,
             llaves: dict[str, Any] | None = None) -> dict[str, Any]:
    """Diccionario de datos, DDL y verificaciones para llevar la tabla a un servidor.

    Es lo que se pide cuando el análisis termina y hay que dejarlo andando:
    cómo se crea la tabla, y cómo se comprueba mañana que sigue estando bien.
    """
    if dialecto not in DIALECTOS:
        raise ValueError(f"Dialecto desconocido: {dialecto}. Válidos: {', '.join(DIALECTOS)}")
    d = DIALECTOS[dialecto]
    prof = perfil or profiling.profile(ds_id)
    ks = llaves or claves(ds_id, perfil=prof)
    tabla = _limpio(prof.get("name") or ds_id, 50)
    cita = lambda s: d["cita"].format(_limpio(s))          # noqa: E731

    numericas = [c["name"] for c in prof.get("columns", []) if c.get("kind") == "numeric"]
    enteras = _columnas_enteras(ds_id, numericas)

    diccionario = [{
        "columna": c["name"],
        "tipo": _tipo_sql(c, d, enteras),
        "nulos_pct": c.get("null_pct"),
        "distintos": c.get("distinct"),
        "obligatoria": (c.get("nulls") or 0) == 0,
        "rol": _rol(c, ks),
        "ejemplo": (c.get("top_values") or [{}])[0].get("value"),
    } for c in prof.get("columns", [])]

    ancho = max([len(cita(x["columna"])) for x in diccionario] or [10])
    campos = [f"    {cita(x['columna']):<{ancho}} {x['tipo']:<16} "
              f"{'NOT NULL' if x['obligatoria'] else 'NULL'}" for x in diccionario]

    pk = ks["pk_simple"][0]["columna"] if ks["pk_simple"] else None
    pk_comp = ks["pk_compuesta"][0]["columnas"] if ks["pk_compuesta"] else None
    # Sin coma al principio: los campos ya se unen con ",\n" más abajo, y una
    # coma de más deja un DDL que no ejecuta en ningún motor.
    if pk:
        campos.append(f"    CONSTRAINT PK_{tabla} PRIMARY KEY ({cita(pk)})")
    elif pk_comp:
        campos.append(f"    CONSTRAINT PK_{tabla} PRIMARY KEY "
                      f"({', '.join(cita(c) for c in pk_comp)})")

    ddl = "\n".join([
        f"-- {prof.get('name')} · {prof.get('rows'):,} filas · {d['label']}".replace(",", "."),
        "-- Generado por MV AutoML Studio a partir del perfilado real de los datos.",
        f"CREATE TABLE {cita(tabla)} (",
        ",\n".join(campos),
        ");",
    ])

    return {
        "dataset_id": ds_id, "tabla": tabla, "dialecto": dialecto,
        "dialecto_label": d["label"],
        "diccionario": diccionario,
        "ddl": ddl,
        "verificaciones": _verificaciones(tabla, prof, ks, cita),
        "dbt": _dbt(tabla, diccionario, pk, pk_comp),
    }


def _rol(col: dict[str, Any], ks: dict[str, Any]) -> str:
    nombre = col["name"]
    if any(k["columna"] == nombre for k in ks["pk_simple"]):
        return "clave primaria"
    if any(nombre in k["columnas"] for k in ks["pk_compuesta"]):
        return "parte de la clave"
    if any(k["columna"] == nombre for k in ks["fk_candidatas"]):
        return "clave foránea"
    if nombre in ks["constantes"]:
        return "constante"
    if col.get("kind") == "datetime":
        return "fecha"
    if col.get("is_text"):
        return "texto libre"
    if col.get("kind") == "numeric":
        return "medida"
    return "dimensión"


def _verificaciones(tabla: str, prof: dict, ks: dict, cita) -> list[dict[str, str]]:
    """Las consultas que hay que poder correr mañana para saber si sigue sana.

    Cada una devuelve cero cuando está todo bien: así se pueden encadenar en un
    trabajo programado sin leerlas una por una.
    """
    v: list[dict[str, str]] = []
    clave = (ks["pk_simple"][0]["columna"] if ks["pk_simple"]
             else (ks["pk_compuesta"][0]["columnas"] if ks["pk_compuesta"] else None))
    if clave:
        cols = ", ".join(cita(c) for c in ([clave] if isinstance(clave, str) else clave))
        v.append({
            "nombre": "La clave no repite",
            "por_que": "Si repite, cualquier cruce con esta tabla multiplica filas.",
            "sql": f"SELECT count(*) AS repetidas FROM (\n"
                   f"  SELECT {cols} FROM {cita(tabla)} GROUP BY {cols} HAVING count(*) > 1\n) t;",
        })
    obligatorias = [c["name"] for c in prof.get("columns", []) if (c.get("nulls") or 0) == 0][:6]
    if obligatorias:
        cond = " OR ".join(f"{cita(c)} IS NULL" for c in obligatorias)
        v.append({
            "nombre": "No aparecen nulos donde hoy no los hay",
            "por_que": "Un nulo nuevo en una columna que siempre venía completa "
                       "suele ser un cambio en el origen, no un dato faltante.",
            "sql": f"SELECT count(*) AS nulos_nuevos FROM {cita(tabla)} WHERE {cond};",
        })
    fechas = [c["name"] for c in prof.get("columns", []) if c.get("kind") == "datetime"]
    if fechas:
        v.append({
            "nombre": "Los datos están frescos",
            "por_que": "Una carga que dejó de correr no da error: simplemente "
                       "deja de traer filas nuevas y nadie se entera.",
            "sql": f"SELECT max({cita(fechas[0])}) AS ultima_fecha FROM {cita(tabla)};",
        })
        v.append({
            "nombre": "No hay fechas futuras",
            "por_que": "Casi siempre es un error de zona horaria o de parseo.",
            "sql": f"SELECT count(*) AS futuras FROM {cita(tabla)} "
                   f"WHERE {cita(fechas[0])} > CURRENT_TIMESTAMP;",
        })
    if int(prof.get("duplicate_row_groups") or 0):
        v.append({
            "nombre": "No hay filas repetidas enteras",
            "por_que": "Hoy las hay: suelen venir de una carga corrida dos veces.",
            "sql": f"SELECT count(*) AS grupos_repetidos FROM (\n"
                   f"  SELECT * FROM {cita(tabla)} GROUP BY ALL HAVING count(*) > 1\n) t;",
        })
    return v


def _dbt(tabla: str, diccionario: list[dict], pk: str | None,
         pk_comp: list[str] | None) -> str:
    claves_pk = [pk] if pk else (pk_comp or [])
    y = ["version: 2", "", "models:", f"  - name: stg_{tabla}",
         f"    description: 'Staging de {tabla} — generado por MV AutoML Studio'",
         "    columns:"]
    for c in diccionario[:40]:
        y.append(f"      - name: {_limpio(c['columna'])}")
        pruebas = []
        if c["columna"] in claves_pk:
            pruebas += ["not_null"] + (["unique"] if pk else [])
        elif c["obligatoria"]:
            pruebas.append("not_null")
        if pruebas:
            y.append("        tests:")
            y += [f"          - {t}" for t in pruebas]
    if pk_comp and not pk:
        y += ["    tests:",
              "      - dbt_utils.unique_combination_of_columns:",
              "          combination_of_columns:",
              *[f"            - {_limpio(c)}" for c in pk_comp]]
    return "\n".join(y)


# ─────────────────────────────────────────────────────────────────────────────
# Todo junto
# ─────────────────────────────────────────────────────────────────────────────
def informe(ds_id: str, dialecto: str = "sqlserver",
            columna_tiempo: str | None = None) -> dict[str, Any]:
    """El análisis de ingeniería completo de un dataset, en una sola pasada.

    Se calcula el perfil una vez y se reparte: recalcularlo por sección sería
    releer el Parquet cuatro veces sin ninguna ganancia.
    """
    prof = profiling.profile(ds_id)
    ks = claves(ds_id, perfil=prof)
    return {
        "dataset_id": ds_id,
        "nombre": prof.get("name"),
        "filas": prof.get("rows"),
        "columnas": prof.get("n_columns"),
        "calidad": prof.get("quality"),
        "claves": ks,
        "tiempo": tiempo(ds_id, columna_tiempo, perfil=prof),
        "contrato": contrato(ds_id, dialecto, perfil=prof, llaves=ks),
    }
