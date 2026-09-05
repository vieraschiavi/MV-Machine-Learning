"""Un escritor de .docx mínimo, con la biblioteca estándar y nada más.

Un .docx es un ZIP con unos pocos XML adentro. Escribirlo a mano es más
trabajo que usar una biblioteca, y aun así conviene: el producto se entrega
como un .exe congelado que ya pesa más de lo que debería, y sumarle una
dependencia con binarios propios (lxml) por un documento de texto es pagar
peso y riesgo de empaquetado por algo que entra en un archivo.

Lo que sí se paga es rigor: si el XML sale mal, Word abre el cartel de
«archivo dañado» y no dice por qué. Por eso `test_bitacora_documento.py`
abre lo generado con un lector de Word real, que rechaza lo que esté mal
formado.

Alcance deliberado: títulos, párrafos, tablas de dos columnas y bloques de
código. Nada de imágenes, encabezados de página ni numeración automática. Si
alguna vez hace falta eso, es el momento de discutir la dependencia, no de
estirar este archivo.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _estilo(sid: str, nombre: str, tamano: int, *, negrita: bool = False,
            color: str = "1F2430", espacio: int = 120, mono: bool = False) -> str:
    fuente = "Consolas" if mono else "Calibri"
    return (
        f'<w:style w:type="paragraph" w:styleId="{sid}">'
        f'<w:name w:val="{nombre}"/><w:qFormat/>'
        f'<w:pPr><w:spacing w:before="{espacio}" w:after="{espacio}"/></w:pPr>'
        f'<w:rPr><w:rFonts w:ascii="{fuente}" w:hAnsi="{fuente}"/>'
        f'<w:sz w:val="{tamano * 2}"/><w:color w:val="{color}"/>'
        + ('<w:b/>' if negrita else '') +
        '</w:rPr></w:style>'
    )


STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:styles xmlns:w="{W}">'
    + _estilo("Normal", "Normal", 11, espacio=60)
    + _estilo("Title", "Title", 24, negrita=True, espacio=240)
    + _estilo("Heading1", "heading 1", 16, negrita=True, color="0B5FFF", espacio=200)
    + _estilo("Heading2", "heading 2", 12, negrita=True, espacio=140)
    + _estilo("Apagado", "Apagado", 10, color="5B6472", espacio=40)
    + _estilo("Codigo", "Codigo", 9, color="1F2430", espacio=60, mono=True)
    + '</w:styles>'
)


def _core(titulo: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:title>{escape(titulo)}</dc:title>'
        '<dc:creator>MV AutoML Studio</dc:creator>'
        '</cp:coreProperties>'
    )


BORDE = ('<w:tblBorders>' + "".join(
    f'<w:{lado} w:val="single" w:sz="4" w:space="0" w:color="D8DDE6"/>'
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>')


class Documento:
    """Acumula bloques y los escribe como un .docx al guardar."""

    def __init__(self, titulo: str = "Documento") -> None:
        self._titulo = titulo
        self._cuerpo: list[str] = []

    # ── bloques ──────────────────────────────────────────────────────────────
    def parrafo(self, texto: str, estilo: str = "Normal") -> Documento:
        self._cuerpo.append(
            f'<w:p><w:pPr><w:pStyle w:val="{estilo}"/></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{escape(str(texto))}</w:t></w:r></w:p>')
        return self

    def titulo(self, texto: str) -> Documento:
        return self.parrafo(texto, "Title")

    def encabezado(self, texto: str, nivel: int = 1) -> Documento:
        return self.parrafo(texto, "Heading1" if nivel == 1 else "Heading2")

    def apagado(self, texto: str) -> Documento:
        return self.parrafo(texto, "Apagado")

    def etiquetado(self, etiqueta: str, texto: str) -> Documento:
        """Un párrafo que empieza con una palabra en negrita: «Por qué: …»."""
        self._cuerpo.append(
            '<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
            f'<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">{escape(etiqueta)}: </w:t></w:r>'
            f'<w:r><w:t xml:space="preserve">{escape(str(texto))}</w:t></w:r></w:p>')
        return self

    def codigo(self, texto: str) -> Documento:
        for linea in str(texto).splitlines() or [""]:
            self.parrafo(linea, "Codigo")
        return self

    def tabla(self, filas: list[tuple[str, str]]) -> Documento:
        if not filas:
            return self
        celdas = []
        for clave, valor in filas:
            celdas.append(
                '<w:tr>' + self._celda(clave, 3200, negrita=True)
                + self._celda(valor, 5800) + '</w:tr>')
        self._cuerpo.append(
            '<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/>'
            + BORDE + '</w:tblPr>' + "".join(celdas) + '</w:tbl>'
            + '<w:p><w:pPr><w:pStyle w:val="Apagado"/></w:pPr></w:p>')
        return self

    def salto_de_pagina(self) -> Documento:
        self._cuerpo.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
        return self

    @staticmethod
    def _celda(texto: str, ancho: int, negrita: bool = False) -> str:
        rpr = '<w:rPr><w:b/><w:sz w:val="20"/></w:rPr>' if negrita else '<w:rPr><w:sz w:val="20"/></w:rPr>'
        return (f'<w:tc><w:tcPr><w:tcW w:w="{ancho}" w:type="dxa"/></w:tcPr>'
                '<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr>'
                f'<w:r>{rpr}<w:t xml:space="preserve">{escape(str(texto))}</w:t></w:r></w:p></w:tc>')

    # ── salida ───────────────────────────────────────────────────────────────
    def xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W}"><w:body>'
            + "".join(self._cuerpo)
            + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
              '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
              '</w:sectPr></w:body></w:document>'
        )

    def guardar(self, destino: str | Path) -> Path:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", RELS)
            z.writestr("docProps/core.xml", _core(self._titulo))
            z.writestr("word/_rels/document.xml.rels", DOC_RELS)
            z.writestr("word/styles.xml", STYLES)
            z.writestr("word/document.xml", self.xml())
        return destino
