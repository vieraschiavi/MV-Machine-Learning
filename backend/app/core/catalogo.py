"""Revisor del catálogo de contenidos: lo que conviene corregir antes de cargarlo.

Un contenido mal tipificado no rompe nada: simplemente no le llega a nadie, o
le llega a quien no debería si alguien lo manda a mano. Este revisor lo dice
antes, contenido por contenido, con tres niveles:

* **error** — el contenido nunca va a poder enviarse así (un programa de
  pacientes sin producto, un catálogo con ids repetidos);
* **aviso** — se puede enviar, pero no a quien probablemente se pensó (una
  promoción de un producto bajo receta con audiencia «todos» sólo les va a
  llegar a profesionales);
* **info** — algo para saber (un país sin reglas propias usa las genéricas).

Con la base de contactos, además, mide el **alcance** de cada contenido:
cuántas personas lo podrían recibir hoy.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from . import consentimiento as K

NIVELES = ("error", "aviso", "info")


def _h(rows: list[dict[str, Any]], cid: Any, nivel: str, motivo: str, sugerencia: str = "") -> None:
    rows.append({"id_contenido": str(cid), "nivel": nivel, "motivo": motivo, "sugerencia": sugerencia})


def _estructura(df: pd.DataFrame, rows: list[dict[str, Any]]) -> pd.DataFrame | None:
    """Lo que impide preparar el catálogo: se informa fila por fila en vez de cortar en el primero."""
    d = df.copy()
    d.columns = [K._clave(c).replace(" ", "_") for c in d.columns]
    faltan = [c for c in ("id_contenido", "tipo") if c not in d.columns]
    if faltan:
        _h(rows, "(catálogo)", "error", f"Faltan columnas: {', '.join(faltan)}.",
           "Usá la plantilla de contenidos.")
        return None
    ids = K.normalizar_id(d["id_contenido"])
    for cid in sorted(set(ids[ids.duplicated()])):
        _h(rows, cid, "error", "id_contenido repetido.", "Cada contenido necesita un id propio.")
    for cid in ids[ids == ""].index:
        _h(rows, f"(fila {cid + 2})", "error", "Contenido sin id.", "Completá id_contenido.")
    tipos = d["tipo"].map(K._clave)
    for cid, t in zip(ids, tipos, strict=True):
        if t not in K.TIPOS_CONTENIDO:
            _h(rows, cid, "error", f"Tipo «{t}» desconocido.", f"Usá: {', '.join(K.TIPOS_CONTENIDO)}.")
    if "audiencia" in d.columns:
        for cid, a in zip(ids, d["audiencia"], strict=True):
            try:
                K._audiencia(a)
            except ValueError as exc:
                _h(rows, cid, "error", str(exc), "")
    validas = (ids != "") & ~ids.duplicated(keep=False) & tipos.isin(K.TIPOS_CONTENIDO)
    if "audiencia" in d.columns:
        validas &= d["audiencia"].map(lambda a: K._clave(a) in K._AUDIENCIA)
    if not validas.any():
        return None
    return K.preparar_contenidos(df[validas.values])


def _reglas(c: dict[str, Any], crudo: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    cid, tipo, aud = c["id_contenido"], c["tipo"], c["audiencia"]
    con_producto = bool(c["producto_clave"])
    receta = c["condicion_venta"] == "receta"
    if not str(c.get("titulo", "")).strip():
        _h(rows, cid, "aviso", "Sin título.", "El título es lo que el equipo y el CRM ven.")
    if con_producto and not K._clave(crudo.get("condicion_venta")):
        _h(rows, cid, "aviso", "Tiene producto y no dice condición de venta: se trata como receta.",
           "Completá receta o venta_libre.")
    elif K._clave(crudo.get("condicion_venta")) and K._condicion(crudo.get("condicion_venta")) == "receta" \
            and K._clave(crudo.get("condicion_venta")).replace(" ", "_") not in K._CONDICION:
        _h(rows, cid, "aviso", f"Condición de venta «{crudo.get('condicion_venta')}» desconocida: se trata como receta.",
           "Usá receta o venta_libre.")
    if tipo in ("programa_paciente",) and not con_producto:
        _h(rows, cid, "error", "Programa de pacientes sin producto: no se le puede enviar a nadie.",
           "Indicá el producto del programa.")
    if tipo == "beneficio" and receta and not con_producto:
        _h(rows, cid, "error", "Beneficio de receta sin producto: no se le puede enviar a nadie.",
           "Indicá el producto o marcá venta_libre.")
    if tipo == "promocion_marca" and receta and aud != "profesional":
        _h(rows, cid, "aviso", "Promoción de un producto bajo receta: sólo les va a llegar a profesionales.",
           "Poné audiencia «profesional», o convertilo en concientización sin marca para el público.")
    if tipo == "concientizacion" and con_producto and receta:
        _h(rows, cid, "aviso", "Concientización que nombra un producto bajo receta: al público no se le envía.",
           "Sacá el producto (concientización sin marca) o pasalo a educación médica.")
    if tipo == "educacion_medica" and aud in ("paciente", "publico"):
        _h(rows, cid, "aviso", "Educación médica con audiencia de pacientes: se envía sólo a profesionales.",
           "Corregí la audiencia o el tipo.")
    if tipo in ("programa_paciente", "beneficio") and aud == "profesional":
        _h(rows, cid, "error", "Programa o beneficio para profesionales: el motor no los envía (código de ética).",
           "Usá audiencia paciente.")
    desconocidos = [p for p in c["paises_set"] if p != "*" and p not in K.POLITICAS]
    if desconocidos:
        _h(rows, cid, "info", f"País sin reglas propias: {', '.join(sorted(desconocidos))}. Se usan las genéricas.",
           "Pedí a legal que valide ese país.")


def revisar(contenidos: pd.DataFrame, contactos: pd.DataFrame | None = None,
            ajustes: dict | None = None) -> dict[str, Any]:
    """Hallazgos por contenido y, si hay contactos, el alcance de cada uno."""
    rows: list[dict[str, Any]] = []
    co = _estructura(contenidos, rows)
    resumen = pd.DataFrame(columns=["id_contenido", "titulo", "tipo", "estado", "alcance"])
    if co is not None:
        crudos = contenidos.copy()
        crudos.columns = [K._clave(c).replace(" ", "_") for c in crudos.columns]
        crudos["id_contenido"] = K.normalizar_id(crudos["id_contenido"])
        crudo_por_id = crudos.drop_duplicates("id_contenido").set_index("id_contenido").to_dict("index")
        for c in co.to_dict("records"):
            _reglas(c, crudo_por_id.get(c["id_contenido"], {}), rows)
        alcance = None
        if contactos is not None:
            ct, _ = K.preparar_contactos(contactos)
            el = K.matriz_elegibilidad(ct, co, ajustes)
            alcance = el[el["motivo"] == ""].groupby("id_contenido").size()
            for cid in co["id_contenido"]:
                if int(alcance.get(cid, 0)) == 0:
                    _h(rows, cid, "aviso", "Con la base de hoy no se le puede enviar a nadie.",
                       "Revisá audiencia, área y países, o los consentimientos de la base.")
        hall = pd.DataFrame(rows, columns=["id_contenido", "nivel", "motivo", "sugerencia"])
        peor = hall.assign(o=hall["nivel"].map({n: i for i, n in enumerate(NIVELES)})).groupby("id_contenido")["o"].min()
        resumen = pd.DataFrame({
            "id_contenido": co["id_contenido"], "titulo": co["titulo"], "tipo": co["tipo"],
            "estado": [NIVELES[int(peor[i])] if i in peor.index and NIVELES[int(peor[i])] != "info" else "ok"
                       for i in co["id_contenido"]],
            "alcance": [int(alcance.get(i, 0)) for i in co["id_contenido"]] if alcance is not None else None})
    hall = pd.DataFrame(rows, columns=["id_contenido", "nivel", "motivo", "sugerencia"])
    hall = hall.sort_values("nivel", key=lambda s: s.map({n: i for i, n in enumerate(NIVELES)}), kind="stable")
    conteo = {n: int((hall["nivel"] == n).sum()) for n in NIVELES}
    return {"hallazgos": hall.reset_index(drop=True), "resumen": resumen.reset_index(drop=True), "conteo": conteo,
            "listo": conteo["error"] == 0}


__all__ = ["NIVELES", "revisar"]
