"""Capa de proveedores de IA. Ninguna prueba sale a la red."""
from __future__ import annotations

import pytest
from app.api.ai import _heuristic_target
from app.core import ai as AI

COLUMNAS = [
    {"name": "IdCliente", "kind": "numeric", "distinct": 30000, "null_pct": 0},
    {"name": "Estado", "kind": "categorical", "distinct": 3, "null_pct": 0},
    {"name": "ScoreCash", "kind": "categorical", "distinct": 6, "null_pct": 0},
    {"name": "DiasAtraso", "kind": "numeric", "distinct": 900, "null_pct": 0},
    {"name": "CuotaRef", "kind": "numeric", "distinct": 9000, "null_pct": 0},
    {"name": "Pago", "kind": "numeric", "distinct": 2, "null_pct": 0},
]


def test_estan_los_cinco_proveedores_pedidos():
    for p in ["openai", "anthropic", "xai", "google", "copilot"]:
        assert p in AI.PROVIDERS
        assert AI.PROVIDERS[p]["label"]
        assert AI.PROVIDERS[p]["fallback_models"]


def test_sin_clave_no_hay_proveedor_activo():
    assert AI.active_provider() is None


def test_configuracion_publica_nunca_expone_la_clave():
    AI.save_config("openai", api_key="sk-secreto-de-prueba-123456", model="gpt-4.1")
    pub = AI.public_config("openai")
    assert "api_key" not in pub
    assert pub["has_key"] is True
    assert "secreto" not in pub["key_masked"]
    assert AI.get_config("openai")["api_key"] == "sk-secreto-de-prueba-123456"
    AI.save_config("openai", api_key="")
    assert AI.public_config("openai")["has_key"] is False


def test_proveedor_desconocido_se_rechaza():
    with pytest.raises(AI.AIError):
        AI.get_config("proveedor_inventado")


def test_chat_sin_clave_avisa_en_vez_de_llamar():
    with pytest.raises(AI.AIError, match="clave"):
        AI.chat("anthropic", "hola")


def test_verificar_sin_clave_devuelve_error_controlado():
    r = AI.verify("google")
    assert r["ok"] is False
    assert r["error"]


def test_actualizar_modelos_sin_clave_cae_a_la_lista_de_respaldo():
    r = AI.refresh_models("xai")
    assert r["ok"] is False
    assert r["models"] == AI.PROVIDERS["xai"]["fallback_models"]


def test_extraccion_de_json_tolera_bloques_de_codigo():
    assert AI._json_from('```json\n{"a": 1}\n```') == {"a": 1}
    assert AI._json_from('texto previo {"b": 2} texto posterior') == {"b": 2}
    assert AI._json_from('[1, 2, 3]') == [1, 2, 3]


@pytest.mark.parametrize("objetivo,esperado", [
    ("quiero predecir si el cliente va a pagar", "Pago"),
    ("predict whether the customer will pay", "Pago"),
    ("prever se o cliente vai pagar", "Pago"),
    ("estimar los dias de atraso", "DiasAtraso"),
    ("customer risk score", "ScoreCash"),
])
def test_heuristica_sin_ia_encuentra_la_columna_en_tres_idiomas(objetivo, esperado):
    r = _heuristic_target(COLUMNAS, objetivo)
    assert r["target"] == esperado
    assert r["confidence"] > 0


def test_la_heuristica_no_propone_un_identificador():
    r = _heuristic_target(COLUMNAS, "el id del cliente")
    assert r["target"] != "IdCliente"


def test_la_heuristica_reconoce_una_pregunta_de_si_o_no():
    r = _heuristic_target(COLUMNAS, "si el cliente va a pagar")
    assert r["task"] == "binary"


def test_sin_coincidencias_ofrece_alternativas():
    r = _heuristic_target(COLUMNAS, "el color favorito del gerente")
    assert r["target"] is None
    assert r["alternatives"]


def test_el_respaldo_de_claude_no_quedo_en_la_generacion_4():
    # Sin clave, la pantalla muestra esta lista: tiene que ser la generación actual.
    respaldo = AI.PROVIDERS["anthropic"]["fallback_models"]
    assert "claude-opus-5" in respaldo and "claude-sonnet-5" in respaldo
    assert not any(m.startswith(("claude-sonnet-4-5", "claude-opus-4-1")) for m in respaldo)


def test_actualizar_modelos_de_claude_sigue_todas_las_paginas(monkeypatch):
    import httpx

    paginas = {
        None: {"data": [{"id": "claude-opus-5"}, {"id": "claude-sonnet-5"}],
               "has_more": True, "last_id": "claude-sonnet-5"},
        "claude-sonnet-5": {"data": [{"id": "claude-haiku-4-5"}],
                            "has_more": False, "last_id": "claude-haiku-4-5"},
    }
    pedidos = []

    def manejar(req: httpx.Request) -> httpx.Response:
        after = req.url.params.get("after_id")
        pedidos.append(after)
        assert req.headers["x-api-key"] == "sk-ant-prueba"
        return httpx.Response(200, json=paginas[after])

    transporte = httpx.MockTransport(manejar)
    monkeypatch.setattr(AI, "_client", lambda timeout=None: httpx.Client(transport=transporte))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")

    r = AI.refresh_models("anthropic")
    assert r["ok"], r
    assert pedidos == [None, "claude-sonnet-5"]
    assert r["models"] == ["claude-haiku-4-5", "claude-opus-5", "claude-sonnet-5"]
