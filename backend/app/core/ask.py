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


def _schema_context(ds_id: str) -> dict[str, Any]:
    """Esquema compacto para el prompt y para el traductor local."""
    spec = D.detect_spec(ds_id)
    meta = S.load_meta(ds_id)
    return {
        "columns": [{"name": c["name"], "type": c["arrow_type"]} for c in meta.columns],
        "rows": meta.rows,
        "time_column": spec.get("time_column"),
        "metrics": [m["name"] for m in spec.get("metrics", [])],
        "dimensions": spec.get("dimensions", []),
    }


GUARD = re.compile(r"^\s*(select|with)\b", re.I)
FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|create|alter|attach|copy|export|"
                       r"install|load|pragma|set)\b", re.I)


def _run_sql(ds_id: str, sql: str, recorte: tuple[str, list] | None = None):
    """Ejecuta la consulta con el guardián de sólo lectura.

    Si el tablero tiene filtros aplicados, la pregunta se responde sobre ese
    recorte y no sobre el dataset entero: sería desconcertante filtrar por dos
    sucursales y que la respuesta hable de las seis.
    """
    sql = sql.strip().rstrip(";")
    if not GUARD.match(sql) or FORBIDDEN.search(sql):
        raise AskError("La consulta generada no es de sólo lectura: se descartó.")
    if sql.count(";") > 0:
        raise AskError("Una sola sentencia por pregunta.")
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
    q = lambda c: '"' + c.replace('"', '""') + '"'  # noqa: E731

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
def ai_answer(ds_id: str, question: str, ctx: dict, lang: str = "es",
              recorte: tuple[str, list] | None = None) -> dict[str, Any]:

    esquema = "\n".join(f"- {c['name']} ({c['type']})" for c in ctx["columns"][:60])
    prompt1 = (
        f"Tabla DuckDB expuesta como {{t}} con {ctx['rows']:,} filas.\n"
        f"Columnas:\n{esquema}\n"
        f"Columna temporal: {ctx.get('time_column') or 'ninguna'}\n\n"
        f"Pregunta del usuario: «{question}»\n\n"
        "Devolvé SOLO un JSON: {\"sql\": \"una consulta SELECT sobre {t} que "
        "responda la pregunta\", \"nota\": \"supuesto tomado, si hubo\"}. "
        "Reglas: sólo lectura, una sentencia, sintaxis DuckDB, agregá LIMIT si "
        "el resultado puede ser largo.")
    r1 = AI.chat(None, prompt1, AI.SYSTEM_ES, max_tokens=600)
    plan = AI._json_from(r1["text"])
    sql = str(plan.get("sql", ""))
    df = _run_sql(ds_id, sql, recorte)

    muestra = df.head(30).to_json(orient="records", date_format="iso")
    idioma = {"es": "español rioplatense", "en": "English", "pt": "português"}.get(lang, "español")
    prompt2 = (
        f"Pregunta: «{question}»\n"
        f"Consulta ejecutada: {sql}\n"
        f"Resultado real (hasta 30 filas): {muestra}\n\n"
        f"Respondé la pregunta en {idioma}, en 1 a 3 frases, usando ÚNICAMENTE "
        f"estos datos. Formateá los números con separador de miles. Sin emojis.")
    r2 = AI.chat(None, prompt2, AI.SYSTEM_ES, max_tokens=400)
    return {"sql": sql, "rows": df, "engine": f"{r1['provider']} · {r1['model']}",
            "answer": r2["text"].strip(), "note": plan.get("nota") or None}


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

    intento_ia: str | None = None
    if AI.active_provider():
        try:
            out = ai_answer(ds_id, question, ctx, lang, recorte)
            return _pack(_con_aviso(out, recorte))
        except (AI.AIError, AskError, ValueError, KeyError) as exc:
            intento_ia = str(exc)[:200]

    out = heuristic_answer(ds_id, question, ctx, recorte)
    if out is not None:
        if intento_ia:
            out["note"] = f"La IA falló ({intento_ia}); respondió el motor local."
        return _pack(_con_aviso(out, recorte))

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
