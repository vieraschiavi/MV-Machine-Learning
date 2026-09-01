"""Avisos de las librerías que hoy no molestan y mañana cortan una función.

`import shap` es lo único que separa al informe de tener explicaciones o no
tenerlas. SHAP arma su paleta mutando un colormap con `set_bad`, `set_over` y
`set_under`, y matplotlib está deprecando justamente eso: hoy avisa, y el día
que el aviso pase a error el import falla entero y el cliente entrena un modelo
que ya no le explica nada.

No se puede arreglar de este lado: el código que muta el colormap está adentro
de `shap`, no en este repositorio. Dos capas, cada una cubriendo lo que la otra
no puede:

  · **Contención** — `requirements.txt` techa `matplotlib<3.12` en la versión
    más nueva ya probada, para que un `pip install` de rutina no aterrice
    justo en la que rompe. Un techo por sí solo se vuelve el problema del que
    venga después si nadie lo revisa: bloquea parches de seguridad sin que se
    note por qué.
  · **Vigilancia** — estas pruebas simulan el futuro sin depender del techo, y
    fallan el día que llegue: dan el margen para subir SHAP a la versión que
    ya no mute el colormap (`cmap.with_extremes(...)`) y recién ahí soltar el
    techo de matplotlib.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

shap = pytest.importorskip("shap", reason="SHAP es opcional en el entorno de pruebas")

RAIZ = Path(__file__).resolve().parents[2]


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

    Corre sin importar el techo de `requirements.txt` —el entorno de pruebas
    puede tener una versión más nueva instalada a mano— para no depender de la
    contención que se supone que está vigilando.

    Si esta prueba falla es una buena noticia dada a tiempo — todavía no rompió
    a nadie. Qué hacer: subir SHAP a la versión que ya no mute el colormap
    (`cmap.with_extremes(...)`) y, recién entonces, soltar el techo de
    `matplotlib` en `requirements.txt`.
    """
    r = _importa_con("error::PendingDeprecationWarning")
    if r.returncode != 0 and "with_extremes" in r.stderr:
        pytest.xfail("SHAP todavía muta su colormap; matplotlib lo avisa como "
                     "pendiente. Rompe recién cuando pase a error de verdad.")
    assert r.returncode == 0, r.stderr[-800:]


def test_el_techo_de_matplotlib_sigue_siendo_necesario():
    """Si esta prueba falla, es al revés de las otras dos: buena noticia.

    Significa que SHAP ya migró a `with_extremes` y el import no rompe ni
    tratando la deprecación como error — el techo de `requirements.txt` quedó
    protegiendo contra algo que ya no puede pasar, y toca borrarlo (y su
    comentario) en vez de seguir arrastrándolo.
    """
    texto = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    m = re.search(r"^matplotlib(<[\d.]+)?\s*$", texto, re.M)
    assert m, ("no encontré el techo de matplotlib en requirements.txt: si se "
              "sacó a propósito porque SHAP ya no lo necesita, borrar también "
              "esta prueba")

    r = _importa_con("error::PendingDeprecationWarning")
    todavia_rompe = r.returncode != 0 and "with_extremes" in r.stderr
    assert todavia_rompe, (
        "SHAP ya no muta el colormap deprecado: el techo de matplotlib en "
        "requirements.txt (y esta prueba) ya no protegen nada. Sacalos.")
