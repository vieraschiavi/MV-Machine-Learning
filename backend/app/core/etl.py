"""Motor de ETL automático.

El ETL no se ejecuta a ciegas: primero se **propone un plan** legible —una
lista de pasos con su motivo— que el usuario puede revisar, desactivar o
editar; recién después se ejecuta. El plan se compila a una única sentencia
SQL de DuckDB, de modo que:

  * se puede auditar (la UI muestra el SQL exacto que se corrió),
  * es reproducible (mismo plan ⇒ mismo resultado),
  * corre fuera de memoria (el tamaño del dataset no importa).

El resultado es un dataset nuevo, derivado, que conserva el linaje al padre.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

import pandas as pd

from . import profiling as P
from . import storage as S

DATE_HINT = re.compile(r"(fecha|date|dia|day|mes|month|anio|año|year|periodo|time|stamp|dt_)", re.I)
ID_HINT = re.compile(r"(^id$|_id$|^id_|codigo|c[oó]digo|nro|numero|n[uú]mero|uuid|guid|documento|cedula|c[eé]dula|ruc|cuit|dni)", re.I)
CURRENCY = re.compile(r"[\$€£¥\s ]")


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sid() -> str:
    return uuid.uuid4().hex[:8]


# ════════════════════════════════════════════════════════════ PROPUESTA ══════
def propose(ds_id: str, target: str | None = None,
            options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Analiza el dataset y devuelve el plan de ETL propuesto."""
    o = {
        "drop_constant": True,
        "drop_identifiers": True,
        "null_threshold": 80.0,       # % de nulos a partir del cual se descarta
        "impute": True,
        "missing_indicator": True,    # marca "este valor faltaba" antes de imputar
        "parse_dates": True,
        "expand_dates": True,
        "cast_numeric_text": True,
        "trim_text": True,
        "group_rare": True,
        "rare_threshold": 0.5,        # % mínimo para que una categoría sobreviva
        "max_categories": 30,
        "clip_outliers": False,       # los árboles no lo necesitan; opcional
        "drop_duplicates": True,
        "leakage_audit": True,
        "leakage_threshold": 0.98,
    }
    o.update(options or {})

    prof = P.profile(ds_id)
    cols = {c["name"]: c for c in prof["columns"]}
    steps: list[dict[str, Any]] = []
    dropped: set[str] = set()

    def add(op: str, column: str | None, reason: str, params: dict | None = None,
            severity: str = "info", enabled: bool = True):
        steps.append({"id": _sid(), "op": op, "column": column, "params": params or {},
                      "reason": reason, "severity": severity, "enabled": enabled})

    # ── 0. detección de tipo real ─────────────────────────────────────────────
    # Se corre ANTES de descartar columnas: una fecha tiene un valor distinto
    # por fila y, sin este paso, se descartaría por "identificador único".
    detected: dict[str, dict[str, Any]] = {}
    for name, c in cols.items():
        if c["kind"] == "categorical" and not c["constant"]:
            d = _detect_cast(ds_id, name, c)
            if d:
                detected[name] = d

    # ── 1. columnas que no aportan ────────────────────────────────────────────
    for name, c in cols.items():
        if name == target:
            continue
        det = detected.get(name, {})
        is_date = c["kind"] == "datetime" or det.get("as") == "datetime"
        is_text = bool(c.get("is_text"))
        # Una clave es numérica ENTERA y DENSA: sus valores llenan el rango
        # (1, 2, 3… con huecos). Un monto entero único no: "391.311.281" tiene
        # un rango millones de veces mayor que la cantidad de filas. Y un
        # importe con decimales no repite nunca y tampoco es una clave.
        # Descartar cualquiera de los dos borraría la variable que más informa.
        continua = _es_magnitud(ds_id, name, c, det)
        if o["drop_constant"] and c["constant"]:
            # una columna con un único valor y muchos nulos no es "constante" a
            # secas: conviene decir las dos cosas para que el motivo no engañe.
            motivo = ("Un solo valor distinto en todo el dataset."
                      if c["null_pct"] < 5 else
                      f"Un solo valor distinto y {c['null_pct']:.1f}% de nulos: "
                      f"no distingue entre filas.")
            add("drop_column", name, motivo, severity="high")
            dropped.add(name)
        elif c["null_pct"] >= o["null_threshold"]:
            add("drop_column", name, f"{c['null_pct']:.1f}% de nulos, por encima del umbral "
                                     f"({o['null_threshold']:.0f}%).", severity="high")
            dropped.add(name)
        elif o["drop_identifiers"] and c["unique_key"] and not is_date and not continua and not is_text:
            add("drop_column", name, "Identificador único por fila: memoriza, no generaliza.", severity="medium")
            dropped.add(name)

    # columnas duplicadas exactas (mismo contenido, distinto nombre)
    for a, b in _duplicate_columns(ds_id, [n for n in cols if n not in dropped and n != target]):
        add("drop_column", b, f"Contenido idéntico a «{a}»: información redundante.", severity="medium")
        dropped.add(b)

    # ── 2. tipos: texto que en realidad es número o fecha ─────────────────────
    live = [n for n in cols if n not in dropped]
    for name in live:
        c = cols[name]
        cast = detected.get(name)
        if c["kind"] != "categorical" or cast is None:
            continue
        if cast["as"] == "numeric" and o["cast_numeric_text"]:
            add("cast_numeric", name,
                f"Texto que en realidad es numérico ({cast['ratio']*100:.0f}% de los valores convierten).",
                {"decimal_comma": cast["decimal_comma"], "strip_symbols": cast["strip_symbols"]})
            cols[name] = {**c, "kind": "numeric"}
        elif cast["as"] == "datetime" and o["parse_dates"]:
            add("parse_datetime", name,
                f"Texto con formato de fecha ({cast['ratio']*100:.0f}% parsea correctamente).",
                {"format": cast.get("format")})
            cols[name] = {**c, "kind": "datetime"}
        elif o["trim_text"] and (cast.get("needs_trim") or cast.get("mixed_case")):
            add("trim_text", name, "Espacios sobrantes o mayúsculas inconsistentes.",
                {"lower": bool(cast.get("mixed_case"))})

    # ── 3. fechas → variables aprovechables por el modelo ─────────────────────
    if o["expand_dates"]:
        for name in [n for n in live if cols[n]["kind"] == "datetime" and n != target]:
            add("expand_datetime", name,
                "Se derivan año, mes, día, día de semana y semana del año; la fecha cruda no la usa el modelo.",
                {"parts": ["year", "month", "day", "dow", "week"]})

    # ── 4. faltantes ─────────────────────────────────────────────────────────
    if o["impute"]:
        for name in [n for n in live if n != target]:
            c = cols[name]
            if c["null_pct"] <= 0:
                continue
            if c["kind"] == "numeric":
                med = (c.get("stats") or {}).get("median")
                if med is None:
                    continue
                if o["missing_indicator"] and c["null_pct"] >= 5:
                    add("missing_indicator", name,
                        f"El propio hecho de faltar puede ser informativo ({c['null_pct']:.1f}% nulos).")
                add("impute_numeric", name,
                    f"Imputación por mediana ({med:,.4g}) sobre {c['null_pct']:.1f}% de nulos.",
                    {"value": float(med), "strategy": "median"})
            elif c["kind"] == "categorical":
                add("impute_categorical", name,
                    f"Imputación con categoría explícita sobre {c['null_pct']:.1f}% de nulos.",
                    {"value": "(sin dato)"})

    # ── 4 bis. texto libre: se declara, no se transforma ─────────────────────
    for name in [n for n in live if cols[n].get("is_text") and n != target]:
        add("text_column", name,
            "Texto libre: se vectoriza con TF-IDF y se comprime a componentes "
            "numéricas al entrenar. No se agrupa ni se descarta.")

    # ── 5. categorías raras y alta cardinalidad ──────────────────────────────
    if o["group_rare"]:
        for name in [n for n in live if cols[n]["kind"] == "categorical" and n != target]:
            c = cols[name]
            if c["distinct"] <= 2 or c.get("is_text"):
                continue
            keep = _frequent_values(ds_id, name, o["rare_threshold"], o["max_categories"])
            if keep is not None and len(keep) < c["distinct"]:
                add("group_rare", name,
                    f"{c['distinct']} categorías → {len(keep)} frecuentes + «(otros)». "
                    f"Las raras generan ruido y sobreajuste.",
                    {"keep": keep, "other": "(otros)"})

    # ── 6. outliers ──────────────────────────────────────────────────────────
    if o["clip_outliers"]:
        for name in [n for n in live if cols[n]["kind"] == "numeric" and n != target]:
            st = cols[name].get("stats") or {}
            if st.get("p01") is None or st.get("p99") is None or st["p99"] <= st["p01"]:
                continue
            if (st.get("outlier_pct") or 0) < 1:
                continue
            add("clip_outliers", name,
                f"Winsorización a los percentiles 1 y 99 ({st.get('outlier_pct', 0):.1f}% fuera de rango).",
                {"lo": float(st["p01"]), "hi": float(st["p99"])})

    # ── 7. filas ─────────────────────────────────────────────────────────────
    if target:
        add("filter_null_target", target,
            "Se descartan las filas sin variable objetivo: no se puede aprender de ellas.",
            severity="high")
    if o["drop_duplicates"] and prof["duplicate_row_groups"] > 0:
        add("drop_duplicates", None,
            f"{prof['duplicate_row_groups']} grupos de filas duplicadas exactas.", severity="medium")

    # ── 8. auditoría de fuga de información ──────────────────────────────────
    leak: list[dict[str, Any]] = []
    if target and o["leakage_audit"]:
        leak = audit_leakage(ds_id, target, threshold=o["leakage_threshold"],
                             skip=[s["column"] for s in steps if s["op"] == "drop_column"])
        for hallazgo in leak:
            if hallazgo["blocked"]:
                add("drop_column", hallazgo["column"],
                    f"FUGA DE INFORMACIÓN: {hallazgo['detail']} Entrenar con esta columna daría "
                    f"métricas irreales que no se repiten en producción.",
                    severity="high")

    plan = {
        "dataset_id": ds_id, "target": target, "options": o,
        "steps": steps, "leakage": leak,
        "summary": _summarize(steps, prof),
    }
    plan["sql"] = compile_sql(ds_id, plan)
    return plan


def _es_magnitud(ds_id: str, name: str, col: dict, det: dict) -> bool:
    """¿Esta columna única es una magnitud (monto, medida) y no una clave?

    Nunca lo es si el nombre grita identificador. Después: decimales ⇒
    magnitud; enteros ⇒ magnitud sólo si son dispersos (densidad < 1‰ del
    rango). Los IDs secuenciales, aun con huecos grandes, son densos.
    """
    if not col.get("unique_key"):
        return False
    if ID_HINT.search(name):
        return False
    if det.get("as") == "numeric":
        if not det.get("integer_like", True):
            return True
        return det.get("density", 1.0) < 1e-3
    if col["kind"] != "numeric":
        return False
    if _tiene_decimales(ds_id, name):
        return True
    st = col.get("stats") or {}
    mn, mx = st.get("min"), st.get("max")
    if mn is None or mx is None or mx <= mn:
        return False
    return (col["non_null"] / (float(mx) - float(mn) + 1)) < 1e-3


def _tiene_decimales(ds_id: str, name: str) -> bool:
    """¿La columna toma algún valor con parte decimal?

    Se consulta el dato, no los estadísticos: el promedio de 1..1200 es 600,5 y
    haría pasar por «continua» a una clave entera perfectamente secuencial.
    Sólo se llama para columnas sin valores repetidos, que son pocas.
    """
    con = S.connect()
    try:
        q = _q(name)
        n = con.execute(
            f"SELECT count(*) FROM {S.glob_expr(ds_id)} "
            f"WHERE {q} IS NOT NULL AND {q} <> floor({q}) LIMIT 1"
        ).fetchone()[0]
        return int(n) > 0
    except Exception:
        return False
    finally:
        con.close()


def _summarize(steps: list[dict], prof: dict) -> dict[str, Any]:
    by_op: dict[str, int] = {}
    for s in steps:
        by_op[s["op"]] = by_op.get(s["op"], 0) + 1
    return {
        "n_steps": len(steps),
        "columns_in": prof["n_columns"],
        "columns_dropped": by_op.get("drop_column", 0),
        "by_op": by_op,
        "rows_in": prof["rows"],
    }


# ═══════════════════════════════════════════════════════════ DETECCIÓN ═══════
def _detect_cast(ds_id: str, name: str, col: dict) -> dict[str, Any] | None:
    """¿Este texto es en realidad número o fecha? Se decide con una muestra."""
    con = S.connect()
    q, t = _q(name), S.glob_expr(ds_id)
    try:
        sample = con.execute(
            f"SELECT {q} v FROM {t} WHERE {q} IS NOT NULL LIMIT 5000"
        ).df()["v"].astype(str)
    finally:
        con.close()
    if sample.empty:
        return None

    needs_trim = bool((sample != sample.str.strip()).mean() > 0.01)
    stripped = sample.str.strip()
    letters = stripped.str.contains(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", regex=True)
    mixed_case = bool(letters.any() and
                      (stripped[letters] != stripped[letters].str.upper()).any() and
                      (stripped[letters] != stripped[letters].str.lower()).any() and
                      stripped.str.lower().nunique() < stripped.nunique())

    # numérico: se prueba con punto decimal y con coma decimal
    cleaned = stripped.str.replace(CURRENCY, "", regex=True).str.replace("%", "", regex=False)
    dot = pd.to_numeric(cleaned.str.replace(",", "", regex=False), errors="coerce")
    comma = pd.to_numeric(cleaned.str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
                          errors="coerce")
    r_dot, r_comma = float(dot.notna().mean()), float(comma.notna().mean())
    if max(r_dot, r_comma) >= 0.95:
        # Ambas lecturas suelen "funcionar": quitarle la coma a «154,37» da
        # 15437, que es un número válido pero equivocado. La convención se
        # decide por la forma de los valores, no por cuál de las dos parsea.
        use_comma = _decimal_is_comma(cleaned, r_dot, r_comma)
        parsed = comma if use_comma else dot
        finitos = parsed.dropna()
        entero = bool(len(finitos) and (finitos % 1 == 0).all())
        rango = float(finitos.max() - finitos.min()) if len(finitos) > 1 else 0.0
        densidad = len(finitos) / (rango + 1) if rango > 0 else 1.0
        return {"as": "numeric", "ratio": max(r_dot, r_comma), "decimal_comma": use_comma,
                "strip_symbols": bool((cleaned != stripped).any()),
                "integer_like": entero, "density": densidad,
                "needs_trim": needs_trim, "mixed_case": mixed_case}

    # fecha: sólo si el nombre lo sugiere o el patrón es inequívoco
    looks_dateish = bool(DATE_HINT.search(name)) or bool(
        stripped.str.match(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?").mean() > 0.9
        or stripped.str.match(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}").mean() > 0.9
    )
    if looks_dateish and not ID_HINT.search(name):
        parsed = pd.to_datetime(stripped, errors="coerce", format="mixed", dayfirst=True)
        r = float(parsed.notna().mean())
        if r >= 0.9:
            return {"as": "datetime", "ratio": r, "needs_trim": needs_trim, "mixed_case": mixed_case}

    if needs_trim or mixed_case:
        return {"as": "text", "ratio": 1.0, "needs_trim": needs_trim, "mixed_case": mixed_case}
    return None


def _decimal_is_comma(values: pd.Series, r_dot: float, r_comma: float) -> bool:
    """¿La coma es el separador decimal en estos valores?

    No alcanza con probar las dos lecturas: quitarle la coma a «154,37» da
    15437, que es un número válido pero equivocado. La convención se deduce de
    la forma de los valores, mirando toda la columna junta:

      * ``1.234,56``  aparecen los dos símbolos → el último es el decimal;
      * ``154,37``    un solo símbolo con 2 dígitos detrás → ese es el decimal;
      * ``1.540``     un solo símbolo con siempre 3 dígitos detrás → es de
        miles, así que el decimal es el otro;
      * ``0.123``     empieza en cero: nadie escribe miles así → es decimal.

    Si la columna no aporta ninguna evidencia (números enteros sin símbolos),
    da lo mismo la elección y gana la lectura que parsea.
    """
    votos_coma = votos_punto = 0
    tails: dict[str, list[int]] = {".": [], ",": []}
    lead_cero: dict[str, bool] = {".": False, ",": False}

    for v in values.dropna().astype(str).head(800):
        i_dot, i_comma = v.rfind("."), v.rfind(",")
        if i_dot >= 0 and i_comma >= 0:
            # los dos símbolos presentes: el que va último es el decimal
            if i_comma > i_dot:
                votos_coma += 2
            else:
                votos_punto += 2
            continue
        for sym, idx in ((".", i_dot), (",", i_comma)):
            if idx < 0:
                continue
            tails[sym].append(len(v) - idx - 1)
            entero = v[:idx].lstrip("+-")
            if entero.startswith("0") or entero == "":
                lead_cero[sym] = True

    for sym, largos in tails.items():
        if not largos:
            continue
        siempre_tres = all(t == 3 for t in largos)
        if siempre_tres and not lead_cero[sym] and len(largos) >= 3:
            # separador de miles: el decimal es el otro símbolo
            if sym == ".":
                votos_coma += len(largos)
            else:
                votos_punto += len(largos)
        else:
            if sym == ".":
                votos_punto += len(largos)
            else:
                votos_coma += len(largos)

    if votos_coma != votos_punto:
        return votos_coma > votos_punto
    return r_comma > r_dot


def _frequent_values(ds_id: str, name: str, pct: float, max_cat: int) -> list[str] | None:
    con = S.connect()
    try:
        df = con.execute(f"""
            SELECT CAST({_q(name)} AS VARCHAR) v, count(*) c
            FROM {S.glob_expr(ds_id)} WHERE {_q(name)} IS NOT NULL
            GROUP BY 1 ORDER BY c DESC
        """).df()
    finally:
        con.close()
    if df.empty:
        return None
    total = float(df["c"].sum())
    keep = [str(v) for v, c in zip(df["v"], df["c"], strict=False) if c / total * 100 >= pct][:max_cat]
    return keep or [str(df["v"].iloc[0])]


def _duplicate_columns(ds_id: str, names: list[str]) -> list[tuple[str, str]]:
    """Pares de columnas con contenido idéntico, detectados por hash agregado."""
    if len(names) < 2:
        return []
    con = S.connect()
    try:
        sel = ", ".join(f"md5(string_agg(COALESCE(CAST({_q(n)} AS VARCHAR),'\\x00'), '|')) AS {_q(n)}"
                        for n in names)
        row = con.execute(f"SELECT {sel} FROM (SELECT * FROM {S.glob_expr(ds_id)} LIMIT 50000)").df()
    except Exception:
        return []
    finally:
        con.close()
    seen: dict[str, str] = {}
    dups: list[tuple[str, str]] = []
    for n in names:
        h = str(row[n].iloc[0]) if n in row.columns else None
        if h is None:
            continue
        if h in seen:
            dups.append((seen[h], n))
        else:
            seen[h] = n
    return dups


# ═════════════════════════════════════════════════════════════ FUGA ══════════
def audit_leakage(ds_id: str, target: str, threshold: float = 0.98,
                  skip: list[str] | None = None, max_rows: int = 120_000) -> list[dict[str, Any]]:
    """Detecta columnas que contienen la respuesta.

    Adaptado del auditor de `probpago_core.auditar_leakage`, generalizado a
    cualquier dataset y a los tres tipos de tarea. Una AUC univariada de 0.99,
    una correlación de 0.999 o un nombre que replica al target son la firma
    de una columna que en producción no va a existir.
    """
    skip = set(skip or [])
    df = S.load_frame(ds_id, max_rows=max_rows)
    if target not in df.columns:
        return []
    y = df[target]
    task = P.infer_task(y)
    tnorm = re.sub(r"[^a-z0-9]", "", target.lower())
    out: list[dict[str, Any]] = []
    for c in df.columns:
        if c == target or c in skip:
            continue
        rel = P._association(df[c], y, task)
        cnorm = re.sub(r"[^a-z0-9]", "", c.lower())
        name_echo = (tnorm and tnorm in cnorm and cnorm != tnorm)
        if rel is None:
            continue
        strength = float(rel.get("strength") or 0.0)
        blocked, detail = False, ""
        if strength >= threshold:
            if rel["metric"] == "eta2" and not name_echo:
                # una categórica de pocos niveles no puede reconstruir un
                # target continuo: explica varianza ENTRE grupos, que en un
                # panel agregado es estructura legítima. Se marca, no se corta.
                detail = (f"Explica casi toda la varianza de «{target}» entre sus grupos "
                          f"(eta² = {rel['value']}). En un panel agregado suele ser "
                          f"estructura, no fuga: revisá si existe al momento de predecir.")
            else:
                blocked = True
                detail = (f"Asociación univariada casi perfecta con «{target}» "
                          f"({rel['metric']} = {rel['value']}).")
        elif name_echo and strength >= 0.85:
            blocked = True
            detail = (f"El nombre deriva de «{target}» y la asociación es muy alta "
                      f"({rel['metric']} = {rel['value']}).")
        elif strength >= threshold - 0.08:
            detail = (f"Asociación muy alta con «{target}» ({rel['metric']} = {rel['value']}). "
                      f"Revisar si esta columna existe al momento de predecir.")
        if detail:
            out.append({"column": c, "metric": rel["metric"], "value": rel["value"],
                        "strength": round(strength, 4), "blocked": blocked, "detail": detail})
    return sorted(out, key=lambda r: -r["strength"])


# ═══════════════════════════════════════════════════════════ COMPILACIÓN ═════
def compile_sql(ds_id: str, plan: dict[str, Any]) -> str:
    """Convierte el plan en una única sentencia SQL de DuckDB."""
    meta = S.load_meta(ds_id)
    order = {c["name"]: i for i, c in enumerate(meta.columns)}
    expr: dict[str, str] = {c["name"]: _q(c["name"]) for c in meta.columns}
    extra: list[tuple[str, str]] = []       # (alias, expresión) columnas nuevas
    drop: set[str] = set()
    where: list[str] = []
    distinct = False

    for s in plan.get("steps", []):
        if not s.get("enabled", True):
            continue
        op, col, p = s["op"], s.get("column"), s.get("params") or {}
        if col is not None and col not in expr and op != "drop_duplicates":
            continue
        e = expr.get(col, "")

        if op == "drop_column":
            drop.add(col)
        elif op == "cast_numeric":
            clean = f"regexp_replace(TRIM(CAST({e} AS VARCHAR)), '[\\$€£¥%\\s]', '', 'g')"
            if p.get("decimal_comma"):
                clean = f"replace(replace({clean}, '.', ''), ',', '.')"
            else:
                clean = f"replace({clean}, ',', '')"
            expr[col] = f"TRY_CAST({clean} AS DOUBLE)"
        elif op == "parse_datetime":
            expr[col] = f"TRY_CAST(TRIM(CAST({e} AS VARCHAR)) AS TIMESTAMP)"
        elif op == "trim_text":
            expr[col] = f"NULLIF(TRIM(CAST({e} AS VARCHAR)), '')"
            if p.get("lower"):
                expr[col] = f"lower({expr[col]})"
        elif op == "expand_datetime":
            for part in p.get("parts", ["year", "month", "day", "dow", "week"]):
                fn = {"year": "year", "month": "month", "day": "day",
                      "dow": "dayofweek", "week": "week", "hour": "hour",
                      "quarter": "quarter"}.get(part)
                if fn:
                    extra.append((f"{col}__{part}", f"{fn}(TRY_CAST({e} AS TIMESTAMP))"))
            drop.add(col)
        elif op == "missing_indicator":
            extra.append((f"{col}__faltante", f"CASE WHEN {e} IS NULL THEN 1 ELSE 0 END"))
        elif op == "impute_numeric":
            expr[col] = f"COALESCE({e}, {float(p.get('value', 0))})"
        elif op == "impute_categorical":
            v = str(p.get("value", "(sin dato)")).replace("'", "''")
            expr[col] = f"COALESCE(NULLIF(TRIM(CAST({e} AS VARCHAR)), ''), '{v}')"
        elif op == "clip_outliers":
            expr[col] = f"least(greatest({e}, {float(p['lo'])}), {float(p['hi'])})"
        elif op == "log_transform":
            expr[col] = f"ln(greatest({e}, 0) + 1)"
        elif op == "group_rare":
            keep = p.get("keep") or []
            other = str(p.get("other", "(otros)")).replace("'", "''")
            lst = ", ".join("'" + str(k).replace("'", "''") + "'" for k in keep)
            if lst:
                expr[col] = (f"CASE WHEN CAST({e} AS VARCHAR) IN ({lst}) "
                             f"THEN CAST({e} AS VARCHAR) ELSE '{other}' END")
        elif op == "filter_null_target":
            where.append(f"{expr.get(col, _q(col))} IS NOT NULL")
        elif op == "drop_duplicates":
            distinct = True
        elif op == "filter_rows":
            cond = str(p.get("sql", "")).strip()
            if cond and ";" not in cond:
                where.append(f"({cond})")

    keep_cols = [n for n in sorted(expr, key=lambda n: order.get(n, 999)) if n not in drop]
    select = [f"{expr[n]} AS {_q(n)}" for n in keep_cols]
    select += [f"{ex} AS {_q(alias)}" for alias, ex in extra]
    if not select:
        select = ["*"]
    sql = "SELECT " + ("DISTINCT " if distinct else "") + ",\n       ".join(select) + "\nFROM {t}"
    if where:
        sql += "\nWHERE " + "\n  AND ".join(where)
    return sql


# ═══════════════════════════════════════════════════════════ EJECUCIÓN ═══════
def execute(ds_id: str, plan: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    """Ejecuta el plan y materializa un dataset nuevo, en bloques."""
    sql = plan.get("sql") or compile_sql(ds_id, plan)
    parent = S.load_meta(ds_id)
    con = S.connect()
    try:
        full = sql.replace("{t}", S.glob_expr(ds_id))
        con.execute(f"CREATE OR REPLACE VIEW etl_out AS {full}")
        n_out = int(con.execute("SELECT count(*) FROM etl_out").fetchone()[0])

        def frames():
            step = S.settings.chunk_rows
            for off in range(0, max(n_out, 1), step):
                df = con.execute(f"SELECT * FROM etl_out LIMIT {step} OFFSET {off}").df()
                if df.empty:
                    break
                yield df

        meta = S.ingest_frames(
            frames(), name or f"{parent.name} · ETL", source="derived",
            origin={"parent": ds_id, "sql": sql,
                    "steps": [s for s in plan.get("steps", []) if s.get("enabled", True)]},
            parent_id=ds_id,
        )
    finally:
        con.close()

    return {
        "dataset": meta.to_dict(),
        "sql": sql,
        "rows_in": parent.rows, "rows_out": meta.rows,
        "rows_removed": parent.rows - meta.rows,
        "columns_in": len(parent.columns), "columns_out": len(meta.columns),
        "applied": [{"op": s["op"], "column": s.get("column"), "reason": s["reason"]}
                    for s in plan.get("steps", []) if s.get("enabled", True)],
    }
