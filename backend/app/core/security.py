"""Autenticación local de la API.

Empaquetada como aplicación de escritorio, la API escucha en `127.0.0.1`. Eso
la protege de la red, **no** de otros procesos del mismo equipo: cualquier
programa local —o una página web abierta en el navegador vía CSRF— podría
llamarla y leer los datos del usuario.

Por eso el proceso de Electron genera un token aleatorio por sesión, se lo pasa
al backend por variable de entorno y a la interfaz por el puente seguro. Cada
request debe traerlo. Si no hay token configurado (desarrollo, o el servidor
lanzado a mano), la autenticación queda desactivada y se avisa en `/api/health`.
"""
from __future__ import annotations

import hmac
import os
import secrets

HEADER = "X-MV-Token"
QUERY = "token"          # para EventSource y descargas, que no mandan encabezados


def expected_token() -> str:
    return os.environ.get("MV_API_TOKEN", "")


def enabled() -> bool:
    return bool(expected_token())


def new_token() -> str:
    return secrets.token_urlsafe(32)


def check(token: str | None) -> bool:
    """Comparación en tiempo constante: no filtra el token por el reloj."""
    esperado = expected_token()
    if not esperado:
        return True
    return bool(token) and hmac.compare_digest(token, esperado)


# Rutas que no exigen token: la interfaz estática y el chequeo de salud, para
# que la ventana pueda cargar y diagnosticar antes de recibir la credencial.
PUBLIC_PREFIXES = ("/assets/", "/api/health")
PUBLIC_EXACT = ("/", "/favicon.ico")


def is_public(path: str) -> bool:
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES)


# ───────────────────────────────────────────────────────── modo servidor ─────
# El programa también corre en el servidor del cliente, y se usa desde el
# navegador de otra máquina. Eso invierte la premisa de arriba: ya no escucha
# en `127.0.0.1` con su dueño delante, sino en una red, con los datos de un
# tercero adentro. `check()` deja pasar TODO cuando no hay token configurado
# —cómodo en el escritorio, una filtración acá—, así que en este modo la falta
# de credencial no se tolera: el programa no arranca.
#
# El modo se declara; no se adivina por la IP de escucha. Una heurística que se
# equivoca hacia el lado inseguro no es una heurística, es un agujero con
# suerte.
MODO_SERVIDOR = "servidor"

# Una credencial de cuatro dígitos en un puerto alcanzable es lo mismo que
# ninguna. Vale más negarse a arrancar que aparentar una protección inexistente.
MINIMO_CREDENCIAL = 16


def es_servidor() -> bool:
    return os.environ.get("MV_MODO", "").strip().lower() == MODO_SERVIDOR


def exigir_credencial_en_servidor() -> None:
    """Corta el arranque en modo servidor si la credencial falta o es débil."""
    if not es_servidor():
        return

    token = expected_token()
    if not token:
        raise RuntimeError(
            "MV_MODO=servidor sin MV_API_TOKEN: el programa quedaría abierto a "
            "cualquiera que alcance el puerto, con los datos adentro. Generá "
            "una credencial larga (por ejemplo: openssl rand -base64 32) y "
            "pasala en MV_API_TOKEN.")
    if len(token) < MINIMO_CREDENCIAL:
        raise RuntimeError(
            f"MV_API_TOKEN es demasiado corta ({len(token)} caracteres): en un "
            f"servidor accesible se adivina. Mínimo {MINIMO_CREDENCIAL} "
            "caracteres; usá openssl rand -base64 32.")
