"""Punto de entrada del backend para PyInstaller.

PyInstaller no sigue imports dinámicos: acá se importa todo lo que el motor
carga en tiempo de ejecución (las familias del zoo, los motores de Excel, los
drivers SQL) para que el análisis estático los incluya en el binario.
"""
from __future__ import annotations

# ruff: noqa: E402
import multiprocessing
import os
import sys

multiprocessing.freeze_support()          # obligatorio en Windows congelado

# ── imports que el análisis estático no ve ───────────────────────────────────
import catboost  # noqa: F401
import lightgbm  # noqa: F401
import openpyxl  # noqa: F401
import optuna  # noqa: F401
import pymssql  # noqa: F401
import pymysql  # noqa: F401
import shap  # noqa: F401
import sklearn.ensemble  # noqa: F401
import sklearn.linear_model  # noqa: F401
import sklearn.naive_bayes  # noqa: F401
import sklearn.neighbors  # noqa: F401
import sklearn.neural_network  # noqa: F401
import sklearn.tree  # noqa: F401
import xgboost  # noqa: F401
import xlsxwriter  # noqa: F401

try:
    import psycopg2  # noqa: F401
except ImportError:
    pass                       # opcional: sin PostgreSQL el resto funciona

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)

from app.main import app  # noqa: E402


def main() -> None:
    import uvicorn

    host = os.environ.get("MV_HOST", "127.0.0.1")
    port = int(os.environ.get("MV_PORT", 8474))
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
