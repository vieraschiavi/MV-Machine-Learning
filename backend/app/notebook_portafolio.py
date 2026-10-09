"""Portafolio y mercado desde un notebook (Fabric, Jupyter, Databricks).

Se usa con el mismo ``import`` que el resto del motor::

    from app import notebook as mv

    ventas = spark.sql("SELECT * FROM VentasLH.ventas_ytd").toPandas()
    matriz = mv.contribucion(ventas, entidad="pais", valor="ventas_usd",
                             mix="presentacion", grupo="area_terapeutica",
                             periodo="periodo")

    estudios = spark.sql("SELECT * FROM MercadoLH.estudios_hta").toPandas()
    analisis = mv.mercado(estudios=estudios,
                          lanzamiento={"pico": 0.12, "meses_al_pico": 18, "horizonte": 36},
                          inicio="2027-01")

    mv.portafolio_para_powerbi("/lakehouse/default/Files/mv/portafolio",
                               contribucion=matriz, mercado=analisis)

``mv.proponer_supuestos(...)`` le pide al motor de IA configurado una primera
versión de los supuestos del embudo cuando todavía no hay estudio: queda
marcada «IA (a validar)» y los estudios que se carguen después la pisan.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from .core import agente_mercado as A
from .core import contribucion as C
from .core import mercado as M
from .core import powerbi_portafolio as P
from .notebook import _ruta_escribible, a_pandas


def contribucion(datos: Any, entidad: str, valor: str, *, mix: str | None = None,
                 niveles_mix: dict[str, int] | None = None, grupo: str | None = None,
                 periodo: str | None = None, umbral_alta: float = 0.10,
                 umbral_media: float = 0.03, top: int = 3,
                 etiqueta: str = "mercados") -> dict[str, dict[str, Any]]:
    """La matriz de contribución y mix, para el total y para cada área.

    Devuelve ``{"Todas": matriz, "<área>": matriz, ...}``; cada matriz trae
    ``entidades`` (las burbujas), ``kpis``, ``lectura`` y ``acciones``.
    """
    cfg = C.Config(entidad=entidad, valor=valor, mix=mix, niveles_mix=niveles_mix,
                   grupo=grupo, periodo=periodo, umbral_alta=umbral_alta,
                   umbral_media=umbral_media, top=top, etiqueta=etiqueta)
    return C.calcular_por_grupo(a_pandas(datos), cfg)


def proponer_supuestos(area_terapeutica: str, molecula: str, enfermedad: str,
                       paises: Sequence[str], *, presentacion: str = "",
                       segmentos: Sequence[str] = ("Hombres", "Mujeres"), notas: str = "",
                       provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Primera versión de los supuestos, propuesta por el motor de IA (a validar)."""
    ctx = A.Contexto(area_terapeutica=area_terapeutica, molecula=molecula, enfermedad=enfermedad,
                     paises=tuple(paises), presentacion=presentacion,
                     segmentos=tuple(segmentos), notas=notas)
    r = A.proponer(ctx, provider=provider, model=model)
    r["tabla"] = pd.DataFrame(r["supuestos"])
    return r


def mercado(supuestos: Any = None, estudios: Any = None, *,
            lanzamiento: dict[str, Any] | None = None, observado: Any = None,
            inicio: str | None = None, n_sim: int = 2000) -> dict[str, Any]:
    """Embudo actual y latente, lecturas por país, tornado y (opcional) lanzamiento.

    ``supuestos`` es la propuesta de la IA (o una tabla propia); ``estudios``,
    los estudios de mercado, que pisan a la propuesta supuesto por supuesto.
    """
    prop = a_pandas(supuestos) if supuestos is not None else None
    est = a_pandas(estudios) if estudios is not None else None
    tabla, avisos = A.combinar(prop, est)
    plan = M.Lanzamiento(**lanzamiento) if lanzamiento else None
    obs = a_pandas(observado) if observado is not None else None
    r = A.analizar(tabla, plan=plan, observado=obs, inicio=inicio, n_sim=n_sim)
    r["avisos"] = [*avisos, *r["avisos"]]
    return r


def portafolio_para_powerbi(carpeta: str | Path, contribucion: dict[str, Any] | None = None,
                            mercado: dict[str, Any] | None = None,
                            formato: str = "parquet") -> dict[str, Path]:
    """Deja las tablas y el kit (tema, medidas DAX, burbujas Deneb) para Power BI."""
    ruta = _ruta_escribible(carpeta, "guardar")
    return P.escribir(ruta, contribucion, mercado, formato=formato)
