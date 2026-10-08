"""Azure Analysis Services (el MDW) y modelos de Power BI Premium como origen de datos.

Analysis Services no habla SQL: habla DAX, por XMLA, con el cliente ADOMD.NET
de Microsoft. Ese cliente —con el usuario corporativo, la ventana de inicio de
sesión de Microsoft (MFA) o un token— ya vive en la suite Adium All in One
(``adium_allinone.analysis_services``), y MV AutoML Studio corre adentro de la
suite en un hilo del mismo proceso. Este módulo lo usa; suelto, dice qué hace
falta en vez de fallar con un error de importación.

Mismas reglas que el resto de los conectores:

* **sólo lectura**: la consulta tiene que ser ``EVALUATE …`` (DAX). La suite lo
  vuelve a controlar antes de conectarse;
* el perfil guarda el servidor en ``host``, el modelo en ``database`` y la
  forma de entrar en ``auth`` (``usuario``, ``ventana`` o ``token``). El token
  viaja en ``password``, que nunca vuelve al navegador.

En «Explorar tablas», los modelos del servidor aparecen como esquemas y las
tablas del modelo elegido, como tablas: el mismo formulario que un servidor SQL.
"""
from __future__ import annotations

import re
import time
from typing import Any

import pandas as pd

ENGINE = "aas"
AUTENTICACIONES = ("usuario", "ventana", "token")
_SERVIDOR = re.compile(r"^(asazure|powerbi)://\S+$", re.I)
_EVALUATE = re.compile(r"^\s*evaluate\b", re.I)
_DEFINE = re.compile(r"^\s*define\b", re.I)
_TIENE_EVALUATE = re.compile(r"\bevaluate\b", re.I)
_TOPN = re.compile(r"^\s*evaluate\s+topn\s*\(", re.I)


class ErrorAAS(RuntimeError):
    """Algo que el usuario tiene que corregir, dicho para el usuario."""


def motor(AS=None):
    """El conector de Analysis Services de la suite, o ErrorAAS si AutoML corre suelto."""
    if AS is not None:
        return AS
    try:
        from adium_allinone import analysis_services
    except Exception as exc:        # suelto: la suite no está en este proceso
        raise ErrorAAS(
            "Analysis Services se lee con el conector de Microsoft (ADOMD.NET) que trae Adium All in One. "
            "Abrí MV AutoML Studio desde la suite y conectate acá mismo.") from exc
    return analysis_services


def _servidor(p: dict[str, Any]) -> str:
    srv = str(p.get("host") or "").strip()
    if not _SERVIDOR.match(srv):
        raise ErrorAAS("El servidor empieza con asazure:// (o powerbi:// para un modelo de Power BI Premium).")
    return srv


def _auth(p: dict[str, Any]) -> str:
    auth = str(p.get("auth") or "usuario")
    if auth not in AUTENTICACIONES:
        raise ErrorAAS(f"Forma de entrar desconocida: {auth}.")
    return auth


def _token(p: dict[str, Any]) -> str:
    return str(p.get("password") or "") if _auth(p) == "token" else ""


def _preparar(p: dict[str, Any], AS=None):
    """Valida el perfil y deja al conector de la suite con la cuenta del perfil. Devuelve (AS, servidor)."""
    srv, auth = _servidor(p), _auth(p)
    usuario, clave = str(p.get("username") or "").strip(), str(p.get("password") or "")
    if auth == "usuario" and not (usuario and clave):
        raise ErrorAAS("Falta el usuario (tu mail de la empresa) o la contraseña.")
    if auth == "token" and not clave.strip():
        raise ErrorAAS("Falta el token.")
    AS = motor(AS)
    faltan = AS.librerias_faltantes() if hasattr(AS, "librerias_faltantes") else []
    if faltan:
        raise ErrorAAS(f"Faltan librerías para hablar con Analysis Services: {', '.join(faltan)}. "
                       "En la suite: Pipeline → «Traer los módulos que faltan».")
    try:
        AS.usar_usuario(srv, usuario if auth == "usuario" else "", clave if auth == "usuario" else "")
        AS.usar_ventana(srv, auth == "ventana")
    except Exception as exc:        # p. ej. un usuario que no es un mail: el conector dice qué corregir
        raise ErrorAAS(str(exc)) from exc
    return AS, srv


def _modelo(p: dict[str, Any], schema: str | None = None) -> str:
    modelo = str(schema or p.get("database") or "").strip()
    if not modelo:
        raise ErrorAAS("Falta el modelo: tocá «Explorar tablas» para ver los modelos del servidor y elegí uno.")
    return modelo


def solo_lectura(consulta: str) -> str:
    """La consulta, si es un EVALUATE (o DEFINE … EVALUATE) de una sola sentencia. Si no, ErrorAAS."""
    q = (consulta or "").strip().rstrip(";").strip()
    if not q:
        raise ErrorAAS("La consulta está vacía. Elegí una tabla o escribí EVALUATE 'Tabla'.")
    lee = _EVALUATE.match(q) or (_DEFINE.match(q) and _TIENE_EVALUATE.search(q))
    if not lee or ";" in q:
        raise ErrorAAS("Contra Analysis Services sólo se permiten consultas DAX de lectura: EVALUATE 'Tabla' "
                       "o EVALUATE SUMMARIZECOLUMNS(…).")
    return q


def consulta_de_tabla(tabla: str) -> str:
    """EVALUATE de una tabla entera, con el nombre bien citado."""
    return "EVALUATE '" + str(tabla).replace("'", "''") + "'"


def con_tope(consulta: str, limite: int) -> str:
    """La consulta recortada a `limite` filas (TOPN), salvo que ya traiga su propio TOPN.

    Un DEFINE … EVALUATE se deja como está: envolverlo exige entender el DAX, y
    la vista previa igual muestra sólo las primeras filas."""
    q = solo_lectura(consulta)
    if _TOPN.match(q) or _DEFINE.match(q):
        return q
    cuerpo = _EVALUATE.sub("", q, count=1).strip()
    return f"EVALUATE TOPN({int(limite)}, {cuerpo})"


def test_connection(p: dict[str, Any], AS=None) -> dict[str, Any]:
    t0 = time.time()
    try:
        AS, srv = _preparar(p, AS)
        modelos = list(AS.listar_modelos(srv, _token(p)))
    except Exception as exc:        # permiso, red, MFA: el conector de la suite ya explica la causa
        return {"ok": False, "error": str(exc)[:400], "ms": int((time.time() - t0) * 1000)}
    if not modelos:
        return {"ok": False, "ms": int((time.time() - t0) * 1000),
                "error": "El servidor no devolvió modelos para esta cuenta (revisá el permiso de lectura)."}
    muestra = ", ".join(modelos[:6]) + ("…" if len(modelos) > 6 else "")
    return {"ok": True, "ms": int((time.time() - t0) * 1000), "engine": ENGINE,
            "version": f"Analysis Services · {len(modelos)} modelo(s): {muestra}", "url": srv}


def list_tables(p: dict[str, Any], schema: str | None = None, AS=None) -> dict[str, Any]:
    """Los modelos del servidor como «esquemas» y las tablas del modelo elegido."""
    AS, srv = _preparar(p, AS)
    token = _token(p)
    try:
        modelos = list(AS.listar_modelos(srv, token))
    except Exception as exc:
        raise ErrorAAS(str(exc)) from exc
    elegido = str(schema or p.get("database") or "").strip() or (modelos[0] if len(modelos) == 1 else "")
    if not elegido:
        return {"schemas": modelos, "schema": None, "tables": []}
    try:
        nombres = list(AS.tablas_del_modelo(srv, elegido, token))
    except Exception as exc:
        raise ErrorAAS(str(exc)) from exc
    return {"schemas": modelos, "schema": elegido,
            "tables": [{"schema": elegido, "name": n, "type": "tabla"} for n in sorted(nombres)]}


def leer(p: dict[str, Any], consulta: str, limite: int | None = None, schema: str | None = None,
         AS=None) -> pd.DataFrame:
    """El resultado de una consulta DAX de lectura (recortada a `limite` filas si se pide)."""
    q = con_tope(consulta, limite) if limite else solo_lectura(consulta)
    AS, srv = _preparar(p, AS)
    try:
        df = AS.consultar(srv, _modelo(p, schema), q, _token(p))
    except ErrorAAS:
        raise
    except Exception as exc:
        raise ErrorAAS(str(exc)[:400]) from exc
    return df.reset_index(drop=True)
