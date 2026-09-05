"""La bitácora convertida en documento: HTML para leer, Word para editar.

El PDF no se genera acá a propósito. Sale de imprimir este mismo HTML —el
escritorio lo hace con un clic y el navegador con Ctrl+P—, de modo que los
tres formatos muestran exactamente lo mismo y no hay una tercera maqueta que
mantener ni una biblioteca de PDF que empaquetar en el .exe. Por eso el HTML
trae sus reglas de impresión: no es un detalle estético, es el PDF.

El HTML es una sola pieza —estilo adentro, cero pedidos a internet— porque el
programa corre en máquinas sin salida a internet y el archivo se archiva para
leerlo dentro de dos años, cuando ese CDN ya no exista.
"""
from __future__ import annotations

import html
import time
from pathlib import Path
from typing import Any

from .docx_simple import Documento

ETAPAS_LABEL = {
    "ingesta": "Ingesta", "etl": "Transformación", "objetivo": "Objetivo",
    "particion": "Partición", "preparacion": "Preparación", "entrenamiento": "Entrenamiento",
    "seleccion": "Selección de variables", "calibracion": "Calibración",
    "evaluacion": "Evaluación", "explicacion": "Explicabilidad", "veredicto": "Veredicto",
}

CSS = """
:root{--fondo:#fff;--tinta:#1f2430;--suave:#5b6472;--linea:#e4e8ef;--marca:#0b5fff;
--tec:#f4f7ff;--cri:#f3faf5;--cri-borde:#1a8f5a;--codigo:#f6f8fa}
*{box-sizing:border-box}
body{margin:0;background:var(--fondo);color:var(--tinta);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.hoja{max-width:900px;margin:0 auto;padding:40px 28px 80px}
h1{font-size:27px;margin:0 0 6px}
.sub{color:var(--suave);margin:0 0 26px;font-size:14px}
.tarjetas{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 26px}
.tarjeta{flex:1 1 150px;border:1px solid var(--linea);border-radius:10px;padding:12px 14px}
.tarjeta b{display:block;font-size:21px;line-height:1.2}
.tarjeta span{color:var(--suave);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.como{border-left:3px solid var(--marca);background:var(--tec);
padding:12px 16px;border-radius:0 8px 8px 0;margin:0 0 30px;font-size:14px}
.paso{border:1px solid var(--linea);border-radius:12px;padding:20px 22px;margin:0 0 18px}
.cabeza{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.orden{background:var(--marca);color:#fff;border-radius:999px;min-width:26px;height:26px;
display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:700}
.etapa{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--suave);
border:1px solid var(--linea);border-radius:999px;padding:2px 9px}
.cabeza h2{font-size:17px;margin:0;flex:1 1 320px}
.dos{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.caja{border-radius:9px;padding:12px 14px;font-size:14px}
.caja.tecnica{background:var(--tec);border-left:3px solid var(--marca)}
.caja.criolla{background:var(--cri);border-left:3px solid var(--cri-borde)}
.caja em{display:block;font-style:normal;font-size:11px;text-transform:uppercase;
letter-spacing:.06em;color:var(--suave);margin-bottom:5px}
.linea{margin:0 0 8px;font-size:14px}
.linea b{color:var(--tinta)}
table{border-collapse:collapse;width:100%;margin-top:12px;font-size:13px}
th,td{border:1px solid var(--linea);padding:6px 10px;text-align:left;vertical-align:top}
th{width:34%;background:#fafbfd;font-weight:600}
pre{background:var(--codigo);border:1px solid var(--linea);border-radius:8px;padding:12px;
overflow-x:auto;font-size:12px;white-space:pre-wrap;word-break:break-word}
footer{color:var(--suave);font-size:12px;border-top:1px solid var(--linea);
margin-top:34px;padding-top:14px}
@media (prefers-color-scheme:dark){
:root{--fondo:#14161c;--tinta:#e8ecf3;--suave:#9aa4b5;--linea:#2a2f3a;--tec:#182135;
--cri:#152a20;--codigo:#1a1e26}
th{background:#1a1e26}}
@media print{
 @page{margin:14mm}
 body{background:#fff;color:#000;font-size:11pt}
 .hoja{max-width:none;padding:0}
 .paso{break-inside:avoid;page-break-inside:avoid;border:1px solid #ccc}
 .dos{grid-template-columns:1fr 1fr}
 .caja.tecnica{background:#f4f7ff}.caja.criolla{background:#f3faf5}
 pre{white-space:pre-wrap}
 .no-imprimir{display:none}
}
"""


def _e(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _fecha(ts: float | None) -> str:
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(ts or time.time()))


# ══════════════════════════════════════════════════════════════════ HTML ══════
def a_html(libro: dict[str, Any]) -> str:
    r = libro.get("resumen") or {}
    partes = [
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        f"<title>{_e(libro.get('titulo', 'Bitácora'))}</title>",
        f"<style>{CSS}</style></head><body><div class=\"hoja\">",
        f"<h1>{_e(libro.get('titulo', 'Bitácora'))}</h1>",
        f"<p class=\"sub\">Generado el {_fecha(libro.get('generado_en'))} · "
        f"MV AutoML Studio</p>",
        _tarjetas(r),
        "<div class=\"como\"><b>Cómo leer esto.</b> Cada paso está contado dos veces y dice lo "
        "mismo: a la izquierda, en <b>lenguaje técnico</b>, con la operación y sus parámetros, "
        "para quien audita el proceso; a la derecha, <b>en criollo</b>, para quien necesita "
        "entender qué le pasó a sus datos y por qué. Debajo, el motivo y cómo repercute en lo "
        "que viene después. Los pasos están en el orden real en que ocurrieron.</div>",
    ]
    partes += [_paso_html(p) for p in libro.get("pasos", [])]
    partes.append(
        "<footer>Documento generado automáticamente a partir del linaje del dataset y de la "
        "ficha del modelo. Cada cifra sale de lo que quedó registrado al ejecutarse el proceso: "
        "no hay valores estimados ni redondeos hechos para este informe.</footer>")
    partes.append("</div></body></html>")
    return "\n".join(partes)


def _tarjetas(r: dict[str, Any]) -> str:
    campos = [
        ("Pasos", r.get("n_pasos")),
        ("Transformaciones", r.get("transformaciones")),
        ("Filas al inicio", _mil(r.get("filas_inicio"))),
        ("Filas al final", _mil(r.get("filas_fin"))),
        ("Columnas al inicio", r.get("columnas_inicio")),
        ("Columnas al final", r.get("columnas_fin")),
    ]
    celdas = "".join(f"<div class=\"tarjeta\"><b>{_e(v if v is not None else '—')}</b>"
                     f"<span>{_e(k)}</span></div>" for k, v in campos)
    return f"<div class=\"tarjetas\">{celdas}</div>"


def _mil(v: Any) -> str:
    try:
        return f"{int(v):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _paso_html(p: dict[str, Any]) -> str:
    ev = "".join(f"<tr><th>{_e(e.get('clave'))}</th><td>{_e(e.get('valor'))}</td></tr>"
                 for e in p.get("evidencia", []))
    tabla = f"<table>{ev}</table>" if ev else ""
    detalle = (f"<pre>{_e(p['detalle'])}</pre>"
               if str(p.get("detalle", "")).strip() else "")
    etapa = ETAPAS_LABEL.get(p.get("etapa", ""), p.get("etapa", ""))
    return (
        "<section class=\"paso\">"
        f"<div class=\"cabeza\"><span class=\"orden\">{_e(p.get('orden'))}</span>"
        f"<span class=\"etapa\">{_e(etapa)}</span><h2>{_e(p.get('titulo'))}</h2></div>"
        "<div class=\"dos\">"
        f"<div class=\"caja tecnica\"><em>Lectura técnica</em>{_e(p.get('tecnico'))}</div>"
        f"<div class=\"caja criolla\"><em>En criollo</em>{_e(p.get('criollo'))}</div>"
        "</div>"
        f"<p class=\"linea\"><b>Por qué se hizo:</b> {_e(p.get('porque'))}</p>"
        f"<p class=\"linea\"><b>Cómo repercute:</b> {_e(p.get('impacto'))}</p>"
        f"{tabla}{detalle}</section>"
    )


# ══════════════════════════════════════════════════════════════════ Word ══════
def a_docx(libro: dict[str, Any], destino: str | Path) -> Path:
    titulo = str(libro.get("titulo", "Bitácora"))
    doc = Documento(titulo)
    doc.titulo(titulo)
    doc.apagado(f"Generado el {_fecha(libro.get('generado_en'))} · MV AutoML Studio")

    r = libro.get("resumen") or {}
    doc.encabezado("Resumen", 1)
    doc.tabla([
        ("Pasos registrados", str(r.get("n_pasos", "—"))),
        ("Transformaciones aplicadas", str(r.get("transformaciones", "—"))),
        ("Filas al inicio → al final", f"{_mil(r.get('filas_inicio'))} → {_mil(r.get('filas_fin'))}"),
        ("Columnas al inicio → al final",
         f"{r.get('columnas_inicio', '—')} → {r.get('columnas_fin', '—')}"),
    ])
    doc.parrafo("Cada paso está contado dos veces y dice lo mismo: primero en lenguaje técnico, "
                "con la operación y sus parámetros, para quien audita el proceso; después en "
                "criollo, para quien necesita entender qué le pasó a sus datos. Los pasos están "
                "en el orden real en que ocurrieron.")

    for p in libro.get("pasos", []):
        etapa = ETAPAS_LABEL.get(p.get("etapa", ""), p.get("etapa", ""))
        doc.encabezado(f"{p.get('orden')}. {p.get('titulo')}", 1)
        doc.apagado(f"Etapa: {etapa}")
        doc.etiquetado("Lectura técnica", p.get("tecnico", ""))
        doc.etiquetado("En criollo", p.get("criollo", ""))
        doc.etiquetado("Por qué se hizo", p.get("porque", ""))
        doc.etiquetado("Cómo repercute", p.get("impacto", ""))
        filas = [(str(e.get("clave", "")), str(e.get("valor", "")))
                 for e in p.get("evidencia", [])]
        doc.tabla(filas)
        if str(p.get("detalle", "")).strip():
            doc.encabezado("Detalle ejecutado", 2)
            doc.codigo(p["detalle"])

    doc.parrafo("Documento generado automáticamente a partir del linaje del dataset y de la "
                "ficha del modelo. Cada cifra sale de lo que quedó registrado al ejecutarse el "
                "proceso.", "Apagado")
    return doc.guardar(destino)
