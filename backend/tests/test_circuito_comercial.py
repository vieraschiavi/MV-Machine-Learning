"""El camino completo del cliente: prueba, vencimiento, pago y activación.

Esta prueba cruza los dos mundos del producto: la licencia la **emite el
servidor web en JavaScript** cuando MercadoPago confirma el pago, y la
**verifica el programa en Python** en la máquina del cliente. Si esos dos lados
dejaran de firmar exactamente los mismos bytes, el cliente pagaría y no podría
activar — y nadie se enteraría hasta la primera venta.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from app.core import licensing as L

FIRMADOR = Path(__file__).resolve().parents[2] / "api" / "pago-confirmado.js"
sin_node = pytest.mark.skipif(shutil.which("node") is None,
                              reason="hace falta Node para emitir como el servidor web")


def emitir_como_el_servidor(clave_privada: str, plan: str, titular: str) -> str:
    """Corre el mismo código que el servidor usa tras un pago aprobado."""
    # Se lee el firmador real y se ejecuta su función tal cual está escrita: si
    # alguien la cambia y deja de coincidir con el verificador, esto lo caza.
    fuente = FIRMADOR.read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("const b64url"):fuente.index("async function enviarPorCorreo")]
    guion = f"""
      const crypto = require('node:crypto');
      const emitirLicencia = new Function('crypto',
        {json.dumps(cuerpo)} + '; return emitirLicencia;')(crypto);
      const dias = {{'profesional-mes': 31, 'profesional-anio': 366,
                     'empresa-mes': 31, 'empresa-anio': 366}}[{json.dumps(plan)}];
      console.log(emitirLicencia('paid', {json.dumps(titular)}, dias,
                                 {json.dumps(clave_privada)}, 'plan:' + {json.dumps(plan)}));
    """
    r = subprocess.run(["node", "-e", guion], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError(f"el firmador del servidor falló: {r.stderr[-400:]}")
    return r.stdout.strip()


@sin_node
@pytest.mark.parametrize(("plan", "dias"), [
    ("profesional-mes", 30),
    ("profesional-anio", 365),
    ("empresa-anio", 365),
])
def test_el_cliente_paga_y_su_licencia_activa_el_programa(plan, dias, tmp_path, monkeypatch):
    monkeypatch.delenv("MV_LICENSE", raising=False)
    monkeypatch.setattr(L, "_marca_de_inicio", lambda: tmp_path / ".prueba")
    L.deactivate()

    priv, pub = L.generate_keypair()
    monkeypatch.setattr(L, "PUBLIC_KEY_B64", pub)

    # 1 · el cliente instala y arranca en prueba, con sus topes
    demo = L.current_tier()
    assert demo.name == "demo" and demo.max_rows == 50_000
    assert not demo.sql_connectors and demo.export_watermark

    # 2 · se le vence la prueba y el programa deja de trabajar
    (tmp_path / ".prueba").write_text(json.dumps({"desde": time.time() - 999 * 86400}))
    assert L.prueba_vencida()
    with pytest.raises(PermissionError, match="prueba"):
        L.check_rows(10)

    # 3 · paga, y el servidor web le emite la licencia
    token = emitir_como_el_servidor(priv, plan, "Cliente que pagó")

    # 4 · la pega en el programa y queda habilitado
    L.activate(token)
    lic, nivel = L.verify(token), L.current_tier()
    assert nivel.name == "paid"
    assert lic.days_left == dias
    assert nivel.max_rows is None and nivel.max_datasets is None
    assert not nivel.export_watermark            # sin marca de agua al exportar
    assert plan in (lic.notes or "")             # queda qué plan compró
    L.check_rows(5_000_000)
    for funcion in ("sql_connectors", "ai_providers", "text_features", "scoring"):
        L.require(funcion)
    assert not L.prueba_vencida()

    # 5 · y sigue habilitado aunque la prueba original esté vencida
    assert L.status()["licensed"] is True
    L.deactivate()
    L.load()


@sin_node
def test_una_licencia_de_otra_clave_no_sirve(tmp_path, monkeypatch):
    """Si alguien firma con su propia clave, el programa la rechaza."""
    monkeypatch.delenv("MV_LICENSE", raising=False)
    monkeypatch.setattr(L, "_marca_de_inicio", lambda: tmp_path / ".prueba")
    L.deactivate()

    ajena, _ = L.generate_keypair()
    _, publica_real = L.generate_keypair()
    monkeypatch.setattr(L, "PUBLIC_KEY_B64", publica_real)

    token = emitir_como_el_servidor(ajena, "profesional-anio", "Falsificador")
    with pytest.raises(L.LicenseError):
        L.verify(token)
    L.load()
