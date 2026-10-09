"""Etapa 3: el revisor del catálogo dice qué contenido no va a llegar a nadie, o no a quien se pensó."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from app.core import catalogo as CAT

EJEMPLOS = Path(__file__).resolve().parents[2] / "examples"


def _c(**kw) -> dict:
    return {"id_contenido": "K1", "titulo": "t", "tipo": "concientizacion", "area_terapeutica": "", "producto": "",
            "condicion_venta": "", "audiencia": "publico", "paises": "*", **kw}


def _motivos(r: dict, cid: str = "K1") -> set[str]:
    h = r["hallazgos"]
    return {f"{n}: {m}" for n, m in zip(h.loc[h["id_contenido"] == cid, "nivel"],
                                         h.loc[h["id_contenido"] == cid, "motivo"], strict=True)}


def test_un_catalogo_bien_armado_queda_listo():
    r = CAT.revisar(pd.DataFrame([_c()]))
    assert r["listo"] and r["conteo"]["error"] == 0 and list(r["resumen"]["estado"]) == ["ok"]


def test_errores_de_estructura_se_informan_todos_juntos():
    r = CAT.revisar(pd.DataFrame([_c(id_contenido="A"), _c(id_contenido="A"), _c(id_contenido="B", tipo="spam"),
                                  _c(id_contenido="C", audiencia="marcianos")]))
    assert not r["listo"]
    txt = " ".join(r["hallazgos"]["motivo"])
    assert "repetido" in txt and "spam" in txt and "Audiencia desconocida" in txt
    assert r["resumen"].empty                       # ninguno quedó válido para revisar más


def test_reglas_de_contenido():
    casos = {
        "P": _c(id_contenido="P", tipo="programa_paciente", audiencia="paciente"),
        "M": _c(id_contenido="M", tipo="promocion_marca", producto="Vasotril", condicion_venta="receta",
                audiencia="todos"),
        "Z": _c(id_contenido="Z", producto="Vasotril", condicion_venta="receta"),
        "E": _c(id_contenido="E", tipo="educacion_medica", audiencia="pacientes"),
        "S": _c(id_contenido="S", tipo="promocion_marca", producto="Vitalix", condicion_venta=""),
        "X": _c(id_contenido="X", condicion_venta="magistral", producto="Algo"),
        "N": _c(id_contenido="N", paises="Narnia", titulo=""),
    }
    r = CAT.revisar(pd.DataFrame(casos.values()))
    assert any(m.startswith("error: Programa de pacientes sin producto") for m in _motivos(r, "P"))
    assert any("sólo les va a llegar a profesionales" in m for m in _motivos(r, "M"))
    assert any("Concientización que nombra un producto bajo receta" in m for m in _motivos(r, "Z"))
    assert any("Educación médica con audiencia de pacientes" in m for m in _motivos(r, "E"))
    assert any("no dice condición de venta" in m for m in _motivos(r, "S"))
    assert any("«magistral» desconocida" in m for m in _motivos(r, "X"))
    assert {"aviso: Sin título.", "info: País sin reglas propias: narnia. Se usan las genéricas."} <= _motivos(r, "N")
    estado = r["resumen"].set_index("id_contenido")["estado"]
    assert estado["P"] == "error" and estado["M"] == "aviso" and not r["listo"]


def test_el_alcance_con_la_base_de_ejemplo():
    co = pd.read_csv(EJEMPLOS / "relacionamiento_contenidos.csv")
    ct = pd.read_csv(EJEMPLOS / "relacionamiento_contactos.csv")
    r = CAT.revisar(co, ct)
    alc = r["resumen"].set_index("id_contenido")["alcance"]
    assert alc["K-14"] > alc["K-04"] > 0             # lo general llega a más que el programa
    assert alc["K-07"] > 0                            # la marca Rx llega, pero sólo a profesionales
    assert r["listo"]
