"""Escribe los datasets de ejemplo en inglés y en portugués.

Los videos del sitio se graban en tres idiomas. La interfaz ya se traducía, pero
los datos no: en el video en inglés los indicadores del tablero decían
`MontoACobrarVencido` y `PorcentajeTotalCobradoSobreAcumulado`, porque un KPI se
llama como la columna de la que sale. Media pantalla en inglés y media en
castellano no se lee como un producto internacional: se lee como una traducción
a medio hacer.

Los números NO se regeneran. Se toma el dataset en castellano y se le cambian
los nombres de columna y las categorías, así el mismo video en tres idiomas
muestra exactamente las mismas cifras y se puede comparar cuadro a cuadro.

Uso:
    python examples/traducir.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
IDIOMAS = ("en", "pt")

# ── gestiones de cobranza ────────────────────────────────────────────────────
COLUMNAS_GESTIONES = {
    "en": {
        "IdGestion": "ActionId", "DiasAtraso": "DaysPastDue", "MontoDeuda": "DebtAmount",
        "Canal": "Channel", "ContactoEfectivo": "ReachedCustomer",
        "PromesasCumplidas": "PromisesKept", "NotaGestor": "AgentNote",
        "Pago30d": "PaidIn30d",
    },
    "pt": {
        "IdGestion": "IdAcao", "DiasAtraso": "DiasAtraso", "MontoDeuda": "ValorDivida",
        "Canal": "Canal", "ContactoEfectivo": "ContatoEfetivo",
        "PromesasCumplidas": "PromessasCumpridas", "NotaGestor": "NotaOperador",
        "Pago30d": "Pagou30d",
    },
}
VALORES_GESTIONES = {
    "en": {
        "Channel": {"whatsapp": "whatsapp", "telefono": "phone", "email": "email",
                    "visita": "visit"},
        "ReachedCustomer": {"si": "yes", "no": "no"},
    },
    "pt": {
        "Canal": {"whatsapp": "whatsapp", "telefono": "telefone", "email": "email",
                  "visita": "visita"},
        "ContatoEfetivo": {"si": "sim", "no": "nao"},
    },
}
# La nota del gestor es texto libre y es una feature de verdad (se vectoriza con
# TF-IDF), así que se traduce frase por frase y no se deja en castellano: si no,
# el video en inglés muestra el módulo de texto libre leyendo español.
NOTAS = {
    "pide plan de pagos en tres cuotas y deja telefono alternativo": {
        "en": "asks for a three-instalment plan and leaves an alternate phone",
        "pt": "pede plano de pagamento em tres parcelas e deixa telefone alternativo"},
    "manifiesta intencion de regularizar apenas cobre el sueldo": {
        "en": "says they intend to catch up as soon as they get paid",
        "pt": "manifesta intencao de regularizar assim que receber o salario"},
    "consulta el monto exacto para ponerse al dia esta semana": {
        "en": "asks for the exact amount to settle up this week",
        "pt": "consulta o valor exato para ficar em dia esta semana"},
    "solicita que le enviemos los datos de la cuenta por escrito": {
        "en": "requests the account details in writing",
        "pt": "solicita que enviemos os dados da conta por escrito"},
    "se deja mensaje en el contestador con los datos de contacto": {
        "en": "voicemail left with the contact details",
        "pt": "deixada mensagem na secretaria eletronica com os dados de contato"},
    "atiende y pide volver a llamar en horario de la tarde": {
        "en": "answers and asks us to call back in the afternoon",
        "pt": "atende e pede para ligar novamente a tarde"},
    "se envia detalle de la deuda por el canal habitual": {
        "en": "debt breakdown sent through the usual channel",
        "pt": "enviado detalhe da divida pelo canal habitual"},
    "toma nota de la gestion sin comprometer una fecha": {
        "en": "takes note of the call without committing to a date",
        "pt": "toma nota do contato sem se comprometer com uma data"},
    "no atiende el telefono, el numero figura fuera de servicio": {
        "en": "no answer, the number is reported out of service",
        "pt": "nao atende o telefone, o numero consta fora de servico"},
    "atendio un tercero que dice no conocer al titular": {
        "en": "a third party answered and says they do not know the account holder",
        "pt": "atendeu um terceiro que diz nao conhecer o titular"},
    "sin respuesta a los mensajes, la direccion registrada es incorrecta": {
        "en": "no reply to messages, the address on file is wrong",
        "pt": "sem resposta as mensagens, o endereco registrado esta incorreto"},
    "se niega a pagar y menciona que iniciara un reclamo": {
        "en": "refuses to pay and says they will file a complaint",
        "pt": "recusa-se a pagar e menciona que iniciara uma reclamacao"},
}

# ── panel mensual de cobranzas ───────────────────────────────────────────────
COLUMNAS_PANEL = {
    "en": {
        "FechaObs": "ObsDate", "Año": "Year", "Mes": "Month",
        "TramoDeuda": "AgeingBucket", "TipoCliente": "CustomerType",
        "MontoACobrarDelMes": "DueThisMonth", "MontoACobrarVencido": "PastDueAmount",
        "MontoACobrarAcumulado": "TotalReceivable",
        "CuotasFuturasCobradas": "FutureInstalmentsCollected",
        "CuotasAtrasadasCobradas": "PastDueInstalmentsCollected",
        "CuotasDelMesCobradas": "CurrentInstalmentsCollected",
        "MoratorioYMultas": "LateFeesAndPenalties",
        "CompensatoriosYDevoluciones": "InterestAndRefunds",
        "TotalCobrado": "TotalCollected",
        "PorcentajeTotalCobradoSobreAcumulado": "CollectedOverReceivablePct",
        "PorcentajeCobradoAtrasadoSobreVencido": "PastDueCollectedPct",
        "PorcentajeTotalCobradoSobreMes": "CollectedOverDuePct",
        "SociosACobrarAcumulado": "CustomersWithReceivable",
        "SociosACobrarVencidos": "CustomersPastDue",
        "SociosACobrarDelMes": "CustomersDueThisMonth",
        "SociosCobrados": "CustomersCollected",
        "SociosAtrasadosCobrados": "PastDueCustomersCollected",
        "SociosDelMesCobrados": "CurrentCustomersCollected",
    },
    "pt": {
        "FechaObs": "DataObs", "Año": "Ano", "Mes": "Mes",
        "TramoDeuda": "FaixaAtraso", "TipoCliente": "TipoCliente",
        "MontoACobrarDelMes": "ValorAReceberDoMes",
        "MontoACobrarVencido": "ValorAReceberVencido",
        "MontoACobrarAcumulado": "ValorAReceberAcumulado",
        "CuotasFuturasCobradas": "ParcelasFuturasRecebidas",
        "CuotasAtrasadasCobradas": "ParcelasAtrasadasRecebidas",
        "CuotasDelMesCobradas": "ParcelasDoMesRecebidas",
        "MoratorioYMultas": "MoraEMultas",
        "CompensatoriosYDevoluciones": "JurosEDevolucoes",
        "TotalCobrado": "TotalRecebido",
        "PorcentajeTotalCobradoSobreAcumulado": "PercentualRecebidoSobreAcumulado",
        "PorcentajeCobradoAtrasadoSobreVencido": "PercentualAtrasadoSobreVencido",
        "PorcentajeTotalCobradoSobreMes": "PercentualRecebidoSobreMes",
        "SociosACobrarAcumulado": "ClientesAReceberAcumulado",
        "SociosACobrarVencidos": "ClientesAReceberVencidos",
        "SociosACobrarDelMes": "ClientesAReceberDoMes",
        "SociosCobrados": "ClientesRecebidos",
        "SociosAtrasadosCobrados": "ClientesAtrasadosRecebidos",
        "SociosDelMesCobrados": "ClientesDoMesRecebidos",
    },
}
VALORES_PANEL = {
    "en": {"CustomerType": {"Consumo": "Consumer", "Tarjeta": "Card",
                            "Prendario": "Secured"}},
    "pt": {"TipoCliente": {"Consumo": "Consumo", "Tarjeta": "Cartao",
                           "Prendario": "Garantido"}},
}


def _traducir(df: pd.DataFrame, columnas: dict[str, str],
              valores: dict[str, dict[str, str]]) -> pd.DataFrame:
    out = df.rename(columns=columnas)
    for col, mapa in valores.items():
        if col in out.columns:
            out[col] = out[col].map(lambda v, m=mapa: m.get(v, v))
    return out


def main() -> None:
    gestiones = pd.read_csv(AQUI / "gestiones_con_texto.csv", sep=";",
                            encoding="utf-8-sig")
    panel = pd.read_excel(AQUI / "cobranzas_panel.xlsx")

    for lang in IDIOMAS:
        g = _traducir(gestiones, COLUMNAS_GESTIONES[lang], VALORES_GESTIONES[lang])
        nota = COLUMNAS_GESTIONES[lang]["NotaGestor"]
        g[nota] = g[nota].map(lambda t, la=lang: NOTAS.get(t, {}).get(la, t))
        sin_traducir = sorted(set(g[nota]) - {v[lang] for v in NOTAS.values()})
        if sin_traducir:
            raise SystemExit(f"notas sin traducir a {lang}: {sin_traducir[:3]}")
        destino = AQUI / f"gestiones_con_texto-{lang}.csv"
        g.to_csv(destino, index=False, sep=";", encoding="utf-8-sig")
        print(f"{len(g)} filas → {destino.name}")

        p = _traducir(panel, COLUMNAS_PANEL[lang], VALORES_PANEL[lang])
        destino = AQUI / f"cobranzas_panel-{lang}.xlsx"
        p.to_excel(destino, index=False)
        print(f"{len(p)} filas → {destino.name}")


if __name__ == "__main__":
    main()
