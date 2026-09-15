"""Conector a Microsoft Fabric: endpoint SQL con autenticación de Entra ID.

Lo que se prueba acá es lo que se puede probar sin un tenant: cómo queda la
URL de conexión, que el secreto no salga del servidor, que el recorte de la
vista previa hable el dialecto correcto y que el error de driver faltante se
entienda. Contra un Fabric real no se probó —no hay tenant en este entorno— y
así está declarado en la documentación.
"""
from __future__ import annotations

import pytest
from app.core import connectors as C

ENDPOINT = "abcdefg.datawarehouse.fabric.microsoft.com"


def _perfil(**extra) -> dict:
    base = {"engine": "fabric", "host": ENDPOINT, "database": "VentasLH",
            "username": "11111111-2222-3333-4444-555555555555",
            "password": "secreto-de-la-aplicacion"}
    base.update(extra)
    return base


# ── catálogo de motores ──────────────────────────────────────────────────────
def test_fabric_figura_entre_los_motores():
    assert "fabric" in C.ENGINES
    assert "Fabric" in C.ENGINES["fabric"]["label"]
    assert C.ENGINES["fabric"]["port"] == 1433


# ── armado de la URL ─────────────────────────────────────────────────────────
def test_service_principal_arma_la_url_con_entra_id():
    url = C.build_url(_perfil())
    assert url.startswith("mssql+pyodbc://")
    assert "Authentication=ActiveDirectoryServicePrincipal" in url
    assert "ODBC+Driver+18+for+SQL+Server" in url
    assert "Encrypt=yes" in url
    assert ENDPOINT in url and "VentasLH" in url


def test_sin_secreto_usa_el_inicio_de_sesion_interactivo():
    url = C.build_url(_perfil(username="martin@empresa.com", password=None))
    assert "Authentication=ActiveDirectoryInteractive" in url
    assert "martin%40empresa.com" in url


def test_sin_usuario_el_mensaje_dice_que_falta():
    with pytest.raises(C.ConnectionError_, match="aplicación"):
        C.build_url(_perfil(username=None, password=None))


def test_el_driver_odbc_se_puede_cambiar():
    url = C.build_url(_perfil(odbc_driver="ODBC Driver 17 for SQL Server"))
    assert "ODBC+Driver+17+for+SQL+Server" in url


def test_los_caracteres_raros_del_secreto_no_rompen_la_url():
    url = C.build_url(_perfil(password="a/b?c=d&e"))
    assert "a%2Fb%3Fc%3Dd%26e" in url


def test_el_perfil_de_la_api_acepta_el_motor_y_el_driver(client):
    """El campo tiene que llegar del formulario al armado de la URL, no perderse."""
    guardado = client.post("/api/connections/save", json={
        "engine": "fabric", "label": "Fabric de prueba", "host": ENDPOINT,
        "database": "VentasLH", "username": "martin@empresa.com",
        "odbc_driver": "ODBC Driver 17 for SQL Server"}).json()["connection"]
    try:
        perfil = C.get_profile(guardado["id"])
        assert perfil["odbc_driver"] == "ODBC Driver 17 for SQL Server"
        assert "ODBC+Driver+17" in C.build_url(perfil)
    finally:
        client.delete(f"/api/connections/{guardado['id']}")


# ── el secreto no vuelve al navegador ────────────────────────────────────────
def test_el_perfil_publico_no_lleva_el_secreto():
    pub = C.public(_perfil(id="conn_x"))
    assert "password" not in pub
    assert "secreto-de-la-aplicacion" not in str(pub)
    assert pub["has_password"] is True


# ── dialecto: Fabric es SQL Server, no PostgreSQL ────────────────────────────
def test_la_vista_previa_recorta_con_top_y_no_con_limit():
    sql = C._wrap_limit("SELECT * FROM ventas", 50, "fabric")
    assert "TOP 50" in sql
    assert "LIMIT" not in sql.upper()


def test_si_la_consulta_ya_recorta_no_se_vuelve_a_envolver():
    sql = C._wrap_limit("SELECT TOP 10 * FROM ventas", 50, "fabric")
    assert sql.count("TOP") == 1


# ── sigue siendo de sólo lectura ─────────────────────────────────────────────
@pytest.mark.parametrize("consulta", [
    "SELECT * INTO copia FROM ventas",
    "DROP TABLE ventas",
    "UPDATE ventas SET monto = 0",
])
def test_fabric_no_abre_la_puerta_a_escribir(consulta):
    with pytest.raises(C.ConnectionError_):
        C.guard(consulta)


# ── error de driver entendible ───────────────────────────────────────────────
def test_el_driver_odbc_faltante_dice_como_resolverlo():
    msg = C._friendly(RuntimeError(
        "('01000', \"[01000] [unixODBC][Driver Manager]Can't open lib "
        "'ODBC Driver 18 for SQL Server' : file not found (0) (SQLDriverConnect)\")"))
    assert "ODBC" in msg
    assert "instal" in msg.lower()


def test_sin_administrador_odbc_en_linux_tambien_se_entiende():
    msg = C._friendly(ImportError(
        "libodbc.so.2: cannot open shared object file: No such file or directory"))
    assert "ODBC" in msg
    assert "unixODBC" in msg
