"""Que la licencia embebida llegue al instalador, y que valide.

El instalador owner lleva su licencia adentro para arrancar en nivel Owner sin
que nadie pegue nada. Eso son tres archivos que tienen que coincidir en la misma
carpeta, escritos por tres piezas distintas que nunca se miran entre sí:

  · el workflow, que **escribe** `license.key` y `public.key`;
  · `electron-builder.yml`, que **empaqueta** una carpeta y no las demás;
  · `main.cjs`, que las **lee** de `resources/` para pasárselas al backend.

Y así estuvo roto: el workflow dejaba la clave pública en `desktop/keys/`, que
`extraResources` no empaqueta. No viajaba en ningún instalador, `licensing.py`
caía a su marcador —33 bytes, cuando Ed25519 necesita 32— y rechazaba TODAS las
licencias. El owner arrancaba en demo con su licencia adentro; al cliente que
pagaba le rebotaba la suya. Ninguna prueba lo vio porque cada pieza, por
separado, estaba bien.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from app.core import licensing as L

RAIZ = Path(__file__).resolve().parents[2]
BATS = sorted((RAIZ / "instalador-owner").glob("*.bat"))
WORKFLOW = RAIZ / ".github" / "workflows" / "desktop.yml"
BUILDER = RAIZ / "desktop" / "electron-builder.yml"
MAIN = RAIZ / "desktop" / "electron" / "main.cjs"
ACTIVADOR = RAIZ / "instalador-owner" / "Activar-OWNER.bat"


def _carpetas_empaquetadas() -> set[str]:
    """Los `from:` de `extraResources` que salen de `desktop/`."""
    texto = BUILDER.read_text(encoding="utf-8")
    bloque = texto[texto.index("extraResources:"):]
    bloque = bloque[:bloque.index("\nwin:")]
    return set(re.findall(r"^\s*-\s*from:\s*(?!\.\.)(\S+)", bloque, re.M))


def _destinos_empaquetados() -> set[str]:
    """Los `to:` de `extraResources`: las carpetas tal como quedan bajo
    `resources/` en el instalador, que es lo que `main.cjs` ve.

    Distinto de `_carpetas_empaquetadas()`, que mira los `from:` que salen de
    `desktop/` para cruzarlos con lo que el workflow escribe. La interfaz viene
    de `../frontend`, fuera de `desktop/`, así que sólo aparece acá.
    """
    texto = BUILDER.read_text(encoding="utf-8")
    bloque = texto[texto.index("extraResources:"):]
    bloque = bloque[:bloque.index("\nwin:")]
    return set(re.findall(r"^\s*to:\s*(\S+)", bloque, re.M))


@pytest.mark.parametrize("archivo", ["license.key", "public.key"])
def test_las_credenciales_se_escriben_donde_se_empaquetan(archivo: str):
    escritos = re.findall(rf'open\("desktop/(\S+)/{archivo}"',
                          WORKFLOW.read_text(encoding="utf-8"))
    assert escritos, f"el workflow no escribe {archivo} en ninguna parte"
    empaquetadas = _carpetas_empaquetadas()
    for carpeta in escritos:
        assert carpeta in empaquetadas, (
            f"el workflow escribe {archivo} en desktop/{carpeta}/, que "
            f"electron-builder no empaqueta ({sorted(empaquetadas)}): no viaja "
            f"en ningún instalador")


@pytest.mark.parametrize("archivo", ["license.key", "public.key"])
def test_el_programa_las_lee_de_esa_misma_carpeta(archivo: str):
    leidas = re.findall(rf"recursos\('(\w+)',\s*'{archivo}'\)",
                        MAIN.read_text(encoding="utf-8"))
    assert leidas, f"main.cjs no lee {archivo}"
    escritos = re.findall(rf'open\("desktop/(\S+)/{archivo}"',
                          WORKFLOW.read_text(encoding="utf-8"))
    assert set(leidas) == set(escritos), (
        f"main.cjs lee {archivo} de resources/{leidas} y el workflow la deja "
        f"en desktop/{escritos}: no se encuentran")


def test_el_programa_le_dice_al_backend_donde_quedo_la_interfaz():
    """Sin `MV_FRONTEND_DIR`, el instalador abre una ventana con un JSON.

    El backend monta la interfaz sólo si `settings.frontend_dir` existe, y por
    omisión la busca junto al código fuente. Dentro del .exe congelado esa ruta
    no existe: no se monta ni `/assets` ni la raíz, y **toda** URL contesta
    `{"detail": "Not Found"}` — que es exactamente lo que ve el usuario, en una
    ventana de Electron, en vez del programa.

    `electron-builder.yml` sí empaqueta la interfaz. Lo que faltaba era que el
    lanzador le dijera dónde quedó. Mismo patrón que el de `public.key`: tres
    piezas correctas por separado que no se encuentran entre sí.
    """
    main = MAIN.read_text(encoding="utf-8")
    m = re.search(r"MV_FRONTEND_DIR:\s*recursos\('(\w+)'\)", main)
    assert m, ("main.cjs no le pasa MV_FRONTEND_DIR al backend: el programa "
               "arranca mostrando {\"detail\": \"Not Found\"}")
    assert m.group(1) in _destinos_empaquetados(), (
        f"main.cjs apunta la interfaz a resources/{m.group(1)}/, que "
        f"electron-builder no empaqueta ({sorted(_destinos_empaquetados())})")


def test_el_smoke_del_instalador_comprueba_que_la_interfaz_se_sirve():
    """La prueba del .exe pedía sólo endpoints de `/api`, así que un backend
    que no monta la interfaz la pasaba entera. Peor: le exportaba
    `MV_FRONTEND_DIR` a mano —la variable que el programa real no le pasaba—,
    con lo que la prueba medía una configuración que no existía en el producto.
    """
    wf = WORKFLOW.read_text(encoding="utf-8")
    bloque = wf[wf.index("Probar el .exe del backend"):]
    bloque = bloque[:bloque.index("- name:", 10)]
    assert 'C.get(f"{B}/")' in bloque, (
        "el smoke del .exe no pide la raíz: un backend que no monta la "
        "interfaz vuelve a pasar la prueba y a fallar en la máquina del cliente")


def test_sin_la_clave_publica_al_lado_no_valida_ni_la_licencia_del_owner():
    """El modo de falla exacto que tuvo el instalador, escrito una vez.

    Cuando el instalador no trae `public.key`, `licensing.py` se queda con el
    marcador que tiene escrito como valor por omisión, que **no es una clave
    Ed25519 válida** —tiene 33 bytes y hacen falta 32—, así que rechaza hasta
    una licencia legítima. Eso es lo que convierte «no empaqueté un archivo» en
    «el producto no se puede vender», sin un solo error visible en el build.

    Se lee del código y no de `L.PUBLIC_KEY_B64` porque `conftest.py` le pone
    una clave de prueba al entorno: mirando el valor en vivo, esta prueba
    estaría midiendo la suite en vez del binario que se entrega.
    """
    import base64

    fuente = Path(L.__file__).read_text(encoding="utf-8")
    marcador = re.search(r'os\.environ\.get\(\s*"MV_LICENSE_PUBLIC_KEY",\s*\n?\s*"([^"]+)"',
                         fuente).group(1)
    assert len(base64.b64decode(marcador)) != 32, (
        "el marcador por omisión pasó a ser una clave Ed25519 válida: un "
        "instalador sin public.key validaría licencias firmadas con ella")

    priv, pub = L.generate_keypair()
    token = L.issue("owner", "Owner build (CI)", days=None, private_key_b64=priv)
    assert L.verify(token, public_key_b64=pub).tier == "owner"

    with pytest.raises(L.LicenseError, match="clave pública embebida es inválida"):
        L.verify(token, public_key_b64=marcador)


def test_el_activador_tiene_el_hueco_que_el_ci_rellena():
    """El CI mete la licencia con un reemplazo de texto: si el hueco cambia de
    forma, el activador sale sin licencia y vuelve a preguntar."""
    texto = ACTIVADOR.read_text(encoding="ascii")
    assert texto.count('set "LIC_EMBEBIDA="') == 1, (
        "el activador tiene que tener exactamente un hueco "
        '`set "LIC_EMBEBIDA="` para que el workflow lo rellene')


def test_el_activador_del_repositorio_viaja_sin_licencia():
    """La copia versionada es una plantilla, no una llave.

    Una licencia fija acá deja de valer apenas cambien las claves —y mientras
    tanto es una llave del producto guardada en el historial, que no se puede
    borrar de los clones que ya se hicieron.
    """
    texto = ACTIVADOR.read_text(encoding="ascii")
    # Un token de verdad, no la palabra: el script nombra el prefijo en un
    # control y en un mensaje de error, y eso es correcto que esté.
    pegadas = re.findall(rf"{L.PREFIX}\.[A-Za-z0-9_-]{{20,}}\.[A-Za-z0-9_-]{{20,}}", texto)
    assert not pegadas, (
        "hay una licencia pegada en el activador versionado: la pone el CI en "
        "la copia que se publica, nunca el repositorio")


def _lineas_con_parentesis_sueltos(texto: str) -> list[str]:
    """Líneas que rompen un bloque `( … )` de cmd.exe desde adentro.

    En batch, un paréntesis suelto dentro de un bloque lo cierra ahí mismo,
    aunque esté en medio de un mensaje entre comillas: el resto de las líneas
    quedan sueltas y el script se rompe entero. cmd.exe no avisa nada — abre la
    ventana, escupe errores y se cierra.
    """
    malas, dentro = [], False
    for cruda in texto.splitlines():
        linea = cruda.strip()
        if not dentro:
            if linea.endswith("(") and not linea.startswith("REM"):
                dentro = True
            continue
        if linea == ")":
            dentro = False
            continue
        if re.fullmatch(r"\)\s*else\s*\(", linea):    # cierra y vuelve a abrir
            continue
        # `^(` y `^)` van escapados y son seguros
        suelto = re.sub(r"\^[()]", "", linea)
        if "(" in suelto or ")" in suelto:
            malas.append(cruda)
    return malas


@pytest.mark.parametrize("bat", BATS, ids=lambda p: p.name)
def test_ningun_bat_se_corta_solo_por_un_parentesis(bat: Path):
    malas = _lineas_con_parentesis_sueltos(bat.read_text(encoding="ascii"))
    assert not malas, (
        f"{bat.name} tiene un paréntesis sin escapar adentro de un bloque, que "
        f"se lo cierra a cmd.exe antes de tiempo: {malas}")


@pytest.mark.parametrize("bat", BATS, ids=lambda p: p.name)
def test_los_bat_son_ascii_con_finales_de_windows(bat: Path):
    """Un acento rompe el mensaje según la página de códigos del equipo, y con
    finales de línea de Unix cmd.exe se come la última orden."""
    crudo = bat.read_bytes()
    crudo.decode("ascii")                       # revienta si hay un acento
    assert b"\r\n" in crudo, f"{bat.name} no tiene finales de línea CRLF"
    sueltos = crudo.replace(b"\r\n", b"").count(b"\n")
    assert sueltos == 0, f"{bat.name} mezcla finales de línea"


def _publicacion_owner() -> dict:
    """El paso que sube los archivos del release owner."""
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    pasos = next(iter(d["jobs"].values()))["steps"]
    return next(p for p in pasos if p.get("name", "").startswith("Publicar OWNER"))


def test_el_release_owner_lleva_una_copia_que_no_pasa_por_el_instalador():
    """La vía que no depende del disco del sistema.

    NSIS descomprime su paquete en `%TEMP%` antes de copiarlo al destino: pide
    el espacio dos veces y la primera siempre en C:, aunque instales en D:.
    Cuando no entra, muere con «error escribiendo al archivo ...\\app-64.7z».
    La copia portable no pasa por ahí.
    """
    archivos = _publicacion_owner()["with"]["files"]
    assert "MV-AutoML-Studio-Owner-Portable.zip" in archivos, (
        "el release owner dejó de publicar la copia portable: sin ella, la "
        "única forma de instalar vuelve a necesitar espacio en C:")
    assert "Instalar-en-otro-disco.bat" in archivos


def test_la_copia_portable_trae_la_carpeta_que_la_hace_portable():
    """Sin `datos/` adentro, el .zip escribe en el perfil del usuario igual.

    Es la señal que `carpeta-datos.cjs` busca para no tocar el disco del
    sistema; si el paso deja de crearla, el .zip sigue armándose y nadie se
    entera hasta ver dónde quedaron los datasets.
    """
    texto = WORKFLOW.read_text(encoding="utf-8")
    bloque = texto[texto.index("Copia portable OWNER"):]
    bloque = bloque[:bloque.index("- name:", 10)]
    assert "win-unpacked/datos" in bloque, (
        "el paso portable no crea la carpeta `datos` dentro del .zip")
    assert "Portable.zip" in bloque


def test_la_copia_portable_trae_como_hacerse_un_acceso_directo():
    """El .zip no instala nada, así que nadie le crea el icono.

    El instalador NSIS deja el acceso en el escritorio y en el menú; la copia
    portable, por no instalar, no deja ninguno — y queda un ejecutable perdido
    en una carpeta, que hay que ir a buscar cada vez. El `.bat` lo resuelve sin
    convertir el portable en una instalación.
    """
    texto = WORKFLOW.read_text(encoding="utf-8")
    bloque = texto[texto.index("Copia portable OWNER"):]
    bloque = bloque[:bloque.index("- name:", 10)]
    assert "Crear-accesos-directos.bat" in bloque, (
        "el .zip portable sale sin el creador de accesos directos: el "
        "ejecutable queda sin icono en el escritorio ni en el menú")


def test_el_creador_de_accesos_se_ejecuta_en_la_ci_y_no_solo_en_el_build():
    """Crear accesos por COM desde PowerShell embebido en un .bat, con una
    ruta que tiene espacios, se rompe en silencio: el .bat termina bien y el
    icono no aparece. Sólo ejecutarlo lo detecta.

    Y tiene que ser en la CI, que corre en cada PR: el build de escritorio
    dispara después del merge, así que ahí un script roto se descubre cuando
    ya está en main.
    """
    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Crear-accesos-directos.bat" in ci, (
        "la CI dejó de ejecutar el creador de accesos: vuelve a ser un "
        "script que nadie prueba hasta que un cliente lo corre")
    assert "MV_SIN_PAUSA" in ci, (
        "sin MV_SIN_PAUSA el .bat se queda esperando una tecla y cuelga la CI")


def test_el_instalador_sigue_creando_los_accesos_directos():
    """Lo que el portable resuelve con un .bat, el instalador ya lo hace solo.

    Se vigila porque son dos caminos para lo mismo: si alguien apagara estas
    opciones, el instalador quedaría igual de mudo que el portable y no habría
    nada que lo delatara hasta que un cliente pregunte dónde quedó el programa.
    """
    builder = BUILDER.read_text(encoding="utf-8")
    for opcion in ("createDesktopShortcut: true", "createStartMenuShortcut: true"):
        assert opcion in builder, f"el instalador dejó de traer {opcion}"


def test_la_carpeta_datos_no_viaja_en_el_instalador():
    """En una instalación normal es dañina: el desinstalador borra el
    directorio del programa, y se llevaría los datasets del cliente."""
    builder = BUILDER.read_text(encoding="utf-8")
    assert "extraFiles" not in builder, (
        "`extraFiles` mete archivos en la raíz del programa y también en el "
        "instalador: si por ahí entrara `datos/`, desinstalar borraría los "
        "datasets del cliente")


def test_el_release_publica_las_huellas_de_lo_que_entrega():
    """Una descarga cortada de 371 MB falla recién a mitad de la instalación,
    con un error de extracción que no menciona la descarga. El SHA-256 a la
    vista convierte eso en diez segundos de verificación."""
    with_ = _publicacion_owner()["with"]
    assert "body_path" in with_, "el cuerpo del release volvió a ser fijo"

    texto = WORKFLOW.read_text(encoding="utf-8")
    bloque = texto[texto.index("Texto del release"):texto.index("Publicar OWNER")]
    assert "sha256" in bloque, "no se calcula ninguna huella"
    for archivo in ("MV-AutoML-Studio-Owner-Setup.exe",
                    "MV-AutoML-Studio-Owner-Portable.zip",
                    "Activar-OWNER.bat"):
        assert archivo in bloque, f"{archivo} se publica sin huella"


@pytest.mark.parametrize("wf", sorted((RAIZ / ".github" / "workflows").glob("*.yml")),
                         ids=lambda p: p.name)
def test_los_workflows_parsean(wf: Path):
    """Un YAML roto no falla: directamente no corre, y no avisa por qué.

    Pasó con un `name:` de paso que llevaba dos puntos sin comillas —
    `Publicar OWNER (sólo colaboradores: el repositorio es privado)` — y YAML
    lee eso como el arranque de otra clave. Es gratis comprobarlo acá.
    """
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load(wf.read_text(encoding="utf-8"))
    assert d, f"{wf.name} quedó vacío"
    assert "jobs" in d and d["jobs"], f"{wf.name} no declara ningún job"


NSH = RAIZ / "desktop" / "build" / "installer.nsh"


def test_el_instalador_avisa_del_espacio_antes_de_empezar():
    """El error que veía el usuario no menciona el espacio por ningún lado.

    NSIS descomprime su paquete en `%TEMP%` y recién después lo copia al
    destino: pide el espacio dos veces, y la primera siempre en el disco del
    sistema, aunque el usuario elija instalar en otro. Cuando no entra, muere
    a mitad de la barra con «error escribiendo al archivo ...\\app-64.7z» —
    un mensaje que no dice qué hacer.

    El chequeo corre ANTES de extraer y nombra las tres salidas: liberar
    espacio, `Instalar-en-otro-disco.bat`, o la copia portable.
    """
    assert NSH.exists(), "no hay script de instalador propio"
    texto = NSH.read_text(encoding="ascii")

    assert "customInit" in texto, (
        "el chequeo tiene que colgar de customInit, que corre antes de extraer")
    assert "DriveSpace" in texto and "$TEMP" in texto, (
        "no mide el espacio libre en el disco donde NSIS descomprime")
    for salida in ("Instalar-en-otro-disco.bat", "portable"):
        assert salida in texto, f"el mensaje no ofrece la salida: {salida}"


def test_electron_builder_incluye_ese_script():
    """Un .nsh que nadie referencia no se compila y no hace nada."""
    builder = BUILDER.read_text(encoding="utf-8")
    m = re.search(r"^\s*include:\s*(\S+)", builder, re.M)
    assert m, "electron-builder.yml no incluye ningún script de instalador"
    assert (RAIZ / "desktop" / m.group(1)).exists(), (
        f"electron-builder.yml apunta a {m.group(1)}, que no existe")


def test_el_instalador_deja_elegir_la_carpeta():
    """Ya se podía, y conviene que siga: el error de espacio no tiene nada que
    ver con esto —ocurre antes, al descomprimir en %TEMP%— y es fácil
    confundir las dos cosas."""
    builder = BUILDER.read_text(encoding="utf-8")
    assert "allowToChangeInstallationDirectory: true" in builder
    assert "oneClick: false" in builder


def test_el_script_del_instalador_es_ascii():
    """NSIS compila con la página de códigos del sistema: un acento en el
    mensaje sale como basura en la pantalla del cliente."""
    NSH.read_bytes().decode("ascii")


def test_el_mensaje_del_instalador_tiene_las_comillas_balanceadas():
    """Lo único de NSIS que se puede comprobar sin compilarlo.

    El mensaje es largo y va partido en varias líneas con `\\` al final. Una
    comilla de más o de menos ahí no se nota leyendo, y el precio de
    descubrirlo es un build de veinte minutos que termina en rojo.
    """
    lineas, acumulada = [], ""
    for cruda in NSH.read_text(encoding="ascii").splitlines():
        linea = cruda.rstrip()
        if linea.lstrip().startswith(";"):
            continue
        if linea.endswith("\\"):
            acumulada += linea[:-1]
            continue
        lineas.append(acumulada + linea)
        acumulada = ""
    assert not acumulada, "el archivo termina con una línea continuada sin cerrar"

    for linea in lineas:
        assert linea.count('"') % 2 == 0, (
            f"comillas sin cerrar en NSIS: {linea[:90]}")


def test_el_instalador_no_bloquea_si_no_puede_medir_el_espacio():
    """Si `DriveSpace` falla, la variable queda vacía. Comparar eso como número
    es impredecible, y equivocarse acá deja a un cliente sin poder instalar por
    una comprobación que ni siquiera pudo hacerse."""
    texto = NSH.read_text(encoding="ascii")
    assert re.search(r'\$\w+ != ""', texto), (
        "el chequeo no contempla que la medición del espacio falle")


def test_el_aviso_de_espacio_no_puede_cerrar_el_instalador():
    """La prueba de esta sesión: doble clic al instalador y no pasaba NADA.

    Este archivo se inserta en `.onInit`. Ahí `Abort` cierra el instalador sin
    mostrar una sola palabra —ni ventana, ni cartel, ni código de error—, y
    desde la máquina del cliente ese síntoma es indistinguible de un ejecutable
    corrupto. Una comprobación de conveniencia no puede tener el poder de matar
    al programa que instala.

    El aviso avisa; la decisión de seguir o cerrar es del usuario.
    """
    texto = NSH.read_text(encoding="ascii")
    codigo = [ln for ln in texto.splitlines() if not ln.lstrip().startswith(";")]

    assert not any(re.search(r"\bAbort\b", ln) for ln in codigo), (
        "hay un Abort en el .onInit del instalador: eso lo cierra en silencio")
    assert not any(re.search(r"\bQuit\b", ln) for ln in codigo), (
        "hay un Quit en el .onInit del instalador: eso lo cierra en silencio")


def test_el_aviso_devuelve_los_registros_que_toma_prestados():
    """`$0`-`$9` y `$R0`-`$R9` son compartidos: electron-builder los usa en su
    propio `.onInit`, justo alrededor de donde se inserta esto. Pisarlos y no
    devolverlos deja el arranque en un estado indefinido, y el modo de falla es
    mudo. El idioma de NSIS para esto es Push al entrar y Pop al salir.
    """
    texto = NSH.read_text(encoding="ascii")
    codigo = [ln for ln in texto.splitlines() if not ln.lstrip().startswith(";")]

    empujados = [ln.split()[1] for ln in codigo if ln.strip().startswith("Push ")]
    sacados = [ln.split()[1] for ln in codigo if ln.strip().startswith("Pop ")]
    assert empujados, "el .nsh usa registros sin guardarlos"
    assert empujados == list(reversed(sacados)), (
        f"la pila queda torcida: entran {empujados}, salen {sacados}")

    tocados = set(re.findall(r"\$R?[0-9]\b", "\n".join(codigo)))
    assert tocados <= set(empujados), (
        f"toca registros que no guardó: {sorted(tocados - set(empujados))}")


def test_el_aviso_no_declara_variables_a_nivel_de_archivo():
    """El error que tiró el build entero, cuatro minutos después de empezar.

    electron-builder compila el DESINSTALADOR en una pasada aparte que incluye
    este mismo archivo pero **no** inserta `customInit`. Una `Var` declarada
    acá queda ahí sin usar, NSIS avisa «warning 6001: Variable not referenced
    or never set» y electron-builder trata sus warnings como errores:

        warning 6001: Variable "mvUnidadTemp" not referenced or never set
        Error: warning treated as error

    Doce minutos de build para enterarse de una línea. Esta prueba tarda un
    milisegundo.
    """
    codigo = [ln for ln in NSH.read_text(encoding="ascii").splitlines()
              if not ln.lstrip().startswith(";")]

    declaradas = [ln.strip() for ln in codigo if re.match(r"^\s*Var\s+\w", ln)]
    assert not declaradas, (
        "declara variables a nivel de archivo; la pasada del desinstalador no "
        f"las usa y NSIS lo trata como error: {declaradas}")


def test_el_aviso_se_calla_en_la_instalacion_silenciosa():
    """Un MessageBox en modo `/S` no lo cierra nadie: la instalación queda
    colgada hasta que alguien mate el proceso. Es además el modo en que la CI
    instala el .exe para probarlo, así que sin esto la prueba se cuelga en vez
    de fallar."""
    texto = NSH.read_text(encoding="ascii")
    assert "${Silent}" in texto, (
        "el aviso no contempla la instalación silenciosa")


def test_la_ci_instala_el_exe_en_vez_de_solo_leerlo():
    """El hueco que dejó pasar un instalador que no instalaba.

    Todas las pruebas de este archivo leen texto: que el `.nsh` exista, que
    `electron-builder.yml` lo referencie, que el mensaje no tenga acentos. Son
    útiles y baratas, y ninguna se entera de que el `.exe` publicado no arranca.

    El único lugar donde eso se puede comprobar es el runner Windows del CI:
    instalar el instalador, en una carpeta elegida, y ver que lo instalado
    levanta. Si ese paso se va del workflow, volvemos a poder publicar un
    programa que al doble clic no hace nada.
    """
    wf = (RAIZ / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")

    assert "/S /D=" in wf, (
        "el CI no instala el .exe en modo silencioso hacia una carpeta elegida")
    assert "MV AutoML Studio.exe" in wf, (
        "el CI no comprueba que la instalación haya dejado el programa")
    for pieza in ("resources\\mv-backend", "resources\\frontend",
                  "resources\\owner"):
        assert pieza in wf, f"el CI no verifica que se instale {pieza}"
    assert "api/health" in wf and "8477" in wf, (
        "el CI no arranca lo que quedó instalado: que los archivos estén no "
        "alcanza, el cliente abre el programa, no la carpeta")


def test_el_diagnostico_del_instalador_viaja_en_el_release():
    """Cuando el instalador no hace nada, «no hace nada» no es un dato.

    Ese síntoma tiene varias causas que desde afuera se ven idénticas: la
    descarga cortada, la marca de archivo bajado de internet, la carpeta
    temporal sin espacio, el .exe dañado. Este .bat las separa sin pedirle al
    usuario que tipee comandos, así que tiene que llegarle en el release —uno
    que se quede en el repositorio no ayuda a nadie.
    """
    bat = RAIZ / "instalador-owner" / "Diagnostico-instalador.bat"
    assert bat.exists(), "no existe el diagnóstico del instalador"

    # NSIS y cmd.exe comparten el mismo problema con los acentos: la consola
    # de Windows los rompe según la página de códigos del sistema.
    bat.read_bytes().decode("ascii")

    texto = bat.read_text(encoding="ascii")
    assert "/NCRC" in texto, (
        "no ofrece saltear la comprobación de integridad, que es lo que "
        "distingue un archivo dañado de un instalador que se cierra solo")
    assert "Zone.Identifier" in texto, (
        "no mira la marca de archivo bajado de internet")

    wf = (RAIZ / ".github" / "workflows" / "desktop.yml").read_text(encoding="utf-8")
    assert "Diagnostico-instalador.bat" in wf, (
        "el diagnóstico no se publica: queda en el repositorio, donde no "
        "le sirve a quien tiene el problema")
