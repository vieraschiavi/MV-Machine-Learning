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
