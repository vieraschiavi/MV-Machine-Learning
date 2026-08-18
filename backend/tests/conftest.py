"""Configuración de las pruebas.

Las variables de entorno se fijan ANTES de importar la aplicación: la
configuración se resuelve en tiempo de importación, así que si el directorio
temporal se define después, las pruebas escribirían en el workspace real.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="mv-tests-"))
for var, sub in [("MV_DATA_DIR", ""), ("MV_UPLOAD_DIR", "uploads"), ("MV_DATASET_DIR", "datasets"),
                 ("MV_MODEL_DIR", "models"), ("MV_EXPORT_DIR", "exports"), ("MV_SECRETS_DIR", "secrets")]:
    os.environ[var] = str(_TMP / sub if sub else _TMP)
os.environ["MV_CHUNK_ROWS"] = "1500"
# ninguna prueba debe salir a internet: se anulan las claves del entorno
for var in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN"]:
    os.environ.pop(var, None)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    return _TMP


@pytest.fixture(scope="session")
def frame_binary() -> pd.DataFrame:
    """Dataset sintético con todos los defectos que el ETL debe encontrar."""
    rng = np.random.default_rng(11)
    n = 1200
    df = pd.DataFrame({
        "id": np.arange(1, n + 1),
        "edad": rng.integers(18, 80, n).astype(float),
        "ingreso": rng.gamma(2, 25_000, n).round(2),
        "region": rng.choice(["Norte", "Sur", "Este", "Oeste"], n),
        "score": rng.choice(list("ABCDE"), n),
        "constante": "X",
        "casi_vacia": np.where(rng.random(n) < 0.95, np.nan, 1.0),
        "fecha": pd.date_range("2024-01-01", periods=n, freq="D").astype(str),
        "monto_texto": [f"$ {v:,.2f}".replace(",", "|").replace(".", ",").replace("|", ".")
                        for v in rng.gamma(2, 1000, n)],
    })
    p = 1 / (1 + np.exp(-(-1.0 + 0.00002 * df.ingreso - 0.03 * (df.edad - 45))))
    df["objetivo"] = rng.binomial(1, p)
    df.loc[rng.choice(n, 60, replace=False), "ingreso"] = np.nan
    return df


@pytest.fixture(scope="session")
def frame_regression() -> pd.DataFrame:
    rng = np.random.default_rng(5)
    n = 900
    df = pd.DataFrame({
        "x1": rng.normal(0, 1, n),
        "x2": rng.gamma(2, 3, n),
        "cat": rng.choice(list("abcd"), n),
        "ruido": rng.normal(0, 1, n),
    })
    df["valor"] = (1000 + 400 * df.x1 + 150 * df.x2 + (df.cat == "a") * 700
                   + rng.normal(0, 120, n)).clip(0)
    return df


@pytest.fixture(scope="session")
def csv_binary(tmp_root: Path, frame_binary: pd.DataFrame) -> Path:
    path = tmp_root / "binary.csv"
    frame_binary.to_csv(path, sep=";", index=False, decimal=",", encoding="latin-1")
    return path


@pytest.fixture(scope="session")
def dataset_binary(csv_binary: Path):
    from app.core import storage
    return storage.ingest_file(csv_binary, "binario")


@pytest.fixture(scope="session")
def client():
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c
