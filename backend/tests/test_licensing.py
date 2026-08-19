"""Licencias, niveles y autenticación local."""
from __future__ import annotations

import io
import json
import os
import time

import numpy as np
import pandas as pd
import pytest
from app.core import licensing as L

PRIV = os.environ["MV_TEST_PRIVATE_KEY"]


def _demo(monkeypatch):
    """Fuerza el nivel demo sin tocar la licencia global de la suite."""
    monkeypatch.setattr(L, "load", lambda: None)


def _csv(n=100, seed=0):
    rng = np.random.default_rng(seed)
    buf = io.BytesIO()
    pd.DataFrame({"x": rng.normal(0, 1, n), "y": rng.binomial(1, .5, n)}).to_csv(buf, index=False)
    return buf.getvalue()


# ── firma y verificación ─────────────────────────────────────────────────────
def test_emitir_y_verificar():
    tok = L.issue("paid", "Cliente Uno", days=30, private_key_b64=PRIV)
    lic = L.verify(tok)
    assert lic.tier == "paid" and lic.licensee == "Cliente Uno"
    assert 29 <= lic.days_left <= 30


def test_firma_corrupta_se_rechaza():
    tok = L.issue("paid", "x", private_key_b64=PRIV)
    with pytest.raises(L.LicenseError, match="firma"):
        L.verify(tok[:-6] + "AAAAAA")


def test_payload_adulterado_se_rechaza():
    """Cambiar demo→owner en el payload sin re-firmar no puede funcionar."""
    import base64
    import json
    tok = L.issue("demo", "x", private_key_b64=PRIV)
    pre, payload, sig = tok.split(".")
    datos = json.loads(base64.urlsafe_b64decode(payload + "==="))
    datos["tier"] = "owner"
    crudo = json.dumps(datos, sort_keys=True, separators=(",", ":")).encode()
    falso = base64.urlsafe_b64encode(crudo).decode().rstrip("=")
    with pytest.raises(L.LicenseError):
        L.verify(f"{pre}.{falso}.{sig}")


def test_clave_ajena_no_valida():
    otra_priv, _ = L.generate_keypair()
    tok = L.issue("owner", "atacante", private_key_b64=otra_priv)
    with pytest.raises(L.LicenseError):
        L.verify(tok)


def test_vencimiento():
    tok = L.issue("paid", "x", days=0, private_key_b64=PRIV)
    with pytest.raises(L.LicenseError, match="venció"):
        L.verify(tok)


def test_formato_invalido():
    for basura in ["", "hola", "MVAS.solo-dos", "OTRO.a.b"]:
        with pytest.raises(L.LicenseError):
            L.verify(basura)


# ── niveles ──────────────────────────────────────────────────────────────────
def test_los_tres_niveles_estan_definidos():
    assert set(L.TIERS) == {"demo", "paid", "owner"}
    assert L.TIERS["demo"].max_rows == 50_000
    assert L.TIERS["paid"].max_rows is None
    assert L.TIERS["owner"].diagnostics and not L.TIERS["paid"].diagnostics


def test_sin_licencia_es_demo(monkeypatch):
    _demo(monkeypatch)
    assert L.current_tier().name == "demo"
    with pytest.raises(PermissionError):
        L.require("sql_connectors")
    with pytest.raises(PermissionError):
        L.check_rows(60_000)
    L.check_rows(50_000)          # dentro del tope pasa
    assert L.cap_budget(600) == 60
    assert L.cap_families(None) == 3


def test_con_licencia_de_la_suite_es_owner():
    assert L.current_tier().name == "owner"
    L.require("diagnostics")      # no lanza


# ── API ──────────────────────────────────────────────────────────────────────
def test_estado_nunca_expone_el_token(client):
    st = client.get("/api/license/status").json()
    assert st["tier"] == "owner"
    assert "token" not in str(st).lower() or st.get("token") is None
    assert "MVAS." not in str(st)


def test_activar_licencia_valida_por_api(client, tmp_root):
    tok = L.issue("paid", "cliente api", days=10, private_key_b64=PRIV)
    r = client.post("/api/license/activate", json={"token": tok, "persist": False})
    assert r.status_code == 200 and r.json()["tier"] == "paid"
    # restaurar el estado de la suite
    L.deactivate()
    assert client.get("/api/license/status").json()["tier"] == "owner"


def test_activar_basura_da_400(client):
    assert client.post("/api/license/activate", json={"token": "x.y.z"}).status_code == 400


def test_demo_bloquea_conectores_y_scoring(client, monkeypatch):
    _demo(monkeypatch)
    r = client.post("/api/connections/test", json={"engine": "sqlite", "database": ":memory:"})
    assert r.status_code == 402
    assert r.json()["code"] == "license_limit"
    r = client.post("/api/automl/score", json={"model_id": "m", "dataset_id": "d"})
    assert r.status_code == 402


def test_demo_limita_filas_en_la_subida(client, monkeypatch):
    # workspace propio, creado ANTES de forzar demo, para que el tope que corte
    # sea el de filas y no el de cantidad de datasets acumulados por la suite
    client.post("/api/workspaces", json={"name": "ws-demo-filas"})
    h = {"X-Workspace": "ws-demo-filas"}
    try:
        _demo(monkeypatch)
        rng = np.random.default_rng(1)
        buf = io.BytesIO()
        pd.DataFrame({"x": rng.normal(0, 1, 60_000)}).to_csv(buf, index=False)
        r = client.post("/api/datasets/upload-stream?filename=grande.csv&name=grande",
                        content=buf.getvalue(), headers=h)
        assert r.status_code == 402
        assert "50" in r.json()["detail"]
        # y el dataset no quedó a medias en el workspace
        assert client.get("/api/datasets", headers=h).json()["datasets"] == []
    finally:
        monkeypatch.undo()
        client.delete("/api/workspaces/ws-demo-filas")


def test_emision_por_api_requiere_owner(client, monkeypatch):
    tok = client.post("/api/license/issue", json={
        "tier": "paid", "licensee": "emitida por api", "days": 5, "private_key": PRIV,
    })
    assert tok.status_code == 200
    assert L.verify(tok.json()["token"]).licensee == "emitida por api"
    _demo(monkeypatch)
    r = client.post("/api/license/issue", json={
        "tier": "paid", "licensee": "x", "private_key": PRIV})
    assert r.status_code == 402


# ── autenticación local ──────────────────────────────────────────────────────
def test_token_de_sesion(client, monkeypatch):
    monkeypatch.setenv("MV_API_TOKEN", "token-de-prueba-123")
    assert client.get("/api/datasets").status_code == 401
    assert client.get("/api/datasets", headers={"X-MV-Token": "otro"}).status_code == 401
    assert client.get("/api/datasets", headers={"X-MV-Token": "token-de-prueba-123"}).status_code == 200
    assert client.get("/api/datasets?token=token-de-prueba-123").status_code == 200
    assert client.get("/api/health").status_code == 200      # público para diagnóstico
    assert client.get("/").status_code == 200                # la interfaz carga


def test_la_prueba_vence_y_la_licencia_la_destraba(tmp_path, monkeypatch):
    """El circuito comercial completo: probás, se vence, pagás, seguís."""
    monkeypatch.delenv("MV_LICENSE", raising=False)   # la suite corre como owner
    monkeypatch.setattr(L, "DEMO_DIAS", 15)
    monkeypatch.setattr(L, "_marca_de_inicio", lambda: tmp_path / ".prueba")
    L.deactivate()

    assert L.dias_de_prueba_restantes() == 15 and not L.prueba_vencida()
    L.check_rows(1000)                                   # trabaja normal

    (tmp_path / ".prueba").write_text(json.dumps({"desde": time.time() - 16 * 86400}))
    assert L.prueba_vencida()
    for llamada in (lambda: L.check_rows(100), lambda: L.cap_budget(60),
                    lambda: L.require("export_excel")):
        with pytest.raises(PermissionError, match="prueba"):
            llamada()

    L.activate(L.issue("paid", "Cliente", days=365, private_key_b64=PRIV))
    L.check_rows(5_000_000)                              # la licencia destraba
    assert not L.prueba_vencida()

    L.deactivate()
    assert L.prueba_vencida(), "borrar la licencia no puede reiniciar el reloj"
    L.load()                       # deja el estado como lo encontró


def test_el_estado_informa_los_dias_que_quedan(tmp_path, monkeypatch):
    monkeypatch.delenv("MV_LICENSE", raising=False)
    monkeypatch.setattr(L, "_marca_de_inicio", lambda: tmp_path / ".prueba")
    L.deactivate()
    st = L.status()
    assert st["trial_days_left"] == L.DEMO_DIAS and st["trial_expired"] is False
