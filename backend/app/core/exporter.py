"""Exportación de resultados: Excel corporativo, CSV y Parquet.

El Excel mantiene el formato aprobado (encabezados azul 1E3A8A, semáforos
verde/ámbar/rojo, montos con separador de miles, porcentajes con un decimal)
y se escribe en modo *constant memory*: las filas se vuelcan a disco a medida
que se generan, así que un listado de un millón de filas no infla la RAM.

Excel tope en 1.048.576 filas por hoja. Cuando el resultado supera ese límite,
el listado se parte en hojas sucesivas y se avisa en el resumen; si aun así no
entra, se recomienda CSV o Parquet, que no tienen tope.
"""
from __future__ import annotations

import math
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import settings  # noqa: F401
from . import storage as S
from . import workspace

AZUL, VERDE, AMBAR, ROJO, GRIS = "#1E3A8A", "#C6EFCE", "#FFEB9C", "#FFC7CE", "#F2F2F2"
XLSX_MAX_ROWS = 1_048_575


def _fmts(wb):
    base = {"border": 1, "border_color": "#BFBFBF"}
    return {
        "title": wb.add_format({"bold": True, "font_size": 13, "font_color": "white",
                                "bg_color": AZUL, "valign": "vcenter", "indent": 1}),
        "sub": wb.add_format({"italic": True, "font_size": 9, "font_color": "#555555"}),
        "head": wb.add_format({"bold": True, "font_color": "white", "bg_color": AZUL,
                               "font_size": 10, "align": "center", "valign": "vcenter",
                               "text_wrap": True, **base}),
        "cell": wb.add_format(base),
        "num": wb.add_format({"num_format": "#,##0.0000", **base}),
        "int": wb.add_format({"num_format": "#,##0", **base}),
        "money": wb.add_format({"num_format": '"$"#,##0', **base}),
        "pct": wb.add_format({"num_format": '0.0"%"', **base}),
        "pct2": wb.add_format({"num_format": '0.00"%"', **base}),
        "ok": wb.add_format({"bg_color": VERDE, "align": "center", **base}),
        "warn": wb.add_format({"bg_color": AMBAR, "align": "center", **base}),
        "bad": wb.add_format({"bg_color": ROJO, "align": "center", **base}),
        "grey": wb.add_format({"bg_color": GRIS, "align": "center", **base}),
        "bold": wb.add_format({"bold": True, **base}),
        "wrap": wb.add_format({"text_wrap": True, "valign": "top", **base}),
    }


def _sem(f, estado: str):
    return {"OK": f["ok"], "REVISAR": f["warn"], "ALERTA": f["bad"]}.get(estado, f["grey"])


def _title(ws, f, text, width):
    ws.merge_range(0, 0, 0, max(width - 1, 1), text, f["title"])
    ws.set_row(0, 26)


def _header(ws, f, row, heads, widths=None):
    for j, h in enumerate(heads):
        ws.write(row, j, h, f["head"])
    ws.set_row(row, 30)
    if widths:
        for j, w in enumerate(widths):
            ws.set_column(j, j, w)


def _v(x):
    """Valor apto para Excel: sin NaN, sin infinitos, sin objetos raros."""
    if x is None:
        return ""
    if isinstance(x, (np.floating, float)):
        return "" if not math.isfinite(float(x)) else float(x)
    if isinstance(x, (np.integer, int)):
        return int(x)
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (list, dict)):
        return str(x)[:400]
    return str(x)


# ═════════════════════════════════════════════════════════════ INFORME ════════
def build_report(path: Path, *, report: dict | None = None, profile: dict | None = None,
                 etl: dict | None = None, dataset_id: str | None = None,
                 data_limit: int = 200_000, title: str = "MV AutoML Studio") -> dict[str, Any]:
    """Genera el Excel completo con todas las hojas que correspondan."""
    import xlsxwriter

    t0 = time.time()
    wb = xlsxwriter.Workbook(str(path), {"constant_memory": True, "nan_inf_to_errors": True})
    f = _fmts(wb)
    sheets: list[str] = []

    if report:
        _sheet_resumen(wb, f, report, title)
        sheets.append("Resumen Ejecutivo")
        _sheet_leaderboard(wb, f, report)
        sheets.append("Comparativa de Modelos")
        _sheet_variables(wb, f, report)
        sheets.append("Analisis de Variables")
        if _sheet_diagnostico(wb, f, report):
            sheets.append("Diagnostico Holdout")
    if profile:
        _sheet_calidad(wb, f, profile)
        sheets.append("Calidad de Datos")
        _sheet_estadisticas(wb, f, profile)
        sheets.append("Analisis Estadistico")
    if etl:
        _sheet_etl(wb, f, etl)
        sheets.append("Plan de ETL")
    if dataset_id:
        n = _sheet_datos(wb, f, dataset_id, data_limit)
        sheets.append(f"Datos ({n:,} filas)")

    if not sheets:
        ws = wb.add_worksheet("Sin contenido")
        _title(ws, f, "No se seleccionó ningún contenido para exportar.", 6)
    wb.close()
    return {"path": str(path), "sheets": sheets, "seconds": round(time.time() - t0, 1),
            "size_bytes": path.stat().st_size}


def _sheet_resumen(wb, f, r, title):
    ws = wb.add_worksheet("Resumen Ejecutivo")
    ws.set_column(0, 0, 38)
    ws.set_column(1, 1, 20)
    ws.set_column(2, 2, 16)
    ws.set_column(3, 3, 14)
    ws.set_column(4, 4, 62)
    ch = r["champion"]
    _title(ws, f, f"{title} — {r['target']} · {r['task_label']} · "
                  f"modelo {ch['model']} · {r['rows_used']:,} filas", 5)
    ws.write(1, 0, "El número que se reporta sale del holdout ciego: la ventana que no se usó "
                   "para elegir hiperparámetros, features, calibración ni modelo campeón.", f["sub"])

    row = 3
    _header(ws, f, row, ["Métrica", "Valor", "Referencia", "Estado", "Qué significa"])
    row += 1
    for m, v in ch["holdout"].items():
        if m in ("n", "threshold", "positive_rate") or v is None:
            continue
        info = _metric_info(m)
        estado = _estado(m, v)
        ws.write(row, 0, info["nombre"], f["cell"])
        ws.write(row, 1, _v(v), f["pct"] if info["pct"] else f["num"])
        ws.write(row, 2, info["ref"], f["cell"])
        ws.write(row, 3, estado, _sem(f, estado))
        ws.write(row, 4, info["texto"], f["wrap"])
        row += 1

    row += 1
    _header(ws, f, row, ["Protocolo de validación", "Detalle", "", "", ""])
    row += 1
    sp = r["split"]
    for k, v in [
        ("Partición", f"{sp['mode']} · {sp['train']:,} entrenamiento / {sp['selection']:,} selección / "
                      f"{sp['holdout']:,} holdout ciego"),
        ("Columna temporal", sp.get("time_column") or "no declarada (partición no temporal)"),
        ("Métrica de decisión", f"{r['metric']} — {r['metric_info']['explanation']}"),
        ("Degradación selección → holdout",
         f"{ch['gap']:+.4f}" if ch.get("gap") is not None else "no calculable"),
        ("Modelos comparados", ", ".join(b["model"] for b in r["leaderboard"])),
        ("Calibración de probabilidad", "isotónica aplicada" if ch.get("calibrated") else "no aplicada"),
        ("Transformación del objetivo",
         f"logarítmica con smearing {r['target_transform']['smearing']:.3f}"
         if r["target_transform"]["log"] else "ninguna"),
        ("Features usadas", f"{r['n_features_used']} de {r['n_features_in']} columnas de entrada"),
        ("Tiempo de entrenamiento", f"{r['seconds']} segundos"),
    ]:
        ws.write(row, 0, k, f["bold"])
        ws.merge_range(row, 1, row, 4, _v(v), f["wrap"])
        row += 1

    row += 1
    _header(ws, f, row, ["Lectura del resultado", "", "", "", ""])
    row += 1
    for n in r["verdict"]["notes"]:
        est = {"ok": "OK", "revisar": "REVISAR", "alerta": "ALERTA"}.get(n["level"], "INFO")
        ws.write(row, 0, est, _sem(f, est))
        ws.merge_range(row, 1, row, 4, n["text"], f["wrap"])
        row += 1
    if r["features"].get("narrative"):
        row += 1
        _header(ws, f, row, ["Lectura de las variables", "", "", "", ""])
        row += 1
        for t in r["features"]["narrative"]:
            ws.merge_range(row, 0, row, 4, t, f["wrap"])
            row += 1


def _metric_info(m: str) -> dict[str, Any]:
    from . import metrics as MT
    nombres = {"auc": "AUC (holdout ciego)", "pr_auc": "PR-AUC", "ks": "KS",
               "brier": "Brier", "ece": "ECE (calibración)", "logloss": "Log loss",
               "accuracy": "Exactitud", "balanced_accuracy": "Exactitud balanceada",
               "precision": "Precisión", "recall": "Recall (cobertura)", "f1": "F1",
               "f1_macro": "F1 macro", "lift_10": "Lift del decil 1",
               "r2": "R²", "rmse": "RMSE", "mae": "MAE", "mape": "MAPE",
               "wmape": "WMAPE", "smape": "SMAPE", "bias": "Sesgo agregado"}
    refs = {"auc": ">= 0,85", "pr_auc": "> tasa base", "ks": ">= 0,30", "brier": "< 0,20",
            "ece": "< 0,05", "r2": "> 0", "wmape": "< 20%", "bias": "±5%",
            "balanced_accuracy": "> 60%", "f1_macro": "> 0,60"}
    pct = m in ("accuracy", "balanced_accuracy", "precision", "recall", "mape",
                "wmape", "smape", "bias")
    return {"nombre": nombres.get(m, m), "ref": refs.get(m, "—"),
            "texto": MT.CATALOG.get(m, (True, "", ""))[2], "pct": pct}


def _estado(m: str, v: float) -> str:
    try:
        v = float(v)
    except Exception:
        return "INFO"
    reglas = {"auc": lambda x: "ALERTA" if x >= 0.99 else ("OK" if x >= 0.75 else "REVISAR"),
              "ks": lambda x: "OK" if x >= 0.30 else "REVISAR",
              "brier": lambda x: "OK" if x < 0.20 else "REVISAR",
              "ece": lambda x: "OK" if x < 0.05 else "REVISAR",
              "r2": lambda x: "OK" if x > 0.5 else ("REVISAR" if x > 0 else "ALERTA"),
              "wmape": lambda x: "OK" if x < 0.20 else "REVISAR",
              "bias": lambda x: "OK" if abs(x) < 0.05 else "REVISAR",
              "balanced_accuracy": lambda x: "OK" if x > 0.6 else "REVISAR"}
    return reglas.get(m, lambda _: "INFO")(v)


def _sheet_leaderboard(wb, f, r):
    ws = wb.add_worksheet("Comparativa de Modelos")
    metric = r["metric"]
    keys = [k for k in r["leaderboard"][0]["holdout"].keys()
            if k not in ("n", "threshold", "positive_rate")]
    heads = ["Modelo", "Tipo", f"{metric} selección", f"{metric} holdout", "Degradación",
             "Configuraciones probadas", "Calibrado"] + [f"{k} holdout" for k in keys]
    _title(ws, f, "COMPARATIVA — cada modelo medido en la ventana de selección y en el holdout ciego",
           len(heads))
    ws.write(1, 0, "La ventana de selección es con la que se eligió el modelo y siempre se ve mejor "
                   "de lo que el modelo es. La columna que vale es la del holdout.", f["sub"])
    _header(ws, f, 3, heads, [46, 13, 17, 17, 14, 16, 11] + [14] * len(keys))
    higher = _higher(metric)
    for i, b in enumerate(r["leaderboard"], start=4):
        s, h = b["selection"].get(metric), b["holdout"].get(metric)
        gap = None if (s is None or h is None) else ((s - h) if higher else (h - s))
        ws.write(i, 0, b["model"], f["bold"] if i == 4 else f["cell"])
        ws.write(i, 1, b["type"], f["cell"])
        ws.write(i, 2, _v(s), f["num"])
        ws.write(i, 3, _v(h), f["num"])
        ws.write(i, 4, _v(gap), f["num"])
        ws.write(i, 5, _v(b.get("n_trials", 0)), f["int"])
        ws.write(i, 6, "sí" if b.get("calibrated") else "no", f["cell"])
        for j, k in enumerate(keys):
            ws.write(i, 7 + j, _v(b["holdout"].get(k)), f["num"])


def _higher(metric: str) -> bool:
    from . import metrics as MT
    return MT.CATALOG.get(metric, (True,))[0]


def _sheet_variables(wb, f, r):
    ws = wb.add_worksheet("Analisis de Variables")
    heads = ["Variable", "Importancia nativa", "Caída de la métrica al permutar",
             "Caída %", "SHAP medio absoluto", "Dirección del efecto"]
    _title(ws, f, "ANÁLISIS DE VARIABLES — aporte de cada columna al modelo campeón", len(heads))
    ws.write(1, 0, "La caída por permutación se mide sobre el holdout ciego: es el aporte real. "
                   "La importancia nativa favorece a las columnas con más valores distintos.", f["sub"])
    _header(ws, f, 3, heads, [34, 18, 27, 12, 20, 26])
    for i, x in enumerate(r["features"]["ranking"], start=4):
        ws.write(i, 0, x["column"], f["cell"])
        ws.write(i, 1, _v(x.get("native")), f["num"])
        ws.write(i, 2, _v(x.get("permutation_drop")), f["num"])
        pctv = x.get("permutation_drop_pct")
        ws.write(i, 3, _v(pctv), f["pct"])
        ws.write(i, 4, _v(x.get("shap_mean_abs")), f["num"])
        ws.write(i, 5, _v(x.get("shap_direction") or ""), f["cell"])


def _sheet_diagnostico(wb, f, r) -> bool:
    d = r.get("diagnostics") or {}
    task = r["task"]
    if task == "binary" and d.get("deciles"):
        ws = wb.add_worksheet("Diagnostico Holdout")
        heads = ["Decil", "Casos", "Positivos", "Probabilidad media", "Tasa real", "Lift",
                 "Captura acumulada"]
        _title(ws, f, "DIAGNÓSTICO SOBRE EL HOLDOUT CIEGO — concentración por decil de score", len(heads))
        ws.write(1, 0, "El decil 1 es el 10% con score más alto. El lift indica cuántas veces más "
                       "positivos hay ahí que en el promedio de la cartera.", f["sub"])
        _header(ws, f, 3, heads, [8, 12, 12, 20, 14, 10, 20])
        for i, x in enumerate(d["deciles"], start=4):
            ws.write(i, 0, _v(x["decil"]), f["int"])
            ws.write(i, 1, _v(x["n"]), f["int"])
            ws.write(i, 2, _v(x["positivos"]), f["int"])
            ws.write(i, 3, _v(x["prob_media"] * 100), f["pct2"])
            ws.write(i, 4, _v(x["tasa_real"] * 100), f["pct2"])
            ws.write(i, 5, _v(x["lift"]), f["num"])
            ws.write(i, 6, _v(x["captura_acum"] * 100), f["pct"])
        row = 4 + len(d["deciles"]) + 1
        cm = d.get("confusion") or {}
        if cm:
            _header(ws, f, row, ["Matriz de confusión", "Predicho positivo", "Predicho negativo", "", "", "", ""])
            ws.write(row + 1, 0, "Real positivo", f["bold"])
            ws.write(row + 1, 1, _v(cm.get("vp")), f["int"])
            ws.write(row + 1, 2, _v(cm.get("fn")), f["int"])
            ws.write(row + 2, 0, "Real negativo", f["bold"])
            ws.write(row + 2, 1, _v(cm.get("fp")), f["int"])
            ws.write(row + 2, 2, _v(cm.get("vn")), f["int"])
            ws.write(row + 3, 0, f"Umbral aplicado: {cm.get('umbral', 0):.4f} "
                                 f"(el que reproduce la tasa base observada)", f["sub"])
        return True
    if task == "regression" and d.get("bins"):
        ws = wb.add_worksheet("Diagnostico Holdout")
        heads = ["Decil de predicción", "Casos", "Valor real medio", "Valor predicho medio", "Desvío %"]
        _title(ws, f, "DIAGNÓSTICO SOBRE EL HOLDOUT CIEGO — real vs predicho por decil", len(heads))
        _header(ws, f, 3, heads, [20, 12, 20, 22, 12])
        for i, x in enumerate(d["bins"], start=4):
            desv = (x["pred"] / x["real"] - 1) * 100 if x["real"] else None
            ws.write(i, 0, _v(x["decil"]), f["int"])
            ws.write(i, 1, _v(x["n"]), f["int"])
            ws.write(i, 2, _v(x["real"]), f["money"])
            ws.write(i, 3, _v(x["pred"]), f["money"])
            ws.write(i, 4, _v(desv), f["pct"])
        tot = d.get("totals") or {}
        row = 4 + len(d["bins"]) + 1
        ws.write(row, 0, "TOTAL", f["bold"])
        ws.write(row, 2, _v(tot.get("real")), f["money"])
        ws.write(row, 3, _v(tot.get("predicho")), f["money"])
        ws.write(row, 4, _v(tot.get("desvio_pct")), f["pct"])
        return True
    if task == "multiclass" and d.get("per_class"):
        ws = wb.add_worksheet("Diagnostico Holdout")
        _title(ws, f, "DIAGNÓSTICO SOBRE EL HOLDOUT CIEGO — desempeño por clase", 4)
        _header(ws, f, 3, ["Clase", "Casos", "Recall", "Precisión"], [26, 12, 12, 12])
        for i, x in enumerate(d["per_class"], start=4):
            ws.write(i, 0, _v(x["clase"]), f["cell"])
            ws.write(i, 1, _v(x["soporte"]), f["int"])
            ws.write(i, 2, _v(x["recall"] * 100), f["pct"])
            ws.write(i, 3, _v(x["precision"] * 100), f["pct"])
        return True
    return False


def _sheet_calidad(wb, f, prof):
    ws = wb.add_worksheet("Calidad de Datos")
    q = prof["quality"]
    heads = ["Severidad", "Columna", "Hallazgo", "", ""]
    _title(ws, f, f"CALIDAD DE DATOS — puntaje {q['score']}/100 ({q['level']}) · "
                  f"{prof['rows']:,} filas × {prof['n_columns']} columnas", 5)
    ws.write(1, 0, f"Altas: {q['counts']['high']} · Medias: {q['counts']['medium']} · "
                   f"Bajas: {q['counts']['low']} · Grupos de filas duplicadas: "
                   f"{prof['duplicate_row_groups']:,}", f["sub"])
    _header(ws, f, 3, heads, [13, 30, 90, 2, 2])
    sev = {"high": ("ALTA", f["bad"]), "medium": ("MEDIA", f["warn"]), "low": ("BAJA", f["grey"])}
    for i, x in enumerate(q["issues"], start=4):
        lbl, fmt = sev.get(x["severity"], ("INFO", f["grey"]))
        ws.write(i, 0, lbl, fmt)
        ws.write(i, 1, x["column"], f["cell"])
        ws.write(i, 2, x["detail"], f["wrap"])


def _sheet_estadisticas(wb, f, prof):
    ws = wb.add_worksheet("Analisis Estadistico")
    heads = ["Columna", "Tipo", "No nulos", "% nulos", "Distintos", "Mínimo", "P25", "Mediana",
             "Media", "P75", "Máximo", "Desvío", "CV", "Asimetría", "Curtosis", "% atípicos",
             "Valor más frecuente", "% del más frecuente"]
    _title(ws, f, "ANÁLISIS ESTADÍSTICO POR COLUMNA", len(heads))
    _header(ws, f, 2, heads, [30, 13, 11, 9, 11] + [14] * 10 + [28, 12])
    for i, c in enumerate(prof["columns"], start=3):
        st = c.get("stats") or {}
        top = (c.get("top_values") or [{}])[0]
        vals = [c["name"], c["kind"], c["non_null"], c["null_pct"], c["distinct"],
                st.get("min"), st.get("p25"), st.get("median"), st.get("mean"), st.get("p75"),
                st.get("max"), st.get("std"), st.get("cv"), st.get("skew"), st.get("kurtosis"),
                st.get("outlier_pct"), top.get("value"), top.get("pct")]
        fmts = [f["cell"], f["cell"], f["int"], f["pct"], f["int"]] + [f["num"]] * 10 + \
               [f["pct"], f["cell"], f["pct"]]
        for j, (v, fm) in enumerate(zip(vals, fmts, strict=False)):
            ws.write(i, j, _v(v), fm)


def _sheet_etl(wb, f, etl):
    ws = wb.add_worksheet("Plan de ETL")
    heads = ["#", "Operación", "Columna", "Motivo"]
    _title(ws, f, f"PLAN DE ETL APLICADO — {etl.get('rows_in', 0):,} → {etl.get('rows_out', 0):,} filas · "
                  f"{etl.get('columns_in', 0)} → {etl.get('columns_out', 0)} columnas", 4)
    ws.write(1, 0, "Cada paso se decidió a partir del perfil del dataset, no de reglas fijas.", f["sub"])
    _header(ws, f, 3, heads, [6, 26, 30, 100])
    for i, s in enumerate(etl.get("applied", []), start=4):
        ws.write(i, 0, i - 3, f["int"])
        ws.write(i, 1, s["op"], f["cell"])
        ws.write(i, 2, _v(s.get("column")), f["cell"])
        ws.write(i, 3, s["reason"], f["wrap"])
    row = 4 + len(etl.get("applied", [])) + 1
    ws.write(row, 0, "SQL ejecutado", f["bold"])
    for k, line in enumerate((etl.get("sql") or "").split("\n")[:200]):
        ws.write(row + 1 + k, 0, line, f["cell"])


def _sheet_datos(wb, f, dataset_id: str, limit: int) -> int:
    meta = S.load_meta(dataset_id)
    cols = [c["name"] for c in meta.columns]
    total = min(meta.rows, limit)
    per_sheet = min(XLSX_MAX_ROWS - 1, total)
    written, sheet_n = 0, 0
    step = 50_000
    while written < total:
        sheet_n += 1
        ws = wb.add_worksheet("Datos" if sheet_n == 1 else f"Datos ({sheet_n})")
        _header(ws, f, 0, cols, [max(12, min(28, len(c) + 6)) for c in cols])
        rows_here = min(per_sheet, total - written)
        r = 1
        for off in range(written, written + rows_here, step):
            n = min(step, written + rows_here - off)
            df = S.query(dataset_id, f"SELECT * FROM {{t}} LIMIT {n} OFFSET {off}")
            if df.empty:
                break
            for rec in df.itertuples(index=False, name=None):
                for j, v in enumerate(rec):
                    ws.write(r, j, _v(v), f["cell"])
                r += 1
        written += rows_here
    return written


# ═════════════════════════════════════════════════════ CSV / PARQUET ═════════
def export_dataset(dataset_id: str, fmt: str = "csv", sep: str = ";",
                   decimal: str = ",", encoding: str = "utf-8-sig",
                   limit: int | None = None) -> dict[str, Any]:
    """Exporta el dataset completo. CSV y Parquet no tienen límite de filas."""
    meta = S.load_meta(dataset_id)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in meta.name)[:60].strip()
    out = workspace.dir_for("exports") / f"{safe or 'dataset'}_{stamp}.{ 'parquet' if fmt=='parquet' else fmt}"
    t0 = time.time()

    if fmt == "parquet":
        import pyarrow as pa
        import pyarrow.parquet as pq
        writer = None
        for df in _iter(dataset_id, limit):
            table = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out, table.schema, compression="zstd")
            writer.write_table(table)
        if writer:
            writer.close()
    else:
        first = True
        with out.open("w", encoding=encoding, newline="") as fh:
            for df in _iter(dataset_id, limit):
                df.to_csv(fh, sep=sep, decimal=decimal, index=False, header=first,
                          lineterminator="\n")
                first = False
    return {"path": str(out), "filename": out.name, "rows": min(meta.rows, limit or meta.rows),
            "size_bytes": out.stat().st_size, "seconds": round(time.time() - t0, 1)}


def _iter(dataset_id: str, limit: int | None) -> Iterator[pd.DataFrame]:
    meta = S.load_meta(dataset_id)
    total = min(meta.rows, limit or meta.rows)
    step = settings.chunk_rows
    for off in range(0, max(total, 1), step):
        n = min(step, total - off)
        if n <= 0:
            break
        df = S.query(dataset_id, f"SELECT * FROM {{t}} LIMIT {n} OFFSET {off}")
        if df.empty:
            break
        yield df
