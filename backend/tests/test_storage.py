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


# ── fechas escritas como texto ────────────────────────────────────────────────
def _tipos(meta) -> dict[str, str]:
    return {c["name"]: c["arrow_type"].lower() for c in meta.columns}


def _ingestar(tmp_root, nombre: str, texto: str):
    ruta = tmp_root / f"{nombre}.csv"
    ruta.write_text(texto, encoding="utf-8")
    return storage.ingest_file(ruta, nombre)


def test_una_fecha_iso_en_csv_llega_tipada(tmp_root):
    """Un CSV no trae tipos. Si la fecha se guarda como texto, el dataset queda
    sin ninguna columna temporal: sin cobertura, sin frescura y con VARCHAR
    donde va una fecha, aunque el archivo esté lleno de fechas."""
    filas = "\n".join(f"2024-0{m}-15,{m * 10}" for m in range(1, 8))
    meta = _ingestar(tmp_root, "iso", f"fecha,monto\n{filas}\n")
    assert "timestamp" in _tipos(meta)["fecha"]
    df = storage.query(meta.id, "SELECT min(fecha) AS d FROM {t}")
    assert str(df["d"].iloc[0])[:10] == "2024-01-15"


def test_el_dia_va_primero_cuando_los_datos_lo_prueban(tmp_root):
    """`25/12/2024` no puede ser el mes 25. Leerlo al revés no falla: corre el
    dato once meses y nadie se entera hasta que el informe mensual no cierra."""
    filas = "\n".join(["25/12/2024,1", "13/11/2024,2", "01/03/2024,3", "07/07/2024,4"])
    meta = _ingestar(tmp_root, "diaprimero", f"fecha,n\n{filas}\n")
    assert "timestamp" in _tipos(meta)["fecha"]
    df = storage.query(meta.id, "SELECT max(fecha) AS d FROM {t}")
    assert str(df["d"].iloc[0])[:10] == "2024-12-25"


def test_con_todo_ambiguo_manda_la_convencion_del_archivo(tmp_root):
    """Puras fechas del 1 al 12: ningún valor prueba el orden. La coma decimal
    delata la configuración regional, que escribe dd/mm/aaaa."""
    filas = "\n".join(["03/01/2024;1,5", "05/02/2024;2,5", "07/03/2024;3,5"])
    meta = _ingestar(tmp_root, "ambiguo", f"fecha;monto\n{filas}\n")
    assert "timestamp" in _tipos(meta)["fecha"]
    df = storage.query(meta.id, "SELECT min(fecha) AS d FROM {t}")
    assert str(df["d"].iloc[0])[:10] == "2024-01-03"


def test_un_codigo_con_guiones_no_se_convierte_en_fecha(tmp_root):
    """El daño de un falso positivo es peor que el de no detectar: la columna
    se llenaría de nulos y el código original se perdería."""
    filas = "\n".join(["1.234-5,a", "9.876-1,b", "4.567-3,c", "2.345-9,d"])
    meta = _ingestar(tmp_root, "codigos", f"codigo,letra\n{filas}\n")
    assert "string" in _tipos(meta)["codigo"]


def test_la_decision_de_fecha_es_la_misma_en_todos_los_bloques(tmp_root):
    """Si cada bloque decidiera por su cuenta, uno escribiría marca de tiempo y
    el otro texto sobre la misma columna, y el Parquet quedaría inconsistente.
    Se cargan más filas que el tamaño de bloque justo para pasar por ahí."""
    from app.config import settings

    n = settings.chunk_rows * 2 + 17
    filas = "\n".join(f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d},{i}" for i in range(n))
    meta = _ingestar(tmp_root, "bloques_fecha", f"fecha,n\n{filas}\n")
    assert len(list(storage.dataset_path(meta.id).glob("part-*.parquet"))) > 1
    assert "timestamp" in _tipos(meta)["fecha"]
    df = storage.query(meta.id, "SELECT count(fecha) AS c FROM {t}")
    assert int(df["c"].iloc[0]) == n
