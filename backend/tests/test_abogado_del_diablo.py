"""Hallazgos de una auditoría adversaria, cada uno reproducido antes de arreglarlo.

No son riesgos imaginados: los tres se verificaron ejecutando contra la
aplicación —atacando los endpoints, y entrenando con datasets hostiles— antes
de escribir una línea de arreglo.

  1. **La validación de rutas usaba `startswith` sobre cadenas.** Es un
     anti-patrón conocido: `/datos/exports-privado/x` empieza con
     `/datos/exports`, así que pasaba el control y el archivo se servía. La
     forma correcta compara rutas, no texto.
  2. **Un objetivo con una sola clase entrenaba igual.** Un dataset donde
     todos los clientes pagaron no tiene nada que predecir; el programa
     devolvía un «modelo» con AUC nulo en vez de decir que el problema no
     existe. Lo peor que puede hacer una herramienta que se vende por honesta
     es entregar un resultado sin significado con cara de resultado.
  3. **El webhook de pago no comparaba el monto.** Verifica contra MercadoPago
     que el pago existe y está aprobado —eso estaba bien—, pero emitía la
     licencia del plan sin mirar cuánto se pagó.

Lo que la auditoría encontró BIEN, y conviene que quede fijado para que no se
rompa: la fuga de datos ya se detecta y se avisa, los precios viven del lado
del servidor, y el webhook no confía en su propio payload.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


# ═══════════════════════════════ 1. rutas: comparar rutas, no cadenas ════════
@pytest.mark.parametrize("modulo", ["exports.py", "bitacora.py"])
def test_la_descarga_compara_rutas_y_no_prefijos_de_texto(modulo):
    """`str(path).startswith(str(base))` deja escapar a un directorio hermano.

    Reproducido con la lógica exacta del endpoint: con `base=/tmp/x/exports` y
    un hermano `/tmp/x/exports-privado`, el pedido
    `../exports-privado/licencias.key` **pasaba** el control y el archivo se
    servía. `Path.is_relative_to` compara rutas y lo rechaza.
    """
    codigo = (RAIZ / "backend" / "app" / "api" / modulo).read_text(encoding="utf-8")

    assert "startswith(str(base))" not in codigo, (
        f"{modulo} valida la ruta comparando texto: un directorio hermano con "
        "el mismo prefijo pasa el control")
    assert "is_relative_to" in codigo, (
        f"{modulo} no usa Path.is_relative_to para validar la ruta")


def test_el_anti_patron_de_prefijos_es_realmente_explotable(tmp_path):
    """La demostración, para que nadie lo tome por un capricho de estilo."""
    base = tmp_path / "exports"
    base.mkdir()
    hermano = tmp_path / "exports-privado"
    hermano.mkdir()
    (hermano / "licencias.key").write_text("clave privada")

    pedido = (base / "../exports-privado/licencias.key").resolve()

    assert str(pedido).startswith(str(base)), (
        "si esto falla, el anti-patrón dejó de ser explotable y la prueba "
        "de arriba perdió su motivo")
    assert not pedido.is_relative_to(base), "is_relative_to tiene que rechazarlo"


# ═════════════════════ 2. un objetivo sin dos clases no es un problema ═══════
def test_un_objetivo_con_una_sola_clase_se_rechaza_con_motivo(dataset_binary):
    """Verificado antes del arreglo: entrenaba igual y devolvía AUC nulo.

    Un dataset donde todos los clientes pagaron no tiene nada que aprender. El
    programa entregaba un «modelo» con `auc: null` —un resultado sin
    significado, con la misma cara que uno bueno—. Ahora se corta antes, y el
    mensaje dice qué pasa y qué hacer.
    """
    import numpy as np
    import pandas as pd
    from app.core import automl

    df = pd.DataFrame({
        "edad": np.arange(100) % 40 + 20,
        "monto": np.arange(100) * 10.0,
        "pago": [1] * 100,          # una sola clase: no hay nada que predecir
    })

    with pytest.raises(ValueError, match="(?i)un solo valor|una sola clase"):
        automl._validar_objetivo(df, "pago")


def test_un_objetivo_con_dos_clases_pasa(dataset_binary):
    """Lo que anda tiene que seguir andando."""
    import numpy as np
    import pandas as pd
    from app.core import automl

    df = pd.DataFrame({"edad": np.arange(100), "pago": [i % 2 for i in range(100)]})

    automl._validar_objetivo(df, "pago")      # no levanta


def test_una_regresion_con_un_solo_valor_tambien_se_rechaza():
    """Predecir una columna constante es igual de inútil, y el caso llega solo:
    una columna de «monto» que quedó en cero para todos."""
    import pandas as pd
    from app.core import automl

    df = pd.DataFrame({"x": range(100), "monto": [0.0] * 100})

    with pytest.raises(ValueError, match="(?i)un solo valor|una sola clase"):
        automl._validar_objetivo(df, "monto")


# ═══════════════════════════ 3. el webhook mira cuánto se pagó ═══════════════
def test_el_webhook_compara_el_monto_contra_el_precio_del_plan():
    """Verificaba que el pago existiera y estuviera aprobado —bien— pero emitía
    el plan del `external_reference` sin mirar el importe.

    No es trivialmente explotable: el `external_reference` lo pone el servidor
    al crear la preferencia. Pero es la comprobación estándar de cualquier
    integración de cobros, cuesta tres líneas, y cubre el caso no adversario:
    un precio que cambió con enlaces viejos dando vueltas.
    """
    codigo = (RAIZ / "api" / "pago-confirmado.js").read_text(encoding="utf-8")

    assert "transaction_amount" in codigo, (
        "el webhook no mira el monto que se pagó")
    assert re.search(r"PRECIO|precios", codigo), (
        "el webhook no tiene contra qué comparar el monto")


def test_los_precios_no_los_pone_el_navegador():
    """Lo que la auditoría encontró bien, fijado para que no se rompa: si los
    precios dependieran de lo que manda el cliente, cualquiera compraría el
    plan Empresa por un peso."""
    codigo = (RAIZ / "api" / "crear-pago.js").read_text(encoding="utf-8")

    assert re.search(r"const PLANES\s*=", codigo), (
        "los precios ya no están fijos del lado del servidor")
    assert "req.body" not in codigo.split("const PLANES")[1].split("}")[0], (
        "el precio sale del cuerpo del pedido")


def test_el_webhook_no_le_cree_a_su_propio_payload():
    """El otro acierto que conviene fijar: un webhook falso no alcanza para
    conseguir una licencia, porque el pago se consulta contra MercadoPago y se
    exige que esté aprobado."""
    codigo = (RAIZ / "api" / "pago-confirmado.js").read_text(encoding="utf-8")

    assert "api.mercadopago.com/v1/payments" in codigo, (
        "el webhook no verifica el pago contra MercadoPago")
    assert "approved" in codigo, "el webhook no exige que el pago esté aprobado"
