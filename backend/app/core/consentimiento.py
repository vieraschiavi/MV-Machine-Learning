"""Quién se puede contactar, para qué y con qué: las reglas de una base propia.

La base de relacionamiento se arma con gente que **eligió entrar** (un
formulario, un programa de pacientes, un registro de profesionales) y que
dio consentimiento **por finalidad**: que la contacten, que le manden
comunicaciones comerciales, que se usen datos de su salud, que se le
personalice el contenido. Cada finalidad se consiente por separado y se puede
retirar. El motor nunca **infiere** una condición de salud: usa sólo lo que la
persona declaró (áreas de interés, productos que le recetaron).

Encima de los consentimientos van las reglas sanitarias de cada país: un
medicamento de venta bajo receta no se promociona al público, sólo a
profesionales de la salud. Las políticas por país vienen con valores
**conservadores por defecto** y marcadas «a validar por legal»: el programa
aplica reglas, no da asesoramiento jurídico.

Tablas de entrada (ver ``plantillas()``):

* **contactos** — una fila por persona, con un id seudónimo (el mail y el
  teléfono viven en el CRM, no en la analítica), país, tipo (paciente,
  cuidador, profesional), los consentimientos y lo declarado.
* **contenidos** — el catálogo: tipo (concientización, programa de pacientes,
  promoción de marca, beneficio, educación médica), área, producto, condición
  de venta (receta o venta libre), audiencia y países habilitados.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any

import pandas as pd

TIPOS_CONTENIDO = ("concientizacion", "programa_paciente", "promocion_marca", "beneficio",
                   "educacion_medica")
TIPOS_CONTACTO = ("paciente", "cuidador", "profesional")
COMERCIALES = ("promocion_marca", "beneficio")
CONSENTIMIENTOS = ("consiente_contacto", "consiente_marketing", "consiente_salud",
                   "consiente_perfilado")
# Campos que identifican a una persona: la analítica no los necesita.
IDENTIFICATORIOS = ("email", "mail", "correo", "telefono", "celular", "whatsapp", "nombre",
                    "apellido", "dni", "documento", "cedula", "cpf", "curp", "rut", "direccion",
                    "domicilio")

MOTIVOS = {
    "baja": "pidió la baja",
    "sin_consentimiento_contacto": "no consintió que lo contacten",
    "sin_doble_optin": "el país pide doble confirmación y no la tiene",
    "pais": "el contenido no está habilitado en su país",
    "audiencia": "el contenido es para otra audiencia",
    "receta_al_publico": "promoción de un medicamento de venta bajo receta a alguien que no es profesional",
    "venta_libre_al_publico": "en su país no se habilitó la promoción de venta libre al público",
    "sin_consentimiento_marketing": "no consintió comunicaciones comerciales",
    "sin_consentimiento_salud": "no consintió el uso de datos de su salud",
    "area_no_declarada": "no declaró interés en esa área terapéutica (no se infiere)",
    "programa_sin_receta_declarada": "es para quien declaró que le recetaron el producto",
}


@dataclass(frozen=True)
class Politica:
    pais: str
    ley_datos: str
    autoridad_sanitaria: str
    promocion_receta_a_publico: bool = False
    promocion_venta_libre_a_publico: bool = True
    doble_optin_obligatorio: bool = False
    frecuencia_max_30d: int = 4
    validado_por_legal: bool = False
    alias: tuple[str, ...] = field(default_factory=tuple)


_BASE = [
    Politica("Uruguay", "Ley 18.331 de protección de datos personales", "MSP", alias=("uy", "ury")),
    Politica("Argentina", "Ley 25.326 de protección de datos personales", "ANMAT", alias=("ar", "arg")),
    Politica("México", "LFPDPPP (datos personales en posesión de particulares)", "COFEPRIS",
             alias=("mx", "mex", "mexico")),
    Politica("Brasil", "LGPD (Lei 13.709)", "ANVISA", alias=("br", "bra", "brazil")),
    Politica("Colombia", "Ley 1581 de 2012", "INVIMA", alias=("co", "col")),
    Politica("Chile", "Ley 19.628 (y su reforma)", "ISP", alias=("cl", "chl")),
    Politica("Perú", "Ley 29733", "DIGEMID", alias=("pe", "per", "peru")),
    Politica("Ecuador", "Ley Orgánica de Protección de Datos Personales", "ARCSA", alias=("ec", "ecu")),
]
GENERICA = Politica("(otro país)", "ley de datos personales del país", "autoridad sanitaria del país")


def _clave(x: Any) -> str:
    """Texto comparable: sin tildes, en minúsculas. Vacío, None y NaN (celda vacía de un CSV) son ''."""
    if x is None or (isinstance(x, float) and x != x):
        return ""
    s = unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode()
    return s.strip().casefold()


POLITICAS = {_clave(p.pais): p for p in _BASE}
for _p in _BASE:
    for _a in _p.alias:
        POLITICAS[_clave(_a)] = _p


def politica(pais: Any, ajustes: dict[str, dict[str, Any]] | None = None) -> Politica:
    """La política de un país, con los ajustes que haya validado legal."""
    base = POLITICAS.get(_clave(pais), replace(GENERICA, pais=str(pais)))
    extra = (ajustes or {}).get(base.pais) or (ajustes or {}).get(str(pais)) or {}
    validos = {k: v for k, v in extra.items() if k in Politica.__dataclass_fields__ and k != "pais"}
    return replace(base, **validos)


# ── normalización ───────────────────────────────────────────────────────────
_SI = {"1", "si", "sí", "s", "true", "verdadero", "x", "yes", "y", "acepta", "ok"}


def _bool(serie: pd.Series) -> pd.Series:
    """Consentimiento como booleano. Lo vacío o dudoso es «no»: no se presume."""
    return serie.map(lambda v: _clave(v) in _SI if not isinstance(v, bool) else v).astype(bool)


def _lista(serie: pd.Series) -> pd.Series:
    return serie.fillna("").map(lambda s: frozenset(_clave(x) for x in str(s).replace(",", ";").split(";")
                                                    if _clave(x)))


def preparar_contactos(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Valida, minimiza y normaliza la tabla de contactos. Devuelve `(tabla, avisos)`."""
    d = df.copy()
    d.columns = [_clave(c).replace(" ", "_") for c in d.columns]
    faltan = [c for c in ("id_contacto", "pais") if c not in d.columns]
    if faltan:
        raise ValueError(f"A la tabla de contactos le faltan columnas: {', '.join(faltan)}.")
    avisos: list[str] = []
    ident = [c for c in d.columns if any(c.startswith(p) for p in IDENTIFICATORIOS)]
    if ident:
        avisos.append("Se descartaron columnas que identifican a la persona (" + ", ".join(ident)
                      + "): la analítica trabaja con un id seudónimo; el contacto vive en el CRM.")
        d = d.drop(columns=ident)
    for c in CONSENTIMIENTOS + ("doble_optin", "baja"):
        d[c] = _bool(d[c]) if c in d.columns else False
    d["tipo"] = d.get("tipo", pd.Series("paciente", index=d.index)).fillna("paciente").map(_clave)
    d.loc[~d["tipo"].isin(TIPOS_CONTACTO), "tipo"] = "paciente"
    for c in ("areas_interes", "productos_recetados"):
        d[c] = _lista(d[c]) if c in d.columns else [frozenset()] * len(d)
    d["id_contacto"] = d["id_contacto"].astype(str)
    dup = d.duplicated("id_contacto", keep="last")
    if dup.any():
        avisos.append(f"{int(dup.sum())} contacto(s) repetido(s): vale la última fila.")
        d = d[~dup]
    return _minimizar(d, avisos), avisos


def _minimizar(d: pd.DataFrame, avisos: list[str]) -> pd.DataFrame:
    """Datos de salud sin consentimiento de salud: no se usan. Se vacían y se avisa."""
    con_salud = d["areas_interes"].map(bool) | d["productos_recetados"].map(bool)
    sobra = con_salud & ~d["consiente_salud"] & (d["tipo"] != "profesional")
    if sobra.any():
        avisos.append(f"{int(sobra.sum())} contacto(s) tienen datos de salud sin consentimiento de "
                      "salud: no se usan. Hay que pedir el consentimiento o borrarlos de la base.")
        d = d.copy()
        d.loc[sobra, "areas_interes"] = [frozenset()] * int(sobra.sum())
        d.loc[sobra, "productos_recetados"] = [frozenset()] * int(sobra.sum())
    return d.reset_index(drop=True)


_CONDICION = {"receta": "receta", "rx": "receta", "bajo_receta": "receta", "venta_bajo_receta": "receta",
              "receta_archivada": "receta", "venta_libre": "venta_libre", "otc": "venta_libre",
              "libre": "venta_libre", "suplemento": "venta_libre"}


def _condicion(x: Any) -> str:
    """Receta o venta libre. Lo desconocido se trata como receta: el lado prudente."""
    k = _clave(x).replace(" ", "_")
    return "" if not k else _CONDICION.get(k, "receta")


def preparar_contenidos(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d.columns = [_clave(c).replace(" ", "_") for c in d.columns]
    faltan = [c for c in ("id_contenido", "tipo") if c not in d.columns]
    if faltan:
        raise ValueError(f"A la tabla de contenidos le faltan columnas: {', '.join(faltan)}.")
    d["tipo"] = d["tipo"].map(_clave)
    raros = sorted(set(d["tipo"]) - set(TIPOS_CONTENIDO))
    if raros:
        raise ValueError(f"Tipos de contenido desconocidos: {', '.join(raros)}. "
                         f"Usá: {', '.join(TIPOS_CONTENIDO)}.")
    for c, defecto in (("area_terapeutica", ""), ("producto", ""), ("condicion_venta", ""),
                       ("audiencia", "todos"), ("paises", "*"), ("titulo", "")):
        d[c] = d[c].fillna(defecto) if c in d.columns else defecto
    d["area_clave"] = d["area_terapeutica"].map(_clave)
    d["producto_clave"] = d["producto"].map(_clave)
    d["condicion_venta"] = d["condicion_venta"].map(_condicion)
    d["audiencia"] = d["audiencia"].map(_clave).replace("", "todos")
    d["paises_set"] = d["paises"].map(lambda s: frozenset(_clave(x) for x in str(s).replace(",", ";").split(";")
                                                          if _clave(x)) or frozenset({"*"}))
    d["id_contenido"] = d["id_contenido"].astype(str)
    return d.reset_index(drop=True)


# ── elegibilidad ────────────────────────────────────────────────────────────
def _contexto(contactos: pd.DataFrame, ajustes: dict | None) -> dict[str, pd.Series]:
    """Lo que depende sólo del contacto, calculado una vez para todo el catálogo."""
    por_pais = {p: politica(p, ajustes) for p in contactos["pais"].unique()}
    pol = contactos["pais"].map(por_pais)
    claves = contactos["pais"].map({p: frozenset({_clave(p), _clave(q.pais), *(_clave(a) for a in q.alias)})
                                    for p, q in por_pais.items()})
    return {"pol": pol, "claves_pais": claves, "prof": contactos["tipo"] == "profesional"}


def motivo_bloqueo(contactos: pd.DataFrame, c: pd.Series, ajustes: dict | None = None,
                   ctx: dict[str, pd.Series] | None = None) -> pd.Series:
    """Para un contenido, el primer motivo que bloquea a cada contacto ('' = elegible).

    El orden importa: primero lo que la persona pidió (baja, consentimientos),
    después lo que la ley no permite, después lo que el contenido no aplica.
    """
    ctx = ctx or _contexto(contactos, ajustes)
    pol, prof, idx = ctx["pol"], ctx["prof"], contactos.index

    def todos(v: bool) -> pd.Series:
        return pd.Series(bool(v), index=idx)

    comercial = c["tipo"] in COMERCIALES
    receta = c["condicion_venta"] == "receta"
    con_area = bool(c["area_clave"])
    paises = c["paises_set"]
    # Un beneficio (descuento, muestra) de un producto bajo receta es para quien
    # declaró que se lo recetaron: igual que un programa de pacientes.
    pide_receta = c["tipo"] == "programa_paciente" or (c["tipo"] == "beneficio" and receta)
    reglas = [
        ("baja", contactos["baja"]),
        ("sin_consentimiento_contacto", ~contactos["consiente_contacto"]),
        ("sin_doble_optin", pol.map(lambda p: p.doble_optin_obligatorio) & ~contactos["doble_optin"]),
        ("pais", todos("*" not in paises) & ~ctx["claves_pais"].map(lambda s: bool(s & paises))),
        ("audiencia", _audiencia_mal(c, prof)),
        ("receta_al_publico", todos(c["tipo"] == "promocion_marca" and receta)
         & ~prof & ~pol.map(lambda p: p.promocion_receta_a_publico)),
        ("venta_libre_al_publico", todos(comercial and c["condicion_venta"] == "venta_libre")
         & ~prof & ~pol.map(lambda p: p.promocion_venta_libre_a_publico)),
        ("sin_consentimiento_marketing", todos(comercial) & ~contactos["consiente_marketing"]),
        ("sin_consentimiento_salud", todos(con_area or pide_receta) & ~prof & ~contactos["consiente_salud"]),
        ("area_no_declarada", todos(con_area) & ~prof
         & ~contactos["areas_interes"].map(lambda s: c["area_clave"] in s)),
        ("programa_sin_receta_declarada", todos(pide_receta) & ~contactos["productos_recetados"].map(
            lambda s: bool(c["producto_clave"]) and c["producto_clave"] in s)),
    ]
    motivo = pd.Series("", index=idx, dtype=object)
    for nombre, mascara in reglas:
        motivo = motivo.where((motivo != "") | ~mascara.fillna(False).astype(bool), nombre)
    return motivo


def _audiencia_mal(c: pd.Series, prof: pd.Series) -> pd.Series:
    """Educación médica sólo a profesionales; programas y beneficios sólo a pacientes y cuidadores.

    Los beneficios a profesionales (regalos, muestras de cortesía) los regulan
    los códigos de la industria: el motor no los envía.
    """
    aud = c["audiencia"]
    if c["tipo"] == "educacion_medica" or aud == "profesional":
        return prof.eq(False)
    if c["tipo"] in ("programa_paciente", "beneficio") or aud in ("paciente", "publico"):
        return prof.copy()
    return pd.Series(False, index=prof.index)


def matriz_elegibilidad(contactos: pd.DataFrame, contenidos: pd.DataFrame,
                        ajustes: dict | None = None) -> pd.DataFrame:
    """Contacto × contenido con el motivo de bloqueo ('' = se puede enviar)."""
    ctx = _contexto(contactos, ajustes)
    partes = []
    for c in contenidos.to_dict("records"):
        c = pd.Series(c)
        m = motivo_bloqueo(contactos, c, ajustes, ctx)
        partes.append(pd.DataFrame({"id_contacto": contactos["id_contacto"].values,
                                    "id_contenido": c["id_contenido"], "motivo": m.values}))
    if not partes:
        return pd.DataFrame(columns=["id_contacto", "id_contenido", "motivo"])
    return pd.concat(partes, ignore_index=True)


def plantillas() -> dict[str, pd.DataFrame]:
    """Tablas vacías (con una fila de ejemplo) para cargar contactos y contenidos."""
    contactos = pd.DataFrame([{
        "id_contacto": "C-000001", "pais": "Uruguay", "ciudad": "Montevideo", "barrio": "Pocitos",
        "sexo": "Mujeres", "rango_edad": "40-59", "tipo": "paciente",
        "canal_captacion": "landing hipertensión", "fecha_alta": "2026-10-01",
        "consiente_contacto": "si", "consiente_marketing": "no", "consiente_salud": "si",
        "consiente_perfilado": "si", "doble_optin": "si", "baja": "no",
        "areas_interes": "Cardiometabólica", "productos_recetados": "", "canal_preferido": "email",
        "especialidad": "", "nse_zona": "medio"}])
    contenidos = pd.DataFrame([{
        "id_contenido": "K-001", "titulo": "Conocé tu presión", "tipo": "concientizacion",
        "area_terapeutica": "Cardiometabólica", "producto": "", "condicion_venta": "",
        "audiencia": "paciente", "paises": "*", "canal": "email"}])
    interacciones = pd.DataFrame([{"id_contacto": "C-000001", "id_contenido": "K-001",
                                   "fecha": "2026-10-02", "evento": "envio"}])
    return {"contactos": contactos, "contenidos": contenidos, "interacciones": interacciones}


__all__ = ["COMERCIALES", "CONSENTIMIENTOS", "MOTIVOS", "POLITICAS", "TIPOS_CONTACTO",
           "TIPOS_CONTENIDO", "Politica", "matriz_elegibilidad", "motivo_bloqueo", "plantillas",
           "politica", "preparar_contactos", "preparar_contenidos"]
