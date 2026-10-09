"""Agente de mercado: arma los supuestos del embudo y lee lo que dicen.

El agente trabaja en tres pasos, y cada uno deja a la vista de dónde sale cada
número:

1. **Proponer** (`proponer`): le pide al motor de IA configurado —el de la
   pestaña de IA— los supuestos del embudo por país y segmento para una
   molécula, una enfermedad y una presentación, junto con la casuística del
   área terapéutica: quién tiene síntomas y no consulta, quién tiene el
   diagnóstico y no se trata, cómo se escalona la terapia, dosis, adherencia y
   acceso. Todo lo que propone queda marcado `IA (a validar)`.
2. **Combinar** (`combinar`): los estudios de mercado que cargue la empresa
   (por país, del formato de `mercado.plantilla`) **pisan** lo propuesto. Un
   número de un estudio vale más que uno de un modelo de lenguaje, siempre.
3. **Analizar** (`analizar`): corre el embudo, el rango P10–P90, el tornado,
   la curva de lanzamiento y el contraste con las ventas reales, y escribe la
   lectura por país: proteger, acelerar o desarrollar, y qué supuesto conviene
   validar primero.

Un modelo de lenguaje puede dar cifras desactualizadas y citar estudios que no
existen. Por eso el agente nunca presenta lo que propone como dato: la
respuesta trae el nivel de evidencia (`estudios`, `mixta`, `solo IA`) y la
cuenta de cuántos supuestos falta validar.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from . import ai
from . import mercado as M

ORIGEN_IA = "IA (a validar)"
ORIGEN_ESTUDIO = "estudio de mercado"
AVISO_IA = ("Los números y las fuentes que propone un modelo de lenguaje son hipótesis: pueden "
            "estar desactualizados o citar estudios que no existen. Reemplazalos por estudios de "
            "mercado del país antes de decidir con esta proyección.")

# Lo que el agente revisa siempre, sea cual sea el área terapéutica.
CASUISTICA = (
    "Subdiagnóstico: quién tiene síntomas y no consulta al médico (por sexo, edad, nivel "
    "socioeconómico, zona), y cuánto pesa en cada país.",
    "Brecha de tratamiento: diagnosticados que no se tratan, abandonan o se tratan sin receta.",
    "Escalonamiento de la terapia: qué parte de la clase está en monoterapia, en combinaciones "
    "dobles y en triples, y hacia dónde se mueve.",
    "Dosis y titulación: dosis diaria, presentaciones, días de tratamiento al año y adherencia real.",
    "Acceso: cobertura pública y privada, precio, genéricos y competencia de la clase.",
    "Curso de la enfermedad: crónica o aguda, estacionalidad, prevalencia que crece con la edad.",
)


class AgenteError(RuntimeError):
    """El agente no pudo armar una propuesta usable."""


@dataclass(frozen=True)
class Contexto:
    area_terapeutica: str
    molecula: str
    enfermedad: str
    paises: tuple[str, ...]
    presentacion: str = ""
    segmentos: tuple[str, ...] = ("Hombres", "Mujeres")
    notas: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ── 1. proponer ─────────────────────────────────────────────────────────────
SISTEMA = ("Sos analista senior de inteligencia de mercado farmacéutico en Latinoamérica. "
           "Estimás embudos epidemiológicos con criterio y decís cuándo no sabés. "
           "Respondés sólo con el JSON pedido.")


def _consigna(c: Contexto) -> str:
    params = "\n".join(f"- {k}: {p.descripcion} ({'tasa 0-1' if p.tipo == M.TASA else 'cantidad'})"
                       for k, p in M.PARAMETROS.items())
    temas = "\n".join(f"- {t}" for t in CASUISTICA)
    return (
        f"Área terapéutica: {c.area_terapeutica}\nMolécula o familia: {c.molecula}\n"
        f"Enfermedad: {c.enfermedad}\nPresentación y dosis: {c.presentacion or 'sin especificar'}\n"
        f"Países: {', '.join(c.paises)}\nSegmentos: {', '.join(c.segmentos)}\n"
        f"Lo que ya sabe la empresa: {c.notas or 'nada cargado'}\n\n"
        f"Parámetros del embudo, por país y segmento:\n{params}\n\n"
        f"Casuística que tenés que cubrir:\n{temas}\n\n"
        "Para cada país y segmento estimá los parámetros que puedas sostener, con mínimo y máximo "
        "honestos (más anchos cuanto menos evidencia haya). En «fuente» nombrá el tipo de estudio "
        "en que te basás (encuesta nacional de salud, estudio poblacional, registro) y el año; si "
        "no conocés uno, escribí «estimación sin fuente». No inventes citas.\n\n"
        "Devolvé SOLO este JSON:\n"
        '{"supuestos": [{"pais": "", "segmento": "", "parametro": "", "valor": 0, "minimo": 0, '
        '"maximo": 0, "fuente": ""}], '
        '"casuistica": [{"tema": "", "lectura": ""}], '
        '"latente": [{"pais": "", "segmento": "", "motivo": ""}], '
        '"advertencias": [""]}'
    )


def _filtrar(filas: list[dict[str, Any]], c: Contexto) -> list[dict[str, Any]]:
    """Sólo los países y segmentos pedidos: lo demás es ruido del modelo."""
    paises = {p.strip().lower() for p in c.paises}
    segs = {s.strip().lower() for s in c.segmentos}
    return [f for f in filas if str(f.get("pais", "")).strip().lower() in paises
            and str(f.get("segmento", "")).strip().lower() in segs]


def proponer(c: Contexto, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Pide al motor de IA los supuestos del embudo y la casuística del área."""
    if not c.paises:
        raise AgenteError("Indicá al menos un país.")
    try:
        r = ai.chat(provider, _consigna(c), SISTEMA, model=model, max_tokens=4000)
    except ai.AIError as exc:
        raise AgenteError(f"El motor de IA no respondió: {exc}") from exc
    try:
        data = ai._json_from(r["text"])
    except (ValueError, json.JSONDecodeError) as exc:
        raise AgenteError("El modelo no devolvió un JSON interpretable. Probá de nuevo o "
                          "cargá los supuestos desde un estudio de mercado.") from exc
    crudas = data.get("supuestos") if isinstance(data, dict) else None
    filas = _filtrar([f for f in (crudas or []) if isinstance(f, dict)], c)
    if not filas:
        raise AgenteError("La propuesta no trae supuestos para los países y segmentos pedidos.")
    for f in filas:
        f["origen"] = ORIGEN_IA
        f["fuente"] = str(f.get("fuente") or "estimación sin fuente")
    try:
        tabla, avisos = M.normalizar(pd.DataFrame(filas))
    except M.SupuestosInvalidos as exc:
        raise AgenteError(str(exc)) from exc
    return {"supuestos": tabla.to_dict("records"), "avisos": [AVISO_IA, *avisos],
            "casuistica": _lista_de_dicts(data.get("casuistica"), ("tema", "lectura")),
            "latente": _lista_de_dicts(data.get("latente"), ("pais", "segmento", "motivo")),
            "advertencias": [str(x) for x in (data.get("advertencias") or []) if x],
            "contexto": asdict(c), "provider": r.get("provider"), "model": r.get("model")}


def _lista_de_dicts(x: Any, claves: tuple[str, ...]) -> list[dict[str, str]]:
    if not isinstance(x, list):
        return []
    return [{k: str(d.get(k, "")) for k in claves} for d in x if isinstance(d, dict)]


# ── 2. combinar ─────────────────────────────────────────────────────────────
def combinar(propuesta: pd.DataFrame | None, estudios: pd.DataFrame | None) -> tuple[pd.DataFrame, list[str]]:
    """Los estudios de mercado pisan lo propuesto por la IA, supuesto por supuesto."""
    partes, avisos = [], []
    if propuesta is not None and len(propuesta):
        p, a = M.normalizar(propuesta)
        partes.append(p)
        avisos += a
    if estudios is not None and len(estudios):
        e, a = M.normalizar(estudios)
        e["origen"] = e["origen"].replace("", ORIGEN_ESTUDIO)
        partes.append(e)
        avisos += a
    if not partes:
        raise M.SupuestosInvalidos("No hay supuestos: cargá un estudio de mercado o pedí una propuesta.")
    todo = pd.concat(partes, ignore_index=True)
    clave = ["pais", "segmento", "parametro"]
    pisados = int(todo.duplicated(clave, keep="last").sum())
    if pisados and len(partes) == 2:
        avisos.append(f"{pisados} supuesto(s) de la IA reemplazado(s) por el estudio de mercado.")
    return todo.drop_duplicates(clave, keep="last").reset_index(drop=True), avisos


def nivel_de_evidencia(supuestos: pd.DataFrame) -> dict[str, Any]:
    """Cuánto de la proyección descansa en estudios y cuánto en la IA."""
    ia = int((supuestos["origen"] == ORIGEN_IA).sum())
    total = len(supuestos)
    nivel = "solo IA" if ia == total else ("estudios" if ia == 0 else "mixta")
    return {"nivel": nivel, "supuestos": total, "de_ia": ia, "de_estudios": total - ia}


# ── 3. analizar ─────────────────────────────────────────────────────────────
def _lectura_pais(pais: str, emb: pd.DataFrame) -> dict[str, Any]:
    g = emb[emb["pais"] == pais]
    prev = float(g["prevalentes"].sum()) or 1.0
    sin_diag, sin_trat = float(g["sin_diagnostico"].sum()), float(g["sin_tratamiento"].sum())
    peor = g.loc[g["sin_diagnostico"].idxmax(), "segmento"] if len(g) > 1 else None
    if sin_diag / prev >= 0.4 and sin_diag >= sin_trat:
        accion = "desarrollar"
        texto = (f"El mercado está escondido: {sin_diag / prev:.0%} de quienes tienen la enfermedad no "
                 "está diagnosticado. Mueve más la detección (campañas, tamizaje, educación al paciente)"
                 + (f", empezando por {peor}." if peor else "."))
    elif sin_trat / prev >= 0.2:
        accion = "acelerar"
        miles = f"{sin_trat:,.0f}".replace(",", ".")
        texto = (f"Hay {miles} pacientes diagnosticados sin tratamiento ({sin_trat / prev:.0%} de "
                 "los prevalentes): el crecimiento está en activación médica, adherencia y acceso.")
    else:
        accion = "proteger"
        texto = ("El mercado ya está diagnosticado y tratado en su mayoría: crecer es ganar participación "
                 "dentro de la clase y defender la base.")
    return {"pais": pais, "accion": accion, "lectura": texto,
            "latente": sin_diag + sin_trat, "en_clase": float(g["en_clase"].sum()),
            "segmento_mas_latente": peor}


def analizar(supuestos: pd.DataFrame, plan: M.Lanzamiento | None = None,
             observado: pd.DataFrame | None = None, inicio: str | None = None,
             n_sim: int = 2000) -> dict[str, Any]:
    """Todo el análisis de mercado sobre una tabla de supuestos ya combinada."""
    pot = M.potencial(supuestos, n_sim=n_sim)
    tabla = pd.DataFrame(pot["supuestos"])
    emb = pd.DataFrame(pot["embudo"])
    medida = "valor_clase" if "valor_clase" in emb else "en_clase"
    tornado = M.sensibilidad(tabla, medida)
    evidencia = nivel_de_evidencia(tabla)
    paises = list(dict.fromkeys(emb["pais"]))
    out = {**pot, "evidencia": evidencia, "medida_sensibilidad": medida,
           "sensibilidad": tornado.to_dict("records"),
           "lecturas": [_lectura_pais(p, emb) for p in paises],
           "recomendaciones": _recomendaciones(tornado, evidencia)}
    if plan is not None:
        lz = M.lanzamiento(tabla, plan, inicio=inicio, n_sim=min(n_sim, 1000))
        out["lanzamiento"] = lz.to_dict("records")
        out["lanzamiento_nota"] = ("Sin historia propia, la curva sale de los supuestos y de la forma "
                                   "de adopción elegida, no de un backtest: el rango P10–P90 refleja "
                                   "la incertidumbre de los supuestos, no un error medido.")
    if observado is not None and len(observado):
        out["contraste"] = M.contrastar(tabla, observado).to_dict("records")
    return out


def _recomendaciones(tornado: pd.DataFrame, ev: dict[str, Any]) -> list[str]:
    recs = []
    if len(tornado):
        top = tornado.iloc[0]
        recs.append(f"El supuesto que más mueve el resultado es «{top['parametro']}»: es el primero "
                    "que conviene validar con un estudio de mercado del país.")
    if ev["de_ia"]:
        recs.append(f"{ev['de_ia']} de {ev['supuestos']} supuestos vienen de la IA y no de un estudio: "
                    "tomá la proyección como hipótesis hasta reemplazarlos.")
    return recs


def narrar(resultado: dict[str, Any], provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Lectura ejecutiva del análisis, escrita por el motor de IA."""
    resumen = {k: resultado.get(k) for k in ("lecturas", "evidencia", "recomendaciones", "contraste")}
    resumen["sensibilidad"] = (resultado.get("sensibilidad") or [])[:5]
    resumen["total"] = [r for r in resultado.get("rango", []) if r["pais"] == "Total"]
    return ai.narrate(resumen, "mercado", provider=provider, model=model)
