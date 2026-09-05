"""Los endpoints de la bitácora, desde donde los llama la pestaña.

Se prueban por HTTP y no llamando al módulo: lo que rompe en producción no es
el cálculo —eso ya tiene sus pruebas— sino el contrato con la interfaz. Un
dataset que no existe tiene que contestar 404 con texto legible, no un 500
que en pantalla se ve como «error inesperado».
"""
from __future__ import annotations

import pytest
from app.core import etl


@pytest.fixture(scope="module")
def derivado(dataset_binary):
    plan = etl.propose(dataset_binary.id, target="objetivo")
    return etl.execute(dataset_binary.id, plan, name="binario · api")["dataset"]["id"]


def test_devuelve_la_bitacora_del_dataset(client, derivado):
    r = client.get("/api/bitacora", params={"dataset_id": derivado})

    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["pasos"] and cuerpo["pasos"][0]["etapa"] == "ingesta"
    assert cuerpo["resumen"]["n_pasos"] == len(cuerpo["pasos"])


def test_sin_dataset_ni_modelo_es_un_pedido_mal_hecho(client):
    r = client.get("/api/bitacora")

    assert r.status_code == 400
    assert "dataset" in r.json()["detail"].lower()


def test_dataset_inexistente_contesta_404_con_texto_legible(client):
    r = client.get("/api/bitacora", params={"dataset_id": "ds_inventado"})

    assert r.status_code == 404
    assert "ds_inventado" in r.json()["detail"]


@pytest.mark.parametrize("formato,extension", [("html", ".html"), ("docx", ".docx")])
def test_exporta_y_deja_el_archivo_listo_para_bajar(client, derivado, formato, extension):
    r = client.post("/api/bitacora/exportar",
                    json={"dataset_id": derivado, "formato": formato})

    assert r.status_code == 200, r.text
    info = r.json()
    assert info["filename"].endswith(extension)
    assert info["size_bytes"] > 0

    bajado = client.get(info["download_url"])
    assert bajado.status_code == 200
    assert len(bajado.content) == info["size_bytes"]


def test_el_html_exportado_se_baja_entero_y_es_html(client, derivado):
    info = client.post("/api/bitacora/exportar",
                       json={"dataset_id": derivado, "formato": "html"}).json()
    texto = client.get(info["download_url"]).content.decode("utf-8")

    assert texto.startswith("<!doctype html>")
    assert "En criollo" in texto


def test_un_formato_que_no_existe_se_rechaza_antes_de_generar_nada(client, derivado):
    r = client.post("/api/bitacora/exportar",
                    json={"dataset_id": derivado, "formato": "wordperfect"})

    assert r.status_code == 400
    assert "html" in r.json()["detail"].lower()


def test_el_pdf_se_explica_en_vez_de_fallar_en_silencio(client, derivado):
    """El PDF no lo genera el backend: sale de imprimir el HTML.

    Si alguien pide «pdf» a este endpoint, la respuesta tiene que decirle por
    dónde va, no contestar un 400 seco que parezca una función faltante.
    """
    r = client.post("/api/bitacora/exportar",
                    json={"dataset_id": derivado, "formato": "pdf"})

    assert r.status_code == 400
    assert "imprim" in r.json()["detail"].lower()


def test_la_descarga_no_alcanza_archivos_que_no_genero_la_bitacora(client):
    """El HTML se sirve con su tipo real, para poder imprimirlo y sacar el PDF.

    Un HTML servido desde el origen del backend corre con su mismo permiso.
    Por eso este endpoint sólo alcanza lo que escribió este módulo: si además
    entregara cualquier archivo de la carpeta de exportaciones, sería una
    puerta abierta a algo que el programa no generó.
    """
    from app.core import workspace

    intruso = workspace.dir_for("exports") / "ajeno.html"
    intruso.write_text("<script>fetch('/api/datasets')</script>", encoding="utf-8")

    assert client.get("/api/bitacora/descargar/ajeno.html").status_code == 404


def test_la_descarga_no_sale_de_la_carpeta_de_exportaciones(client):
    r = client.get("/api/bitacora/descargar/..%2F..%2Fmeta.json")

    assert r.status_code == 404
