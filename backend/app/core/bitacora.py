"""La bitácora del pipeline: qué se le hizo a los datos, en orden y por qué.

El programa siempre supo esto. El plan de ETL guarda el motivo de cada paso,
la ficha del modelo guarda cómo se partieron los datos y con qué se midió el
resultado. Lo que faltaba era juntarlo en una sola línea de tiempo y contarlo
dos veces: una para quien audita el código y otra para quien firma el informe.

Reglas de esta construcción:

  * **Se reconstruye, no se recalcula.** Cada número sale del linaje del
    dataset (`DatasetMeta.origin`) o de la ficha del modelo. La bitácora no
    vuelve a leer los datos ni estima nada: si un dato no quedó registrado,
    no aparece.
  * **El orden es el del pipeline**, no el de las categorías: archivo crudo →
    transformaciones → partición → entrenamiento → medición → veredicto.
  * **Los textos viven en `glosario.py`**, uno solo por operación, y se
    completan con los valores reales de lo ejecutado.

El resultado alimenta la pestaña Bitácora y los tres formatos exportables.
"""
from __future__ import annotations

import time
from typing import Any

from . import glosario
from . import registry as R
from . import storage as S

MAX_COLUMNAS_LISTADAS = 12          # arriba de esto la lista deja de leerse
MAX_PROFUNDIDAD_LINAJE = 20         # corta un linaje circular por datos corruptos


# ═══════════════════════════════════════════════════════════════ formato ══════
def _n(v: Any) -> str:
    """Número con punto de miles, como se escribe acá."""
    try:
        return f"{int(v):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(v)


def _lista(nombres: list[str]) -> str:
    if not nombres:
        return "—"
    if len(nombres) <= MAX_COLUMNAS_LISTADAS:
        return ", ".join(nombres)
    resto = len(nombres) - MAX_COLUMNAS_LISTADAS
    return ", ".join(nombres[:MAX_COLUMNAS_LISTADAS]) + f" y {resto} más"


def _ev(clave: str, valor: Any) -> dict[str, str]:
    return {"clave": clave, "valor": str(valor)}


# ═══════════════════════════════════════════════════════════════ linaje ═══════
def _linaje(ds_id: str) -> list[S.DatasetMeta]:
    """Del dataset pedido hasta el archivo original, devuelto en orden."""
    cadena: list[S.DatasetMeta] = []
    actual: str | None = ds_id
    vistos: set[str] = set()
    while actual and actual not in vistos and len(cadena) < MAX_PROFUNDIDAD_LINAJE:
        vistos.add(actual)
        meta = S.load_meta(actual)
        cadena.append(meta)
        actual = meta.parent_id
    return list(reversed(cadena))


# ══════════════════════════════════════════════════════════════ ingesta ═══════
def _paso_ingesta(meta: S.DatasetMeta) -> dict[str, Any]:
    o = meta.origin or {}
    fuente = {"upload": "archivo subido", "sql": "consulta a una base",
              "derived": "dataset derivado"}.get(meta.source, meta.source)
    ev = [_ev("Origen", o.get("file") or o.get("table") or fuente),
          _ev("Filas leídas", _n(meta.rows)),
          _ev("Columnas", _n(len(meta.columns)))]
    if o.get("bytes"):
        ev.append(_ev("Tamaño", f"{round(o['bytes'] / 1_048_576, 1)} MB"))
    if o.get("sep"):
        ev.append(_ev("Separador detectado", repr(o["sep"])))
    if o.get("encoding"):
        ev.append(_ev("Codificación detectada", o["encoding"]))

    tipos: dict[str, int] = {}
    for c in meta.columns:
        t = str(c.get("arrow_type", "")).split("[")[0] or "desconocido"
        tipos[t] = tipos.get(t, 0) + 1
    if tipos:
        ev.append(_ev("Tipos reconocidos",
                      ", ".join(f"{k}: {v}" for k, v in sorted(tipos.items()))))

    return {
        "etapa": "ingesta",
        "titulo": f"Lectura de «{meta.name}»",
        "tecnico": ("Ingesta por bloques a Parquet con detección automática de codificación, "
                    "separador y separador decimal; el tipo de cada columna se infiere de una "
                    "muestra y queda fijado en el esquema."),
        "criollo": ("Se leyó el archivo original y se guardó en un formato interno más rápido, "
                    "reconociendo solo cómo estaba escrito: el idioma de los caracteres, con qué "
                    "signo se separan las columnas y cuál es la coma de los decimales."),
        "porque": ("Un archivo mal leído arruina todo lo que viene después, y el error aparece "
                   "recién al final, disfrazado de mal resultado del modelo."),
        "impacto": ("Todo lo que sigue trabaja sobre esta lectura. El formato interno permite "
                    "trabajar con archivos más grandes que la memoria de la máquina."),
        "evidencia": ev,
        "ops": [],
    }


# ══════════════════════════════════════════════════════════════════ ETL ═══════
def _agrupar(pasos: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Junta los pasos por operación, conservando el orden de aparición."""
    orden: list[str] = []
    grupos: dict[str, list[dict[str, Any]]] = {}
    for s in pasos:
        op = s.get("op", "")
        if op not in grupos:
            grupos[op] = []
            orden.append(op)
        grupos[op].append(s)
    return [(op, grupos[op]) for op in orden]


def _paso_etl(op: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    columnas = [s["column"] for s in steps if s.get("column")]
    detalle = "; ".join(str((s.get("params") or {}).get("sql", "")) for s in steps).strip("; ")
    datos = {"n": len(steps), "columnas": _lista(columnas) or "—", "detalle": detalle or "—"}

    p = glosario.op(op)
    if p is None:
        # Operación nueva sin traducción: se muestra igual, con su motivo original.
        titulo = op.replace("_", " ").capitalize()
        tecnico = f"Operación «{op}» sobre {datos['columnas']}."
        criollo = "Se aplicó un ajuste sobre esas columnas."
        porque = steps[0].get("reason", "—")
        impacto = "Ver el motivo registrado por el planificador."
    else:
        titulo = p.titulo
        tecnico = p.tecnico.format(**datos)
        criollo = p.criollo.format(**datos)
        porque = p.porque
        impacto = p.impacto

    ev = [_ev("Columnas afectadas", len(columnas) or len(steps))]
    if columnas:
        ev.append(_ev("Cuáles", _lista(columnas)))
    # Los motivos que escribió el planificador, con sus números reales.
    for s in steps[:MAX_COLUMNAS_LISTADAS]:
        if s.get("reason"):
            ev.append(_ev(s.get("column") or "General", s["reason"]))

    return {"etapa": "etl", "titulo": titulo, "tecnico": tecnico, "criollo": criollo,
            "porque": porque, "impacto": impacto, "evidencia": ev, "ops": [op]}


def _pasos_etl(padre: S.DatasetMeta, hijo: S.DatasetMeta) -> list[dict[str, Any]]:
    steps = [s for s in (hijo.origin or {}).get("steps", []) if s.get("enabled", True)]
    out = [_paso_etl(op, grupo) for op, grupo in _agrupar(steps)]

    sql = (hijo.origin or {}).get("sql")
    quitadas = padre.rows - hijo.rows
    out.append({
        "etapa": "etl",
        "titulo": "Ejecución del plan y materialización del resultado",
        "tecnico": ("Todos los pasos anteriores se compilan a una única sentencia SQL de DuckDB "
                    "y se ejecutan de una sola pasada, por bloques, sobre el dataset padre. El "
                    "resultado se materializa como dataset nuevo con linaje al original."),
        "criollo": ("Todos los cambios se aplicaron juntos, de una sola vez, sobre una copia. El "
                    "archivo original queda intacto y siempre se puede volver a él."),
        "porque": ("Aplicar los cambios de una sola pasada es más rápido y, sobre todo, "
                   "repetible: la misma consulta sobre los mismos datos da siempre el mismo "
                   "resultado, y queda escrita para que cualquiera la revise."),
        "impacto": ("Lo que sigue trabaja sobre el dataset transformado. El original conserva "
                    "todas sus filas por si hay que rehacer el camino con otro criterio."),
        "evidencia": [
            _ev("Filas antes", _n(padre.rows)),
            _ev("Filas después", _n(hijo.rows)),
            _ev("Filas descartadas", f"{_n(quitadas)}"
                f" ({round(100 * quitadas / padre.rows, 2) if padre.rows else 0}%)"),
            _ev("Columnas antes", _n(len(padre.columns))),
            _ev("Columnas después", _n(len(hijo.columns))),
        ],
        "detalle": sql or "",
        "ops": [],
    })
    return out


# ═══════════════════════════════════════════════════════════════ modelo ══════
def _paso(etapa: str, evidencia: list[dict[str, str]], titulo: str | None = None,
          detalle: str = "") -> dict[str, Any]:
    p = glosario.etapa(etapa)
    if p is None:
        raise KeyError(f"Etapa sin traducción en el glosario: {etapa}")
    paso = {"etapa": etapa if etapa != "objetivo_log" else "preparacion",
            "titulo": titulo or p.titulo, "tecnico": p.tecnico, "criollo": p.criollo,
            "porque": p.porque, "impacto": p.impacto, "evidencia": evidencia, "ops": []}
    if detalle:
        paso["detalle"] = detalle
    return paso


def _pasos_modelo(card: dict[str, Any]) -> list[dict[str, Any]]:
    rep = card.get("report") or {}
    if not rep:
        return []
    split = rep.get("split") or {}
    champ = rep.get("champion") or {}
    mi = rep.get("metric_info") or {}
    out: list[dict[str, Any]] = []

    out.append(_paso("objetivo", [
        _ev("Columna a predecir", rep.get("target", "—")),
        _ev("Tipo de tarea", rep.get("task_label") or rep.get("task", "—")),
        _ev("Métrica de decisión", rep.get("metric", "—")),
        _ev("Qué mide", mi.get("what") or mi.get("descripcion") or "—"),
        _ev("Filas usadas", _n(rep.get("rows_used", 0))),
        _ev("Columnas candidatas", _n(rep.get("n_features_in", 0))),
    ]))

    modo = {"time": "temporal (por fecha)", "random": "aleatoria estratificada"}.get(
        split.get("mode"), split.get("mode", "—"))
    ev_split = [
        _ev("Modo de partición", modo),
        _ev("Entrenamiento", _n(split.get("train", 0))),
        _ev("Selección", _n(split.get("selection", 0))),
        _ev("Holdout (ventana cerrada)", _n(split.get("holdout", 0))),
    ]
    if split.get("time_column"):
        ev_split.append(_ev("Columna de tiempo", split["time_column"]))
    out.append(_paso("particion", ev_split))

    out.append(_paso("preparacion", [
        _ev("Columnas de entrada", _n(rep.get("n_features_in", 0))),
        _ev("Columnas tras la preparación", _n(rep.get("n_features_used", 0))),
        _ev("Ajustado con", "sólo el tramo de entrenamiento"),
    ]))

    tt = rep.get("target_transform") or {}
    if tt.get("log"):
        out.append(_paso("objetivo_log", [
            _ev("Transformación", "logaritmo natural de (objetivo + 1)"),
            _ev("Corrección de smearing", tt.get("smearing", "—")),
        ], titulo=glosario.ETAPAS["objetivo_log"].titulo))

    board = rep.get("leaderboard") or []
    ev_train = [_ev("Familias probadas", _n(len(board)))]
    if board:
        ev_train.append(_ev("Cuáles", _lista([str(b.get("model", "?")) for b in board])))
    ev_train += [
        _ev("Modelo ganador", champ.get("model", "—")),
        _ev("Tiempo total", f"{rep.get('seconds', '—')} s"),
    ]
    out.append(_paso("entrenamiento", ev_train))

    fs = rep.get("feature_selection") or {}
    if fs.get("applied"):
        out.append(_paso("seleccion", [
            _ev("Variables antes", _n(fs.get("before", 0))),
            _ev("Variables después", _n(fs.get("after", 0))),
            _ev("Criterio", "aporte medido, verificando que el resultado no caiga"),
        ]))

    if champ.get("calibrated"):
        out.append(_paso("calibracion", [
            _ev("Técnica", "regresión isotónica"),
            _ev("Ajustada sobre", "la ventana de selección"),
        ]))

    metrica = rep.get("metric", "")
    hold, sel = champ.get("holdout") or {}, champ.get("selection") or {}
    ev_eval = [_ev(f"{metrica} en la ventana cerrada", hold.get(metrica, "—")),
               _ev(f"{metrica} en selección", sel.get(metrica, "—"))]
    if champ.get("gap") is not None:
        ev_eval.append(_ev("Distancia entre ambas", champ["gap"]))
    for k, v in list(hold.items()):
        if k != metrica:
            ev_eval.append(_ev(k, v))
    out.append(_paso("evaluacion", ev_eval))

    ranking = ((rep.get("features") or {}).get("ranking") or [])[:10]
    if ranking:
        out.append(_paso("explicacion", [
            _ev(f"{i + 1}. {r.get('feature', '?')}", r.get("importance", "—"))
            for i, r in enumerate(ranking)
        ]))

    ver = rep.get("verdict") or {}
    if ver:
        ev_ver = [_ev("Semáforo", ver.get("level", "—"))]
        ev_ver += [_ev(n.get("level", "nota"), n.get("text", "")) for n in ver.get("notes", [])]
        out.append(_paso("veredicto", ev_ver))
    return out


# ════════════════════════════════════════════════════════════ construcción ═══
def construir(dataset_id: str | None = None, model_id: str | None = None) -> dict[str, Any]:
    """Arma la bitácora completa del pipeline, en orden de ejecución."""
    if not dataset_id and not model_id:
        raise ValueError("Indicá un dataset o un modelo para armar la bitácora.")

    card: dict[str, Any] | None = None
    if model_id:
        try:
            card = R.card(model_id)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Modelo inexistente: {model_id}") from e
        dataset_id = dataset_id or card.get("dataset_id")

    pasos: list[dict[str, Any]] = []
    cadena: list[S.DatasetMeta] = []
    if dataset_id:
        cadena = _linaje(dataset_id)
        pasos.append(_paso_ingesta(cadena[0]))
        for padre, hijo in zip(cadena, cadena[1:], strict=False):
            pasos.extend(_pasos_etl(padre, hijo))

    if card:
        pasos.extend(_pasos_modelo(card))

    for i, p in enumerate(pasos, 1):
        p["orden"] = i

    raiz, hoja = (cadena[0], cadena[-1]) if cadena else (None, None)
    return {
        "generado_en": time.time(),
        "titulo": _titulo(card, hoja),
        "dataset": hoja.to_dict() if hoja else None,
        "modelo": {k: v for k, v in (card or {}).items() if k != "report"} if card else None,
        "pasos": pasos,
        "resumen": {
            "n_pasos": len(pasos),
            "etapas": list(dict.fromkeys(p["etapa"] for p in pasos)),
            "filas_inicio": raiz.rows if raiz else None,
            "filas_fin": hoja.rows if hoja else None,
            "columnas_inicio": len(raiz.columns) if raiz else None,
            "columnas_fin": len(hoja.columns) if hoja else None,
            "transformaciones": sum(len(p["ops"]) for p in pasos),
        },
    }


def _titulo(card: dict[str, Any] | None, hoja: S.DatasetMeta | None) -> str:
    if card:
        return f"Bitácora técnica · {card.get('name', 'modelo')}"
    return f"Bitácora técnica · {hoja.name if hoja else 'pipeline'}"
