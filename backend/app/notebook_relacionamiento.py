"""Relacionamiento con consentimiento desde un notebook (Fabric, Jupyter, Databricks).

    from app import notebook as mv

    r = mv.relacionamiento(
        contactos=spark.sql("SELECT * FROM CrmLH.contactos_seudonimos"),
        contenidos=spark.sql("SELECT * FROM CrmLH.catalogo_contenidos"),
        interacciones=spark.sql("SELECT * FROM CrmLH.interacciones"),
        poblacion=spark.sql("SELECT * FROM PublicosLH.censo"),
        prevalencias=spark.sql("SELECT * FROM PublicosLH.prevalencias"),
        escucha=spark.sql("SELECT * FROM PublicosLH.escucha_social"),
        area="Cardiometabólica", segmentar=("sexo", "rango_edad"))

    r["recomendaciones"]        # el siguiente mejor contenido por persona, con el porqué
    mv.relacionamiento_para_powerbi("/lakehouse/default/Files/mv/relacionamiento", r)

La salida deja las tablas y medidas del tablero y, en ``modelo_fabric/``, el
modelo estrella con su DDL Delta y la celda que lo carga en el Lakehouse.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import programa_relacionamiento as PR
from .notebook_portafolio import _ruta_escribible, a_pandas


def relacionamiento(contactos: Any, contenidos: Any, interacciones: Any = None, *, poblacion: Any = None,
                    prevalencias: Any = None, escucha: Any = None, area: str | None = None,
                    por_barrio: bool = False, segmentar: tuple[str, ...] = (),
                    temas: dict[str, list[str]] | None = None, hoy: Any = None,
                    ajustes: dict | None = None, por_contacto: int = 3) -> dict[str, Any]:
    """Recomendaciones, embudo, KPIs, auditoría y, con fuentes públicas, cobertura y escucha."""
    def pd_o_nada(x: Any) -> Any:
        return a_pandas(x) if x is not None else None
    return PR.analizar(a_pandas(contactos), a_pandas(contenidos), pd_o_nada(interacciones),
                       poblacion=pd_o_nada(poblacion), prevalencias=pd_o_nada(prevalencias),
                       escucha=pd_o_nada(escucha), area=area, por_barrio=por_barrio, segmentar=segmentar,
                       temas=temas, hoy=hoy, ajustes=ajustes, por_contacto=por_contacto)


def relacionamiento_para_powerbi(carpeta: str | Path, resultado: dict[str, Any],
                                 formato: str = "parquet") -> dict[str, Path]:
    """Tablas y medidas para Power BI, y el modelo estrella para el Lakehouse en `modelo_fabric/`."""
    return PR.exportar(_ruta_escribible(carpeta, "guardar"), resultado, formato=formato)
