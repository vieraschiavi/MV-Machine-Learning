"""Preguntale a tus datos: preguntas en lenguaje natural sobre el dataset.

Dos motores, y la interfaz siempre dice cuál respondió:

* **Con IA configurada** — el proveedor elegido traduce la pregunta a UNA
  consulta SQL de sólo lectura sobre el esquema real; la consulta pasa por el
  mismo guardián que el resto de la plataforma, se ejecuta en DuckDB y el
  modelo redacta la respuesta **a partir del resultado ejecutado**. La IA
  nunca inventa el número: lo calcula el motor, la IA lo explica.

* **Sin IA** — un traductor propio cubre las preguntas frecuentes (totales,
  promedios, máximos, conteos, top N, agrupar por, filtrar por año). Es
  honesto sobre su alcance: si no entiende, dice qué formas sí entiende.

En ambos casos la respuesta trae la consulta SQL ejecutada: el número siempre
se puede auditar.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from . import ai as AI
from . import dashboards as D
from . import storage as S

MAX_ROWS = 200


class AskError(RuntimeError):
    pass


def _norm(x: str) -> str:
    x = unicodedata.normalize("NFKD", x.lower())
    return "".join(c for c in x if not unicodedata.combining(c))


MAX_EJEMPLOS = 8


def q(col: str) -> str:
    """Identificador entrecomillado, con las comillas internas escapadas."""
    return '"' + str(col).replace('"', '""') + '"'


def _valores_de_ejemplo(ds_id: str, columnas: list[dict]) -> dict[str, list[str]]:
    """Hasta ocho valores reales por columna de texto.

    Es la diferencia entre que «los clientes vencidos» se traduzca a
    `Estado = 'Vencido'` o a `Estado = 'vencidos'`: el modelo no puede adivinar
    cómo está escrito un valor si nunca lo vio.
    """
    de_texto = [c["name"] for c in columnas
                if str(c.get("type", "")).lower().startswith(("string", "utf8", "large_string"))]
    if not de_texto:
        return {}
    piezas = ", ".join(
        f'(SELECT string_agg(DISTINCT v, \'|\') FROM '
        f'(SELECT CAST({q(c)} AS VARCHAR) v FROM {{t}} WHERE {q(c)} IS NOT NULL '
        f'LIMIT 400) WHERE v <> \'\') AS {q(c)}'
        for c in de_texto[:25])
    try:
        fila = S.query(ds_id, f"SELECT {piezas}").iloc[0]
    except Exception:                      # una columna rara no puede tumbar la pregunta
        return {}
    out: dict[str, list[str]] = {}
    for c in de_texto[:25]:
        crudo = fila.get(c)
        if crudo:
            vals = [v for v in str(crudo).split("|") if v][:MAX_EJEMPLOS]
            # Una columna de texto libre no aporta como ejemplo y llena el
            # prompt: se recorta el valor y, si igual son párrafos, se omite.
            vals = [(v[:44] + "…") if len(v) > 45 else v for v in vals]
            if vals and sum(len(v) for v in vals) <= 260:
                out[c] = vals
    return out


def _schema_context(ds_id: str, con_ejemplos: bool = True) -> dict[str, Any]:
    """Esquema compacto para el prompt y para el traductor local."""
    spec = D.detect_spec(ds_id)
    meta = S.load_meta(ds_id)
    columnas = [{"name": c["name"], "type": c["arrow_type"]} for c in meta.columns]
    return {
        "columns": columnas,
        "rows": meta.rows,
        "time_column": spec.get("time_column"),
        "metrics": [m["name"] for m in spec.get("metrics", [])],
        "dimensions": spec.get("dimensions", []),
        "samples": _valores_de_ejemplo(ds_id, columnas) if con_ejemplos else {},
    }


# ── barrera de sólo lectura ──────────────────────────────────────────────────
# Un `\b` en vez de un espacio: «DELETE\nFROM» y «DELETE/**/FROM» son la misma
# operación escrita distinto. En DuckDB además hay que frenar lo que lee y
# escribe el disco desde un SELECT —`read_csv`, `copy`, `install`— porque eso
# es acceso al equipo del cliente, no una consulta.
PROHIBIDAS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|"
    r"exec|execute|merge|grant|revoke|attach|detach|vacuum|reindex|pragma|"
    r"into|"                                        # SELECT … INTO / REPLACE INTO
    r"copy|export|import|install|load|"             # DuckDB toca el filesystem
    r"read_csv|read_csv_auto|read_parquet|read_json|read_json_auto|read_text|"
    r"read_blob|glob|parquet_scan|csv_scan|"
    r"load_file|outfile|dumpfile|"                  # MySQL
    r"pg_read_file|pg_ls_dir|lo_export|lo_import|"  # Postgres
    r"openrowset|opendatasource|xp_cmdshell)\b"     # SQL Server
    r"|\bxp_|\bsp_executesql",
    re.I,
)
GUARD = re.compile(r"^\s*(select|with)\b", re.I)

# Los comentarios y los literales se sacan ANTES de mirar el SQL: sin eso,
# «SELECT ';' AS separador» dispara la alarma sin motivo, y a la vez nada de lo
# que se esconda dentro de un texto puede evadir la barrera, porque no se mira.
_COMENTARIOS = (re.compile(r"/\*.*?\*/", re.S), re.compile(r"--[^\n]*"))
_LITERAL = re.compile(r"'(?:[^']|'')*'")


def solo_lectura(sql: str) -> str:
    """Devuelve el SQL si es una lectura pura; si no, lo rechaza.

    Vive en el punto de ejecución y no en el orquestador a propósito: cualquier
    camino que llegue a la base —la IA, el traductor local, una consulta
    reejecutada— pasa por acá sin excepción.
    """
    if not sql or not sql.strip():
        raise AskError("La consulta quedó vacía.")
    limpio = sql
    for c in _COMENTARIOS:
        limpio = c.sub(" ", limpio)
    limpio = limpio.strip().rstrip(";")
    sin_texto = _LITERAL.sub("''", limpio)

    if ";" in sin_texto:
        raise AskError("Una sola sentencia por pregunta.")
    if not GUARD.match(sin_texto):
        raise AskError("La consulta debe empezar con SELECT o WITH: se descartó.")
    prohibida = PROHIBIDAS.search(sin_texto)
    if prohibida:
        raise AskError(f"«{prohibida.group(0).strip()}» no está permitido: "
                       f"la plataforma nunca modifica ni lee archivos de tu equipo.")
    return limpio


def _run_sql(ds_id: str, sql: str, recorte: tuple[str, list] | None = None):
    """Ejecuta la consulta con el guardián de sólo lectura.

    Si el tablero tiene filtros aplicados, la pregunta se responde sobre ese
    recorte y no sobre el dataset entero: sería desconcertante filtrar por dos
    sucursales y que la respuesta hable de las seis.
    """
    sql = solo_lectura(sql)
    params: list = []
    if recorte and recorte[0]:
        where, wp = recorte
        veces = sql.count("{t}")
        sql = sql.replace("{t}", f"(SELECT * FROM {{t}}{where})")
        params = list(wp) * veces
    return S.query(ds_id, f"SELECT * FROM ({sql}) LIMIT {MAX_ROWS}", params)


# ═══════════════════════════════════════════════════ traductor local ═════════
AGGS = [
    (r"\b(total|suma|sum|cuanto se|cuánto se)\b", "sum"),
    (r"\b(promedio|media|average|avg)\b", "avg"),
    (r"\b(maximo|máximo|max|mayor)\b", "max"),
    (r"\b(minimo|mínimo|min|menor)\b", "min"),
    (r"\b(cuantos|cuantas|conteo|count|cantidad de registros)\b", "count"),
]


def _match_column(texto: str, columnas: list[str]) -> str | None:
    """La columna cuyo nombre mejor aparece en la pregunta."""
    t = _norm(texto)
    mejor, puntaje = None, 0
    for col in columnas:
        tokens = [w for w in re.split(r"[^a-z0-9]+", _norm(re.sub(r"([a-z])([A-Z])", r"\1 \2", col))) if len(w) > 2]
        hits = sum(1 for w in tokens if w in t)
        if hits > puntaje:
            mejor, puntaje = col, hits
    return mejor


def heuristic_answer(ds_id: str, question: str, ctx: dict,
                     recorte: tuple[str, list] | None = None) -> dict[str, Any] | None:
    """Motor sin IA. Devuelve None si la pregunta no encaja en ningún patrón."""
    t = _norm(question)
    columnas = [c["name"] for c in ctx["columns"]]

    agg = next((a for patron, a in AGGS if re.search(patron, t)), None)
    metrica = _match_column(question, ctx["metrics"] or columnas)
    dimension = None
    m_por = re.search(r"\bpor\b\s+(.+?)(?:\?|$| en | del | de la )", t)
    if m_por:
        dimension = _match_column(m_por.group(1), ctx["dimensions"] or columnas)
    anio = re.search(r"\b(20\d{2})\b", t)
    top = re.search(r"\btop\s*(\d+)", t)

    where = ""
    if anio and ctx.get("time_column"):
        where = f" WHERE year({q(ctx['time_column'])}) = {int(anio.group(1))}"

    if agg == "count" and not dimension:
        sql = f"SELECT count(*) AS registros FROM {{t}}{where}"
    elif agg and metrica and dimension:
        sql = (f"SELECT {q(dimension)} AS grupo, {agg}({q(metrica)}) AS valor "
               f"FROM {{t}}{where} GROUP BY 1 ORDER BY valor DESC"
               + (f" LIMIT {int(top.group(1))}" if top else ""))
    elif agg and metrica:
        sql = f"SELECT {agg}({q(metrica)}) AS valor FROM {{t}}{where}"
    elif top and metrica:
        sql = (f"SELECT * FROM {{t}}{where} ORDER BY {q(metrica)} DESC "
               f"LIMIT {int(top.group(1))}")
    else:
        return None

    df = _run_sql(ds_id, sql, recorte)
    return {"sql": sql, "rows": df, "engine": "reglas locales",
            "answer": _narrate_local(agg, metrica, dimension, df)}


def _fmt(v: float, dec: int = 0) -> str:
    """1234567.89 → «1.234.567,89»: miles con punto, decimal con coma."""
    s = f"{float(v):,.{dec}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _narrate_local(agg, metrica, dimension, df) -> str:
    if df.empty:
        return "La consulta no devolvió filas con ese recorte."
    if "registros" in df.columns:
        return f"Hay {_fmt(df['registros'].iloc[0])} registros."
    nombre = {"sum": "El total", "avg": "El promedio", "max": "El máximo",
              "min": "El mínimo"}.get(agg, "El valor")
    if dimension and len(df) > 1:
        tope = df.iloc[0]
        return (f"{nombre} de {metrica} por {dimension}: lidera "
                f"«{tope.iloc[0]}» con {_fmt(tope['valor'])}. "
                f"La tabla trae los {len(df)} grupos.")
    if "valor" in df.columns:
        return f"{nombre} de {metrica} es {_fmt(df['valor'].iloc[0], 2)}."
    return f"Se devuelven {len(df)} filas ordenadas por {metrica}."


# ═══════════════════════════════════════════════════════ motor con IA ════════
def _ficha_del_esquema(ctx: dict) -> str:
    """La tabla descrita como se la describiría a una persona.

    Tipo, columna temporal y —lo que más cambia el resultado— los valores que
    realmente aparecen en cada columna de texto.
    """
    lineas = [f"TABLA: {{t}}  ({ctx['rows']:,} filas)".replace(",", "."), "Columnas:"]
    muestras = ctx.get("samples") or {}
    for c in ctx["columns"][:60]:
        linea = f"  - {c['name']} ({c['type']})"
        if c["name"] in muestras:
            linea += "  valores: " + ", ".join(f"«{v}»" for v in muestras[c["name"]])
        if c["name"] == ctx.get("time_column"):
            linea += "  [columna temporal]"
        lineas.append(linea)
    return "\n".join(lineas)


def _pedir_sql(question: str, ficha: str, error_previo: str = "", sql_previo: str = "") -> dict:
    """Le pide el SQL al proveedor. Con `error_previo`, le pide corregirlo."""
    reglas = (
        "Reglas: una sola sentencia; sólo SELECT o WITH; sintaxis DuckDB; usá "
        "EXCLUSIVAMENTE las columnas del esquema, no inventes nombres; si la "
        "pregunta pide un ranking agregá ORDER BY y LIMIT; alias legibles en "
        "castellano para las columnas calculadas.")
    if error_previo:
        prompt = (
            f"{ficha}\n\nPregunta: «{question}»\n\n"
            f"Esta consulta falló:\n{sql_previo}\n\n"
            f"La base respondió: {error_previo}\n\n"
            f"Corregila. {reglas}\n"
            'Devolvé SOLO un JSON: {"sql": "...", "nota": "qué estaba mal", '
            '"confianza": 0-100}.')
    else:
        prompt = (
            f"{ficha}\n\nPregunta del usuario: «{question}»\n\n"
            f"{reglas}\n"
            'Devolvé SOLO un JSON: {"sql": "la consulta", "nota": "supuesto '
            'tomado, si hubo", "confianza": 0-100}.')
    r = AI.chat(None, prompt, AI.SYSTEM_ES, max_tokens=700)
    plan = AI._json_from(r["text"])
    plan["_provider"] = f"{r['provider']} · {r['model']}"
    return plan


def ai_answer(ds_id: str, question: str, ctx: dict, lang: str = "es",
              recorte: tuple[str, list] | None = None) -> dict[str, Any]:
    """Traduce, ejecuta y narra. Si la base rechaza el SQL, lo hace corregir.

    Ese segundo intento es barato y cambia mucho el resultado: los mensajes de
    DuckDB nombran la columna que no existe y sugieren las parecidas, así que
    el modelo casi siempre acierta con esa pista.
    """
    ficha = _ficha_del_esquema(ctx)
    plan = _pedir_sql(question, ficha)
    sql = str(plan.get("sql", ""))
    intentos: list[str] = []
    df = None
    for _ in range(2):
        try:
            df = _run_sql(ds_id, sql, recorte)
            break
        except AskError:
            raise                                   # la barrera no se reintenta
        except Exception as exc:
            fallo = str(exc).split("\n")[0][:300]
            intentos.append(fallo)
            plan = _pedir_sql(question, ficha, fallo, sql)
            sql = str(plan.get("sql", ""))
    if df is None:
        raise AskError("La consulta no pudo ejecutarse: " + " · ".join(intentos))

    muestra = df.head(30).to_json(orient="records", date_format="iso")
    idioma = {"es": "español rioplatense", "en": "English", "pt": "português"}.get(lang, "español")
    prompt2 = (
        f"Pregunta: «{question}»\n"
        f"Consulta ejecutada: {sql}\n"
        f"Resultado real (hasta 30 filas): {muestra}\n\n"
        f"Respondé la pregunta en {idioma}, en 1 a 3 frases, usando ÚNICAMENTE "
        f"estos datos. Formateá los números con separador de miles. Sin emojis.")
    r2 = AI.chat(None, prompt2, AI.SYSTEM_ES, max_tokens=400)

    nota = plan.get("nota") or None
    if intentos:
        nota = (f"{nota}. " if nota else "") + f"Se corrigió la consulta: {intentos[0]}"
    return {"sql": sql, "rows": df, "engine": plan["_provider"],
            "answer": r2["text"].strip(), "note": nota,
            "confidence": plan.get("confianza")}


def _recorte(ds_id: str, filters: dict[str, Any] | None) -> tuple[str, list] | None:
    """WHERE de los filtros del tablero, validado contra el spec del servidor."""
    if not filters:
        return None
    from . import dashboards as D
    where, params = D._where(D.detect_spec(ds_id), filters)
    return (where, params) if where else None


def _con_aviso(out: dict[str, Any], recorte) -> dict[str, Any]:
    if recorte:
        aviso = "La respuesta sale del recorte filtrado del tablero, no de todo el dataset."
        out["note"] = f"{out['note']} {aviso}" if out.get("note") else aviso
    return out


# ═══════════════════════════════════════════════════════════ fachada ═════════
def ask(ds_id: str, question: str, lang: str = "es",
        filters: dict[str, Any] | None = None) -> dict[str, Any]:

    if not question or not question.strip():
        raise AskError("Escribí una pregunta.")
    ctx = _schema_context(ds_id)
    recorte = _recorte(ds_id, filters)

    # El traductor local va primero, no como respaldo: si la pregunta es una de
    # las formas frecuentes, responde al instante, sin costo y sin mandar nada
    # afuera. La IA queda para lo que las reglas no cubren.
    out = heuristic_answer(ds_id, question, ctx, recorte)
    if out is not None:
        return _pack(_con_aviso(out, recorte))

    intento_ia: str | None = None
    if AI.active_provider():
        try:
            out = ai_answer(ds_id, question, ctx, lang, recorte)
            return _pack(_con_aviso(out, recorte))
        except (AI.AIError, AskError, ValueError, KeyError) as exc:
            intento_ia = str(exc)[:200]

    ejemplos = []
    if ctx["metrics"]:
        m = ctx["metrics"][0]
        ejemplos.append(f"total de {m}")
        if ctx["dimensions"]:
            ejemplos.append(f"promedio de {m} por {ctx['dimensions'][0]}")
        ejemplos.append(f"top 5 por {m}")
    ejemplos.append("cuántos registros hay")
    raise AskError(
        "No pude interpretar la pregunta"
        + (f" (la IA tampoco: {intento_ia})" if intento_ia else " con las reglas locales")
        + ". Formas que entiendo: " + "; ".join(f"«{e}»" for e in ejemplos) + ".")


def _pack(out: dict[str, Any]) -> dict[str, Any]:
    import json

    df = out.pop("rows")
    return {
        **out,
        "columns": list(df.columns),
        "rows": json.loads(df.to_json(orient="records", date_format="iso")),
        "row_count": int(len(df)),
    }
