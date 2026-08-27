"""La puerta de la descarga y el formulario de pedido de demo.

El instalador dejó de publicarse abierto: el release queda en borrador y la
única puerta es `/api/descargar`, que exige una licencia válida. Eso convierte
a la verificación de la firma en algo de lo que depende que un cliente que pagó
pueda instalar — y en la barrera que impide que cualquiera se lleve el archivo.

Acá se prueban las dos piezas que deciden:

  · `verificarLicencia`, contra licencias emitidas por el **firmador de Python**.
    Son dos implementaciones distintas del mismo algoritmo; si se separaran, el
    comprador se quedaría afuera con su licencia legítima en la mano.
  · `validar` del pedido de demo, que es lo que separa un prospecto de un robot.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from app.core import licensing as L

API = Path(__file__).resolve().parents[2] / "api"
pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="hace falta Node para correr las funciones del sitio")


def _node(guion: str):
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr[-600:]
    return json.loads(r.stdout)


def verificar_en_el_servidor(token: str, publica: str):
    """Corre el verificador real del sitio sobre un token."""
    return _node(
        f"import {{ verificarLicencia }} from {json.dumps((API / '_firmar.js').as_uri())};\n"
        f"console.log(JSON.stringify(verificarLicencia({json.dumps(token)},"
        f" {json.dumps(publica)})));\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# La puerta de la descarga
# ─────────────────────────────────────────────────────────────────────────────
def test_la_licencia_del_cliente_abre_la_descarga():
    """Firmada en Python, verificada en el sitio: tienen que coincidir."""
    priv, pub = L.generate_keypair()
    token = L.issue("paid", "Cliente que pagó", days=365, private_key_b64=priv)

    lic = verificar_en_el_servidor(token, pub)
    assert lic is not None, "el sitio rechazó una licencia legítima"
    assert lic["tier"] == "paid"
    assert lic["licensee"] == "Cliente que pagó"


def test_la_licencia_de_dueno_tambien_abre():
    priv, pub = L.generate_keypair()
    token = L.issue("owner", "Martín Viera", days=None, private_key_b64=priv)
    lic = verificar_en_el_servidor(token, pub)
    assert lic is not None and lic["tier"] == "owner"
    assert lic["expires_at"] is None


def test_una_licencia_vencida_no_abre():
    """Se dejó de pagar: el programa que ya tiene sigue siendo suyo, pero no
    puede volver a bajar el instalador con una licencia muerta."""
    priv, pub = L.generate_keypair()
    token = L.issue("paid", "Ex cliente", days=-1, private_key_b64=priv)
    assert verificar_en_el_servidor(token, pub) is None


def test_una_licencia_firmada_con_otra_clave_no_abre():
    ajena, _ = L.generate_keypair()
    _, publica_real = L.generate_keypair()
    token = L.issue("paid", "Falsificador", days=365, private_key_b64=ajena)
    assert verificar_en_el_servidor(token, publica_real) is None


@pytest.mark.parametrize("basura", [
    "", "cualquier cosa", "MVAS.", "MVAS.a.b", "MVAS..",
    "MVAS.eyJ0aWVyIjoib3duZXIifQ.", "../../etc/passwd", "null",
])
def test_nada_de_lo_que_no_sea_una_licencia_abre(basura):
    """Lo que llega por la dirección lo escribe cualquiera: no puede tumbar la
    función ni colarse."""
    _, pub = L.generate_keypair()
    assert verificar_en_el_servidor(basura, pub) is None


def test_no_alcanza_con_inventar_el_contenido():
    """Alguien arma un payload que dice «owner» y lo manda sin firma válida."""
    import base64
    _, pub = L.generate_keypair()
    payload = base64.urlsafe_b64encode(
        json.dumps({"tier": "owner", "expires_at": None, "licensee": "Yo"},
                   sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
    inventada = f"MVAS.{payload}.{'A' * 86}"
    assert verificar_en_el_servidor(inventada, pub) is None


# ─────────────────────────────────────────────────────────────────────────────
# El pedido de demo
# ─────────────────────────────────────────────────────────────────────────────
def validar_pedido(cuerpo: dict):
    return _node(
        f"import {{ validar }} from {json.dumps((API / 'solicitar-demo.js').as_uri())};\n"
        f"console.log(JSON.stringify(validar({json.dumps(cuerpo)})));\n"
    )


BUENO = {"nombre": "Ana Pérez", "empresa": "Financiera Sur", "pais": "Uruguay",
         "correo": "Ana.Perez@FinancieraSur.com", "telefono": "099 123 456",
         "mensaje": "Quiero predecir qué deudores pagan a 30 días."}


def test_un_pedido_completo_pasa_y_queda_prolijo():
    r = validar_pedido(BUENO)
    assert "error" not in r, r
    d = r["datos"]
    assert d["nombre"] == "Ana Pérez"
    assert d["correo"] == "ana.perez@financierasur.com"   # normalizado
    assert d["empresa"] == "Financiera Sur"
    assert d["mensaje"].startswith("Quiero predecir")


def test_los_campos_opcionales_son_opcionales():
    r = validar_pedido({k: v for k, v in BUENO.items()
                        if k not in ("telefono", "mensaje")})
    assert "error" not in r, r
    assert r["datos"]["telefono"] == "" and r["datos"]["mensaje"] == ""


@pytest.mark.parametrize(("campo", "valor"), [
    ("nombre", ""), ("nombre", "Al"),
    ("empresa", ""), ("pais", ""),
    ("correo", ""), ("correo", "sin-arroba"), ("correo", "ana@sinpunto"),
    ("correo", "ana@ejemplo."),
])
def test_un_pedido_incompleto_no_pasa(campo, valor):
    r = validar_pedido(BUENO | {campo: valor})
    assert "error" in r, f"{campo}={valor!r} pasó y no debería"
    assert r.get("datos") is None


def test_el_campo_trampa_corta_a_los_robots():
    """Está oculto por CSS: una persona nunca lo completa."""
    r = validar_pedido(BUENO | {"web": "http://spam.example"})
    assert "error" in r and r.get("datos") is None


def test_un_mensaje_enorme_se_recorta_en_vez_de_rebotar():
    """Alguien que pega tres páginas no tiene que perder el pedido."""
    r = validar_pedido(BUENO | {"mensaje": "x" * 9000})
    assert "error" not in r
    assert len(r["datos"]["mensaje"]) == 2000


def test_los_saltos_de_linea_no_ensucian_el_correo():
    """Los datos se arman en un correo de texto: un nombre con saltos de línea
    podría hacerle decir cualquier cosa."""
    r = validar_pedido(BUENO | {"nombre": "Ana\n\nCorreo: otro@ejemplo.com"})
    assert "error" not in r
    assert "\n" not in r["datos"]["nombre"]


# ─────────────────────────────────────────────────────────────────────────────
# Qué instalador se lleva cada uno
# ─────────────────────────────────────────────────────────────────────────────
def _pedir_descarga(token: str, publica: str) -> dict:
    """Corre `/api/descargar` de verdad, con GitHub simulado.

    Lo que interesa no es la respuesta de GitHub sino **qué archivo pide**: el
    cliente que compró tiene que recibir el instalador normal y el dueño, la
    compilación con su licencia adentro. Confundirlos en un sentido regala el
    programa entero; en el otro deja al dueño sin forma de probarlo.
    """
    guion = f"""
const pedidos = [];
globalThis.fetch = async (url, opciones) => {{
  pedidos.push(String(url));
  if (String(url).includes('/releases')) {{
    return {{ ok: true, json: async () => ([
      {{ assets: [{{ name: 'MV-AutoML-Studio-Setup.exe', url: 'https://api.github/cliente' }},
                  {{ name: 'MV-AutoML-Studio-Owner-Setup.exe', url: 'https://api.github/owner' }}] }},
    ]) }};
  }}
  return {{ ok: true, status: 302,
           headers: {{ get: () => 'https://objetos.github/' + String(url).split('/').pop() }} }};
}};
process.env.MV_LICENSE_PUBLIC_KEY = {json.dumps(publica)};
process.env.GITHUB_TOKEN = 'token-de-prueba';
const mod = await import({json.dumps((API / 'descargar.js').as_uri())});
let salida = {{}};
const res = {{
  setHeader() {{}},
  status(c) {{ salida.codigo = c; return this }},
  json(b) {{ salida.cuerpo = b; return this }},
  redirect(c, d) {{ salida.codigo = c; salida.destino = d; return this }},
}};
// La función registra cada descarga por consola: se calla mientras corre, o
// su línea se mezcla con la respuesta que lee la prueba.
const decir = console.log;
console.log = () => {{}};
await mod.default({{ query: {{ lic: {json.dumps(token)} }}, headers: {{}} }}, res);
console.log = decir;
console.log(JSON.stringify({{ ...salida, pedidos }}));
"""
    return _node(guion)


def test_el_cliente_que_pago_recibe_el_instalador_normal():
    priv, pub = L.generate_keypair()
    token = L.issue("paid", "Cliente", days=365, private_key_b64=priv)

    r = _pedir_descarga(token, pub)
    assert r["codigo"] == 302, r
    assert "cliente" in r["destino"], r["destino"]


def test_el_dueno_recibe_la_compilacion_owner():
    """Sin esto, probar la versión completa pide entrar a GitHub y bajar a mano
    un release en borrador. La licencia de dueño ya alcanza."""
    priv, pub = L.generate_keypair()
    token = L.issue("owner", "Owner", days=None, private_key_b64=priv)

    r = _pedir_descarga(token, pub)
    assert r["codigo"] == 302, r
    assert "owner" in r["destino"], r["destino"]


def test_una_licencia_vencida_no_se_lleva_ninguno():
    priv, pub = L.generate_keypair()
    token = L.issue("owner", "Owner", days=0, private_key_b64=priv)

    r = _pedir_descarga(token, pub)
    assert r["codigo"] == 403, r
    assert not r.get("destino")
