"""Ingeniería de datos: claves, tiempo, cruces y contrato.

Las cuatro respuestas de este módulo tienen algo en común: **se equivocan en
silencio**. Una clave mal propuesta, un cruce N:N que multiplica filas, un
«faltan 1.030 días» sobre un panel mensual o un `DECIMAL(18,4)` para un año no
levantan ninguna excepción — salen prolijos y están mal. Así que las pruebas
van justo a esos casos y no al camino feliz.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.core import ingenieria as I
from app.core import storage as S


def _cargar(df: pd.DataFrame, nombre: str, tmp_path) -> str:
    p = tmp_path / f"{nombre}.csv"
    df.to_csv(p, index=False)
    return S.ingest_file(p, name=nombre, source="prueba").id


# ─────────────────────────────────────────────────────────────────────────────
# Claves
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def ds_claves(tmp_path_factory) -> str:
    """Una tabla con una clave real y dos columnas que sólo parecen serlo."""
    n = 500
    rng = np.random.default_rng(3)
    df = pd.DataFrame({
        "IdOperacion": np.arange(1000, 1000 + n),          # la clave de verdad
        "MontoDeuda": rng.gamma(2, 5000, n).round(2),      # único por casualidad
        "Comentario": [f"nota libre distinta numero {i} con bastante texto" for i in range(n)],
        "IdCliente": rng.integers(1, 60, n),               # foránea
        "Sucursal": rng.choice(["Centro", "Norte", "Sur"], n),
        "Moneda": "UYU",                                    # constante
    })
    return _cargar(df, "claves", tmp_path_factory.mktemp("ing"))


def test_encuentra_la_clave_de_verdad(ds_claves):
    k = I.claves(ds_claves)
    assert [x["columna"] for x in k["pk_simple"]] == ["IdOperacion"]
    assert not k["sin_clave"]


def test_un_importe_que_no_repite_no_es_una_clave(ds_claves):
    """`MontoDeuda` no repite en 500 filas, pero nadie identifica una fila por
    lo que sale. Proponerlo sería ruido con apariencia de hallazgo."""
    k = I.claves(ds_claves)
    propuestas = [x["columna"] for x in k["pk_simple"] + k["pk_candidata"]]
    assert "MontoDeuda" not in propuestas


def test_un_texto_libre_tampoco_es_una_clave(ds_claves):
    """No repite porque cada uno escribió algo distinto, no porque identifique."""
    k = I.claves(ds_claves)
    propuestas = [x["columna"] for x in k["pk_simple"] + k["pk_candidata"]]
    assert "Comentario" not in propuestas


def test_marca_las_constantes_y_las_foraneas(ds_claves):
    k = I.claves(ds_claves)
    assert k["constantes"] == ["Moneda"]
    assert "IdCliente" in [f["columna"] for f in k["fk_candidatas"]]


def test_clave_compuesta_cuando_no_hay_simple(tmp_path):
    """Entidad + período: la forma más común de clave compuesta real."""
    filas = [{"IdCliente": c, "Periodo": p, "Saldo": float(c * p)}
             for c in range(1, 41) for p in range(1, 13)]
    ds = _cargar(pd.DataFrame(filas), "compuesta", tmp_path)
    k = I.claves(ds)
    assert not k["pk_simple"], "no debería haber clave simple"
    assert k["pk_compuesta"], "tendría que haber encontrado la compuesta"
    assert set(k["pk_compuesta"][0]["columnas"]) == {"IdCliente", "Periodo"}
    assert not k["sin_clave"]


def test_dice_que_no_hay_clave_cuando_no_la_hay(tmp_path):
    """Callarse sería peor: el que carga la tabla creería que está identificada."""
    df = pd.DataFrame({"categoria": ["a", "b"] * 50, "valor": [1.5, 2.5] * 50})
    k = I.claves(_cargar(df, "sinclave", tmp_path))
    assert k["sin_clave"]
    assert not k["pk_simple"] and not k["pk_compuesta"]


# ─────────────────────────────────────────────────────────────────────────────
# Tiempo
# ─────────────────────────────────────────────────────────────────────────────
def test_un_panel_mensual_no_es_un_dataset_roto(tmp_path):
    """El caso que arruina la confianza en la herramienta.

    Un panel con una fila por mes tiene, contado en días, el 97% del calendario
    vacío. Reportarlo como «faltan 1.030 días» es cierto y es inútil: parece
    una catástrofe cuando no falta nada.
    """
    meses = pd.date_range("2023-01-01", periods=36, freq="MS")
    df = pd.DataFrame({"FechaObs": np.repeat(meses, 5),
                       "Monto": np.arange(180, dtype=float)})
    t = I.tiempo(_cargar(df, "mensual", tmp_path))
    assert t["granularidad"] == "mensual"
    assert t["unidad"] == "meses"
    assert t["periodos_faltantes"] == 0
    assert t["cobertura_pct"] == 100.0


def test_un_hueco_de_verdad_en_datos_mensuales_se_ve(tmp_path):
    meses = [m for m in pd.date_range("2023-01-01", periods=12, freq="MS")
             if m.month not in (4, 5)]
    df = pd.DataFrame({"FechaObs": meses, "Monto": np.arange(len(meses), dtype=float)})
    t = I.tiempo(_cargar(df, "mensual_hueco", tmp_path))
    assert t["granularidad"] == "mensual"
    assert t["periodos_faltantes"] == 2
    assert any(h.startswith("2023-04") for h in t["huecos"])


def test_en_datos_diarios_los_huecos_se_cuentan_por_dia(tmp_path):
    dias = [d for d in pd.date_range("2024-01-01", periods=60, freq="D")
            if d.day not in (10, 11, 12)]
    df = pd.DataFrame({"Fecha": dias, "N": np.arange(len(dias), dtype=float)})
    t = I.tiempo(_cargar(df, "diario", tmp_path))
    assert t["granularidad"] == "diario"
    assert t["periodos_faltantes"] == 6      # días 10-12 de enero y de febrero


def test_avisa_de_fechas_futuras(tmp_path):
    """Casi siempre es zona horaria o un parseo mal hecho, no un dato real."""
    base = pd.Timestamp.now().normalize()
    fechas = list(pd.date_range(base - pd.Timedelta(days=90), periods=90, freq="D"))
    fechas += [base + pd.Timedelta(days=400)] * 3
    df = pd.DataFrame({"Fecha": fechas, "N": np.arange(len(fechas), dtype=float)})
    t = I.tiempo(_cargar(df, "futuras", tmp_path))
    assert t["fechas_futuras"] == 3


def test_mide_la_frescura(tmp_path):
    """Una carga que dejó de correr no da error: deja de traer filas nuevas."""
    fin = pd.Timestamp.now().normalize() - pd.Timedelta(days=200)
    df = pd.DataFrame({"Fecha": pd.date_range(fin - pd.Timedelta(days=100), fin, freq="D"),
                       "N": 1.0})
    t = I.tiempo(_cargar(df, "vieja", tmp_path))
    assert 198 <= t["frescura_dias"] <= 202


def test_sin_columna_de_fecha_devuelve_nada_en_vez_de_romperse(tmp_path):
    df = pd.DataFrame({"a": [1.0, 2.0] * 30, "b": list("xy") * 30})
    assert I.tiempo(_cargar(df, "sinfecha", tmp_path)) is None


@pytest.mark.parametrize(("serie", "esperado"), [
    ([10, 20, 30, 40, 50, 60], "creciente"),
    ([60, 50, 40, 30, 20, 10], "decreciente"),
    ([100, 101, 99, 100, 100, 101], "estable"),
    ([5, 5], None),                                  # muy pocos puntos
])
def test_la_tendencia_se_mide_contra_la_escala_de_la_serie(serie, esperado):
    """+3 por mes es ruido si el promedio son 50.000 y un cambio enorme si son 20."""
    assert I._tendencia(serie) == esperado


# ─────────────────────────────────────────────────────────────────────────────
# Cruces entre tablas
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def cruces(tmp_path_factory) -> dict:
    d = tmp_path_factory.mktemp("cruces")
    clientes = pd.DataFrame({"IdCliente": np.arange(1, 101),
                             "Nombre": [f"Cliente {i}" for i in range(1, 101)]})
    # 1:N — cada cliente con varias operaciones
    ops = pd.DataFrame({"IdCliente": np.repeat(np.arange(1, 101), 4),
                        "Monto": np.arange(400, dtype=float)})
    # N:N — la misma columna repetida de los dos lados
    etiquetas = pd.DataFrame({"IdCliente": np.repeat(np.arange(1, 51), 3),
                              "Etiqueta": ["a", "b", "c"] * 50})
    # misma columna, valores que no se pisan
    ajenos = pd.DataFrame({"IdCliente": np.arange(9000, 9100),
                           "Otro": np.arange(100, dtype=float)})
    return {
        "clientes": _cargar(clientes, "clientes", d),
        "ops": _cargar(ops, "operaciones", d),
        "etiquetas": _cargar(etiquetas, "etiquetas", d),
        "ajenos": _cargar(ajenos, "ajenos", d),
    }


def _par(sug, a: str, b: str):
    for s in sug:
        if {s["izquierda"], s["derecha"]} == {a, b}:
            return s
    return None


def test_detecta_el_cruce_uno_a_muchos(cruces):
    r = I.joins([cruces["clientes"], cruces["ops"]])
    s = _par(r["sugerencias"], "clientes", "operaciones")
    assert s is not None, "no encontró el cruce evidente"
    assert s["columna"] == "IdCliente"
    assert s["cardinalidad"] in ("1:N", "N:1")
    assert s["riesgo"] == "bajo"
    assert s["solape_pct"] == 100.0


def test_avisa_del_cruce_que_multiplica_filas(cruces):
    """N:N infla el resultado en silencio: es la forma más común de arruinar
    un número sin que salte ningún error."""
    r = I.joins([cruces["ops"], cruces["etiquetas"]])
    s = _par(r["sugerencias"], "operaciones", "etiquetas")
    assert s is not None
    assert s["cardinalidad"] == "N:N"
    assert s["riesgo"] == "alto"
    assert "multiplica" in s["aviso"]


def test_no_propone_cruces_por_coincidencia_de_nombre(cruces):
    """Dos columnas `IdCliente` sin un solo valor en común no son un cruce."""
    r = I.joins([cruces["clientes"], cruces["ajenos"]])
    assert _par(r["sugerencias"], "clientes", "ajenos") is None


def test_con_un_solo_dataset_lo_dice_en_vez_de_devolver_vacio(cruces):
    r = I.joins([cruces["clientes"]])
    assert r["sugerencias"] == []
    assert "dos datasets" in r.get("nota", "")


# ─────────────────────────────────────────────────────────────────────────────
# Contrato
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def ds_contrato(tmp_path_factory) -> str:
    n = 300
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        "IdMovimiento": np.arange(1, n + 1),
        "Año": 2024,
        "Mes": rng.integers(1, 13, n),
        "Importe": rng.gamma(2, 900, n).round(2),
        "Descripción": rng.choice(["alta", "baja", "ajuste"], n),
        "Fecha": pd.date_range("2024-01-01", periods=n, freq="D"),
    })
    return _cargar(df, "movimientos", tmp_path_factory.mktemp("contrato"))


def test_los_enteros_no_salen_como_decimales(ds_contrato):
    """La ingesta guarda todo número como `double`. Si el DDL se fiara del tipo
    declarado, un año quedaría DECIMAL(18,4) en el servidor destino."""
    c = I.contrato(ds_contrato, "sqlserver")
    tipos = {x["columna"]: x["tipo"] for x in c["diccionario"]}
    assert tipos["Año"] == "BIGINT"
    assert tipos["Mes"] == "BIGINT"
    assert tipos["Importe"].startswith("DECIMAL")


def test_los_acentos_se_transliteran_en_vez_de_borrarse(ds_contrato):
    """Borrándolos, `Año` queda `A_o`, que no lo reconoce nadie."""
    ddl = I.contrato(ds_contrato, "sqlserver")["ddl"]
    assert "[Ano]" in ddl
    assert "A_o" not in ddl
    assert "Descripcion" in ddl


def test_la_clave_encontrada_entra_en_el_ddl(ds_contrato):
    ddl = I.contrato(ds_contrato, "sqlserver")["ddl"]
    assert "PRIMARY KEY" in ddl and "IdMovimiento" in ddl


def test_el_ddl_generado_se_puede_ejecutar(ds_contrato):
    """La prueba de verdad de un DDL es que corra, no que se lea bien.

    Se ejecuta el dialecto DuckDB contra un motor real: una coma de más antes
    del `CONSTRAINT`, un tipo mal escrito o un nombre sin citar no se ven
    leyendo el texto y hacen fallar el pegado en el servidor del cliente.
    """
    import duckdb

    ddl = I.contrato(ds_contrato, "duckdb")["ddl"]
    con = duckdb.connect()
    try:
        con.execute(ddl)
        columnas = [r[0] for r in con.execute("DESCRIBE movimientos").fetchall()]
    finally:
        con.close()
    assert "IdMovimiento" in columnas


def test_las_verificaciones_generadas_se_pueden_ejecutar(ds_contrato):
    """Si no corren, el trabajo programado que las encadena falla la primera vez."""
    import duckdb

    co = I.contrato(ds_contrato, "duckdb")
    con = duckdb.connect()
    try:
        con.execute(co["ddl"])
        for v in co["verificaciones"]:
            con.execute(v["sql"])
    finally:
        con.close()


@pytest.mark.parametrize(("dialecto", "cita", "fecha"), [
    ("sqlserver", "[IdMovimiento]", "DATETIME2"),
    ("postgresql", '"IdMovimiento"', "TIMESTAMP"),
    ("mysql", "`IdMovimiento`", "DATETIME"),
])
def test_cada_motor_recibe_su_propia_sintaxis(ds_contrato, dialecto, cita, fecha):
    """Un DDL con la sintaxis de otro motor no se ejecuta: falla al pegarlo."""
    ddl = I.contrato(ds_contrato, dialecto)["ddl"]
    assert cita in ddl
    assert fecha in ddl


def test_un_dialecto_inventado_se_rechaza(ds_contrato):
    with pytest.raises(ValueError, match="Dialecto"):
        I.contrato(ds_contrato, "oracle-12")


def test_las_verificaciones_sirven_para_correrlas_solas(ds_contrato):
    """Cada una tiene que poder ir a un trabajo programado sin leerla."""
    v = I.contrato(ds_contrato, "sqlserver")["verificaciones"]
    nombres = [x["nombre"] for x in v]
    assert any("clave" in n.lower() for n in nombres)
    assert any("fresc" in n.lower() for n in nombres)
    assert any("futur" in n.lower() for n in nombres)
    for x in v:
        assert x["sql"].strip().upper().startswith("SELECT")
        assert x["por_que"], "cada verificación tiene que decir por qué importa"


def test_el_informe_completo_trae_todo_junto(ds_contrato):
    r = I.informe(ds_contrato, "postgresql")
    assert r["filas"] == 300
    assert r["claves"]["pk_simple"]
    assert r["tiempo"]["granularidad"] == "diario"
    assert r["contrato"]["dialecto_label"] == "PostgreSQL"
    assert r["calidad"]["score"] >= 0
