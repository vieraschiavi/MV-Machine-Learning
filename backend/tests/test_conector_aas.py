"""Azure Analysis Services (el MDW) como origen, y la extracción de varias tablas de una vez.

El conector real habla XMLA con el cliente ADOMD.NET de Microsoft (Windows) y
vive en la suite Adium All in One. Acá se prueba contra un doble con la misma
interfaz (`adium_allinone.analysis_services`): lo que importa es que AutoML le
pida lo correcto —sólo lectura, el modelo elegido, el tope de filas— y que el
resultado llegue al workspace como dataset.
"""
from __future__ import annotations

import sqlite3
import time

import pandas as pd
import pytest
from app.core import conector_aas as AASC
from app.core import connectors as C
from app.core import storage

SRV = "asazure://brazilsouth.asazure.windows.net/mdw"


class ASFalso:
    """El conector de la suite, sin Microsoft de por medio."""

    def __init__(self, modelos=("MDW Comercial", "MDW Finanzas"), falla_en=()):
        self.modelos = list(modelos)
        self.falla_en = set(falla_en)
        self.consultas: list[tuple[str, str, str]] = []
        self.cuentas: list[tuple] = []

    def librerias_faltantes(self):
        return []

    def usar_usuario(self, srv, usuario, clave):
        self.cuentas.append(("usuario", srv, usuario, bool(clave)))

    def usar_ventana(self, srv, si=True):
        self.cuentas.append(("ventana", srv, si))

    def listar_modelos(self, srv, token=""):
        return list(self.modelos)

    def tablas_del_modelo(self, srv, modelo, token=""):
        return ["Ventas", "Producto", "Calendario"]

    def consultar(self, srv, modelo, consulta, token=""):
        self.consultas.append((modelo, consulta, token))
        if any(f"'{t}'" in consulta for t in self.falla_en):
            raise RuntimeError("El usuario no tiene permiso de lectura sobre la tabla.")
        n = 3 if "TOPN(3," in consulta else 40
        return pd.DataFrame({"Producto": [f"P{i % 5}" for i in range(n)], "Unidades": range(n)})


@pytest.fixture
def falso(monkeypatch):
    f = ASFalso()
    monkeypatch.setattr(AASC, "motor", lambda AS=None: f)
    return f


def _perfil(**extra):
    p = {"id": "conn_aas", "engine": "aas", "host": SRV, "auth": "usuario",
         "username": "ana@empresa.com", "password": "secreta"}
    p.update(extra)
    return p


# ── sólo lectura ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("consulta", ["SELECT * FROM Ventas", "DROP TABLE x", "", "EVALUATE 'A'; EVALUATE 'B'",
                                      "DEFINE MEASURE x = 1"])
def test_solo_se_aceptan_evaluate(consulta):
    with pytest.raises(AASC.ErrorAAS):
        AASC.solo_lectura(consulta)


def test_el_tope_envuelve_en_topn_salvo_que_ya_tenga():
    assert AASC.con_tope("EVALUATE 'Ventas'", 50) == "EVALUATE TOPN(50, 'Ventas')"
    assert AASC.con_tope("evaluate topn(5, 'Ventas')", 50) == "evaluate topn(5, 'Ventas')"
    assert AASC.consulta_de_tabla("Ventas d'Or") == "EVALUATE 'Ventas d''Or'"
    definida = "DEFINE MEASURE 'Ventas'[x] = 1 EVALUATE ROW(\"x\", [x])"
    assert AASC.solo_lectura(definida) == definida and AASC.con_tope(definida, 50) == definida


# ── conexión ──────────────────────────────────────────────────────────────
def test_probar_conexion_lista_los_modelos(falso):
    r = C.test_connection(_perfil())
    assert r["ok"] is True and "2 modelo(s)" in r["version"] and "MDW Comercial" in r["version"]
    assert ("usuario", SRV, "ana@empresa.com", True) in falso.cuentas


@pytest.mark.parametrize("perfil,texto", [
    (_perfil(host="servidor-sql.empresa.com"), "asazure://"),
    (_perfil(password=""), "contraseña"),
    (_perfil(auth="token", password=""), "token"),
    (_perfil(auth="magia"), "desconocida"),
])
def test_probar_conexion_dice_que_falta(falso, perfil, texto):
    r = C.test_connection(perfil)
    assert r["ok"] is False and texto in r["error"]


def test_ventana_de_microsoft_no_pide_contrasena(falso):
    r = C.test_connection(_perfil(auth="ventana", username="", password=""))
    assert r["ok"] is True
    assert ("ventana", SRV, True) in falso.cuentas


def test_suelto_explica_que_hace_falta_la_suite(monkeypatch):
    import builtins
    real = builtins.__import__

    def sin_suite(name, *a, **k):
        if name.startswith("adium_allinone"):
            raise ImportError("no está la suite")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sin_suite)
    r = C.test_connection(_perfil())
    assert r["ok"] is False and "Adium All in One" in r["error"]


# ── explorar ──────────────────────────────────────────────────────────────
def test_los_modelos_son_los_esquemas_y_hay_que_elegir_uno(falso):
    r = C.list_tables(_perfil())
    assert r["schemas"] == ["MDW Comercial", "MDW Finanzas"] and r["schema"] is None and r["tables"] == []
    r = C.list_tables(_perfil(), "MDW Comercial")
    assert r["schema"] == "MDW Comercial"
    assert [t["name"] for t in r["tables"]] == ["Calendario", "Producto", "Ventas"]
    assert all(t["schema"] == "MDW Comercial" for t in r["tables"])


def test_con_un_solo_modelo_se_elige_solo(monkeypatch):
    f = ASFalso(modelos=["MDW"])
    monkeypatch.setattr(AASC, "motor", lambda AS=None: f)
    r = C.list_tables(_perfil())
    assert r["schema"] == "MDW" and len(r["tables"]) == 3


def test_vista_previa_usa_el_modelo_elegido_y_el_tope(falso):
    r = C.preview(_perfil(), "EVALUATE 'Ventas'", 3, "MDW Finanzas")
    assert r["n"] == 3 and r["columns"] == ["Producto", "Unidades"]
    assert falso.consultas[-1] == ("MDW Finanzas", "EVALUATE TOPN(3, 'Ventas')", "")


def test_vista_previa_sin_modelo_lo_pide(falso):
    with pytest.raises(C.ConnectionError_, match="Falta el modelo"):
        C.preview(_perfil(), "EVALUATE 'Ventas'", 3)


def test_el_token_viaja_solo_en_modo_token(falso):
    C.preview(_perfil(auth="token", password="eyJ.token"), "EVALUATE 'Ventas'", 3, "MDW")
    assert falso.consultas[-1][2] == "eyJ.token"
    C.preview(_perfil(), "EVALUATE 'Ventas'", 3, "MDW")
    assert falso.consultas[-1][2] == ""


# ── extraer ───────────────────────────────────────────────────────────────
def test_extraer_deja_un_dataset_de_analysis_services(falso):
    out = C.extract(_perfil(), "EVALUATE 'Ventas'", "Ventas MDW", schema="MDW Comercial")
    ds = out["dataset"]
    assert ds["rows"] == 40 and ds["source"] == "aas"
    assert storage.load_meta(ds["id"]).origin["database"] == "MDW Comercial"


def test_varias_tablas_de_una_vez_y_una_sin_permiso_no_frena_las_otras(monkeypatch):
    f = ASFalso(falla_en={"Calendario"})
    monkeypatch.setattr(AASC, "motor", lambda AS=None: f)
    tablas = [{"name": n, "schema": "MDW Comercial"} for n in ("Ventas", "Producto", "Calendario")]
    out = C.extract_many(_perfil(), tablas)
    assert [d["name"] for d in out["datasets"]] == ["Ventas", "Producto"]
    assert out["errors"][0]["table"] == "Calendario" and "permiso" in out["errors"][0]["error"]
    assert {c[1] for c in f.consultas} == {"EVALUATE 'Ventas'", "EVALUATE 'Producto'", "EVALUATE 'Calendario'"}


def test_si_ninguna_tabla_sale_es_un_error(monkeypatch):
    f = ASFalso(falla_en={"Ventas"})
    monkeypatch.setattr(AASC, "motor", lambda AS=None: f)
    with pytest.raises(C.ConnectionError_, match="ninguna tabla"):
        C.extract_many(_perfil(), [{"name": "Ventas", "schema": "MDW"}])
    with pytest.raises(C.ConnectionError_, match="al menos una"):
        C.extract_many(_perfil(), [])


def test_el_perfil_guarda_como_entrar_sin_devolver_la_clave():
    pub = C.save_profile(_perfil(id=None, label="MDW"))
    assert pub["auth"] == "usuario" and pub["has_password"] is True and "password" not in pub
    C.delete_profile(pub["id"])


# ── por la API, contra SQLite: varias tablas del mismo servidor ───────────
def _esperar(client, job_id, timeout=120):
    limite = time.time() + timeout
    while time.time() < limite:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("terminado", "error", "cancelado"):
            return job
        time.sleep(0.2)
    raise AssertionError("el trabajo no terminó")


def test_api_extrae_varias_tablas_sql_un_dataset_por_tabla(client, tmp_root):
    ruta = tmp_root / "varias.db"
    con = sqlite3.connect(ruta)
    pd.DataFrame({"id": range(30), "monto": range(30)}).to_sql("ventas", con, index=False, if_exists="replace")
    pd.DataFrame({"id": range(7), "nombre": list("abcdefg")}).to_sql("clientes", con, index=False,
                                                                      if_exists="replace")
    con.close()
    pid = client.post("/api/connections/save", json={"engine": "sqlite", "database": str(ruta),
                                                       "label": "varias"}).json()["connection"]["id"]
    r = client.post(f"/api/connections/{pid}/extract-many",
                    json={"tables": [{"name": "ventas"}, {"name": "clientes"}]})
    assert r.status_code == 200, r.text
    job = _esperar(client, r.json()["id"])
    assert job["status"] == "terminado", job
    res = job["result"]
    assert [(d["name"], d["rows"]) for d in res["datasets"]] == [("ventas", 30), ("clientes", 7)]
    assert client.get("/api/datasets/active").json()["dataset"]["id"] == res["datasets"][0]["id"]
    assert client.post(f"/api/connections/{pid}/extract-many", json={"tables": []}).status_code == 400


def test_capacidades_ofrecen_analysis_services(client):
    ids = {e["id"] for e in client.get("/api/capabilities").json()["sql_engines"]}
    assert "aas" in ids
