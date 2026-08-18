"""Ingesta y consulta de datasets."""
from __future__ import annotations

import pytest
from app.core import storage


def test_ingesta_csv_detecta_separador_y_decimal(dataset_binary, frame_binary):
    assert dataset_binary.rows == len(frame_binary)
    assert dataset_binary.origin["sep"] == ";"
    assert dataset_binary.origin["decimal"] == ","
    nombres = [c["name"] for c in dataset_binary.columns]
    assert nombres == list(frame_binary.columns)


def test_ingesta_por_bloques_conserva_todas_las_filas(tmp_root, frame_binary):
    """El tamaño de bloque es menor que el dataset: se ejercita el camino de varios Parquet."""
    path = tmp_root / "bloques.csv"
    frame_binary.to_csv(path, index=False)
    meta = storage.ingest_file(path, "bloques")
    assert meta.rows == len(frame_binary)
    folder = storage.dataset_path(meta.id)
    assert len(list(folder.glob("part-*.parquet"))) >= 1
    df = storage.query(meta.id, "SELECT count(*) n FROM {t}")
    assert int(df["n"].iloc[0]) == len(frame_binary)


def test_ingesta_excel(tmp_root, frame_binary):
    path = tmp_root / "hoja.xlsx"
    frame_binary.head(300).to_excel(path, index=False)
    meta = storage.ingest_file(path, "excel")
    assert meta.rows == 300
    assert len(meta.columns) == frame_binary.shape[1]


def test_ingesta_parquet(tmp_root, frame_binary):
    path = tmp_root / "datos.parquet"
    frame_binary.head(400).to_parquet(path, index=False)
    meta = storage.ingest_file(path, "parquet")
    assert meta.rows == 400


def test_extension_no_soportada_da_error_claro(tmp_root):
    path = tmp_root / "archivo.docx"
    path.write_bytes(b"contenido")
    with pytest.raises(storage.IngestError) as exc:
        storage.ingest_file(path, "malo")
    assert "no soportada" in str(exc.value).lower()


def test_identificador_invalido_se_rechaza():
    with pytest.raises(storage.IngestError):
        storage.dataset_path("../../etc/passwd")


def test_load_frame_muestrea_cuando_supera_el_maximo(dataset_binary):
    df = storage.load_frame(dataset_binary.id, max_rows=100)
    assert 0 < len(df) <= dataset_binary.rows
    completo = storage.load_frame(dataset_binary.id)
    assert len(completo) == dataset_binary.rows


def test_head_y_preview(dataset_binary):
    df = storage.head(dataset_binary.id, 5)
    assert len(df) == 5


def test_ingest_frames_desde_iterador(frame_regression):
    meta = storage.ingest_frames(iter([frame_regression.head(100), frame_regression.tail(100)]),
                                 "por partes", source="derived")
    assert meta.rows == 200


def test_borrado(tmp_root, frame_regression):
    path = tmp_root / "borrable.csv"
    frame_regression.to_csv(path, index=False)
    meta = storage.ingest_file(path, "borrable")
    storage.delete_dataset(meta.id)
    with pytest.raises(storage.IngestError):
        storage.load_meta(meta.id)
