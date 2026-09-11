"""Que la CI no queme la cuota de Actions sin que nadie lo haya decidido.

El repositorio es privado, así que cada minuto de runner se descuenta de una
cuota mensual, y los runners de Windows cuentan **el doble**. Dos descuidos de
configuración la agotaron, y con ella se fue la capacidad de compilar y
entregar el producto: durante tres días hubo código correcto en `main` que
ningún cliente podía tocar.

Los dos descuidos, medidos:

  1. **`ci.yml` disparaba en `push` a todas las ramas Y en `pull_request`.**
     Cada push a una rama con PR abierto corría la suite completa DOS VECES,
     sobre el mismo commit. Verificado sobre `7f00bb0`: los runs 34543134661
     (push) y 34543137404 (pull_request), idénticos. Eso es la mitad de la
     cuota tirada.

  2. **El build de escritorio disparaba en cada push a `main`.** Son unos 20
     minutos en un runner de Windows, o sea ~40 minutos de cuota, cada vez que
     se mergea algo — aunque el merge no toque el instalador.

Lo que NO se toca, y es a propósito: la suite sigue corriendo entera en cada
PR, en los tres entornos. Ahorrar cuota apagando pruebas sería cambiar un
problema por otro peor.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOWS = RAIZ / ".github" / "workflows"


def _disparadores(archivo: str) -> dict:
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load((WORKFLOWS / archivo).read_text(encoding="utf-8"))
    # PyYAML lee la clave `on:` como el booleano True.
    return d.get(True, d.get("on", {})) or {}


def test_la_ci_no_corre_dos_veces_sobre_el_mismo_commit():
    """`push` a todas las ramas + `pull_request` = la suite dos veces.

    Con el PR abierto, cada push dispara un run por el push y otro por el PR,
    sobre el mismo commit y con el mismo resultado. La cobertura no mejora: lo
    único que cambia es que la cuota dura la mitad.

    El `push` queda acotado a `main` —para saber el estado de la rama que se
    entrega— y las ramas de trabajo las cubre el disparador de `pull_request`.
    """
    on = _disparadores("ci.yml")

    assert "pull_request" in on, "sin esto, los PR dejarían de verificarse"
    ramas = (on.get("push") or {}).get("branches", [])
    assert "**" not in ramas, (
        "ci.yml corre en push a TODAS las ramas y además en pull_request: "
        "cada push con PR abierto gasta la suite dos veces")
    assert "main" in ramas, "conviene saber el estado de main después de cada merge"


def test_el_build_de_escritorio_no_se_dispara_en_cada_merge():
    """Veinte minutos de runner Windows —cuarenta de cuota— por cada merge,
    toque o no el instalador.

    Queda por etiqueta y a pedido: sacar un instalador pasa a ser una decisión,
    que es lo que siempre fue en la práctica.
    """
    on = _disparadores("desktop.yml")

    assert "workflow_dispatch" in on, (
        "sin esto no habría forma de pedir un instalador cuando se lo necesita")
    ramas = (on.get("push") or {}).get("branches", [])
    assert "main" not in ramas, (
        "el build de escritorio se dispara en cada push a main: son ~40 "
        "minutos de cuota por merge, aunque el merge no toque el instalador")
    assert (on.get("push") or {}).get("tags"), (
        "se perdió el disparo por etiqueta, que es como se marca una versión")


def test_la_suite_sigue_corriendo_entera_en_cada_pr():
    """El límite del ahorro: no se apaga ninguna prueba ni ningún entorno.

    Ahorrar cuota recortando cobertura sería cambiar un problema por otro peor
    —y este repositorio ya publicó un instalador que no instalaba justamente
    por confiar en una verificación que no verificaba—.
    """
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))

    matriz = d["jobs"]["backend"]["strategy"]["matrix"]["include"]
    sistemas = {m["so"] for m in matriz}
    assert "ubuntu-latest" in sistemas and "windows-latest" in sistemas, (
        "se perdió un sistema operativo de la matriz")
    assert len(matriz) >= 3, f"la matriz se recortó a {len(matriz)} entradas"
    assert set(d["jobs"]) >= {"backend", "frontend", "lint"}, (
        "se apagó un job entero de la CI")
