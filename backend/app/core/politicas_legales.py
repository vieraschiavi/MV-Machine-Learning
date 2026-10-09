"""Las reglas por país que valida legal: guardadas, con quién y cuándo, y su historial.

El programa trae valores **conservadores** por país (``consentimiento.Politica``)
y los marca «a validar». Este módulo es el circuito para que legal los
confirme o los cambie sin tocar código:

1. Se baja la **planilla de validación**: una fila por país con cada regla, el
   valor que el programa asume, la pregunta que legal tiene que responder y
   columnas para el valor validado, la norma, quién valida y la fecha.
2. Legal la completa y se sube. Se aplican sólo las filas firmadas (con
   ``validado_por``); el resto queda como estaba.
3. Lo validado se guarda por workspace en ``relacionamiento/politicas.json`` y
   el análisis lo usa solo. Cada cambio queda en el **historial**: qué campo,
   valor anterior y nuevo, quién y cuándo.

Una regla nunca se afloja sin firma: habilitar la promoción de receta al
público, apagar el doble opt-in o subir el tope de envíos exige
``validado_por``.
"""
from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path
from typing import Any

import pandas as pd

from . import consentimiento as K
from . import workspace

CAMPOS = {  # campo: (tipo, pregunta para legal)
    "promocion_receta_a_publico": (bool, "¿Se permite promocionar medicamentos de venta bajo receta al público "
                                         "general? (en la región, normalmente NO)"),
    "promocion_venta_libre_a_publico": (bool, "¿Se permite promocionar productos de venta libre al público "
                                              "con consentimiento comercial?"),
    "doble_optin_obligatorio": (bool, "¿La ley o la política interna exige doble confirmación (doble opt-in) "
                                      "antes del primer envío?"),
    "frecuencia_max_30d": (int, "¿Cuántos envíos por persona cada 30 días como máximo?"),
}
_ARCHIVO = "politicas.json"
_LOCK = threading.Lock()


def _ruta() -> Path:
    p = workspace.root() / "relacionamiento"
    p.mkdir(parents=True, exist_ok=True)
    return p / _ARCHIVO


def _leer() -> dict[str, Any]:
    p = _ruta()
    if not p.exists():
        return {"paises": {}, "historial": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _escribir(datos: dict[str, Any]) -> None:
    p = _ruta()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def _valor(campo: str, v: Any) -> Any:
    tipo = CAMPOS[campo][0]
    if tipo is bool:
        if isinstance(v, bool):
            return v
        k = K._clave(v)
        if k in K._SI or k in {"verdadero"}:
            return True
        if k in K._NO or k == "":
            return False
        raise ValueError(f"«{campo}»: «{v}» no es sí ni no.")
    try:
        n = int(float(v))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"«{campo}»: «{v}» no es un número entero.") from exc
    if not 0 <= n <= 30:
        raise ValueError(f"«{campo}»: tiene que estar entre 0 y 30.")
    return n


def _afloja(campo: str, antes: Any, despues: Any) -> bool:
    """¿El cambio relaja una regla respecto de lo que había?"""
    if campo == "promocion_receta_a_publico":
        return bool(despues) and not bool(antes)
    if campo == "doble_optin_obligatorio":
        return bool(antes) and not bool(despues)
    if campo == "frecuencia_max_30d":
        return int(despues) > int(antes)
    if campo == "promocion_venta_libre_a_publico":
        return bool(despues) and not bool(antes)
    return False


def guardar(pais: str, cambios: dict[str, Any], *, validado_por: str = "", norma: str = "",
            nota: str = "") -> dict[str, Any]:
    """Aplica los cambios de un país con su firma. Devuelve la política resultante."""
    base = K.politica(pais)
    nombre = base.pais
    validado_por = (validado_por or "").strip()
    with _LOCK:
        datos = _leer()
        actual = datos["paises"].get(nombre, {})
        vigente = {c: actual.get(c, getattr(base, c)) for c in CAMPOS}
        registro = []
        nuevos = dict(actual)
        for campo, v in cambios.items():
            if campo not in CAMPOS:
                raise ValueError(f"Campo desconocido: «{campo}». Se pueden ajustar: {', '.join(CAMPOS)}.")
            valor = _valor(campo, v)
            if valor == vigente[campo]:
                continue
            if _afloja(campo, vigente[campo], valor) and not validado_por:
                raise ValueError(f"Relajar «{campo}» en {nombre} exige la firma de legal (validado_por).")
            registro.append({"campo": campo, "antes": vigente[campo], "despues": valor})
            nuevos[campo] = valor
        if validado_por:
            nuevos.update({"validado_por_legal": True, "validado_por": validado_por,
                           "fecha_validacion": time.strftime("%Y-%m-%d"), "norma": norma.strip(),
                           "nota": nota.strip()})
        if registro or validado_por:
            datos["paises"][nombre] = nuevos
            datos["historial"].append({"fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "pais": nombre,
                                       "validado_por": validado_por or None, "norma": norma.strip() or None,
                                       "cambios": registro})
            _escribir(datos)
    return vigentes([nombre])[0]


def ajustes() -> dict[str, dict[str, Any]]:
    """Lo validado, en el formato que espera ``consentimiento.politica``."""
    out = {}
    for pais, v in _leer()["paises"].items():
        out[pais] = {k: v[k] for k in (*CAMPOS, "validado_por_legal") if k in v}
    return out


def combinar(pedido: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Lo guardado y, encima, los ajustes de un pedido puntual (para simular un escenario)."""
    base = ajustes()
    for pais, v in (pedido or {}).items():
        base[pais] = {**base.get(pais, {}), **v}
    return base


def vigentes(paises: list[str] | None = None) -> list[dict[str, Any]]:
    """Las reglas que se aplican hoy por país, con su firma si la tienen."""
    guardado = _leer()["paises"]
    nombres = paises or sorted({*(p.pais for p in K.POLITICAS.values()), *guardado})
    out = []
    for nombre in dict.fromkeys(nombres):
        pol = K.politica(nombre, ajustes())
        g = guardado.get(pol.pais, {})
        out.append({"pais": pol.pais, "ley_datos": pol.ley_datos, "autoridad_sanitaria": pol.autoridad_sanitaria,
                    **{c: getattr(pol, c) for c in CAMPOS}, "validado_por_legal": pol.validado_por_legal,
                    "validado_por": g.get("validado_por"), "fecha_validacion": g.get("fecha_validacion"),
                    "norma": g.get("norma"), "nota": g.get("nota")})
    return out


def historial(limite: int = 200) -> list[dict[str, Any]]:
    return list(reversed(_leer()["historial"]))[:limite]


# ── planilla para legal ─────────────────────────────────────────────────────
COLUMNAS_PLANILLA = ["pais", "ley_datos", "autoridad_sanitaria", "regla", "pregunta", "valor_que_asume_el_programa",
                     "valor_validado", "norma_o_fuente", "validado_por", "fecha", "nota"]


def planilla(paises: list[str] | None = None) -> bytes:
    """Excel con una fila por país y regla, para que legal complete y firme."""
    filas = []
    for v in vigentes(paises):
        for campo, (_, pregunta) in CAMPOS.items():
            filas.append({"pais": v["pais"], "ley_datos": v["ley_datos"], "autoridad_sanitaria": v["autoridad_sanitaria"],
                          "regla": campo, "pregunta": pregunta, "valor_que_asume_el_programa": _legible(v[campo]),
                          "valor_validado": "", "norma_o_fuente": "", "validado_por": "", "fecha": "", "nota": ""})
    df = pd.DataFrame(filas, columns=COLUMNAS_PLANILLA)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="Validación legal", index=False)
        pd.DataFrame({"Cómo completar": [
            "Una fila por país y regla. Completar «valor_validado» (sí/no o un número), la norma, quién valida y la fecha.",
            "Sólo se aplican las filas con «validado_por». Las demás quedan con el valor conservador del programa.",
            "Relajar una regla (por ejemplo, habilitar receta al público) sin firma se rechaza.",
            "El programa aplica reglas; no da asesoramiento jurídico.",
        ]}).to_excel(xw, sheet_name="Instrucciones", index=False)
        hoja = xw.sheets["Validación legal"]
        for col, ancho in zip("ABCDEFGHIJK", (14, 34, 14, 30, 70, 14, 14, 30, 22, 12, 30), strict=True):
            hoja.column_dimensions[col].width = ancho
        hoja.freeze_panes = "D2"
    return buf.getvalue()


def _legible(v: Any) -> Any:
    return ("sí" if v else "no") if isinstance(v, bool) else v


def importar_planilla(contenido: bytes) -> dict[str, Any]:
    """Aplica las filas firmadas de la planilla. Devuelve qué se aplicó y qué se ignoró."""
    try:
        df = pd.read_excel(io.BytesIO(contenido), sheet_name="Validación legal", dtype=object)
    except Exception as exc:  # noqa: BLE001 - cualquier archivo que no sea la planilla
        raise ValueError("No es la planilla de validación: falta la hoja «Validación legal».") from exc
    faltan = [c for c in ("pais", "regla", "valor_validado", "validado_por") if c not in df.columns]
    if faltan:
        raise ValueError(f"A la planilla le faltan columnas: {', '.join(faltan)}.")
    df = df.where(df.notna(), "")
    for col in ("norma_o_fuente", "nota"):
        if col not in df.columns:
            df[col] = ""
    firmadas = df[df["validado_por"].astype(str).str.strip() != ""]
    aplicadas, errores = [], []
    for (pais, firma, norma), grupo in firmadas.groupby(
            [firmadas["pais"].astype(str), firmadas["validado_por"].astype(str).str.strip(),
             firmadas["norma_o_fuente"].astype(str)], sort=False):
        cambios = {str(r["regla"]): r["valor_validado"] for _, r in grupo.iterrows()
                   if str(r["valor_validado"]).strip() != ""}
        notas = "; ".join(str(n) for n in grupo["nota"] if str(n).strip())
        try:
            guardar(pais, cambios, validado_por=firma, norma=norma, nota=notas)
            aplicadas.append({"pais": pais, "validado_por": firma, "reglas": len(cambios)})
        except ValueError as exc:
            errores.append({"pais": pais, "error": str(exc)})
    return {"aplicadas": aplicadas, "errores": errores, "sin_firma": int(len(df) - len(firmadas))}


__all__ = ["CAMPOS", "ajustes", "combinar", "guardar", "historial", "importar_planilla", "planilla", "vigentes"]
