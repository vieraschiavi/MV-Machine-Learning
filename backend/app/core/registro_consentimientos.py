"""El libro de consentimientos: cada «sí» y cada «no», con su evidencia.

La tabla de contactos dice el estado de hoy; el libro dice **cómo se llegó**:
una fila por evento, que nunca se borra ni se edita (sólo se agregan filas).
Es lo que se muestra si una autoridad o la propia persona pregunta «¿cuándo
acepté esto, dónde y qué decía el texto?».

Columnas: ``id_contacto``, ``finalidad`` (contacto, marketing, salud,
perfilado, doble_optin), ``accion`` (otorga, retira, confirma, baja),
``fecha``, ``canal`` (landing, formulario de farmacia, call center…),
``version_texto`` (la versión exacta del texto aceptado; ver ``TEXTOS``).

El estado vigente de cada finalidad es el **último** evento de esa finalidad:
quien aceptó y después retiró, no consiente. Una ``baja`` retira todo.

Los textos del formulario están versionados: si cambia una coma, cambia la
versión, y el libro dice qué versión aceptó cada persona.
"""
from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd

from .consentimiento import _clave, normalizar_id

FINALIDADES = ("contacto", "marketing", "salud", "perfilado")
ACCIONES = ("otorga", "retira", "confirma", "baja")
COLUMNAS = ["id_contacto", "finalidad", "accion", "fecha", "canal", "version_texto"]

# Los textos de las cuatro casillas (ninguna se marca sola). La versión es el
# hash del texto: no hay forma de cambiar uno sin que cambie su versión.
_TEXTOS_BASE = {
    "es": {
        "contacto": "Quiero recibir información de salud y novedades del programa por email o WhatsApp.",
        "marketing": "Acepto recibir ofertas y promociones de productos de venta libre.",
        "salud": ("Autorizo el uso de las áreas de salud y tratamientos que declaro para recibir contenido "
                  "sobre ellos."),
        "perfilado": "Acepto que se use mi actividad (aperturas, clics) para elegir lo que me llega.",
    },
    "pt": {
        "contacto": "Quero receber informações de saúde e novidades do programa por e-mail ou WhatsApp.",
        "marketing": "Aceito receber ofertas e promoções de produtos isentos de prescrição.",
        "salud": ("Autorizo o uso das áreas de saúde e tratamentos que declaro para receber conteúdo "
                  "sobre eles."),
        "perfilado": "Aceito que minha atividade (aberturas, cliques) seja usada para escolher o que recebo.",
    },
}


def version(texto: str) -> str:
    return "v-" + hashlib.sha256(texto.encode()).hexdigest()[:10]


TEXTOS = {idioma: {f: {"texto": t, "version": version(t)} for f, t in casillas.items()}
          for idioma, casillas in _TEXTOS_BASE.items()}
VERSIONES = {v["version"]: (idioma, f) for idioma, cas in TEXTOS.items() for f, v in cas.items()}


def preparar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    d = df.copy()
    d.columns = [_clave(c).replace(" ", "_") for c in d.columns]
    faltan = [c for c in ("id_contacto", "finalidad", "accion", "fecha") if c not in d.columns]
    if faltan:
        raise ValueError(f"Al libro de consentimientos le faltan columnas: {', '.join(faltan)}.")
    avisos: list[str] = []
    for c in ("canal", "version_texto"):
        d[c] = d[c].fillna("").astype(str) if c in d.columns else ""
    d["finalidad"] = d["finalidad"].map(_clave).replace({"doble_opt_in": "doble_optin", "optin": "doble_optin"})
    d["accion"] = d["accion"].map(_clave)
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce", utc=True).dt.tz_localize(None)
    d["id_contacto"] = normalizar_id(d["id_contacto"])
    malas = (~d["finalidad"].isin((*FINALIDADES, "doble_optin", "todas"))) | (~d["accion"].isin(ACCIONES)) \
        | d["fecha"].isna() | (d["id_contacto"] == "")
    if malas.any():
        avisos.append(f"Se ignoraron {int(malas.sum())} evento(s) del libro con finalidad, acción, fecha o id "
                      "inválidos.")
    d = d[~malas]
    sin_version = (d["accion"] == "otorga") & (d["version_texto"].str.strip() == "")
    if sin_version.any():
        avisos.append(f"{int(sin_version.sum())} consentimiento(s) otorgado(s) sin versión del texto: no hay "
                      "evidencia de qué se aceptó. Conviene volver a pedirlos.")
    return d[COLUMNAS].sort_values(["id_contacto", "fecha"], kind="stable").reset_index(drop=True), avisos


def estado(libro: pd.DataFrame) -> pd.DataFrame:
    """Estado vigente por contacto: el último evento de cada finalidad manda; una baja retira todo."""
    if libro.empty:
        return pd.DataFrame(columns=["id_contacto", *(f"consiente_{f}" for f in FINALIDADES), "doble_optin",
                                     "baja", "ultimo_cambio"])
    filas = []
    for cid, ev in libro.groupby("id_contacto", sort=False):
        st = dict.fromkeys(FINALIDADES, False)
        versiones = {}
        doble, baja = False, False
        for e in ev.itertuples():
            if e.accion == "baja":
                st = dict.fromkeys(FINALIDADES, False)
                baja, doble = True, False
            elif e.finalidad == "doble_optin" and e.accion == "confirma":
                doble = True
            elif e.finalidad in FINALIDADES or e.finalidad == "todas":
                objetivo = FINALIDADES if e.finalidad == "todas" else (e.finalidad,)
                for f in objetivo:
                    st[f] = e.accion == "otorga"
                    if e.accion == "otorga":
                        baja = False
                        versiones[f] = e.version_texto
        filas.append({"id_contacto": cid, **{f"consiente_{f}": v for f, v in st.items()}, "doble_optin": doble,
                      "baja": baja, "ultimo_cambio": ev["fecha"].max(),
                      **{f"version_{f}": versiones.get(f, "") for f in FINALIDADES}})
    return pd.DataFrame(filas)


def aplicar(contactos: pd.DataFrame, libro: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """El libro manda sobre la tabla de contactos: para quien tiene eventos, su estado sale del libro."""
    ev, avisos = preparar(libro)
    st = estado(ev)
    d = contactos.copy()
    d["id_contacto"] = normalizar_id(d["id_contacto"])
    en_libro = d["id_contacto"].isin(set(st["id_contacto"]))
    cols = [*(f"consiente_{f}" for f in FINALIDADES), "doble_optin", "baja"]
    if en_libro.any():
        s = st.set_index("id_contacto")
        for c in cols:
            d.loc[en_libro, c] = d.loc[en_libro, "id_contacto"].map(s[c]).map(lambda v: "si" if v else "no")
    sin = int((~en_libro).sum())
    if sin:
        avisos.append(f"{sin} contacto(s) sin eventos en el libro de consentimientos: se usan los valores de la "
                      "tabla, pero no hay evidencia de cuándo ni cómo consintieron.")
    discrepan = _discrepancias(contactos, st)
    if discrepan:
        avisos.append(f"{discrepan} contacto(s) tenían en la tabla un consentimiento que el libro no respalda: "
                      "manda el libro. Revisar la sincronización con el CRM.")
    return d, avisos


def _discrepancias(contactos: pd.DataFrame, st: pd.DataFrame) -> int:
    if st.empty or "consiente_contacto" not in contactos.columns:
        return 0
    m = contactos.assign(id_contacto=normalizar_id(contactos["id_contacto"])).merge(
        st[["id_contacto", "consiente_contacto"]], on="id_contacto", suffixes=("", "_libro"))
    tabla = m["consiente_contacto"].map(lambda v: _clave(v) in {"si", "1", "true", "yes", "x", "s"} or v is True)
    return int((tabla & ~m["consiente_contacto_libro"].astype(bool)).sum())


def plantilla() -> pd.DataFrame:
    v = TEXTOS["es"]
    return pd.DataFrame([
        {"id_contacto": "C-000001", "finalidad": "contacto", "accion": "otorga", "fecha": "2026-10-01 10:15",
         "canal": "landing hipertensión", "version_texto": v["contacto"]["version"]},
        {"id_contacto": "C-000001", "finalidad": "salud", "accion": "otorga", "fecha": "2026-10-01 10:15",
         "canal": "landing hipertensión", "version_texto": v["salud"]["version"]},
        {"id_contacto": "C-000001", "finalidad": "doble_optin", "accion": "confirma", "fecha": "2026-10-01 10:22",
         "canal": "email de confirmación", "version_texto": ""},
    ])


def evidencia(libro: pd.DataFrame, id_contacto: Any) -> list[dict[str, Any]]:
    """Para el derecho de acceso: cada evento de la persona, con el texto exacto que aceptó."""
    ev, _ = preparar(libro)
    filas = ev[ev["id_contacto"] == normalizar_id(pd.Series([id_contacto])).iloc[0]]
    out = []
    for r in filas.to_dict("records"):
        idioma, fin = VERSIONES.get(r["version_texto"], (None, None))
        out.append({**r, "fecha": str(r["fecha"]),
                    "texto_aceptado": TEXTOS[idioma][fin]["texto"] if idioma else None})
    return out




# ── el formulario de captación ──────────────────────────────────────────────
_UI = {
    "es": {"titulo": "Sumate al programa", "email": "Email", "whatsapp": "WhatsApp (opcional)",
           "aviso": "Leé el aviso de privacidad", "enviar": "Quiero sumarme",
           "nota": "Ninguna casilla viene marcada. Podés retirar cada permiso cuando quieras, desde cualquier "
                   "mensaje. Te vamos a mandar un email para confirmar."},
    "pt": {"titulo": "Participe do programa", "email": "E-mail", "whatsapp": "WhatsApp (opcional)",
           "aviso": "Leia o aviso de privacidade", "enviar": "Quero participar",
           "nota": "Nenhuma opção vem marcada. Você pode retirar cada permissão quando quiser, em qualquer "
                   "mensagem. Vamos enviar um e-mail para confirmar."},
}


def formulario_html(idioma: str = "es", accion: str = "https://crm.ejemplo/consentimientos",
                    aviso_privacidad: str = "https://ejemplo/privacidad", canal: str = "landing") -> str:
    """Formulario embebible: cuatro casillas sin marcar, con la versión de cada texto en el envío.

    Envía al CRM (``accion``), no a este programa: el mail y el teléfono viven allá.
    """
    import html as H
    if idioma not in TEXTOS:
        raise ValueError(f"Idioma «{idioma}» no disponible: {', '.join(TEXTOS)}.")
    ui, t = _UI[idioma], TEXTOS[idioma]
    casillas = "\n".join(
        f'    <label class="casilla"><input type="checkbox" name="consiente_{f}" value="{t[f]["version"]}"'
        f'{" required" if f == "contacto" else ""}> <span>{H.escape(t[f]["texto"])}</span></label>'
        for f in FINALIDADES)
    return f"""<!doctype html>
<html lang="{idioma}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H.escape(ui["titulo"])}</title>
<style>
  :root {{ --tinta:#1F2933; --marca:#1C7C7D; --suave:#EAF2F1; }}
  body {{ margin:0; font:16px/1.5 Calibri, Carlito, Arial, sans-serif; color:var(--tinta); background:#fff; }}
  form {{ max-width:560px; margin:24px auto; padding:0 16px; }}
  h1 {{ font:700 28px Cambria, Caladea, Georgia, serif; color:#0F3B44; }}
  label {{ display:block; margin:12px 0; }}
  input[type=email], input[type=tel] {{ width:100%; padding:10px; font:inherit; border:1px solid #c9d6d4; border-radius:8px; box-sizing:border-box; }}
  .casilla {{ display:flex; gap:10px; align-items:flex-start; background:var(--suave); padding:12px; border-radius:8px; }}
  .casilla input {{ margin-top:4px; }}
  .nota {{ font-size:14px; color:#4A5672; }}
  button {{ background:var(--marca); color:#fff; border:0; border-radius:8px; padding:12px 20px; font:700 16px inherit; cursor:pointer; }}
</style>
</head>
<body>
<form method="post" action="{H.escape(accion)}">
  <h1>{H.escape(ui["titulo"])}</h1>
  <label>{H.escape(ui["email"])}<input type="email" name="email" required autocomplete="email"></label>
  <label>{H.escape(ui["whatsapp"])}<input type="tel" name="whatsapp" autocomplete="tel"></label>
{casillas}
  <input type="hidden" name="canal" value="{H.escape(canal)}">
  <input type="hidden" name="idioma" value="{idioma}">
  <p class="nota">{H.escape(ui["nota"])} <a href="{H.escape(aviso_privacidad)}" target="_blank" rel="noopener">{H.escape(ui["aviso"])}</a>.</p>
  <button type="submit">{H.escape(ui["enviar"])}</button>
</form>
</body>
</html>
"""


__all__ = ["ACCIONES", "FINALIDADES", "TEXTOS", "aplicar", "estado", "evidencia", "formulario_html", "plantilla",
           "preparar", "version"]
