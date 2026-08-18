"""Capa de proveedores de IA: ChatGPT, Claude, Grok, Gemini y Copilot.

Tres cosas que la UI necesita y que acá se resuelven:

  1. **Actualizar** — pedirle al proveedor su catálogo real de modelos, en vez
     de una lista escrita a mano que envejece.
  2. **Elegir** — guardar qué modelo se usa para cada proveedor.
  3. **Verificar** — mandar una llamada mínima y confirmar que la clave, el
     modelo y la red funcionan de verdad.

La IA es *opcional*: toda la plataforma (ETL, AutoML, exportación) funciona
sin ninguna clave configurada. La IA agrega interpretación en lenguaje
natural, no capacidad de cálculo.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import settings

# ── catálogo de proveedores ───────────────────────────────────────────────────
PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "ChatGPT (OpenAI)",
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "key_hint": "sk-…",
        "docs": "https://platform.openai.com/api-keys",
        "style": "openai",
        "fallback_models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
    },
    "anthropic": {
        "label": "Claude (Anthropic)",
        "base_url": "https://api.anthropic.com/v1",
        "key_env": "ANTHROPIC_API_KEY",
        "key_hint": "sk-ant-…",
        "docs": "https://console.anthropic.com/settings/keys",
        "style": "anthropic",
        "fallback_models": ["claude-sonnet-4-5", "claude-opus-4-1", "claude-haiku-4-5"],
    },
    "xai": {
        "label": "Grok (xAI)",
        "base_url": "https://api.x.ai/v1",
        "key_env": "XAI_API_KEY",
        "key_hint": "xai-…",
        "docs": "https://console.x.ai",
        "style": "openai",
        "fallback_models": ["grok-4", "grok-3", "grok-3-mini"],
    },
    "google": {
        "label": "Gemini (Google)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "key_env": "GEMINI_API_KEY",
        "key_hint": "AIza…",
        "docs": "https://aistudio.google.com/apikey",
        "style": "gemini",
        "fallback_models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    },
    "copilot": {
        "label": "Copilot (GitHub Models)",
        "base_url": "https://models.github.ai",
        "key_env": "GITHUB_TOKEN",
        "key_hint": "ghp_… (token con permiso models:read)",
        "docs": "https://github.com/marketplace/models",
        "style": "github",
        "fallback_models": ["openai/gpt-4.1", "openai/gpt-4o", "microsoft/phi-4"],
    },
    "custom": {
        "label": "Compatible con OpenAI (Azure, OpenRouter, Ollama, LM Studio…)",
        "base_url": "",
        "key_env": "MV_CUSTOM_AI_KEY",
        "key_hint": "clave del servicio (vacío si es local)",
        "docs": "",
        "style": "openai",
        "fallback_models": [],
    },
}


class AIError(RuntimeError):
    """Error de proveedor con mensaje pensado para mostrar en pantalla."""


# ── credenciales ──────────────────────────────────────────────────────────────
def _file() -> Path:
    return settings.secrets_dir / "ai_providers.json"


def _read() -> dict[str, dict]:
    f = _file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write(d: dict[str, dict]) -> None:
    f = _file()
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def get_config(provider: str) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise AIError(f"Proveedor desconocido: {provider}")
    saved = _read().get(provider, {})
    spec = PROVIDERS[provider]
    key = saved.get("api_key") or os.environ.get(spec["key_env"], "")
    return {
        "provider": provider,
        "api_key": key,
        "base_url": (saved.get("base_url") or spec["base_url"] or "").rstrip("/"),
        "model": saved.get("model") or (spec["fallback_models"][0] if spec["fallback_models"] else ""),
        "models": saved.get("models") or list(spec["fallback_models"]),
        "verified_at": saved.get("verified_at"),
        "verified_model": saved.get("verified_model"),
        "from_env": bool(not saved.get("api_key") and os.environ.get(spec["key_env"])),
    }


def save_config(provider: str, api_key: str | None = None, model: str | None = None,
                base_url: str | None = None, models: list[str] | None = None,
                **extra) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise AIError(f"Proveedor desconocido: {provider}")
    all_ = _read()
    cur = all_.get(provider, {})
    if api_key is not None and api_key != "":
        cur["api_key"] = api_key.strip()
    if api_key == "":
        cur.pop("api_key", None)
    if model:
        cur["model"] = model
    if base_url is not None:
        cur["base_url"] = base_url.strip()
    if models is not None:
        cur["models"] = models
    cur.update({k: v for k, v in extra.items() if v is not None})
    all_[provider] = cur
    _write(all_)
    return public_config(provider)


def public_config(provider: str) -> dict[str, Any]:
    c = get_config(provider)
    spec = PROVIDERS[provider]
    key = c.pop("api_key", "")
    c.update({
        "label": spec["label"], "key_hint": spec["key_hint"], "docs": spec["docs"],
        "has_key": bool(key),
        "key_masked": (key[:6] + "…" + key[-4:]) if len(key) > 12 else ("•" * len(key)),
        "default_base_url": spec["base_url"],
    })
    return c


def active_provider() -> str | None:
    """Proveedor marcado como activo (o el primero verificado que haya)."""
    d = _read()
    act = d.get("__active__", {}).get("provider")
    if act in PROVIDERS and get_config(act).get("api_key"):
        return act
    for p in PROVIDERS:
        if get_config(p).get("api_key"):
            return p
    return None


def set_active(provider: str) -> None:
    d = _read()
    d["__active__"] = {"provider": provider}
    _write(d)


def status() -> dict[str, Any]:
    return {"providers": [public_config(p) for p in PROVIDERS],
            "active": active_provider()}


# ── llamadas HTTP ─────────────────────────────────────────────────────────────
def _client(timeout: float | None = None) -> httpx.Client:
    return httpx.Client(timeout=timeout or settings.ai_timeout,
                        follow_redirects=True, trust_env=True)


def _headers(provider: str, cfg: dict) -> dict[str, str]:
    style = PROVIDERS[provider]["style"]
    key = cfg["api_key"]
    if style == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01",
                "content-type": "application/json"}
    if style == "gemini":
        return {"content-type": "application/json"}
    return {"Authorization": f"Bearer {key}", "content-type": "application/json"}


def _http_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        body = (exc.response.text or "")[:400]
        try:
            j = exc.response.json()
            body = (j.get("error", {}).get("message") if isinstance(j.get("error"), dict)
                    else j.get("message") or body) or body
        except Exception:
            pass
        mapa = {401: "Clave rechazada (401): revisá que esté completa y vigente.",
                403: "Acceso denegado (403): la clave no tiene permiso sobre este modelo.",
                404: "No encontrado (404): el modelo no existe para esta clave o la URL base es otra.",
                429: "Límite de tasa alcanzado (429): esperá unos segundos y reintentá.",
                500: "El proveedor devolvió un error interno (500).",
                529: "El proveedor está sobrecargado: reintentá en unos segundos."}
        return f"{mapa.get(code, f'Error HTTP {code}')} {body}".strip()
    if isinstance(exc, httpx.ConnectError):
        return "No se pudo conectar con el proveedor. Revisá la red, el proxy o la URL base."
    if isinstance(exc, httpx.TimeoutException):
        return "El proveedor no respondió dentro del tiempo de espera."
    return str(exc)[:300]


def refresh_models(provider: str) -> dict[str, Any]:
    """Pide al proveedor su catálogo actual de modelos (botón *Actualizar*)."""
    cfg = get_config(provider)
    spec = PROVIDERS[provider]
    if not cfg["api_key"] and provider != "custom":
        return {"ok": False, "models": spec["fallback_models"], "source": "lista de respaldo",
                "error": "Cargá la clave de API para traer el catálogo real del proveedor."}
    base = cfg["base_url"] or spec["base_url"]
    style = spec["style"]
    try:
        with _client(20) as cli:
            if style == "gemini":
                r = cli.get(f"{base}/models", params={"key": cfg["api_key"], "pageSize": 200})
                r.raise_for_status()
                items = r.json().get("models", [])
                models = [m["name"].split("/")[-1] for m in items
                          if "generateContent" in (m.get("supportedGenerationMethods") or [])]
            elif style == "github":
                r = cli.get(f"{base}/catalog/models",
                            headers={"Authorization": f"Bearer {cfg['api_key']}",
                                     "Accept": "application/vnd.github+json"})
                r.raise_for_status()
                items = r.json()
                items = items if isinstance(items, list) else items.get("models", [])
                models = [m.get("id") or m.get("name") for m in items if (m.get("id") or m.get("name"))]
            else:
                r = cli.get(f"{base}/models", headers=_headers(provider, cfg))
                r.raise_for_status()
                data = r.json()
                items = data.get("data") or data.get("models") or []
                models = [m.get("id") or m.get("name") for m in items if (m.get("id") or m.get("name"))]
        models = sorted({str(m) for m in models if m})
        if style == "openai" and provider == "openai":
            chat = [m for m in models if m.startswith(("gpt", "o1", "o3", "o4", "chatgpt"))]
            models = chat or models
        save_config(provider, models=models)
        return {"ok": True, "models": models, "source": "catálogo del proveedor",
                "count": len(models)}
    except Exception as exc:
        return {"ok": False, "models": spec["fallback_models"], "source": "lista de respaldo",
                "error": _http_error(exc)}


def chat(provider: str | None, prompt: str, system: str | None = None,
         model: str | None = None, max_tokens: int = 1200,
         temperature: float = 0.2, timeout: float | None = None) -> dict[str, Any]:
    """Una llamada de texto, normalizada entre los cinco proveedores."""
    provider = provider or active_provider()
    if not provider:
        raise AIError("No hay ningún proveedor de IA configurado.")
    cfg = get_config(provider)
    spec = PROVIDERS[provider]
    model = model or cfg["model"]
    if not model:
        raise AIError(f"Elegí un modelo para {spec['label']}.")
    if not cfg["api_key"] and provider != "custom":
        raise AIError(f"Falta la clave de API de {spec['label']}.")
    base = cfg["base_url"] or spec["base_url"]
    style = spec["style"]
    t0 = time.time()
    try:
        with _client(timeout) as cli:
            if style == "anthropic":
                body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
                        "messages": [{"role": "user", "content": prompt}]}
                if system:
                    body["system"] = system
                r = cli.post(f"{base}/messages", headers=_headers(provider, cfg), json=body)
                r.raise_for_status()
                j = r.json()
                text = "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")
                usage = j.get("usage", {})
                tokens = {"in": usage.get("input_tokens"), "out": usage.get("output_tokens")}
            elif style == "gemini":
                body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
                if system:
                    body["systemInstruction"] = {"parts": [{"text": system}]}
                r = cli.post(f"{base}/models/{model}:generateContent",
                             params={"key": cfg["api_key"]}, headers={"content-type": "application/json"},
                             json=body)
                r.raise_for_status()
                j = r.json()
                cands = j.get("candidates") or []
                text = "".join(p.get("text", "") for p in
                               (cands[0].get("content", {}).get("parts", []) if cands else []))
                um = j.get("usageMetadata", {})
                tokens = {"in": um.get("promptTokenCount"), "out": um.get("candidatesTokenCount")}
            else:
                msgs = ([{"role": "system", "content": system}] if system else []) + \
                       [{"role": "user", "content": prompt}]
                url = f"{base}/inference/chat/completions" if style == "github" else f"{base}/chat/completions"
                body = {"model": model, "messages": msgs, "temperature": temperature,
                        "max_tokens": max_tokens}
                r = cli.post(url, headers=_headers(provider, cfg), json=body)
                r.raise_for_status()
                j = r.json()
                ch = (j.get("choices") or [{}])[0]
                text = (ch.get("message") or {}).get("content") or ch.get("text") or ""
                u = j.get("usage", {})
                tokens = {"in": u.get("prompt_tokens"), "out": u.get("completion_tokens")}
        return {"ok": True, "provider": provider, "model": model, "text": (text or "").strip(),
                "ms": int((time.time() - t0) * 1000), "tokens": tokens}
    except Exception as exc:
        raise AIError(_http_error(exc)) from exc


def verify(provider: str, model: str | None = None) -> dict[str, Any]:
    """Botón *Verificar*: prueba real de extremo a extremo, no un ping."""
    try:
        r = chat(provider, "Respondé exactamente con la palabra: OPERATIVO",
                 system="Sos un verificador de conectividad. Respondé sólo lo pedido.",
                 model=model, max_tokens=16, temperature=0, timeout=30)
        ok = "OPERATIVO" in r["text"].upper()
        save_config(provider, model=r["model"], verified_at=time.time(),
                    verified_model=r["model"] if ok else None)
        return {"ok": ok, "provider": provider, "model": r["model"], "ms": r["ms"],
                "answer": r["text"][:120], "tokens": r["tokens"],
                "detail": ("Conexión, clave y modelo verificados." if ok else
                           "Respondió, pero con un texto inesperado. La conexión funciona.")}
    except AIError as exc:
        return {"ok": False, "provider": provider, "model": model, "error": str(exc)}


# ── asistencias concretas dentro del producto ────────────────────────────────
SYSTEM_ES = (
    "Sos un analista de datos senior. Respondés en español rioplatense, con precisión "
    "técnica y sin adornos. No usás emojis. Si un dato no está en el contexto, lo decís "
    "en vez de inventarlo."
)


def _json_from(text: str) -> Any:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        t = t[4:] if t.lower().startswith("json") else t
    a, b = t.find("{"), t.rfind("}")
    c, d = t.find("["), t.rfind("]")
    if a >= 0 and (a < c or c < 0):
        t = t[a:b + 1]
    elif c >= 0:
        t = t[c:d + 1]
    return json.loads(t)


def suggest_target(columns: list[dict], objective_text: str,
                   provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Traduce lo que el usuario escribió en el cartel a una columna real."""
    cols = "\n".join(f"- {c['name']} ({c.get('kind', '?')}, {c.get('distinct', '?')} valores distintos, "
                     f"{c.get('null_pct', 0)}% nulos)" for c in columns[:120])
    prompt = (
        f"Objetivo escrito por el usuario:\n«{objective_text}»\n\n"
        f"Columnas disponibles:\n{cols}\n\n"
        "Devolvé SOLO un JSON con esta forma:\n"
        '{"target": "nombre exacto de la columna", "task": "binary|multiclass|regression", '
        '"confidence": 0.0-1.0, "reason": "una frase", '
        '"exclude": ["columnas que no deberían usarse como predictoras y por qué no"], '
        '"alternatives": ["otras columnas candidatas"]}'
    )
    r = chat(provider, prompt, SYSTEM_ES, model=model, max_tokens=700)
    try:
        data = _json_from(r["text"])
    except Exception:
        return {"ok": False, "raw": r["text"], "error": "El modelo no devolvió un JSON interpretable."}
    names = {c["name"] for c in columns}
    if data.get("target") not in names:
        data["warning"] = f"El modelo propuso «{data.get('target')}», que no existe en el dataset."
        data["target"] = None
    data.update({"ok": True, "provider": r["provider"], "model": r["model"]})
    return data


def narrate(payload: dict, kind: str, lang: str = "es",
            provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Lectura ejecutiva de un resultado (perfil, ETL o entrenamiento)."""
    idioma = {"es": "español rioplatense", "en": "English", "pt": "português do Brasil"}.get(lang, "español")
    consigna = {
        "profile": "Resumí el estado del dataset: qué hay, qué problemas de calidad tiene y "
                   "qué habría que arreglar antes de modelar.",
        "etl": "Explicá qué transformaciones se aplicaron y por qué, y qué riesgo quedó abierto.",
        "training": "Explicá qué tan bueno es el modelo en el holdout ciego, qué variables mandan, "
                    "y qué decisión de negocio se puede tomar con esto. Sé honesto sobre las limitaciones.",
    }.get(kind, "Resumí el contenido.")
    prompt = (f"Idioma de la respuesta: {idioma}.\n{consigna}\n"
              f"Máximo 200 palabras, en párrafos cortos, sin emojis, sin viñetas decorativas.\n\n"
              f"Datos:\n```json\n{json.dumps(payload, ensure_ascii=False, default=str)[:14000]}\n```")
    r = chat(provider, prompt, SYSTEM_ES, model=model, max_tokens=900)
    return {"ok": True, "text": r["text"], "provider": r["provider"], "model": r["model"]}


def review_etl(plan: dict, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Segunda opinión sobre el plan de ETL antes de ejecutarlo."""
    resumen = {"target": plan.get("target"),
               "steps": [{"op": s["op"], "column": s.get("column"), "reason": s["reason"]}
                         for s in plan.get("steps", [])][:120],
               "leakage": plan.get("leakage", [])[:20]}
    prompt = ("Revisá este plan de ETL. Devolvé SOLO un JSON:\n"
              '{"riesgos": ["..."], "faltantes": ["..."], "pasos_a_revisar": '
              '[{"column": "...", "motivo": "..."}], "veredicto": "una frase"}\n\n'
              f"```json\n{json.dumps(resumen, ensure_ascii=False, default=str)[:12000]}\n```")
    r = chat(provider, prompt, SYSTEM_ES, model=model, max_tokens=900)
    try:
        return {"ok": True, **_json_from(r["text"]), "provider": r["provider"], "model": r["model"]}
    except Exception:
        return {"ok": True, "veredicto": r["text"][:1500], "provider": r["provider"], "model": r["model"]}
