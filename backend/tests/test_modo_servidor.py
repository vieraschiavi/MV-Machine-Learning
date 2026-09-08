"""Modo servidor: el programa corre en la máquina del cliente, no en la tuya.

El caso que lo motiva: un consultor externo trabaja para un cliente cuyos datos
no pueden salir de la infraestructura del cliente —ni a su laptop personal, ni
a la laptop que le dio la contratista—. Además esa laptop suele tener bloqueada
la ejecución de `.exe` y `.bat`, así que instalar no es una opción.

La salida es la que el programa ya casi era: el backend sirve la interfaz, así
que puede correr en el servidor del cliente y usarse desde el navegador. Los
datasets, los modelos y los informes quedan en el disco de ESE servidor. Por la
laptop sólo pasan píxeles.

Eso cambia una premisa de seguridad, y es lo que fijan estas pruebas:

  1. **En escritorio, sin token la autenticación se apaga sola.** Es deliberado:
     la API escucha en `127.0.0.1` y el que la lanza a mano es el dueño del
     equipo. En un servidor expuesto a una red, esa misma línea deja los datos
     del cliente abiertos a cualquiera que alcance el puerto. En modo servidor,
     sin credencial el programa NO ARRANCA.
  2. **La licencia owner viaja por entorno y no toca el disco.** Un archivo de
     licencia en el servidor del cliente es una credencial abandonada ahí.
  3. **El modo se declara explícitamente.** Nada de adivinarlo por la IP de
     escucha: equivocarse hacia el lado inseguro no puede depender de una
     heurística.
"""
from __future__ import annotations

import pytest
from app.core import security as S


@pytest.fixture
def entorno(monkeypatch):
    """Entorno limpio: sin modo ni token heredados de otra prueba."""
    monkeypatch.delenv("MV_MODO", raising=False)
    monkeypatch.delenv("MV_API_TOKEN", raising=False)
    return monkeypatch


# ═══════════════════════════════════════════════ el modo se declara ══════════
def test_por_omision_el_programa_esta_en_modo_escritorio(entorno):
    """Quien no sabe que existe el modo servidor no puede caer en él."""
    assert not S.es_servidor()


def test_el_modo_servidor_se_declara_explicitamente(entorno):
    entorno.setenv("MV_MODO", "servidor")
    assert S.es_servidor()


def test_el_modo_no_distingue_mayusculas_ni_espacios(entorno):
    """`MV_MODO=" Servidor "` en un compose mal copiado no puede dejar el
    programa en modo escritorio sin avisar: fallaría hacia el lado inseguro."""
    entorno.setenv("MV_MODO", "  Servidor  ")
    assert S.es_servidor()


# ═════════════════════════════════════ sin credencial no arranca ═════════════
def test_en_servidor_sin_credencial_el_programa_no_arranca(entorno):
    """La prueba que sostiene todo el modo.

    `enabled()` devuelve False cuando no hay `MV_API_TOKEN`, y el middleware
    deja pasar todo. En el escritorio eso es una comodidad; en un servidor con
    los datos de un cliente adentro es una filtración esperando a que alguien
    escanee el puerto.
    """
    entorno.setenv("MV_MODO", "servidor")

    with pytest.raises(RuntimeError, match="MV_API_TOKEN"):
        S.exigir_credencial_en_servidor()


def test_en_servidor_con_credencial_arranca(entorno):
    entorno.setenv("MV_MODO", "servidor")
    entorno.setenv("MV_API_TOKEN", "una-clave-larga-y-secreta")

    S.exigir_credencial_en_servidor()      # no levanta


def test_una_credencial_corta_no_alcanza_para_exponer_datos_ajenos(entorno):
    """`MV_API_TOKEN=1234` en un servidor accesible es lo mismo que nada: se
    adivina en segundos. Vale más negarse a arrancar que dar una sensación de
    protección que no existe."""
    entorno.setenv("MV_MODO", "servidor")
    entorno.setenv("MV_API_TOKEN", "1234")

    with pytest.raises(RuntimeError, match="(?i)corta|caracteres"):
        S.exigir_credencial_en_servidor()


def test_en_escritorio_sin_credencial_sigue_arrancando(entorno):
    """No romper lo que anda: el .exe y el portable lanzan el backend sin token
    cuando el usuario lo abre a mano, y escuchan sólo en 127.0.0.1."""
    S.exigir_credencial_en_servidor()      # modo escritorio: no levanta


# ══════════════════════════════════ la licencia no queda en el disco ═════════
def test_la_licencia_del_servidor_viaja_por_entorno_y_no_toca_el_disco(
        monkeypatch, tmp_path):
    """Un `license.key` escrito en el servidor del cliente es una credencial
    abandonada ahí: sobrevive al contenedor y la lee cualquiera con acceso al
    volumen. `MV_LICENSE` la mantiene en el proceso y nada más.
    """
    from app.core import licensing as L

    monkeypatch.setattr(L, "_store_path", lambda: tmp_path / "license.key")
    monkeypatch.setattr(L, "_ACTIVE", None, raising=False)
    priv, pub = L.generate_keypair()
    token = L.issue("owner", "Modo servidor", days=None, private_key_b64=priv)
    monkeypatch.setattr(L, "PUBLIC_KEY_B64", pub, raising=False)
    monkeypatch.setenv("MV_LICENSE", token)

    lic = L.load()

    assert lic is not None and lic.tier == "owner"
    assert not (tmp_path / "license.key").exists(), (
        "la licencia se escribió en el disco del cliente")


# ════════════════════════════════════════════════════════ el contenedor ══════
RAIZ = __import__("pathlib").Path(__file__).resolve().parents[2]
DOCKERFILE = RAIZ / "Dockerfile"
COMPOSE = RAIZ / "docker-compose.yml"
DOCKERIGNORE = RAIZ / ".dockerignore"


def test_el_contenedor_no_corre_como_root():
    """Si alguien encuentra un agujero en el programa, que no se encuentre
    además con la máquina del cliente entera."""
    d = DOCKERFILE.read_text(encoding="utf-8")

    assert "USER mv" in d, "el contenedor corre como root"
    assert d.index("USER mv") < d.index("CMD"), (
        "el USER tiene que estar antes del CMD, o el proceso arranca como root")


def test_el_contenedor_declara_el_modo_servidor():
    """Sin `MV_MODO=servidor` la guarda de credencial no se activa y el
    contenedor quedaría con la autenticación apagada."""
    assert "MV_MODO=servidor" in DOCKERFILE.read_text(encoding="utf-8")


def test_la_imagen_no_se_lleva_claves_ni_licencias():
    """Una imagen es un archivo que se copia. Una licencia horneada adentro es
    una credencial que se copia con ella, a donde sea que vaya la imagen."""
    ign = DOCKERIGNORE.read_text(encoding="utf-8")

    for patron in ("**/*.key", "**/owner/", ".env"):
        assert patron in ign, f".dockerignore no excluye {patron}"


def test_el_compose_exige_credencial_y_licencia_al_levantar():
    """`${VAR:?mensaje}` corta el `docker compose up` con un mensaje legible.
    Sin eso, faltar una variable se descubre cuando el contenedor ya arrancó
    —o peor, arrancó mal— en la máquina del cliente."""
    c = COMPOSE.read_text(encoding="utf-8")

    for var in ("MV_API_TOKEN", "MV_LICENSE", "MV_LICENSE_PUBLIC_KEY"):
        assert f"${{{var}:?" in c, f"el compose no exige {var} al levantar"


def test_el_puerto_no_queda_expuesto_a_la_red_por_omision():
    """El caso de uso es «los datos del cliente no salen de su servidor». Una
    copia levantada a las apuradas no puede quedar escuchando en toda la red
    de la empresa porque nadie tocó una variable."""
    c = COMPOSE.read_text(encoding="utf-8")

    assert "${MV_BIND:-127.0.0.1}" in c, (
        "el puerto se publica sin restringir la interfaz de escucha")


def test_los_datos_del_cliente_viven_en_un_volumen_de_su_servidor():
    """Si no hay volumen, los datasets viven adentro del contenedor y
    desaparecen con él: el cliente perdería su trabajo en el primer reinicio."""
    c = COMPOSE.read_text(encoding="utf-8")

    assert ":/datos" in c, "no hay volumen para los datos"
    assert "MV_DATA_DIR=/datos" in DOCKERFILE.read_text(encoding="utf-8"), (
        "el programa no guarda en la ruta que el compose monta")


# ═════════════════════════════════════════════ la pantalla de acceso ═════════
def test_la_pantalla_de_acceso_tiene_sus_textos_en_los_tres_idiomas():
    """El error que sólo se vio abriendo el navegador.

    `t()` resuelve claves **anidadas**: `t('acceso.title')` busca
    `dict['acceso']['title']`. Las claves agregadas planas —`"acceso.title"` en
    el primer nivel— hacen que `t()` no encuentre nada y devuelva la clave, así
    que la pantalla salía diciendo literalmente «acceso.title».

    Las pruebas de paridad de idiomas no lo notaron: las claves estaban en los
    tres diccionarios, sólo que en el lugar equivocado.
    """
    import json

    for lang in ("es", "en", "pt"):
        d = json.loads((RAIZ / "frontend" / "assets" / "i18n" / f"{lang}.json")
                       .read_text(encoding="utf-8"))
        assert isinstance(d.get("acceso"), dict), (
            f"{lang}.json no tiene «acceso» como objeto anidado; t() no lo va "
            "a encontrar y la pantalla va a mostrar el nombre de la clave")
        planas = [k for k in d if k.startswith("acceso.")]
        assert not planas, f"{lang}.json tiene claves planas: {planas}"
        for clave in ("title", "lead", "clave", "entrar", "error", "ayuda"):
            assert d["acceso"].get(clave), f"falta acceso.{clave} en {lang}"


def test_la_clave_de_acceso_no_sobrevive_a_cerrar_la_pestana():
    """En una laptop laboral —prestada, compartida, con perfil administrado— la
    credencial del servidor de un cliente no puede quedar guardada. Verificado
    en navegador: una sesión nueva vuelve a pedirla."""
    api = (RAIZ / "frontend" / "assets" / "js" / "api.js").read_text(encoding="utf-8")

    assert "sessionStorage" in api, "la clave de acceso no usa sessionStorage"
    assert "localStorage.setItem('mv.acceso'" not in api, (
        "la clave de acceso se guarda en localStorage: sobrevive al navegador")
