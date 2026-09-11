"""Qué pasa cuando el programa atiende a más de una persona a la vez.

En la laptop de un analista esto no se nota: hay un usuario y un trabajo por
vez. En modo servidor —una VM del cliente, varias personas contra la misma
instancia— cada uno de estos detalles cambia de categoría, así que los tres se
midieron ejecutando antes de tocar una línea:

  1. **El registro de trabajos dejaba la conexión SQLite abierta.** El propio
     módulo documenta por qué eso no se hace (``_catalogo``), y todos los demás
     caminos la cierran; el historial de trabajos se había quedado afuera.
  2. **La ingesta corría dentro del event loop.** Subir un archivo congelaba el
     servidor entero mientras duraba: medido, 3 ms de latencia en reposo contra
     955 ms durante la ingesta de 9 MB — y eso escala con el tamaño del
     archivo, que es justo lo que este producto promete no limitar.
  3. Lo que ya estaba bien y conviene fijar: **los datos de dos clientes no se
     cruzan**. La demo que se corrió aparte fue con ocho workspaces subiendo y
     entrenando de verdad contra la misma instancia, verificada hasta el
     Parquet en disco; acá queda la versión que puede correr en cada CI: seis
     subiendo a la vez, y ocho trabajos en segundo plano heredando cada uno su
     workspace.
"""
from __future__ import annotations

import gc
import io
import sqlite3
import threading
import time

import pytest


# ══════════════════════════ 1. el catálogo se cierra ═════════════════════════
def _conexiones_abiertas() -> int:
    """Conexiones SQLite vivas y usables en el proceso.

    Con el recolector apagado, una conexión que nadie cerró sigue abierta: es
    la diferencia entre «se cierra» y «se cierra cuando el recolector pase».
    """
    n = 0
    for obj in gc.get_objects():
        if isinstance(obj, sqlite3.Connection):
            try:
                obj.execute("SELECT 1")
                n += 1
            except sqlite3.ProgrammingError:
                pass
    return n


def _ficha_de_trabajo(i: int) -> dict:
    ahora = time.time()
    return {"id": f"job_conc_{i}", "kind": "entrenamiento", "title": "prueba",
            "status": "terminado", "created_at": ahora, "started_at": ahora,
            "finished_at": ahora, "workspace": "principal"}


@pytest.mark.parametrize("registrar", ["record_job", "record_model"])
def test_el_catalogo_no_queda_abierto_al_registrar(registrar):
    """`with sqlite3.connect(...)` confirma la transacción pero NO cierra.

    En Windows eso deja tomado el archivo: el usuario no puede borrar ni mover
    su propio workspace hasta que pase el recolector, y el error que ve no
    menciona ningún programa. Medido antes del arreglo: cinco trabajos
    registrados dejaban cinco conexiones abiertas.
    """
    from app.core import workspace as W

    def registro(i: int) -> None:
        if registrar == "record_job":
            W.record_job(_ficha_de_trabajo(i))
        else:
            W.record_model({"id": f"mdl_conc{i:08d}", "name": "m", "dataset_id": "ds",
                            "target": "y", "task": "binary", "metric": "auc",
                            "score": 0.8, "model": "lgbm", "created_at": time.time()})

    registro(0)                    # la primera crea el archivo
    gc.collect()
    antes = _conexiones_abiertas()

    gc.disable()
    try:
        for i in range(1, 6):
            registro(i)
        abiertas = _conexiones_abiertas() - antes
    finally:
        gc.enable()
        gc.collect()

    assert abiertas == 0, (
        f"{registrar} dejó {abiertas} conexiones al catálogo abiertas de 5 "
        "registros: en Windows el workspace queda tomado")


# ════════════════════ 2. la ingesta no bloquea a los demás ═══════════════════
def test_la_ingesta_no_corre_dentro_del_event_loop(client, monkeypatch):
    """Subir un archivo no puede congelar al resto de los usuarios.

    Leer un CSV y escribir Parquet es trabajo bloqueante: adentro de una
    corrutina ocupa el único hilo que atiende a TODO el servidor. Con 9 MB la
    latencia del resto pasó de 3 ms a 955 ms; con los archivos que este
    producto promete soportar, de segundos a minutos.

    La comprobación no mide tiempo —sería flaky—: pregunta desde dónde se
    ejecutó. `asyncio.get_running_loop()` sólo responde si está corriendo
    dentro del event loop, que es exactamente lo que no debe pasar.
    """
    import asyncio

    from app.api import datasets as api
    from app.core import storage

    visto: dict[str, bool] = {}
    original = storage.ingest_file

    def espia(*a, **kw):
        try:
            asyncio.get_running_loop()
            visto["en_el_loop"] = True
        except RuntimeError:
            visto["en_el_loop"] = False
        return original(*a, **kw)

    monkeypatch.setattr(api.storage, "ingest_file", espia)

    csv = b"a,b\n1,2\n3,4\n5,6\n"
    r = client.post("/api/datasets/upload",
                    files={"file": ("chico.csv", io.BytesIO(csv), "text/csv")})

    assert r.status_code == 200, r.text
    assert visto.get("en_el_loop") is False, (
        "la ingesta corre dentro del event loop: mientras dura, el servidor no "
        "atiende a nadie más")


# ═══════════════ 3. los datos de dos clientes no se cruzan ═══════════════════
def test_workspaces_en_paralelo_no_se_ven_entre_si(client):
    """El caso que motivó el modo servidor: dos clientes en la misma instancia.

    Seis workspaces suben al mismo tiempo un archivo con su propia marca. Al
    terminar, cada uno tiene que ver sus datasets y ninguno ajeno —y el disco
    tiene que decir lo mismo que la API—.
    """
    clientes = [f"paralelo{i}" for i in range(1, 7)]
    for c in clientes:
        client.post("/api/workspaces", json={"name": c})

    fallos: list[str] = []
    listas: dict[str, list[str]] = {}
    largada = threading.Barrier(len(clientes))

    def trabajo(cliente: str) -> None:
        try:
            filas = "\n".join(f"{i},{cliente}-confidencial" for i in range(50))
            csv = f"id,secreto\n{filas}\n".encode()
            largada.wait(timeout=30)
            r = client.post("/api/datasets/upload",
                            files={"file": (f"{cliente}.csv", io.BytesIO(csv), "text/csv")},
                            headers={"X-Workspace": cliente})
            if r.status_code != 200:
                fallos.append(f"{cliente}: subida {r.status_code} {r.text[:200]}")
                return
            listado = client.get("/api/datasets", headers={"X-Workspace": cliente}).json()
            listas[cliente] = [d["name"] for d in listado["datasets"]]
        except Exception as exc:                      # pragma: no cover - diagnóstico
            fallos.append(f"{cliente}: {type(exc).__name__}: {exc}")

    hilos = [threading.Thread(target=trabajo, args=(c,)) for c in clientes]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=120)

    assert not fallos, fallos
    for cliente, nombres in listas.items():
        ajenos = [n for n in nombres if not n.startswith(cliente)]
        assert not ajenos, f"{cliente} ve datasets de otro cliente: {ajenos}"
        assert nombres, f"{cliente} no ve su propio dataset"


def test_cada_trabajo_en_segundo_plano_hereda_su_workspace(client):
    """Los trabajos largos corren en otro hilo, y el workspace viaja por
    *context variable*: si no se propagara, el modelo de un cliente se
    guardaría en la carpeta de otro. Ocho trabajos simultáneos, cada uno
    lanzado desde un workspace distinto.
    """
    from app.core import jobs
    from app.core import workspace as W

    nombres = [f"herencia{i}" for i in range(1, 9)]
    for n in nombres:
        if not W.exists(n):
            W.create(n)

    visto: dict[str, str] = {}
    largada = threading.Barrier(len(nombres))

    def lanzar(nombre: str) -> dict:
        token = W.activate(nombre)
        try:
            def trabajo(progress):
                largada.wait(timeout=30)      # que los ocho estén adentro a la vez
                visto[nombre] = W.current()
                return {"ok": True}
            return jobs.run("prueba", f"herencia de {nombre}", trabajo)
        finally:
            W.deactivate(token)

    fichas = [lanzar(n) for n in nombres]

    limite = time.time() + 60
    while time.time() < limite:
        if all(jobs.public(f["id"])["status"] in ("terminado", "error") for f in fichas):
            break
        time.sleep(0.05)

    for ficha in fichas:
        estado = jobs.public(ficha["id"])
        assert estado["status"] == "terminado", estado.get("error")
    assert visto == {n: n for n in nombres}, (
        f"un trabajo corrió en el workspace equivocado: {visto}")
