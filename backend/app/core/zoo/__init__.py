"""Registro extensible de familias de modelos.

Patrón tomado del component registry de DashAI y adaptado: cada familia es un
`ModelSpec` declarado en un archivo de este paquete y registrado con
`@register`. Agregar un modelo nuevo es agregar un archivo acá —no se toca el
motor— y el modelo entra automáticamente en el protocolo de tres ventanas,
la calibración y la comparación contra la combinación.

La diferencia con DashAI es deliberada: allá cada modelo declara su schema de
UI; acá declara su espacio de búsqueda de Optuna y su prioridad, porque lo que
este motor automatiza es la optimización y la validación, no el formulario.
"""
from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_REGISTRY: dict[str, ModelSpec] = {}
_DISCOVERED = False


@dataclass(frozen=True)
class ModelSpec:
    """Declaración completa de una familia de modelos."""

    name: str                              # identificador estable (snake_case)
    label: str                             # nombre para mostrar
    matrix: str                            # "tree" (ordinal+NaN) | "linear" (one-hot escalado)
    tasks: tuple[str, ...]                 # subconjunto de binary/multiclass/regression
    make: Callable[[str, dict, int], Any]  # (task, params, random_state) -> estimador
    space: Callable[[Any], dict]           # (trial de Optuna) -> params
    default: dict[str, Any] = field(default_factory=dict)
    priority: int = 50                     # menor = compite primero
    max_rows: int | None = None            # None = sin tope; si no, se omite en datasets grandes
    available: Callable[[], bool] = lambda: True
    description: str = ""


def register(spec: ModelSpec) -> ModelSpec:
    if spec.matrix not in ("tree", "linear"):
        raise ValueError(f"{spec.name}: matrix debe ser 'tree' o 'linear'")
    if not spec.tasks:
        raise ValueError(f"{spec.name}: declarar al menos una tarea")
    _REGISTRY[spec.name] = spec
    return spec


def _discover() -> None:
    """Importa todos los módulos del paquete; cada import registra sus specs."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    for mod in pkgutil.iter_modules(__path__):
        if not mod.name.startswith("_"):
            importlib.import_module(f"{__name__}.{mod.name}")
    _DISCOVERED = True


def all_specs() -> dict[str, ModelSpec]:
    _discover()
    return dict(_REGISTRY)


def catalog(task: str | None = None) -> list[dict[str, Any]]:
    """Ficha pública del catálogo, para la API y la interfaz."""
    _discover()
    out = []
    for s in sorted(_REGISTRY.values(), key=lambda s: s.priority):
        if task and task not in s.tasks:
            continue
        out.append({
            "name": s.name, "label": s.label, "matrix": s.matrix,
            "tasks": list(s.tasks), "priority": s.priority,
            "max_rows": s.max_rows, "available": bool(s.available()),
            "description": s.description,
        })
    return out


def build_zoo(task: str, cfg, n_rows: int, n_feats: int) -> dict[str, dict[str, Any]]:
    """Selecciona las familias que compiten, en el formato que consume el motor.

    Respeta `cfg.models` (lista explícita de familias) si viene; si no, toma
    las disponibles para la tarea y el tamaño, ordenadas por prioridad.
    """
    _discover()
    wanted = list(getattr(cfg, "models", None) or [])
    rs = cfg.random_state
    out: dict[str, dict[str, Any]] = {}
    specs = sorted(_REGISTRY.values(), key=lambda s: s.priority)
    for s in specs:
        if wanted and s.name not in wanted:
            continue
        if task not in s.tasks or not s.available():
            continue
        if not wanted and s.max_rows is not None and n_rows > s.max_rows:
            continue
        out[s.name] = {
            "matrix": s.matrix,
            "space": s.space,
            "default": dict(s.default),
            "make": (lambda p, _s=s: _s.make(task, p, rs)),
            "label": s.label,
        }
    return out
