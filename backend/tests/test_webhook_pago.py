"""El webhook de MercadoPago, ejercitado como lo ejercita MercadoPago.

`test_circuito_comercial.py` prueba el firmador. Esto prueba el paso anterior:
el aviso de pago llega, el servidor decide si corresponde emitir, y con qué
plan. Ahí es donde están las decisiones que pueden costar plata:

  · si le creyera al cuerpo del aviso, cualquiera mandaría un POST diciendo
    «pagado» y se llevaría una licencia sin pagar;
  · si emitiera con un pago pendiente, entregaría el producto antes de cobrar;
  · si se equivocara de plan, le daría un año a quien compró un mes.

Se corre el archivo real `api/pago-confirmado.js` con la red interceptada: el
`fetch` devuelve el pago que queremos, sin salir a internet.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from app.core import licensing as L

RAIZ = Path(__file__).resolve().parents[2]
WEBHOOK = RAIZ / "api" / "pago-confirmado.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="hace falta Node para correr el webhook")


def llamar_al_webhook(pago: dict, privada: str, cuerpo: dict | None = None,
                      sin_cabeceras: bool = False) -> dict:
    """Corre el handler real con `fetch` interceptado. Devuelve lo que registró."""
    cabeceras = "" if sin_cabeceras else "headers: { host: 'mv-automl-studio.vercel.app' }"
    guion = f"""
      process.env.MP_ACCESS_TOKEN = 'token-de-prueba';
      process.env.MV_LICENSE_PRIVATE_KEY = {json.dumps(privada)};
      delete process.env.RESEND_API_KEY;          // sin correo: sólo el registro

      // La red no existe: el pago es el que dice la prueba. Si el handler
      // dejara de consultar y le creyera al aviso, esto no se llamaría nunca
      // y la licencia saldría igual — que es exactamente el agujero a evitar.
      let consultas = 0;
      globalThis.fetch = async (url, opciones) => {{
        consultas++;
        if (!String(url).includes('/v1/payments/')) throw new Error('URL inesperada: ' + url);
        if (opciones?.headers?.Authorization !== 'Bearer token-de-prueba') {{
          throw new Error('el webhook consultó sin el token del servidor');
        }}
        return {{ ok: true, json: async () => ({json.dumps(pago)}) }};
      }};

      const registrado = [];
      console.log = (...a) => registrado.push(a.join(' '));
      const errores = [];
      console.error = (...a) => errores.push(a.join(' '));

      const {{ default: handler }} = await import({json.dumps(WEBHOOK.as_uri())});
      let estado = 0;
      const res = {{ status(c) {{ estado = c; return this; }}, end() {{ return this; }},
                     json(x) {{ return this; }}, setHeader() {{}} }};
      await handler({{ method: 'POST', body: {json.dumps(cuerpo or {"data": {"id": "999"}})},
                       query: {{}}, {cabeceras} }}, res);

      process.stderr.write(JSON.stringify(
        {{ estado, consultas, registrado, errores }}) + '\\n');
    """
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr[-600:]
    return json.loads(r.stderr.strip().splitlines()[-1])


def pago_aprobado(plan: str) -> dict:
    return {
        "status": "approved",
        "external_reference": f"{plan}:1750000000000",
        "payer": {"email": "cliente@empresa.com", "first_name": "Ana", "last_name": "Pérez"},
        "transaction_amount": 39,
        "currency_id": "USD",
    }


@pytest.mark.parametrize(("plan", "dias"), [
    ("profesional-mes", 30),
    ("profesional-anio", 365),
    ("empresa-mes", 30),
    ("empresa-anio", 365),
])
def test_pago_aprobado_emite_la_licencia_del_plan_que_compro(plan, dias, monkeypatch):
    priv, pub = L.generate_keypair()
    monkeypatch.setattr(L, "PUBLIC_KEY_B64", pub)

    salida = llamar_al_webhook(pago_aprobado(plan), priv)
    assert salida["estado"] == 200
    assert salida["consultas"] == 1, "el webhook tiene que consultar el pago, no creerle al aviso"
    assert not salida["errores"], salida["errores"]

    registro = json.loads(salida["registrado"][0])
    assert registro["plan"] == plan
    assert registro["titular"] == "Ana Pérez"
    assert registro["correo"] == "cliente@empresa.com"

    # y la licencia que emitió sirve de verdad en el programa
    lic = L.verify(registro["licencia"])
    assert lic.tier == "paid"
    assert lic.days_left == dias
    assert f"plan:{plan}" in (lic.notes or "")
    assert "pago:999" in (lic.notes or "")      # queda atada a la operación


def test_el_cobro_no_se_cae_si_el_pedido_llega_sin_cabeceras(monkeypatch):
    """El enlace de descarga se arma con el host del pedido cuando falta SITIO.
    Si eso lanzara, la excepción cancelaría la emisión: el cliente habría pagado
    y no recibiría ni la licencia. Vale más un enlace feo que ninguna licencia."""
    priv, pub = L.generate_keypair()
    monkeypatch.setattr(L, "PUBLIC_KEY_B64", pub)

    guion_sin_cabeceras = llamar_al_webhook(
        pago_aprobado("profesional-anio"), priv, sin_cabeceras=True)
    assert not guion_sin_cabeceras["errores"], guion_sin_cabeceras["errores"]
    registro = json.loads(guion_sin_cabeceras["registrado"][0])
    assert L.verify(registro["licencia"]).tier == "paid"


@pytest.mark.parametrize("estado", ["pending", "in_process", "rejected", "cancelled"])
def test_un_pago_que_no_esta_aprobado_no_emite_nada(estado, monkeypatch):
    priv, pub = L.generate_keypair()
    monkeypatch.setattr(L, "PUBLIC_KEY_B64", pub)

    pago = pago_aprobado("profesional-anio") | {"status": estado}
    salida = llamar_al_webhook(pago, priv)
    assert salida["estado"] == 200            # a MercadoPago se le contesta bien igual
    assert not any("MVAS." in linea for linea in salida["registrado"]), \
        f"se emitió una licencia con un pago en estado {estado}"


def test_no_le_cree_al_aviso_aunque_venga_diciendo_aprobado(monkeypatch):
    """El aviso puede mentir; el estado siempre sale de la consulta."""
    priv, pub = L.generate_keypair()
    monkeypatch.setattr(L, "PUBLIC_KEY_B64", pub)

    # el atacante manda un cuerpo completo, con todo lo que haría falta
    cuerpo = {"data": {"id": "999"}, "status": "approved",
              "external_reference": "empresa-anio:1", "payer": {"email": "gratis@vivo.com"}}
    # pero el pago real, el que devuelve la consulta, está rechazado
    salida = llamar_al_webhook(pago_aprobado("empresa-anio") | {"status": "rejected"},
                               priv, cuerpo=cuerpo)
    assert not any("MVAS." in linea for linea in salida["registrado"])


def test_un_plan_desconocido_no_emite_una_licencia_cualquiera(monkeypatch):
    priv, pub = L.generate_keypair()
    monkeypatch.setattr(L, "PUBLIC_KEY_B64", pub)

    pago = pago_aprobado("plan-que-no-existe")
    salida = llamar_al_webhook(pago, priv)
    assert not any("MVAS." in linea for linea in salida["registrado"])
    assert any("plan desconocido" in e for e in salida["errores"])
