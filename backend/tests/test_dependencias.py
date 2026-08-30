"""Avisos de las librerías que hoy no molestan y mañana cortan una función.

`import shap` es lo único que separa al informe de tener explicaciones o no
tenerlas. SHAP arma su paleta mutando un colormap con `set_bad`, `set_over` y
`set_under`, y matplotlib está deprecando justamente eso: hoy avisa, y el día
que el aviso pase a error el import falla entero y el cliente entrena un modelo
que ya no le explica nada.

No se puede arreglar de este lado —el código está adentro de `shap`— y clavar
un techo de versión a matplotlib deja el problema para el que venga después,
además de bloquear parches de seguridad. Lo que sí se puede es enterarse a
tiempo: esta prueba simula el futuro y falla cuando llegue, con margen para
subir la versión de SHAP que lo corrija.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

shap = pytest.importorskip("shap", reason="SHAP es opcional en el entorno de pruebas")


def _importa_con(filtro: str) -> subprocess.CompletedProcess:
    """Importa SHAP en un proceso limpio con ese filtro de avisos.

    En un proceso aparte porque el aviso lo emite el módulo al cargarse: una vez
    importado acá, nada lo vuelve a emitir.
    """
    return subprocess.run([sys.executable, "-W", filtro, "-c", "import shap"],
                          capture_output=True, text=True, timeout=300)


def test_shap_importa_con_las_deprecaciones_vigentes_como_error():
    """El estado normal: los avisos ya deprecados no rompen el import."""
    r = _importa_con("error::DeprecationWarning")
    assert r.returncode == 0, (
        "SHAP dejó de importar con las deprecaciones vigentes tratadas como "
        f"error. Sin SHAP no hay explicación de variables:\n{r.stderr[-800:]}")


def test_aviso_temprano_si_matplotlib_deja_de_tolerar_la_paleta_de_shap():
    """El futuro, simulado: cuando `set_bad` deje de ser un aviso pendiente.

    Si esta prueba falla es una buena noticia dada a tiempo — todavía no rompió
    a nadie. Qué hacer: subir SHAP a la versión que ya no mute el colormap
    (`cmap.with_extremes(...)`) y, si esa versión no existe todavía, fijar
    `matplotlib` por debajo del corte hasta que salga.
    """
    r = _importa_con("error::PendingDeprecationWarning")
    if r.returncode != 0 and "with_extremes" in r.stderr:
        pytest.xfail("SHAP todavía muta su colormap; matplotlib lo avisa como "
                     "pendiente. Rompe recién cuando pase a error de verdad.")
    assert r.returncode == 0, r.stderr[-800:]
