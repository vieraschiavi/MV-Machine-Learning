"""Escucha social agregada: de qué se habla, dónde y con qué tono. Nunca quién.

Toma la exportación de una herramienta de escucha con licencia (o de la API
oficial de una red, dentro de sus términos) y la convierte en **conteos**:
menciones por país, semana y tema, con el sentimiento. Lo que no hace, a
propósito:

* no guarda autores, usuarios, enlaces ni ids de publicación: esas columnas se
  descartan al entrar, y del texto se borran @menciones, mails, teléfonos y URL;
* no devuelve ningún texto: sólo números y los términos más frecuentes de cada
  tema;
* no publica una celda con menos de ``K_MINIMO`` menciones.

**Farmacovigilancia.** Si un laboratorio escucha redes sobre sus productos y
aparece un posible evento adverso, tiene que derivarlo. Por eso cuenta las
menciones de un producto con lenguaje de evento adverso, y avisa: la revisión
caso por caso se hace en la herramienta de escucha (que sí tiene el texto), por
el equipo de farmacovigilancia, no en la analítica.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pandas as pd

from .consentimiento import _clave

K_MINIMO = 5
DESCARTAR = ("autor", "author", "usuario", "user", "username", "handle", "perfil", "profile", "nombre",
             "name", "email", "mail", "url", "link", "enlace", "id_post", "post_id", "tweet_id", "id_tweet",
             "seguidores", "followers", "avatar", "telefono", "phone")
_URL = re.compile(r"https?://\S+|www\.\S+")
_MAIL = re.compile(r"\S+@\S+\.\S+")
_MENCION = re.compile(r"@\w+")
_TEL = re.compile(r"\+?\d[\d\s\-()]{6,}\d")
_PALABRA = re.compile(r"[a-z0-9ñ]+")
POSITIVAS = frozenset("""bien bueno buena buenisimo excelente genial mejor mejore mejoro alivio aliviado funciona
funciono recomiendo recomendado recomendada ayudo ayuda gracias feliz contento contenta eficaz efectivo rapido facil barato economico encanta
otimo otima bom boa melhor melhorou funcionou recomendo obrigado feliz adoro""".split())
NEGATIVAS = frozenset("""mal malo mala peor horrible terrible caro cara carisimo dolor duele odio miedo nunca
falta faltante desabastecimiento problema problemas grave triste preocupa preocupado empeoro inutil
ruim pior caro dor medo problema piorou""".split())
NEGACION = frozenset({"no", "nunca", "ni", "sin", "nao", "nem"})
EVENTO_ADVERSO = ("efecto adverso", "efectos adversos", "efecto secundario", "efectos secundarios",
                  "reaccion", "me hizo mal", "me cayo mal", "alergia", "nauseas", "vomito", "mareo", "mareos",
                  "internaron", "hospital", "efeito colateral", "efeitos colaterais", "reacao")
VACIAS = frozenset("""de la que el en y a los se del las un por con no una su para es al lo como mas o pero sus le ya
fue este ha si porque esta son entre cuando muy sin sobre tambien me hasta hay donde quien desde todo nos
durante todos uno les ni contra otros ese eso ante ellos e esto mi antes algunos que unos yo otro otras otra
el tanto esa estos mucho quienes nada muchos cual poco ella estar estas algunas algo nosotros mis tu te ti
tus ellas vos q x d re rt da do em os um uma pra para com nao""".split())


def limpiar(texto: Any) -> str:
    """Saca del texto lo que identifica a alguien (URL, mails, @menciones, teléfonos)."""
    s = _URL.sub(" ", str(texto or ""))
    s = _MAIL.sub(" ", s)
    s = _MENCION.sub(" ", s)
    return _TEL.sub(" ", s)


def _terminos(temas: dict[str, list[str]]) -> dict[str, list[str]]:
    out = {}
    for tema, lista in temas.items():
        t = sorted({_clave(x) for x in lista if _clave(x)}, key=len, reverse=True)
        if t:
            out[str(tema)] = t
    if not out:
        raise ValueError("Definí al menos un tema con sus términos (ej. {'Hipertensión': ['presión alta', "
                         "'hipertensión']}).")
    return out


def _contiene(texto: str, termino: str) -> bool:
    return re.search(rf"(?<![a-z0-9ñ]){re.escape(termino)}(?![a-z0-9ñ])", texto) is not None


def sentimiento(texto: str) -> int:
    """+1, 0 o −1 con un léxico corto en español y portugués; una negación cercana invierte."""
    palabras = _PALABRA.findall(texto)
    puntos = 0
    for i, w in enumerate(palabras):
        signo = 1 if w in POSITIVAS else -1 if w in NEGATIVAS else 0
        if signo and NEGACION & set(palabras[max(0, i - 2):i]):
            signo = -signo
        puntos += signo
    return (puntos > 0) - (puntos < 0)


def preparar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    d = df.copy()
    d.columns = [_clave(c).replace(" ", "_") for c in d.columns]
    faltan = [c for c in ("texto", "fecha") if c not in d.columns]
    if faltan:
        raise ValueError(f"A la exportación de escucha le faltan columnas: {', '.join(faltan)}.")
    avisos = []
    fuera = [c for c in d.columns if any(c == x or c.startswith(x + "_") for x in DESCARTAR)]
    if fuera:
        avisos.append("Se descartaron columnas que identifican a quien publicó (" + ", ".join(fuera)
                      + "): la escucha se analiza agregada.")
        d = d.drop(columns=fuera)
    d["fecha"] = pd.to_datetime(d["fecha"], errors="coerce", utc=True).dt.tz_localize(None)
    d = d.dropna(subset=["fecha"])
    d["pais"] = d["pais"].fillna("(sin país)") if "pais" in d.columns else "(sin país)"
    d["texto"] = d["texto"].map(lambda s: _clave(limpiar(s)))
    return d[["fecha", "pais", "texto"]].reset_index(drop=True), avisos


def agregar(df: pd.DataFrame, temas: dict[str, list[str]], *, productos: list[str] | None = None,
            k_minimo: int = K_MINIMO) -> dict[str, Any]:
    """Menciones por país, semana y tema, con sentimiento, términos y alertas de farmacovigilancia."""
    d, avisos = preparar(df)
    terminos = _terminos(temas)
    filas, palabras = [], {t: Counter() for t in terminos}
    prods = list(dict.fromkeys(_clave(p) for p in (productos or []) if _clave(p)))
    ea = Counter()
    for r in d.itertuples():
        s = sentimiento(r.texto)
        for tema, lista in terminos.items():
            if any(_contiene(r.texto, x) for x in lista):
                filas.append((r.pais, r.fecha.to_period("W").start_time, tema, s))
                palabras[tema].update(w for w in _PALABRA.findall(r.texto)
                                      if w not in VACIAS and len(w) > 2 and w not in " ".join(lista))
        if prods and any(_contiene(r.texto, x) for x in EVENTO_ADVERSO):
            ea.update(p for p in prods if _contiene(r.texto, p))
    m = pd.DataFrame(filas, columns=["pais", "semana", "tema", "s"])
    if m.empty:
        tabla = pd.DataFrame(columns=["pais", "semana", "tema", "menciones", "positivas", "negativas",
                                      "sentimiento_neto"])
    else:
        tabla = (m.assign(positivas=m["s"] > 0, negativas=m["s"] < 0)
                 .groupby(["pais", "semana", "tema"])
                 .agg(menciones=("s", "size"), positivas=("positivas", "sum"), negativas=("negativas", "sum"))
                 .reset_index())
        tabla["sentimiento_neto"] = (tabla["positivas"] - tabla["negativas"]) / tabla["menciones"]
    chicas = tabla["menciones"] < k_minimo
    if chicas.any():
        avisos.append(f"{int(chicas.sum())} celda(s) país·semana·tema con menos de {k_minimo} menciones no se "
                      "publican.")
    tabla = tabla[~chicas].assign(semana=lambda t: pd.to_datetime(t["semana"]).dt.strftime("%Y-%m-%d"))
    totales = m.groupby("tema").size() if not m.empty else pd.Series(dtype=int)
    top = [{"tema": t, "termino": w, "menciones": n} for t, c in palabras.items()
           if totales.get(t, 0) >= k_minimo for w, n in c.most_common(10) if n >= k_minimo]
    fv = [{"producto": p, "menciones_posible_evento_adverso": n} for p, n in ea.items() if n]
    if fv:
        avisos.append("Hay menciones de productos propios con lenguaje de evento adverso: farmacovigilancia "
                      "tiene que revisarlas en la herramienta de escucha y reportar lo que corresponda.")
    return {"menciones": tabla.reset_index(drop=True), "terminos": pd.DataFrame(top),
            "farmacovigilancia": pd.DataFrame(fv, columns=["producto", "menciones_posible_evento_adverso"]),
            "publicaciones": len(d), "avisos": avisos}


def temas_del_catalogo(contenidos: pd.DataFrame) -> dict[str, list[str]]:
    """Un tema por área terapéutica y uno por producto del catálogo de contenidos."""
    temas: dict[str, list[str]] = {}
    for col in ("area_terapeutica", "producto"):
        if col in contenidos.columns:
            for v in contenidos[col].dropna().astype(str):
                if v.strip():
                    temas.setdefault(v.strip(), [v.strip()])
    return temas


__all__ = ["K_MINIMO", "agregar", "limpiar", "preparar", "sentimiento", "temas_del_catalogo"]
