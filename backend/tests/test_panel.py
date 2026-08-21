"""El panel del negocio tiene que decir la verdad sobre la plata.

Los números del panel son los que se usan para decidir si el producto da o no
da. Un error acá no rompe nada visible: simplemente muestra un ingreso que no
existe. Por eso se le da una lista de pagos armada a mano, con los casos
molestos que MercadoPago devuelve en la vida real —pendientes, rechazados,
devoluciones parciales, el mismo cliente comprando dos veces— y se verifica
cada total contra la cuenta hecha aparte.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parents[2] / "api" / "panel.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="hace falta Node para correr el panel")


def pago(estado, monto, neto, plan, correo, fecha, devuelto=0.0):
    return {
        "status": estado,
        "transaction_amount": monto,
        "transaction_details": {"net_received_amount": neto},
        "transaction_amount_refunded": devuelto,
        "external_reference": f"{plan}:1750000000000",
        "payer": {"email": correo},
        "date_approved": fecha,
        "currency_id": "USD",
        "payment_method_id": "visa",
    }


PAGOS = [
    pago("approved", 390.0, 366.60, "profesional-anio", "ana@empresa.com", "2026-08-11T10:00:00Z"),
    pago("approved", 39.0, 36.66, "profesional-mes", "ANA@empresa.com", "2026-08-03T10:00:00Z"),
    pago("approved", 1290.0, 1212.60, "empresa-anio", "beto@banco.com", "2026-07-20T10:00:00Z"),
    # devolución parcial: se cobró, pero parte volvió
    pago("approved", 129.0, 121.26, "empresa-mes", "caro@fin.com", "2026-07-05T10:00:00Z", devuelto=29.0),
    pago("pending", 39.0, 0.0, "profesional-mes", "dani@x.com", "2026-08-15T10:00:00Z"),
    pago("in_process", 39.0, 0.0, "profesional-mes", "eze@x.com", "2026-08-16T10:00:00Z"),
    pago("rejected", 390.0, 0.0, "profesional-anio", "fabi@x.com", "2026-08-17T10:00:00Z"),
    pago("cancelled", 39.0, 0.0, "profesional-mes", "gonza@x.com", "2026-08-18T10:00:00Z"),
]


@pytest.fixture(scope="module")
def resumen():
    guion = (
        f"import {{ resumirVentas }} from {json.dumps(PANEL.as_uri())};\n"
        f"console.log(JSON.stringify(resumirVentas({json.dumps(PAGOS)})));\n"
    )
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-500:]
    return json.loads(r.stdout)


def test_cuenta_clientes_distintos_no_compras(resumen):
    # Ana compró dos veces con el mismo correo en distinta caja: es un cliente.
    assert resumen["ventas"] == 4
    assert resumen["clientes"] == 3


def test_el_bruto_es_el_precio_de_lista(resumen):
    assert resumen["bruto"] == pytest.approx(390 + 39 + 1290 + 129)


def test_el_neto_descuenta_comision_y_devoluciones(resumen):
    # Lo que MercadoPago realmente deposita, menos lo que se devolvió.
    esperado = (366.60 + 36.66 + 1212.60 + 121.26) - 29.0
    assert resumen["neto"] == pytest.approx(esperado, abs=0.01)
    assert resumen["comision"] == pytest.approx(resumen["bruto"] - resumen["neto"], abs=0.01)
    assert resumen["devuelto"] == pytest.approx(29.0)


def test_los_que_no_entraron_no_suman_plata(resumen):
    assert resumen["pendientes"] == 2      # pending + in_process
    assert resumen["rechazados"] == 2      # rejected + cancelled
    # y ninguno de esos cuatro aportó un peso al neto
    assert resumen["neto"] < resumen["bruto"]


def test_abre_por_plan_y_por_mes(resumen):
    assert set(resumen["porPlan"]) == {
        "profesional-anio", "profesional-mes", "empresa-anio", "empresa-mes"}
    assert resumen["porPlan"]["empresa-anio"]["ventas"] == 1
    assert resumen["porMes"]["2026-08"]["ventas"] == 2
    assert resumen["porMes"]["2026-07"]["ventas"] == 2
    # los meses tienen que cerrar contra el total
    assert sum(m["neto"] for m in resumen["porMes"].values()) == pytest.approx(
        resumen["neto"], abs=0.01)


def test_si_falta_el_neto_no_se_inventa_un_numero(resumen):
    """Sin `net_received_amount` se usa el bruto, que es conservador hacia arriba
    pero no fabrica un dato: mejor mostrar el precio que un neto imaginario."""
    guion = (
        f"import {{ resumirVentas }} from {json.dumps(PANEL.as_uri())};\n"
        "const p = [{status:'approved', transaction_amount: 100,"
        " external_reference:'profesional-mes:1', payer:{email:'x@y.com'},"
        " date_approved:'2026-08-01T00:00:00Z', currency_id:'USD'}];\n"
        "console.log(JSON.stringify(resumirVentas(p)));\n"
    )
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-500:]
    d = json.loads(r.stdout)
    assert d["bruto"] == 100 and d["neto"] == 100 and d["comision"] == 0


def test_la_clave_del_panel_se_compara_sin_filtrar_el_tiempo():
    """`claveValida` no puede cortar en la primera letra distinta."""
    firmar = PANEL.parent / "_firmar.js"
    guion = (
        f"import {{ claveValida }} from {json.dumps(firmar.as_uri())};\n"
        "const r = [claveValida('abc','abc'), claveValida('abd','abc'),"
        " claveValida('ab','abc'), claveValida('','abc'),"
        " claveValida('abc',''), claveValida(undefined,'abc')];\n"
        "console.log(JSON.stringify(r));\n"
    )
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-500:]
    assert json.loads(r.stdout) == [True, False, False, False, False, False]
