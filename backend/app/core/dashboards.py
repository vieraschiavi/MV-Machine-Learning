"""Dashboards automáticos: KPIs, gráficos y tabla, deducidos del dataset.

No hay plantillas por rubro. El motor mira el perfil real —tipos, cardinalidad,
nombres, varianza— y decide qué merece un KPI, qué serie se grafica y por qué
dimensiones se puede filtrar. El mismo código arma el tablero de un panel de
cobranzas, de un CSV de ventas o de una extracción SQL.

Todo el cálculo es SQL sobre DuckDB contra el Parquet: los filtros y las
agregaciones corren fuera de memoria, así que el tablero de 200 filas y el de
20 millones responden igual.
"""
from __future__ import annotations

import math
import re
from typing import Any

from . import etl as E
from . import profiling as P
from . import storage as S

# nombres que delatan una métrica de negocio (es señal, no requisito)
MONEY_HINT = re.compile(
    r"(monto|importe|total|cobrado|cobrar|venta|revenue|amount|precio|price|"
    r"saldo|deuda|facturacion|ingreso|cost|gasto|valor)", re.I)
COUNT_HINT = re.compile(r"(cantidad|cuota|socio|cliente|count|unidade|qty|numero)", re.I)
PCT_HINT = re.compile(r"(porcentaje|pct|tasa|ratio|percent|_pc$)", re.I)
ID_LIKE = re.compile(r"(^id|_id$|codigo|uuid|nro)", re.I)

MAX_METRICS = 6
MAX_DIMENSIONS = 4
MAX_FILTER_LEVELS = 40


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _ex(exprs: dict[str, str] | None, col: str) -> str:
    """SQL de una columna: el nombre, o el casteo si el dato viene como texto.

    Un panel exportado a mano suele traer «401.593.821» y «2023-01» guardados
    como texto: sin castearlos, la métrica más importante del dataset y su eje
    temporal quedan afuera del tablero.
    """
    return (exprs or {}).get(col) or _q(col)


# columnas de período escritas como texto: 2023-01, 2023/01, 202301, 01/2023
PERIODO = re.compile(r"^\s*(\d{4}[-/](0[1-9]|1[0-2])|\d{6}|(0[1-9]|1[0-2])[-/]\d{4})\s*$")
# magnitudes que se promedian: sumar días de atraso o una edad no significa nada
AVG_HINT = re.compile(r"(dias|days|edad|age|antiguedad|promedio|average|mean|"
                      r"score|puntaje|indice|index)", re.I)


def _derived(ds_id: str, cols: list[dict]) -> tuple[dict[str, str], dict[str, str], dict[str, dict]]:
    """Columnas de texto que en realidad son número o período.

    Devuelve la expresión SQL de cada una y qué tipo pasa a tener, reusando el
    mismo detector que usa el ETL para no tener dos criterios distintos.
    """
    exprs: dict[str, str] = {}
    tipos: dict[str, str] = {}
    stats: dict[str, dict] = {}
    for c in cols:
        if c["kind"] not in ("categorical", "text") or c["constant"]:
            continue
        name = c["name"]
        try:
            muestra = S.query(ds_id, f"SELECT CAST({_q(name)} AS VARCHAR) v FROM {{t}} "
                                     f"WHERE {_q(name)} IS NOT NULL LIMIT 200")["v"].astype(str)
        except Exception:
            continue
        if muestra.empty:
            continue
        if float(muestra.str.match(PERIODO).mean()) >= 0.95:
            v = f"replace(replace(TRIM(CAST({_q(name)} AS VARCHAR)), '/', '-'), ' ', '')"
            # 202301 y 01-2023 se llevan a 2023-01 antes de fechar
            v = (f"CASE WHEN length({v}) = 6 AND {v} NOT LIKE '%-%' "
                 f"THEN substr({v}, 1, 4) || '-' || substr({v}, 5, 2) "
                 f"WHEN substr({v}, 3, 1) = '-' "
                 f"THEN substr({v}, 4, 4) || '-' || substr({v}, 1, 2) ELSE {v} END")
            exprs[name] = f"TRY_CAST({v} || '-01' AS TIMESTAMP)"
            tipos[name] = "datetime"
            continue
        try:
            det = E._detect_cast(ds_id, name, c)
        except Exception:
            det = None
        if det and det.get("as") == "numeric" and det.get("ratio", 0) >= 0.95:
            limpio = (f"regexp_replace(TRIM(CAST({_q(name)} AS VARCHAR)), "
                      f"'[\\$€£¥%\\s]', '', 'g')")
            limpio = (f"replace(replace({limpio}, '.', ''), ',', '.')"
                      if det.get("decimal_comma")
                      else f"replace({limpio}, ',', '')")
            exprs[name] = f"TRY_CAST({limpio} AS DOUBLE)"
            tipos[name] = "numeric"
            st = _stats_of(ds_id, exprs[name])
            if st is None:               # todo nulo o constante: no es métrica
                del exprs[name], tipos[name]
                continue
            stats[name] = st
    return exprs, tipos, stats


def _stats_of(ds_id: str, expr: str) -> dict[str, float] | None:
    """Dispersión de una columna derivada, que el perfil no pudo calcular."""
    try:
        r = S.query(ds_id, f"SELECT avg({expr}) m, stddev_samp({expr}) s, "
                           f"min({expr}) lo, max({expr}) hi FROM {{t}}")
    except Exception:
        return None
    m, s = r["m"].iloc[0], r["s"].iloc[0]
    if m is None or s is None or not math.isfinite(float(s)) or float(s) == 0:
        return None
    return {"mean": float(m), "std": float(s), "cv": abs(float(s) / float(m)) if m else 0.0,
            "min": float(r["lo"].iloc[0]), "max": float(r["hi"].iloc[0])}


# ═══════════════════════════════════════════════════════ especificación ══════
def detect_spec(ds_id: str) -> dict[str, Any]:
    """Analiza el dataset y propone el tablero: KPIs, gráficos, filtros, tabla."""
    prof = P.profile(ds_id)
    cols = prof["columns"]
    exprs, tipos, stats = _derived(ds_id, cols)
    # una columna de texto que resultó ser número o período se trata como tal
    cols = [dict(c, kind=tipos.get(c["name"], c["kind"]),
                 stats=stats.get(c["name"], c.get("stats")))
            for c in cols]

    tiempo = _pick_time(cols, ds_id, exprs)
    metricas = _pick_metrics(cols)
    dimensiones = _pick_dimensions(cols, prof["rows"])
    ml = _pick_ml(cols)

    kpis = _build_kpis(metricas, ml, tiempo, prof["rows"])
    charts = _build_charts(metricas, dimensiones, tiempo, ml)
    filtros = _build_filters(ds_id, dimensiones, tiempo, exprs)

    return {
        "dataset_id": ds_id,
        "expressions": exprs,
        "title": prof["name"],
        "rows": prof["rows"],
        "time_column": tiempo,
        "metrics": metricas,
        "dimensions": [d["name"] for d in dimensiones],
        "ml_columns": ml,
        "kpis": kpis,
        "charts": charts,
        "filters": filtros,
        "table": {"columns": [c["name"] for c in cols][:24], "page_size": 50},
        "notes": _notes(tiempo, metricas, dimensiones, ml),
    }


def _pick_time(cols: list[dict], ds_id: str, exprs: dict[str, str]) -> str | None:
    fechas = [c for c in cols if c["kind"] == "datetime"]
    if not fechas:
        return None
    # la de mayor cardinalidad suele ser la observación, no un vencimiento fijo
    return max(fechas, key=lambda c: c["distinct"])["name"]


def _pick_metrics(cols: list[dict]) -> list[dict[str, Any]]:
    """Numéricas que informan, ordenadas por cuánto parecen 'de negocio'."""
    candidatas = []
    for c in cols:
        # una magnitud continua no repite nunca y sigue siendo métrica: la
        # exclusión por unicidad sólo vale para claves con nombre de clave
        if c["kind"] != "numeric" or c["constant"]:
            continue
        if ID_LIKE.search(c["name"]):
            continue
        st = c.get("stats") or {}
        if st.get("std") in (None, 0):
            continue
        es_conteo = bool(COUNT_HINT.search(c["name"]))
        es_monto = bool(MONEY_HINT.search(c["name"])) and not es_conteo
        es_pct = bool(PCT_HINT.search(c["name"]) or
                      (st.get("min", 0) >= 0 and st.get("max", 0) <= 100 and
                       "pct" in c["name"].lower()))
        # el monto manda; el conteo acompaña; el porcentaje se promedia
        puntaje = (3.0 if es_monto else (2.0 if es_pct else (1.2 if es_conteo else 0.5)))
        puntaje += min((st.get("cv") or 0), 1.0)          # variar informa
        # sumar días de atraso, edades o puntajes no significa nada: se promedian
        promedia = es_pct or bool(AVG_HINT.search(c["name"]))
        candidatas.append({"name": c["name"], "score": round(puntaje, 2),
                           "format": "percent" if es_pct else ("money" if es_monto else "number"),
                           "agg": "avg" if promedia else "sum"})
    candidatas.sort(key=lambda m: -m["score"])
    return candidatas[:MAX_METRICS]


def _pick_dimensions(cols: list[dict], rows: int) -> list[dict[str, Any]]:
    """Categóricas de baja cardinalidad: por ellas se filtra y se agrupa."""
    out = []
    for c in cols:
        if c["kind"] != "categorical" or c.get("is_text") or c["constant"]:
            continue
        if 2 <= c["distinct"] <= min(MAX_FILTER_LEVELS, max(rows // 5, 2)):
            out.append({"name": c["name"], "levels": c["distinct"]})
    out.sort(key=lambda d: d["levels"])
    return out[:MAX_DIMENSIONS]


def _pick_ml(cols: list[dict]) -> dict[str, Any]:
    """Columnas que dejó un scoring: probabilidades y predicción."""
    probas = [c["name"] for c in cols if c["name"].startswith("prob_")]
    pred = next((c["name"] for c in cols if c["name"] == "prediccion"), None)
    return {"probabilities": probas, "prediction": pred}


def _build_kpis(metricas, ml, tiempo, rows) -> list[dict[str, Any]]:
    kpis: list[dict[str, Any]] = [{
        "id": "filas", "label": "Registros", "kind": "rows", "format": "number",
    }]
    for m in metricas[:4]:
        kpis.append({
            "id": f"{m['agg']}_{m['name']}", "label": titulo(m["name"]), "kind": "metric",
            "column": m["name"], "agg": m["agg"], "format": m["format"],
            "delta_vs_prev": bool(tiempo),      # variación contra el período anterior
        })
    if ml["probabilities"]:
        kpis.append({"id": "prob_media", "label": titulo(ml["probabilities"][0]),
                     "kind": "metric", "column": ml["probabilities"][0],
                     "agg": "avg", "format": "percent_unit"})
    return kpis


def _build_charts(metricas, dimensiones, tiempo, ml) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []
    if tiempo and metricas:
        for m in metricas[:2]:
            charts.append({"id": f"serie_{m['name']}", "type": "line",
                           "x": tiempo, "grain": "month",
                           "y": m["name"], "agg": m["agg"], "format": m["format"],
                           "title": f"{m['name']} por mes"})
    for d in dimensiones[:2]:
        if metricas:
            m = metricas[0]
            charts.append({"id": f"por_{d['name']}", "type": "bars",
                           "x": d["name"], "y": m["name"], "agg": m["agg"],
                           "format": m["format"],
                           "title": f"{m['name']} por {d['name']}"})
        else:
            charts.append({"id": f"conteo_{d['name']}", "type": "bars",
                           "x": d["name"], "y": None, "agg": "count",
                           "format": "number", "title": f"Registros por {d['name']}"})
    if metricas:
        charts.append({"id": f"dist_{metricas[0]['name']}", "type": "histogram",
                       "column": metricas[0]["name"],
                       "title": f"Distribución de {metricas[0]['name']}"})
    if ml["probabilities"]:
        charts.append({"id": "dist_prob", "type": "histogram",
                       "column": ml["probabilities"][0],
                       "title": f"Distribución de {ml['probabilities'][0]}"})
    return charts[:6]


def _build_filters(ds_id, dimensiones, tiempo, exprs=None) -> list[dict[str, Any]]:
    filtros = []
    if tiempo:
        qt = _ex(exprs, tiempo)
        r = S.query(ds_id, f"SELECT min({qt}) a, max({qt}) b FROM {{t}}")
        filtros.append({"id": tiempo, "type": "daterange", "column": tiempo,
                        "min": str(r["a"].iloc[0]), "max": str(r["b"].iloc[0])})
    for d in dimensiones:
        vals = S.query(ds_id, f"""
            SELECT CAST({_q(d['name'])} AS VARCHAR) v, count(*) c FROM {{t}}
            WHERE {_q(d['name'])} IS NOT NULL GROUP BY 1 ORDER BY c DESC
            LIMIT {MAX_FILTER_LEVELS}""")
        filtros.append({"id": d["name"], "type": "multiselect", "column": d["name"],
                        "options": [str(v) for v in vals["v"]]})
    return filtros


def titulo(col: str) -> str:
    """«PorcentajeTotalCobrado» → «Porcentaje total cobrado».

    Los nombres de columna vienen pegados o en mayúsculas y el tablero los
    mostraba tal cual: ilegibles de un vistazo.
    """
    s = re.sub(r"[_\-]+", " ", col)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:1].upper() + s[1:].lower() if s.isupper() else s[:1].upper() + s[1:]


def _notes(tiempo, metricas, dimensiones, ml) -> list[str]:
    notas = []
    if tiempo:
        notas.append(f"Serie temporal detectada en «{titulo(tiempo)}»: los KPIs "
                     f"comparan contra el mes anterior, contra el mismo mes del "
                     f"año pasado y el acumulado del año contra el anterior.")
    if not metricas:
        notas.append("No se detectaron métricas numéricas de negocio: el tablero "
                     "muestra conteos por categoría.")
    if ml["probabilities"]:
        notas.append("El dataset trae columnas de scoring: se agregan los KPIs del modelo.")
    return notas


# ═══════════════════════════════════════════════════════════ ejecución ═══════
def _where(spec: dict, filters: dict[str, Any] | None) -> tuple[str, list]:
    """Compila los filtros activos a un WHERE parametrizado (sin inyección)."""
    if not filters:
        return "", []
    conds, params = [], []
    validos = {f["column"]: f for f in spec.get("filters", [])}
    for col, valor in filters.items():
        f = validos.get(col)
        if f is None or valor in (None, "", []):
            continue
        q = _ex(spec.get("expressions"), col)
        if f["type"] == "daterange":
            desde, hasta = (valor.get("from"), valor.get("to")) if isinstance(valor, dict) else (None, None)
            if desde:
                conds.append(f"{q} >= CAST(? AS TIMESTAMP)")
                params.append(str(desde))
            if hasta:
                # el día 'hasta' entra entero, pero la medianoche del siguiente no:
                # con datos mensuales, <= sumando un día colaba el mes de más
                conds.append(f"{q} < CAST(? AS TIMESTAMP) + INTERVAL 1 DAY")
                params.append(str(hasta))
        else:
            valores = valor if isinstance(valor, list) else [valor]
            marcas = ", ".join("?" for _ in valores)
            conds.append(f"CAST({q} AS VARCHAR) IN ({marcas})")
            params.extend(str(v) for v in valores)
    return (" WHERE " + " AND ".join(conds)) if conds else "", params


def _and(where: str, cond: str) -> str:
    """Suma una condición al WHERE ya compilado, exista o no."""
    return f"{where} AND {cond}" if where else f" WHERE {cond}"


def run(ds_id: str, spec: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ejecuta el tablero con los filtros activos y devuelve todos los datos.

    El spec se deduce siempre acá, del dataset: nada de lo que llega del
    navegador entra en el SQL salvo los filtros, y esos van parametrizados.
    """
    spec = detect_spec(ds_id)
    exprs = spec.get("expressions") or {}
    where, params = _where(spec, filters)
    tiempo = spec.get("time_column")

    out: dict[str, Any] = {"spec": spec, "filters": filters or {}}
    out["kpis"] = [_run_kpi(ds_id, k, where, params, tiempo, exprs) for k in spec["kpis"]]
    out["charts"] = [_run_chart(ds_id, c, where, params, exprs) for c in spec["charts"]]

    tabla_cols = ", ".join(_q(c) for c in spec["table"]["columns"])
    df = S.query(ds_id, f"SELECT {tabla_cols} FROM {{t}}{where} "
                        f"LIMIT {int(spec['table']['page_size'])}", params)
    total = S.query(ds_id, f"SELECT count(*) n FROM {{t}}{where}", params)
    import json as _json
    out["table"] = {
        "columns": spec["table"]["columns"],
        "rows": _json.loads(df.to_json(orient="records", date_format="iso")),
        "total": int(total["n"].iloc[0]),
    }
    return out


def _run_kpi(ds_id, kpi, where, params, tiempo, exprs=None) -> dict[str, Any]:
    if kpi["kind"] == "rows":
        df = S.query(ds_id, f"SELECT count(*) v FROM {{t}}{where}", params)
        return {**kpi, "value": float(df["v"].iloc[0])}
    q = _ex(exprs, kpi["column"])
    agg = {"sum": f"sum({q})", "avg": f"avg({q})", "min": f"min({q})",
           "max": f"max({q})"}[kpi["agg"]]
    df = S.query(ds_id, f"SELECT {agg} v FROM {{t}}{where}", params)
    valor = df["v"].iloc[0]
    ok = valor is not None and math.isfinite(float(valor))
    resultado = {**kpi, "value": float(valor) if ok else None}

    if kpi.get("delta_vs_prev") and tiempo:
        resultado["comparisons"] = _comparaciones(ds_id, kpi, agg, where, params,
                                                  _ex(exprs, tiempo))
        # se conserva la variación mensual suelta: la usa la exportación
        mes = next((c for c in resultado["comparisons"] if c["id"] == "mom"), None)
        if mes:
            resultado["delta_pct"] = mes.get("delta_pct")
            resultado["delta_period"] = resultado["comparisons"][0].get("period")
    return resultado


def _num(v) -> float | None:
    """El valor como número, o None si vino nulo o no finito."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _comparaciones(ds_id, kpi, agg, where, params, qt) -> list[dict[str, Any]]:
    """Mes contra mes, año contra año y acumulado del año contra el anterior.

    Una métrica que ya es un porcentaje no varía «un 8 % más»: varía **8 puntos
    porcentuales**. Mezclar las dos unidades es el error clásico de estos
    tableros, así que cada comparación dice en qué unidad está expresada.
    """
    serie = S.query(ds_id, f"""
        SELECT date_trunc('month', {qt}) p, {agg} v FROM {{t}}{where}
        GROUP BY 1 ORDER BY 1""", params)
    if serie.empty:
        return []
    serie = serie.dropna(subset=["p"])
    if serie.empty:
        return []

    periodos = [str(p)[:7] for p in serie["p"]]
    valores = {periodos[i]: _num(serie["v"].iloc[i]) for i in range(len(periodos))}
    actual = periodos[-1]
    anio, mes = int(actual[:4]), int(actual[5:7])
    es_pct = kpi.get("format") == "percent"

    def _mismo_mes(a: int) -> str:
        return f"{a:04d}-{mes:02d}"

    def _acumulado(a: int) -> float | None:
        """Acumulado del año hasta el mes actual: se comparan tramos iguales."""
        vs = [valores[f"{a:04d}-{m:02d}"] for m in range(1, mes + 1)
              if valores.get(f"{a:04d}-{m:02d}") is not None]
        if not vs:
            return None
        return sum(vs) / len(vs) if kpi["agg"] == "avg" or es_pct else sum(vs)

    candidatas = [
        ("mom", "mes anterior", valores.get(actual),
         valores.get(f"{anio:04d}-{mes - 1:02d}" if mes > 1 else f"{anio - 1:04d}-12")),
        ("yoy", "mismo mes del año anterior", valores.get(actual),
         valores.get(_mismo_mes(anio - 1))),
        ("ytd", "acumulado del año anterior", _acumulado(anio), _acumulado(anio - 1)),
    ]

    out: list[dict[str, Any]] = []
    for cid, etiqueta, hoy, antes in candidatas:
        if hoy is None or antes is None:
            continue
        comp = {"id": cid, "label": etiqueta, "period": actual,
                "value": hoy, "previous": antes, "unit": "pp" if es_pct else "pct"}
        if es_pct:
            comp["delta_pp"] = round(hoy - antes, 2)
            comp["direction"] = 1 if comp["delta_pp"] > 0 else (-1 if comp["delta_pp"] < 0 else 0)
        elif antes != 0:
            comp["delta_pct"] = round((hoy / antes - 1) * 100, 2)
            comp["direction"] = 1 if comp["delta_pct"] > 0 else (-1 if comp["delta_pct"] < 0 else 0)
        else:
            continue                       # dividir por cero no informa nada
        out.append(comp)
    return out


def _run_chart(ds_id, chart, where, params, exprs=None) -> dict[str, Any]:
    t = dict(chart)
    if chart["type"] == "line":
        qx, qy = _ex(exprs, chart["x"]), _ex(exprs, chart["y"])
        agg = f"sum({qy})" if chart["agg"] == "sum" else f"avg({qy})"
        # el grano se valida contra la lista, nunca se interpola lo que llegue
        grano = chart.get("grain", "month")
        if grano not in ("day", "week", "month", "quarter", "year"):
            grano = "month"
        df = S.query(ds_id, f"""
            SELECT date_trunc('{grano}', {qx}) x, {agg} y
            FROM {{t}}{where} GROUP BY 1 ORDER BY 1""", params)
        t["data"] = [{"x": str(a)[:10], "y": None if b is None else float(b)}
                     for a, b in zip(df["x"], df["y"], strict=False)]
    elif chart["type"] == "bars":
        qx = _ex(exprs, chart["x"])
        qy = _ex(exprs, chart["y"]) if chart["y"] else None
        agg = ("count(*)" if chart["y"] is None else
               (f"sum({qy})" if chart["agg"] == "sum" else f"avg({qy})"))
        df = S.query(ds_id, f"""
            SELECT CAST({qx} AS VARCHAR) x, {agg} y
            FROM {{t}}{_and(where, f"{qx} IS NOT NULL")}
            GROUP BY 1 ORDER BY y DESC LIMIT 14""", params)
        t["data"] = [{"x": str(a), "y": None if b is None else float(b)}
                     for a, b in zip(df["x"], df["y"], strict=False)]
    elif chart["type"] == "histogram":
        q = _ex(exprs, chart["column"])
        r = S.query(ds_id, f"""
            SELECT quantile_cont({q}, 0.01) lo, quantile_cont({q}, 0.99) hi
            FROM {{t}}{where}""", params)
        lo, hi = r["lo"].iloc[0], r["hi"].iloc[0]
        # con 0 filas filtradas los percentiles llegan como NaN, no como None:
        # interpolar nan en el SQL haría que DuckDB lo lea como columna
        if (lo is None or hi is None
                or not math.isfinite(float(lo)) or not math.isfinite(float(hi))
                or float(hi) <= float(lo)):
            t["data"] = []
        else:
            w = (float(hi) - float(lo)) / 20
            cond = f"{q} IS NOT NULL AND {q} BETWEEN {float(lo)} AND {float(hi)}"
            df = S.query(ds_id, f"""
                SELECT least(floor(({q} - {float(lo)}) / {w}), 19) b, count(*) c
                FROM {{t}}{_and(where, cond)}
                GROUP BY 1 ORDER BY 1""", params)
            cuentas = {int(b): int(c) for b, c in zip(df["b"], df["c"], strict=False) if b is not None}
            t["data"] = [{"x": float(lo) + i * w, "y": cuentas.get(i, 0)} for i in range(20)]
    return t


# ═══════════════════════════════════════════════════════ exportación ═════════
def export(ds_id: str, spec: dict | None, filters: dict | None,
           fmt: str = "xlsx") -> dict[str, Any]:
    """Exporta el estado filtrado del tablero: KPIs + datos de cada gráfico +
    la tabla completa (no sólo la página visible)."""
    import time as _t

    from . import workspace

    datos = run(ds_id, spec, filters)
    spec = datos["spec"]
    where, params = _where(spec, filters)
    stamp = _t.strftime("%Y%m%d-%H%M%S")

    if fmt == "csv":
        out = workspace.dir_for("exports") / f"tablero_{stamp}.csv"
        cols = ", ".join(_q(c) for c in spec["table"]["columns"])
        con = S.connect()
        try:
            full = f"SELECT {cols} FROM {S.glob_expr(ds_id)}{where}"
            con.execute(f"COPY ({full}) TO '{out.as_posix()}' "
                        f"(HEADER, DELIMITER ';')", params)
        finally:
            con.close()
        return {"path": str(out), "filename": out.name, "format": "csv",
                "rows": datos["table"]["total"]}

    import xlsxwriter

    from .exporter import _fmts, _header, _title, _v
    out = workspace.dir_for("exports") / f"tablero_{stamp}.xlsx"
    wb = xlsxwriter.Workbook(str(out), {"constant_memory": True, "nan_inf_to_errors": True})
    f = _fmts(wb)

    ws = wb.add_worksheet("KPIs")
    _title(ws, f, f"TABLERO — {spec['title']}", 4)
    _header(ws, f, 2, ["KPI", "Valor", "Variación vs período anterior", "Período"],
            [34, 20, 26, 12])
    for i, k in enumerate(datos["kpis"], start=3):
        ws.write(i, 0, k["label"], f["cell"])
        fmt_celda = {"money": f["money"], "percent": f["pct"], "percent_unit": f["pct"],
                     "number": f["int"]}.get(k["format"], f["num"])
        v = k.get("value")
        if k["format"] == "percent_unit" and v is not None:
            v = v * 100
        ws.write(i, 1, _v(v), fmt_celda)
        ws.write(i, 2, _v(k.get("delta_pct")), f["pct"])
        ws.write(i, 3, _v(k.get("delta_period") or ""), f["cell"])
    fila = 4 + len(datos["kpis"])
    if filters:
        ws.write(fila, 0, f"Filtros aplicados: {filters}", f["cell"])

    for ch in datos["charts"]:
        nombre = re.sub(r"[^\w ]", "", ch["title"])[:28] or ch["id"][:28]
        ws = wb.add_worksheet(nombre)
        _title(ws, f, ch["title"].upper(), 2)
        _header(ws, f, 2, [ch.get("x") or ch.get("column") or "x", "valor"], [30, 20])
        for i, punto in enumerate(ch.get("data") or [], start=3):
            ws.write(i, 0, _v(punto["x"]), f["cell"])
            ws.write(i, 1, _v(punto["y"]), f["num"])

    ws = wb.add_worksheet("Datos")
    cols = spec["table"]["columns"]
    _header(ws, f, 0, cols, [max(12, min(26, len(c) + 5)) for c in cols])
    paso = 50_000
    fila = 1
    total = datos["table"]["total"]
    for off in range(0, max(total, 1), paso):
        df = S.query(ds_id, f"SELECT {', '.join(_q(c) for c in cols)} FROM {{t}}{where} "
                            f"LIMIT {paso} OFFSET {off}", params)
        if df.empty:
            break
        for rec in df.itertuples(index=False, name=None):
            for j, v in enumerate(rec):
                ws.write(fila, j, _v(v), f["cell"])
            fila += 1
    from .exporter import _marca_de_agua
    _marca_de_agua(wb, f)
    wb.close()
    return {"path": str(out), "filename": out.name, "format": "xlsx", "rows": total}
