"""Licencias y niveles de producto: demo, paga y owner.

Una licencia es un token firmado con **Ed25519**. La clave privada nunca sale
del equipo que emite (o del secreto de CI); la aplicación sólo lleva la clave
**pública** y verifica la firma. Eso significa que nadie puede fabricarse una
licencia editando un archivo de texto: necesitaría la privada.

Ser honestos con el alcance: en una aplicación de escritorio el binario está en
manos del usuario y siempre se puede parchear. Esto no es un DRM inviolable —
ninguno lo es— sino la protección estándar y razonable: evita la copia trivial
del token y deja el registro de a quién se emitió cada licencia.

Formato del token::

    MVAS.<payload en base64url>.<firma en base64url>

El payload es JSON: nivel, titular, emisión, vencimiento y funciones extra.
"""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

PREFIX = "MVAS"

# Clave pública de producción. La privada vive en el secreto de CI
# (MV_LICENSE_PRIVATE_KEY) y en el equipo del owner: nunca en el repositorio.
# Se puede sobreescribir por entorno para operar con un juego de claves propio.
PUBLIC_KEY_B64 = os.environ.get(
    "MV_LICENSE_PUBLIC_KEY",
    "0PJvJvJnJ4kZ3ZKQ7cJ8kZ0000000000000000000000=",  # marcador: se reemplaza al emitir
)


# ───────────────────────────────────────────────────────── niveles ────────────
@dataclass(frozen=True)
class Tier:
    """Qué puede hacer cada nivel. Los topes son del producto, no del motor."""

    name: str
    label: str
    max_rows: int | None                # filas por dataset (None = sin tope)
    max_datasets: int | None
    max_workspaces: int | None
    max_model_families: int | None      # familias que compiten a la vez
    max_budget_seconds: int             # tope del presupuesto de optimización
    sql_connectors: bool
    ai_providers: bool
    text_features: bool
    export_excel: bool
    export_watermark: bool              # marca de agua en el informe
    scoring: bool
    diagnostics: bool                   # panel interno (sólo owner)


TIERS: dict[str, Tier] = {
    "demo": Tier(
        name="demo", label="Demo",
        max_rows=50_000, max_datasets=3, max_workspaces=1,
        max_model_families=3, max_budget_seconds=60,
        sql_connectors=False, ai_providers=False, text_features=False,
        export_excel=True, export_watermark=True, scoring=False, diagnostics=False,
    ),
    "paid": Tier(
        name="paid", label="Profesional",
        max_rows=None, max_datasets=None, max_workspaces=None,
        max_model_families=None, max_budget_seconds=3600,
        sql_connectors=True, ai_providers=True, text_features=True,
        export_excel=True, export_watermark=False, scoring=True, diagnostics=False,
    ),
    "owner": Tier(
        name="owner", label="Owner",
        max_rows=None, max_datasets=None, max_workspaces=None,
        max_model_families=None, max_budget_seconds=7200,
        sql_connectors=True, ai_providers=True, text_features=True,
        export_excel=True, export_watermark=False, scoring=True, diagnostics=True,
    ),
}

DEFAULT_TIER = "demo"


class LicenseError(RuntimeError):
    """Licencia inválida, vencida o ilegible. El mensaje va a pantalla."""


# ──────────────────────────────────────────────────────── payload ─────────────
@dataclass
class License:
    id: str
    tier: str
    licensee: str
    issued_at: float
    expires_at: float | None = None
    notes: str = ""
    features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def expired(self) -> bool:
        # «>=» y no «>»: una licencia cuyo vencimiento es este instante está
        # vencida. Con «>» dependía de la resolución del reloj —en Windows es
        # de unos 16 ms— y una licencia recién vencida podía seguir valiendo.
        return self.expires_at is not None and time.time() >= self.expires_at

    @property
    def days_left(self) -> int | None:
        if self.expires_at is None:
            return None
        return max(0, int((self.expires_at - time.time()) // 86400))


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


# ───────────────────────────────────────────────────────── emisión ────────────
def generate_keypair() -> tuple[str, str]:
    """Genera un par de claves nuevo. Devuelve (privada_b64, pública_b64)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.generate()
    priv_raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    return base64.b64encode(priv_raw).decode(), base64.b64encode(pub_raw).decode()


def issue(tier: str, licensee: str, days: int | None = None,
          private_key_b64: str | None = None, notes: str = "") -> str:
    """Emite una licencia firmada. Requiere la clave privada."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if tier not in TIERS:
        raise LicenseError(f"Nivel desconocido: {tier}. Válidos: {', '.join(TIERS)}")
    key_b64 = private_key_b64 or os.environ.get("MV_LICENSE_PRIVATE_KEY", "")
    if not key_b64:
        raise LicenseError(
            "Falta la clave privada de firma. Pasala por parámetro o en "
            "MV_LICENSE_PRIVATE_KEY (se genera con `generate_keypair`).")
    priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(key_b64))

    lic = License(
        id=f"lic_{uuid.uuid4().hex[:12]}", tier=tier, licensee=licensee,
        issued_at=time.time(),
        expires_at=(time.time() + days * 86400) if days is not None else None,
        notes=notes,
    )
    payload = json.dumps(lic.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    sig = priv.sign(payload)
    return f"{PREFIX}.{_b64e(payload)}.{_b64e(sig)}"


# ────────────────────────────────────────────────────── verificación ──────────
def verify(token: str, public_key_b64: str | None = None) -> License:
    """Verifica la firma y la vigencia. Lanza `LicenseError` si algo falla."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not token or not token.strip():
        raise LicenseError("La licencia está vacía.")
    partes = token.strip().split(".")
    if len(partes) != 3 or partes[0] != PREFIX:
        raise LicenseError("El formato de la licencia no es válido. "
                           f"Se espera {PREFIX}.<datos>.<firma>")
    try:
        payload = _b64d(partes[1])
        sig = _b64d(partes[2])
    except Exception as exc:
        raise LicenseError("La licencia está corrupta o mal copiada.") from exc

    key_b64 = public_key_b64 or PUBLIC_KEY_B64
    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(key_b64))
    except Exception as exc:
        raise LicenseError("La clave pública embebida es inválida.") from exc

    try:
        pub.verify(sig, payload)
    except InvalidSignature as exc:
        raise LicenseError("La firma no corresponde: la licencia no fue emitida "
                           "por MV AutoML Studio.") from exc

    try:
        lic = License(**json.loads(payload))
    except Exception as exc:
        raise LicenseError("Los datos de la licencia no se pudieron leer.") from exc

    if lic.tier not in TIERS:
        raise LicenseError(f"La licencia declara un nivel desconocido: {lic.tier}")
    if lic.expired:
        raise LicenseError(
            f"La licencia venció el "
            f"{time.strftime('%d/%m/%Y', time.localtime(lic.expires_at))}.")
    return lic


# ──────────────────────────────────────────────────── estado activo ───────────
_ACTIVE: License | None = None
_SOURCE: str = "sin licencia"


def _store_path() -> Path:
    from ..config import settings
    return settings.data_dir / "license.key"


def activate(token: str, persist: bool = True) -> License:
    """Valida y activa una licencia; opcionalmente la guarda en el equipo."""
    global _ACTIVE, _SOURCE
    lic = verify(token)
    _ACTIVE, _SOURCE = lic, "activada"
    if persist:
        p = _store_path()
        p.write_text(token.strip(), encoding="utf-8")
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
    return lic


def deactivate() -> None:
    global _ACTIVE, _SOURCE
    _ACTIVE, _SOURCE = None, "sin licencia"
    _store_path().unlink(missing_ok=True)


def load() -> License | None:
    """Carga la licencia desde el entorno o desde el archivo guardado.

    Prioridad: variable de entorno (la usan las compilaciones owner, que la
    llevan embebida) y después el archivo del equipo.
    """
    global _ACTIVE, _SOURCE
    if _ACTIVE is not None and not _ACTIVE.expired:
        return _ACTIVE

    desde_entorno = os.environ.get("MV_LICENSE")
    if desde_entorno:
        try:
            _ACTIVE = verify(desde_entorno)
            _SOURCE = "compilación owner"
            return _ACTIVE
        except LicenseError:
            pass

    p = _store_path()
    if p.exists():
        try:
            _ACTIVE = verify(p.read_text(encoding="utf-8"))
            _SOURCE = "activada en este equipo"
            return _ACTIVE
        except LicenseError:
            _ACTIVE = None
    return _ACTIVE


def current_tier() -> Tier:
    lic = load()
    return TIERS[lic.tier] if lic else TIERS[DEFAULT_TIER]


def status() -> dict[str, Any]:
    """Estado para la interfaz: nunca devuelve el token."""
    lic = load()
    tier = current_tier()
    return {
        "tier": tier.name,
        "label": tier.label,
        "limits": asdict(tier),
        "licensed": lic is not None,
        "source": _SOURCE if lic else "sin licencia (modo demo)",
        "licensee": lic.licensee if lic else None,
        "license_id": lic.id if lic else None,
        "expires_at": lic.expires_at if lic else None,
        "days_left": lic.days_left if lic else None,
    }


# ───────────────────────────────────────────────────── aplicación ─────────────
def require(feature: str) -> None:
    """Corta la operación si el nivel actual no incluye la función.

    Se llama en el borde de la API, nunca en el medio de un cálculo: que la
    negativa llegue antes de que el usuario espere tres minutos.
    """
    tier = current_tier()
    permitido = getattr(tier, feature, False)
    if not permitido:
        raise PermissionError(
            f"«{_nombre(feature)}» no está disponible en el nivel {tier.label}. "
            f"Actualizá la licencia para habilitarlo.")


def _nombre(feature: str) -> str:
    return {
        "sql_connectors": "Conexión a servidores SQL",
        "ai_providers": "Motor de IA",
        "text_features": "Texto libre como variable",
        "scoring": "Aplicar el modelo a un dataset",
        "diagnostics": "Panel de diagnóstico",
        "export_excel": "Informe en Excel",
    }.get(feature, feature)


def cap_rows(rows: int) -> int:
    """Tope de filas del nivel; devuelve el efectivo."""
    tier = current_tier()
    return rows if tier.max_rows is None else min(rows, tier.max_rows)


def _miles(n: int) -> str:
    """1234567 → «1.234.567», que es como se escribe acá."""
    return f"{int(n):,}".replace(",", ".")


def check_rows(rows: int) -> None:
    tier = current_tier()
    if tier.max_rows is not None and rows > tier.max_rows:
        raise PermissionError(
            f"El nivel {tier.label} admite hasta {_miles(tier.max_rows)} filas por dataset "
            f"y este trae {_miles(rows)}. Actualizá la licencia para levantar el tope.")


def check_count(actual: int, feature: str) -> None:
    """Tope de cantidad (datasets, workspaces)."""
    tier = current_tier()
    limite = getattr(tier, feature, None)
    if limite is not None and actual >= limite:
        nombre = {"max_datasets": "datasets", "max_workspaces": "workspaces"}.get(feature, feature)
        raise PermissionError(
            f"El nivel {tier.label} admite hasta {limite} {nombre}. "
            f"Eliminá alguno o actualizá la licencia.")


def cap_budget(seconds: int) -> int:
    return min(int(seconds), current_tier().max_budget_seconds)


def cap_families(n: int | None) -> int | None:
    tier = current_tier()
    if tier.max_model_families is None:
        return n
    return tier.max_model_families if n is None else min(n, tier.max_model_families)
