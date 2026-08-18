"""Genera `gestiones_con_texto.csv`: gestiones de cobranza sintéticas.

El dataset de ejemplo tiene que servir para mostrar el producto de verdad, así
que la señal está donde estaría en la vida real: el atraso, el monto, si hubo
contacto efectivo y el historial de promesas explican la mayor parte del pago,
y la nota del gestor **aporta** —describe la predisposición del deudor— sin
contener la respuesta. Un texto que diga «confirma la transferencia» es fuga,
no una feature: con eso el modelo da AUC 1.0 y no se aprende nada.

Los datos son inventados de punta a punta. No hay ninguna persona real acá.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FILAS = 3000
SEMILLA = 20260818

CANALES = {                    # efecto del canal sobre el pago (log-odds)
    "whatsapp": 0.45,
    "telefono": 0.30,
    "email": -0.10,
    "visita": 0.15,
}

# Notas por predisposición. Cada grupo empuja el pago en una dirección, pero
# ninguna nota lo determina: la misma frase aparece en casos que pagan y en
# casos que no.
NOTAS = {
    0.9: [  # buena predisposición
        "pide plan de pagos en tres cuotas y deja telefono alternativo",
        "manifiesta intencion de regularizar apenas cobre el sueldo",
        "consulta el monto exacto para ponerse al dia esta semana",
        "solicita que le enviemos los datos de la cuenta por escrito",
    ],
    0.0: [  # contacto neutro
        "se deja mensaje en el contestador con los datos de contacto",
        "atiende y pide volver a llamar en horario de la tarde",
        "se envia detalle de la deuda por el canal habitual",
        "toma nota de la gestion sin comprometer una fecha",
    ],
    -0.9: [  # mala predisposición
        "no atiende el telefono, el numero figura fuera de servicio",
        "atendio un tercero que dice no conocer al titular",
        "sin respuesta a los mensajes, la direccion registrada es incorrecta",
        "se niega a pagar y menciona que iniciara un reclamo",
    ],
}


def generar(filas: int = FILAS, semilla: int = SEMILLA) -> pd.DataFrame:
    r = np.random.default_rng(semilla)

    dias = np.clip(r.gamma(2.2, 55, filas), 1, 900).round()
    monto = np.clip(r.lognormal(10.6, 0.85, filas), 800, 4_000_000).round(2)
    canal = r.choice(list(CANALES), filas, p=[0.34, 0.28, 0.24, 0.14])
    contacto = r.random(filas) < (0.72 - 0.22 * (dias > 180))
    promesas = r.poisson(0.8, filas)

    # El gestor escribe según lo que pasó en la gestión. La nota se relaciona
    # con el contacto, pero no lo calca: si calcara, el texto sería la
    # respuesta disfrazada y el modelo daría un AUC perfecto y mentiroso.
    tono = np.where(
        ~contacto,
        r.choice([-0.9, 0.0, 0.9], filas, p=[0.45, 0.50, 0.05]),
        r.choice([0.9, 0.0, -0.9], filas, p=[0.40, 0.38, 0.22]),
    )

    logit = (
        2.9
        - 3.8 * np.log10(dias)                # cuanto más viejo, menos se cobra
        - 1.1 * np.log10(monto / 20_000)      # el monto grande cuesta más
        + 3.4 * contacto                      # hablar con la persona pesa
        + 1.1 * promesas                      # historial de cumplimiento
        + np.array([CANALES[c] for c in canal])
        + 0.6 * tono                          # la nota aporta, no decide
        + r.normal(0, 0.15, filas)            # todo lo que no se observa
    )
    paga = (1 / (1 + np.exp(-logit)) > r.random(filas)).astype(int)

    notas = [r.choice(NOTAS[t]) for t in tono]
    return pd.DataFrame({
        "IdGestion": np.arange(1, filas + 1),
        "DiasAtraso": dias,
        "MontoDeuda": monto,
        "Canal": canal,
        "ContactoEfectivo": np.where(contacto, "si", "no"),
        "PromesasCumplidas": promesas,
        "NotaGestor": notas,
        "Pago30d": paga,
    })


if __name__ == "__main__":
    df = generar()
    salida = Path(__file__).resolve().parent / "gestiones_con_texto.csv"
    df.to_csv(salida, index=False, sep=";", encoding="utf-8-sig")
    print(f"{len(df)} filas → {salida}")
    print(f"tasa de pago: {df['Pago30d'].mean():.1%}")
