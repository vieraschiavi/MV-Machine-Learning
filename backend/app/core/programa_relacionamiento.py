"""El programa de relacionamiento entero: base propia + fuentes públicas, en una llamada.

Junta los módulos para la API y el notebook:

* ``relacionamiento`` — elegibilidad, «siguiente mejor contenido», embudo, KPIs y auditoría;
* ``territorio`` — nivel socioeconómico de la zona y cobertura contra censo y prevalencias;
* ``escucha`` — de qué se habla en redes, agregado;
* ``modelo_fabric`` y ``powerbi_relacionamiento`` — la salida.

Cada fuente pública es opcional: sin censo no hay cobertura, sin escucha no
hay temas, y el resto funciona igual.
"""
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from . import consentimiento as K
from . import escucha as S
from . import modelo_fabric as F
from . import politicas_legales as PL
from . import powerbi_relacionamiento as P
from . import registro_consentimientos as RC
from . import relacionamiento as R
from . import territorio as T


def analizar(contactos: pd.DataFrame, contenidos: pd.DataFrame, interacciones: pd.DataFrame | None = None,
             *, poblacion: pd.DataFrame | None = None, prevalencias: pd.DataFrame | None = None,
             escucha: pd.DataFrame | None = None, area: str | None = None, por_barrio: bool = False,
             segmentar: tuple[str, ...] = (), temas: dict[str, list[str]] | None = None,
             hoy: Any = None, ajustes: dict | None = None, por_contacto: int = 3,
             politicas_guardadas: bool = True, consentimientos: pd.DataFrame | None = None,
             busquedas: pd.DataFrame | None = None) -> dict[str, Any]:
    """Todo el análisis. Devuelve tablas (DataFrames), avisos y lo necesario para el modelo."""
    if politicas_guardadas:
        # Lo que legal validó en este workspace es la base; un ajuste del pedido simula un escenario encima.
        ajustes = PL.combinar(ajustes)
    avisos_libro: list[str] = []
    libro = None
    if consentimientos is not None:
        # El libro de consentimientos manda sobre la tabla: para quien tiene eventos, el estado sale de ahí.
        contactos, avisos_libro = RC.aplicar(contactos, consentimientos)
        libro = RC.preparar(consentimientos)[0]
    r = R.analizar(contactos, contenidos, interacciones, hoy=hoy, ajustes=ajustes, por_contacto=por_contacto)
    avisos = [*avisos_libro, *r["avisos"]]
    ct, co = r["_preparado"]["contactos"], r["_preparado"]["contenidos"]
    pob = T.preparar_poblacion(poblacion) if poblacion is not None else None
    pv = T.preparar_prevalencias(prevalencias) if prevalencias is not None else None
    if pob is not None:
        ct = T.enriquecer(ct, pob)
    r["cobertura"], r["cobertura_resumen"] = pd.DataFrame(), None
    if pob is not None and pv is not None:
        areas = list(dict.fromkeys(pv["area_terapeutica"]))
        elegida = area or (areas[0] if areas else None)
        if elegida:
            r["cobertura"] = T.cobertura(ct, pob, pv, elegida, por_barrio=por_barrio, segmentar=segmentar)
            r["cobertura_resumen"] = T.resumen(r["cobertura"])
        r["areas_prevalencia"] = areas
    elif (pob is None) != (pv is None):
        avisos.append("Para la cobertura hacen falta las dos tablas públicas: población (censo) y prevalencias.")
    r["escucha_menciones"] = r["escucha_terminos"] = r["farmacovigilancia"] = pd.DataFrame()
    if escucha is not None:
        productos = [p for p in co["producto"].astype(str) if p.strip()]
        temas = temas or S.temas_del_catalogo(co)
    if escucha is not None and not temas:
        avisos.append("La escucha se salteó: el catálogo no tiene áreas ni productos y no se indicaron temas.")
    elif escucha is not None:
        e = S.agregar(escucha, temas, productos=productos)
        r["escucha_menciones"], r["escucha_terminos"] = e["menciones"], e["terminos"]
        r["farmacovigilancia"], r["escucha_publicaciones"] = e["farmacovigilancia"], e["publicaciones"]
        avisos += e["avisos"]
    r["busquedas"] = pd.DataFrame()
    if busquedas is not None and not busquedas.empty:
        b = busquedas.copy()
        b.columns = [K._clave(c) for c in b.columns]
        faltan = [c for c in ("pais", "region", "termino", "interes") if c not in b.columns]
        if faltan:
            raise ValueError(f"A la tabla de búsquedas le faltan columnas: {', '.join(faltan)} (usá el importador "
                             "de Google Trends).")
        r["busquedas"] = b[["pais", "region", "termino", "interes"]]
    r["avisos"] = avisos
    r["_preparado"] = {**r["_preparado"], "contactos": ct, "poblacion": pob, "prevalencias": pv,
                       "consentimientos": libro}
    return r


def a_json(r: dict[str, Any], max_filas: int = 500) -> dict[str, Any]:
    """Para la pantalla: las tablas como listas, las grandes recortadas."""
    publico = {k: v for k, v in r.items() if not k.startswith("_")}
    out = R.a_json(publico, max_recomendaciones=max_filas)
    for k in ("cobertura", "escucha_menciones"):
        if isinstance(r.get(k), pd.DataFrame):
            v = r[k].head(max_filas)
            out[k] = v.astype(object).where(v.notna(), None).to_dict("records")
    return out


def modelo(r: dict[str, Any]) -> dict[str, pd.DataFrame]:
    p = r["_preparado"]
    return F.construir(contactos=p["contactos"], contenidos=p["contenidos"], interacciones=p["interacciones"],
                       recomendaciones=r["recomendaciones"], poblacion=p["poblacion"],
                       prevalencias=p["prevalencias"], escucha=r["escucha_menciones"],
                       cobertura=r["cobertura"], consentimientos=p.get("consentimientos"),
                       busquedas=r.get("busquedas"), hoy=r["hoy"])


def exportar(carpeta: str | Path, r: dict[str, Any], formato: str = "parquet") -> dict[str, Path]:
    """Tablas para Power BI (con sus medidas) y, en `modelo_fabric/`, el modelo estrella para el Lakehouse."""
    ruta = Path(carpeta).expanduser()
    salida = P.escribir(ruta, r, formato=formato)
    salida.update({f"modelo_fabric/{k}": v for k, v in
                   F.escribir(ruta / "modelo_fabric", modelo(r), formato=formato).items()})
    return salida


def empaquetar(r: dict[str, Any], destino_zip: Path, formato: str = "parquet") -> Path:
    """Un zip con las dos salidas, armado en una carpeta temporal."""
    with tempfile.TemporaryDirectory(prefix="mv-rel-") as tmp:
        exportar(tmp, r, formato=formato)
        with zipfile.ZipFile(destino_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(Path(tmp).rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(tmp).as_posix())
    return destino_zip


__all__ = ["a_json", "analizar", "empaquetar", "exportar", "modelo"]
