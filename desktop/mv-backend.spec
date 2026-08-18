# -*- mode: python -*-
"""Spec de PyInstaller para el backend de MV AutoML Studio (onedir)."""
import os
from PyInstaller.utils.hooks import (collect_data_files, collect_dynamic_libs,
                                     collect_submodules)

raiz = os.path.abspath(os.path.join(SPECPATH, ".."))

# los submódulos *.testing de los frameworks de ML arrastran pytest/hypothesis:
# se filtran, no van en un binario de producción
sin_tests = lambda n: "testing" not in n and ".tests" not in n

datas, binaries, hidden = [], [], []
for paquete in ["lightgbm", "xgboost", "catboost", "shap", "duckdb", "pyarrow"]:
    datas += collect_data_files(paquete)
    binaries += collect_dynamic_libs(paquete)
    hidden += collect_submodules(paquete, filter=sin_tests)

hidden += collect_submodules("sklearn", filter=sin_tests)
hidden += collect_submodules("uvicorn")
hidden += collect_submodules("anyio")
hidden += ["pymssql", "pymysql", "xlsxwriter", "openpyxl", "optuna",
           "app", "app.main"]

# CUDA no viaja en un instalador de escritorio: 450 MB de bibliotecas de GPU
# que el motor no usa (los árboles corren en CPU). En Windows además no vienen.
binaries = [(src, dst) for src, dst in binaries if "nvidia" not in src.lower()]
datas = [(src, dst) for src, dst in datas
         if "nvidia" not in str(src).lower() and "/test" not in str(src)]

a = Analysis(
    [os.path.join(SPECPATH, "backend_entry.py")],
    pathex=[os.path.join(raiz, "backend")],
    datas=datas + [(os.path.join(raiz, "backend", "app"), "app")],
    binaries=binaries,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "IPython", "jupyter", "pytest", "PIL",
              "hypothesis", "numba", "llvmlite",
              "nvidia", "nvidia.cuda_runtime", "nvidia.cublas", "nvidia.nccl"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="mv-backend",
          console=True, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, name="mv-backend")
