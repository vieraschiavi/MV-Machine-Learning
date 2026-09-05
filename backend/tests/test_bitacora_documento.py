"""La bitácora, convertida en un documento que se puede mandar por correo.

Tres formatos, tres motivos: HTML para leerla en pantalla y archivarla, Word
para que el gerente la edite y le agregue su párrafo, y PDF para adjuntarla a
un expediente. El PDF sale de imprimir este mismo HTML —el escritorio lo hace
solo—, así que lo que hay que garantizar acá es el HTML y el .docx.

Lo que fijan estas pruebas:

  * El HTML es **una sola pieza**: sin hojas de estilo ni tipografías traídas
    de internet. El programa corre en máquinas sin salida a internet y el
    archivo se guarda para leerlo dentro de dos años.
  * El HTML **escapa** lo que viene de los datos. El nombre de un dataset lo
    escribe el usuario, y un nombre con `<script>` no puede volverse código.
  * El .docx es un **OOXML válido de verdad**: no alcanza con que sea un zip
    con nombres bonitos, tiene que abrirlo un lector de Word. La prueba lo
    abre con `python-docx`, que es exigente con la estructura.
"""
from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree as ET

import pytest
from app.core import bitacora, documento, etl


@pytest.fixture(scope="module")
def libro(dataset_binary):
    plan = etl.propose(dataset_binary.id, target="objetivo")
    out = etl.execute(dataset_binary.id, plan, name="binario · doc")
    return bitacora.construir(dataset_id=out["dataset"]["id"])


# ══════════════════════════════════════════════════════════════════ HTML ══════
def test_el_html_no_pide_nada_a_internet(libro):
    """En una máquina sin red, un HTML con CDN se ve roto y sin explicación."""
    html = documento.a_html(libro)

    externos = re.findall(r'(?:src|href)\s*=\s*"(https?://[^"]+)"', html)
    assert not externos, f"el documento depende de {externos}"


def test_el_html_trae_su_propio_estilo_y_sabe_imprimirse(libro):
    html = documento.a_html(libro)

    assert "<style" in html, "sin estilo propio queda ilegible fuera del programa"
    assert "@media print" in html, "el PDF sale de imprimir esto: necesita reglas de impresión"


def test_el_html_respeta_el_orden_de_los_pasos(libro):
    """Si el documento reordena, deja de contar la historia que contaba."""
    html = documento.a_html(libro)
    posiciones = [html.index(p["titulo"]) for p in libro["pasos"]]

    assert posiciones == sorted(posiciones)


def test_el_html_trae_las_dos_lecturas_de_cada_paso(libro):
    html = documento.a_html(libro)

    for p in libro["pasos"]:
        assert p["tecnico"][:40] in html, f"falta la lectura técnica del paso {p['orden']}"
        assert p["criollo"][:40] in html, f"falta la lectura criolla del paso {p['orden']}"


def test_el_html_escapa_lo_que_escribio_el_usuario(libro):
    """El nombre del dataset lo pone una persona; no puede volverse código."""
    envenenado = dict(libro, titulo='Bitácora <script>alert("x")</script>')
    html = documento.a_html(envenenado)

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_el_html_dice_de_donde_salio_cada_numero(libro):
    """Sin la evidencia, el documento es una opinión bien escrita."""
    html = documento.a_html(libro)
    alguna = libro["pasos"][0]["evidencia"][0]

    assert alguna["clave"] in html
    assert alguna["valor"] in html


# ══════════════════════════════════════════════════════════════════ Word ══════
PARTES = ["[Content_Types].xml", "_rels/.rels", "word/document.xml",
          "word/_rels/document.xml.rels", "word/styles.xml"]


def test_el_docx_tiene_las_partes_obligatorias(libro, tmp_path):
    destino = documento.a_docx(libro, tmp_path / "b.docx")

    with zipfile.ZipFile(destino) as z:
        faltan = [p for p in PARTES if p not in z.namelist()]
    assert not faltan, f"partes que Word exige y no están: {faltan}"


def test_todos_los_xml_del_docx_parsean(libro, tmp_path):
    """Un XML mal armado abre el diálogo «el archivo está dañado»."""
    destino = documento.a_docx(libro, tmp_path / "b.docx")

    with zipfile.ZipFile(destino) as z:
        for nombre in [n for n in z.namelist() if n.endswith(".xml") or n.endswith(".rels")]:
            ET.fromstring(z.read(nombre))          # revienta si está mal formado


def test_word_de_verdad_puede_abrir_el_documento(libro, tmp_path):
    """La prueba que importa: que un lector real lo lea, no que el zip exista.

    `python-docx` es dependencia de las pruebas, no del producto: el .docx se
    escribe con la biblioteca estándar para no sumarle peso al instalador.
    """
    docx = pytest.importorskip("docx", reason="python-docx sólo se usa para validar")
    destino = documento.a_docx(libro, tmp_path / "b.docx")

    doc = docx.Document(str(destino))
    texto = "\n".join(p.text for p in doc.paragraphs)

    assert libro["titulo"] in texto
    for p in libro["pasos"]:
        assert p["titulo"] in texto, f"el paso {p['orden']} no llegó al documento"


def test_el_docx_conserva_las_dos_lecturas_y_la_evidencia(libro, tmp_path):
    docx = pytest.importorskip("docx")
    destino = documento.a_docx(libro, tmp_path / "b.docx")

    doc = docx.Document(str(destino))
    texto = "\n".join(p.text for p in doc.paragraphs)
    texto += "\n" + "\n".join(c.text for t in doc.tables for f in t.rows for c in f.cells)

    primero = libro["pasos"][0]
    assert primero["tecnico"][:40] in texto
    assert primero["criollo"][:40] in texto
    assert primero["evidencia"][0]["clave"] in texto


def test_el_docx_escapa_los_caracteres_que_rompen_el_xml(tmp_path):
    """Un «&» sin escapar en un nombre de columna basta para dañar el archivo."""
    docx = pytest.importorskip("docx")
    libro = {
        "titulo": "Bitácora & compañía <ventas>",
        "generado_en": 0, "dataset": None, "modelo": None,
        "resumen": {"n_pasos": 1, "etapas": ["ingesta"], "filas_inicio": 1, "filas_fin": 1,
                    "columnas_inicio": 1, "columnas_fin": 1, "transformaciones": 0},
        "pasos": [{"orden": 1, "etapa": "ingesta", "titulo": "Lectura de «A & B»",
                   "tecnico": "TRY_CAST(x AS DOUBLE) donde a < b & c > d",
                   "criollo": "Se leyó el archivo <original>",
                   "porque": "porque sí & porque no", "impacto": "ninguno",
                   "evidencia": [{"clave": "A & B", "valor": "<1>"}], "ops": []}],
    }

    doc = docx.Document(str(documento.a_docx(libro, tmp_path / "raro.docx")))
    texto = "\n".join(p.text for p in doc.paragraphs)

    assert "Bitácora & compañía <ventas>" in texto
    assert "a < b & c > d" in texto
