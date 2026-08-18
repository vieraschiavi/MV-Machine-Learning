"""Endpoints de proveedores de IA: configurar, actualizar, verificar y usar."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core import ai as AI
from ..core import registry, storage

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def status() -> dict[str, Any]:
    return AI.status()


class ConfigBody(BaseModel):
    provider: str
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    set_active: bool = False


@router.post("/config")
def config(body: ConfigBody) -> dict[str, Any]:
    try:
        cfg = AI.save_config(body.provider, body.api_key, body.model, body.base_url)
        if body.set_active:
            AI.set_active(body.provider)
        return {"config": cfg, "active": AI.active_provider()}
    except AI.AIError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/models/refresh")
def refresh(body: ConfigBody) -> dict[str, Any]:
    """Botón *Actualizar*: trae el catálogo real de modelos del proveedor."""
    if body.api_key:
        AI.save_config(body.provider, body.api_key, base_url=body.base_url)
    try:
        return AI.refresh_models(body.provider)
    except AI.AIError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/verify")
def verify(body: ConfigBody) -> dict[str, Any]:
    """Botón *Verificar*: llamada real de extremo a extremo."""
    if body.api_key or body.base_url:
        AI.save_config(body.provider, body.api_key, body.model, body.base_url)
    return AI.verify(body.provider, body.model)


class TargetBody(BaseModel):
    dataset_id: str
    objective: str
    provider: str | None = None
    model: str | None = None


@router.post("/suggest-target")
def suggest_target(body: TargetBody) -> dict[str, Any]:
    """Traduce el objetivo escrito en lenguaje natural a una columna del dataset."""
    from ..core import profiling

    try:
        prof = profiling.profile(body.dataset_id)
    except storage.IngestError as exc:
        raise HTTPException(404, str(exc)) from exc
    cols = [{"name": c["name"], "kind": c["kind"], "distinct": c["distinct"],
             "null_pct": c["null_pct"]} for c in prof["columns"]]
    heur = _heuristic_target(cols, body.objective)
    if not AI.active_provider() and not body.provider:
        return {"ok": True, "source": "heurística local", **heur,
                "note": "Sin proveedor de IA configurado: la sugerencia sale de la coincidencia "
                        "de texto con los nombres de columna."}
    try:
        r = AI.suggest_target(cols, body.objective, body.provider, body.model)
        r["source"] = "IA"
        r["heuristic"] = heur
        return r
    except AI.AIError as exc:
        return {"ok": True, "source": "heurística local", **heur, "ai_error": str(exc)}


def _heuristic_target(cols: list[dict], objective: str) -> dict[str, Any]:
    """Respaldo sin IA: coincidencia de raíces entre el objetivo y los nombres.

    No alcanza con comparar palabras enteras: quien escribe «si el cliente va a
    pagar» quiere la columna «Pago». Se comparan raíces (prefijo común), se
    ignoran acentos y se descartan las palabras vacías del castellano, el
    inglés y el portugués.
    """
    import re
    import unicodedata

    STOP = {
        # artículos, preposiciones y muletillas de los tres idiomas
        "del", "las", "los", "una", "unos", "unas", "por", "con", "sin", "para",
        "que", "como", "cual", "cuales", "esta", "este", "esto", "esa", "ese",
        "sobre", "entre", "desde", "hasta", "cada", "mas", "muy", "todo", "toda",
        "the", "and", "for", "with", "from", "into", "その", "dos", "das", "aos",
        "nos", "nas", "pelo", "pela", "seu", "sua", "meu", "minha",
        # verbos y sustantivos genéricos de un pedido de predicción
        "quiero", "queremos", "necesito", "predecir", "prediccion", "estimar",
        "calcular", "saber", "cliente", "clientes", "proximos", "proximo",
        "meses", "mes", "siguiente", "value", "want", "predict", "would", "will",
        "next", "customer", "whether", "prever", "previsao", "quero", "preciso",
        "seguinte", "variable", "modelo", "model", "target", "objetivo",
    }

    def norm(x: str) -> str:
        x = unicodedata.normalize("NFKD", str(x).lower())
        return "".join(c for c in x if not unicodedata.combining(c))

    def tokens(x: str) -> list[str]:
        return [w for w in re.split(r"[^a-z0-9]+", norm(x)) if len(w) > 2]

    def stem_match(a: str, b: str) -> float:
        """1.0 si son iguales; 0.7 si comparten raíz; 0.4 si uno contiene al otro."""
        if a == b:
            return 1.0
        common = 0
        for ca, cb in zip(a, b, strict=False):
            if ca != cb:
                break
            common += 1
        need = max(3, min(len(a), len(b)) - 2)
        if common >= need:
            return 0.7
        if len(a) > 3 and len(b) > 3 and (a in b or b in a):
            return 0.4
        return 0.0

    # puente entre idiomas: el objetivo puede estar en inglés y las columnas en
    # castellano, o al revés. Cada grupo comparte significado de negocio.
    SYN = [
        {"pay", "pago", "pagar", "pagamento", "payment", "paid", "cobro", "cobrar"},
        {"amount", "monto", "importe", "valor", "montante"},
        {"churn", "baja", "cancelacion", "cancelamento", "attrition", "fuga"},
        {"price", "precio", "preco"},
        {"default", "mora", "moroso", "inadimplencia", "incumplimiento", "atraso", "delay", "late"},
        {"revenue", "ingreso", "ingresos", "receita", "facturacion", "billing"},
        {"sale", "sales", "venta", "ventas", "venda", "vendas"},
        {"fraud", "fraude"},
        {"score", "puntaje", "pontuacao", "rating", "calificacion"},
        {"risk", "riesgo", "risco"},
        {"debt", "deuda", "divida", "saldo", "balance"},
        {"income", "renta", "salario", "sueldo", "salary", "wage"},
        {"date", "fecha", "data", "dia", "day", "mes", "month"},
        {"quantity", "cantidad", "quantidade", "count", "unidades", "units"},
        {"cost", "costo", "custo", "gasto", "expense"},
        {"conversion", "convertir", "convert", "conversao"},
        {"demand", "demanda", "volumen", "volume"},
        {"quota", "cuota", "parcela", "installment"},
    ]

    def synonyms(w: str) -> set[str]:
        # sólo se expande a partir de palabras largas: con tres letras («del»,
        # «con») cualquier raíz choca con cualquier grupo y el puente entre
        # idiomas empieza a inventar coincidencias.
        out = {w}
        for group in SYN:
            # con palabras cortas («pay», «id») sólo vale la coincidencia
            # exacta: emparejar por raíz haría que «del» active «delay».
            hit = (w in group) if len(w) < 4 else any(stem_match(w, g) >= 0.7 for g in group)
            if hit:
                out |= group
        return out

    words = [w for w in tokens(objective) if w not in STOP]
    binary_intent = bool(re.search(r"\b(si|whether|se)\b", norm(objective)))

    scored = []
    for c in cols:
        col_tokens = tokens(c["name"])
        if not col_tokens:
            continue
        score = 0.0
        for w in words:
            variants = synonyms(w)
            best = max((stem_match(v, ct) for v in variants for ct in col_tokens), default=0.0)
            score += best
        if score <= 0:
            continue
        # una columna con dos valores encaja con una pregunta de sí o no
        if binary_intent and c.get("distinct") == 2:
            score += 0.5
        # un identificador nunca es la variable a predecir
        if re.search(r"^id|_id$|codigo|uuid", norm(c["name"])):
            score -= 1.0
        if (c.get("null_pct") or 0) > 60:
            score -= 0.5
        scored.append((score, c))

    scored.sort(key=lambda t: -t[0])
    scored = [s for s in scored if s[0] > 0.35]
    if not scored:
        return {"target": None, "confidence": 0.0,
                "reason": "Ninguna columna coincide con el texto del objetivo. "
                          "Elegí la columna objetivo de la lista.",
                "alternatives": [c["name"] for c in cols[:8]]}

    top, best = scored[0]
    distinct = best.get("distinct") or 0
    task = ("binary" if distinct == 2 else
            ("multiclass" if best["kind"] == "categorical" and distinct <= 20 else
             ("regression" if best["kind"] == "numeric" else "multiclass")))
    return {
        "target": best["name"], "task": task,
        "confidence": round(min(0.45 + 0.18 * top, 0.92), 2),
        "reason": f"«{best['name']}» es la columna cuyo nombre mejor coincide con el objetivo escrito.",
        "alternatives": [c["name"] for _, c in scored[1:5]],
    }


class NarrateBody(BaseModel):
    kind: str = "training"
    lang: str = "es"
    payload: dict[str, Any] | None = None
    model_id: str | None = None
    dataset_id: str | None = None
    provider: str | None = None
    model: str | None = None


@router.post("/narrate")
def narrate(body: NarrateBody) -> dict[str, Any]:
    payload = body.payload
    if payload is None and body.model_id:
        card = registry.card(body.model_id)
        r = card.get("report", {})
        payload = {"target": r.get("target"), "task": r.get("task_label"),
                   "metric": r.get("metric"), "champion": r.get("champion"),
                   "split": r.get("split"), "verdict": r.get("verdict"),
                   "top_features": (r.get("features") or {}).get("ranking", [])[:8]}
    if payload is None and body.dataset_id:
        from ..core import profiling
        p = profiling.profile(body.dataset_id)
        payload = {"rows": p["rows"], "columns": p["n_columns"], "quality": p["quality"]}
    if payload is None:
        raise HTTPException(400, "No hay contenido para narrar.")
    try:
        return AI.narrate(payload, body.kind, body.lang, body.provider, body.model)
    except AI.AIError as exc:
        raise HTTPException(400, str(exc)) from exc


class ReviewBody(BaseModel):
    plan: dict[str, Any]
    provider: str | None = None
    model: str | None = None


@router.post("/review-etl")
def review_etl(body: ReviewBody) -> dict[str, Any]:
    try:
        return AI.review_etl(body.plan, body.provider, body.model)
    except AI.AIError as exc:
        raise HTTPException(400, str(exc)) from exc
