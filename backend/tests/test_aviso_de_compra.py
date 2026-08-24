"""El aviso de que alguien arrancó un pago.

Llega antes que el cobro confirmado, así que sirve para saber que hay alguien
decidiéndose ahora. Tiene dos requisitos que se contradicen si no se los cuida:

  · **No puede repetirse.** El que duda toca el botón varias veces; sin una
    guarda, un solo interesado manda cinco correos y el aviso deja de leerse.
  · **No puede estorbar.** Si Resend está caído, o falta la clave, o el aviso
    tarda, el comprador tiene que llegar al checkout igual. Perder una venta por
    no poder avisar de ella sería absurdo — y es el modo de falla que hay que
    probar a propósito, porque es el que no se nota hasta que pasa.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[2] / "api"
pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="hace falta Node para correr las funciones del sitio")


def _node(guion: str):
    r = subprocess.run(["node", "--input-type=module", "-e", guion],
                       capture_output=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr[-600:]
    return json.loads(r.stdout)


# ─────────────────────────────────────────────────────────────────────────────
# La guarda contra avisos repetidos
# ─────────────────────────────────────────────────────────────────────────────
def guarda(llamadas: list[dict]) -> list[bool]:
    """Corre `yaAvisado` con las claves y tiempos que se le pidan."""
    return _node(
        f"import {{ yaAvisado }} from {json.dumps((API / '_avisar.js').as_uri())};\n"
        f"const pasos = {json.dumps(llamadas)};\n"
        "console.log(JSON.stringify(pasos.map((p) => yaAvisado(p.clave, p.ahora, p.ventana))));\n"
    )


def test_el_primer_clic_avisa_y_los_siguientes_no():
    """El caso que motiva todo: el mismo cliente tocando cinco veces."""
    t = 1_700_000_000_000
    clics = [{"clave": "pago:ana@x.com:profesional-mes",
              "ahora": t + i * 4_000, "ventana": 1_800_000} for i in range(5)]
    assert guarda(clics) == [False, True, True, True, True]


def test_dos_personas_distintas_avisan_las_dos():
    """La guarda no puede tapar una venta ajena."""
    t = 1_700_000_000_000
    assert guarda([
        {"clave": "pago:ana@x.com:profesional-mes", "ahora": t, "ventana": 1_800_000},
        {"clave": "pago:beto@y.com:profesional-mes", "ahora": t + 1_000, "ventana": 1_800_000},
    ]) == [False, False]


def test_la_misma_persona_cambiando_de_plan_avisa_de_nuevo():
    """Pasar de Profesional a Empresa es información, no ruido."""
    t = 1_700_000_000_000
    assert guarda([
        {"clave": "pago:ana@x.com:profesional-mes", "ahora": t, "ventana": 1_800_000},
        {"clave": "pago:ana@x.com:empresa-anio", "ahora": t + 2_000, "ventana": 1_800_000},
    ]) == [False, False]


def test_pasada_la_ventana_vuelve_a_avisar():
    """Si vuelve al otro día, es un intento nuevo y hay que enterarse."""
    t = 1_700_000_000_000
    assert guarda([
        {"clave": "pago:ana@x.com:profesional-mes", "ahora": t, "ventana": 1_800_000},
        {"clave": "pago:ana@x.com:profesional-mes", "ahora": t + 1_800_001, "ventana": 1_800_000},
    ]) == [False, False]


def test_la_memoria_no_crece_para_siempre():
    """En una instancia de vida larga, lo vencido se tira."""
    guion = (
        f"import {{ yaAvisado }} from {json.dumps((API / '_avisar.js').as_uri())};\n"
        "const t = 1700000000000;\n"
        "for (let i = 0; i < 500; i++) yaAvisado('k' + i, t + i, 1000);\n"
        "// mucho después: la próxima llamada barre todo lo vencido\n"
        "yaAvisado('nuevo', t + 10_000_000, 1000);\n"
        "yaAvisado('nuevo', t + 10_000_000, 1000);\n"
        "console.log(JSON.stringify(yaAvisado('k0', t + 10_000_001, 1000)));\n"
    )
    # k0 venció hace rato: tiene que volver a avisar, no quedar recordado.
    assert _node(guion) is False


# ─────────────────────────────────────────────────────────────────────────────
# El cobro por encima del aviso
# ─────────────────────────────────────────────────────────────────────────────
def crear_pago(env_extra: str = "", resend_rompe: bool = False,
               email: str = "ana@empresa.com") -> dict:
    """Corre el handler real de `crear-pago.js` con MercadoPago simulado."""
    resend = ("() => { throw new Error('Resend caído'); }" if resend_rompe
              else "async () => ({ ok: true, text: async () => '' })")
    guion = f"""
      process.env.MP_ACCESS_TOKEN = 'token-de-prueba';
      process.env.SITIO = 'https://mv-automl-studio.vercel.app';
      {env_extra}

      let checkout = 0, avisos = 0;
      const romperResend = {json.dumps(resend_rompe)};
      globalThis.fetch = async (url, opciones) => {{
        if (String(url).includes('mercadopago.com')) {{
          checkout++;
          return {{ ok: true, json: async () => ({{
            init_point: 'https://www.mercadopago.com.uy/checkout/v1/redirect?pref_id=x' }}) }};
        }}
        if (String(url).includes('resend.com')) {{
          avisos++;
          if (romperResend) throw new Error('Resend caído');
          return {{ ok: true, text: async () => '' }};
        }}
        throw new Error('URL inesperada: ' + url);
      }};

      const errores = [];
      console.error = (...a) => errores.push(a.join(' '));

      const {{ default: handler }} = await import(
        {json.dumps((API / 'crear-pago.js').as_uri())});
      let estado = 0, cuerpo = null;
      const res = {{ status(c) {{ estado = c; return this; }},
                     json(x) {{ cuerpo = x; return this; }},
                     end() {{ return this; }}, setHeader() {{}} }};
      await handler({{ method: 'POST',
                       body: {{ plan: 'profesional-mes', email: {json.dumps(email)} }},
                       headers: {{ host: 'mv-automl-studio.vercel.app' }} }}, res);

      // El aviso no se espera: se le da un respiro para que corra su catch.
      await new Promise((r) => setTimeout(r, 60));
      console.log(JSON.stringify({{ estado, cuerpo, checkout, avisos, errores }}));
    """
    del resend
    return _node(guion)


def test_el_comprador_llega_al_checkout_aunque_el_aviso_no_salga():
    """El modo de falla que importa: si Resend se cae, la venta sigue."""
    r = crear_pago("process.env.RESEND_API_KEY = 're_prueba';", resend_rompe=True)
    assert r["estado"] == 200
    assert r["cuerpo"]["url"].startswith("https://www.mercadopago.com.uy/")
    assert r["checkout"] == 1, "no se creó la preferencia de pago"


def test_sin_clave_de_correo_el_cobro_funciona_igual():
    """Es el estado de hoy: RESEND_API_KEY todavía no está cargada."""
    r = crear_pago("delete process.env.RESEND_API_KEY;")
    assert r["estado"] == 200
    assert r["cuerpo"]["url"]
    assert r["avisos"] == 0, "intentó mandar correo sin clave"


def test_con_clave_de_correo_avisa_una_sola_vez():
    r = crear_pago("process.env.RESEND_API_KEY = 're_prueba';")
    assert r["estado"] == 200 and r["avisos"] == 1


def test_el_precio_del_aviso_sale_del_servidor_no_del_navegador():
    """Si el monto del aviso viniera del cliente, el correo mentiría."""
    guion = f"""
      process.env.MP_ACCESS_TOKEN = 'tok';
      process.env.RESEND_API_KEY = 're_prueba';
      let texto = '';
      globalThis.fetch = async (url, opciones) => {{
        if (String(url).includes('mercadopago.com')) {{
          return {{ ok: true, json: async () => ({{ init_point: 'https://x' }}) }};
        }}
        texto = JSON.parse(opciones.body).text;
        return {{ ok: true, text: async () => '' }};
      }};
      const {{ default: handler }} = await import(
        {json.dumps((API / 'crear-pago.js').as_uri())});
      const res = {{ status() {{ return this; }}, json() {{ return this; }},
                     end() {{ return this; }}, setHeader() {{}} }};
      await handler({{ method: 'POST',
                       body: {{ plan: 'empresa-anio', email: 'x@y.com', precio: 1 }},
                       headers: {{}} }}, res);
      await new Promise((r) => setTimeout(r, 60));
      console.log(JSON.stringify(texto));
    """
    texto = _node(guion)
    assert "US$ 1290" in texto, texto     # el del servidor
    assert "US$ 1\n" not in texto         # no el que mandó el navegador
