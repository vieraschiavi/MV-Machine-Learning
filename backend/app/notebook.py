"""MV AutoML dentro de un notebook de Python (Microsoft Fabric, Jupyter, Databricks).

En un notebook de Fabric el dato ya está adentro: sale del Lakehouse a un
DataFrame de Spark y no hay archivo que subir ni servidor que levantar. Este
módulo expone el mismo motor que usa el programa de escritorio, con el mismo
protocolo de validación —entrenamiento, selección y **holdout ciego**—, para
llamarlo desde una celda::

    from app import notebook as mv

    datos = spark.sql("SELECT * FROM VentasLH.clientes").toPandas()
    modelo = mv.entrenar(datos, objetivo="compro", excluir=["cliente_id"])
    print(modelo.resumen())

    modelo.guardar("/lakehouse/default/Files/mv/modelo_compras")
    modelo.para_powerbi("/lakehouse/default/Files/mv/salida", datos=datos)

Dos aclaraciones que importan:

* **No es una puerta de atrás a la licencia.** Los topes del nivel (filas,
  presupuesto, familias de modelos, scoring) se aplican igual que en la API.
* **Se escribe en rutas locales o montadas**, no en URLs de OneLake. En un
  notebook de Fabric la ruta montada es ``/lakehouse/default/Files/...``; una
  ``abfss://`` se copia después con ``notebookutils``.
"""
from __future__ import annotations

import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .config import settings
from .core import automl as A
from .core import licensing as L
from .core import registry as R

ARCHIVO_MODELO = "modelo.joblib"
ARCHIVO_FICHA = "ficha.json"
FORMATOS = ("parquet", "csv")

# Esquemas que no se pueden abrir con una ruta de archivo común. Se listan para
# poder explicar qué hacer en su lugar, en vez de fallar con un ENOENT.
REMOTOS = ("abfss://", "wasbs://", "wasb://", "s3://", "s3a://", "gs://",
           "http://", "https://", "dbfs:/")

_SEMAFORO = {"ok": "Se puede usar", "revisar": "Hay que revisarlo antes de usarlo",
             "alerta": "No lo uses todavía"}


# ─────────────────────────────────────────────────────── entrada de datos ────
def a_pandas(datos: Any) -> pd.DataFrame:
    """Lo que venga del notebook, convertido a pandas.

    Fabric entrega DataFrames de Spark; Polars y PyArrow aparecen en los
    notebooks de quien ya trabaja con datos. Todos saben convertirse solos: lo
    único que hace falta es preguntarles.
    """
    if isinstance(datos, pd.DataFrame):
        return datos
    for metodo in ("toPandas", "to_pandas"):          # Spark · Polars · PyArrow
        conversor = getattr(datos, metodo, None)
        if callable(conversor):
            convertido = conversor()
            if isinstance(convertido, pd.DataFrame):
                return convertido
    if isinstance(datos, (dict, list)):
        return pd.DataFrame(datos)
    raise TypeError(
        f"No sé cómo leer un {type(datos).__name__}. Pasá un DataFrame de pandas, uno de "
        "Spark (Fabric), uno de Polars, una tabla de PyArrow, o un diccionario de columnas.")


def _tabla(datos: Any, quien: str) -> pd.DataFrame:
    df = a_pandas(datos)
    if df.empty:
        raise ValueError(f"{quien} llegó sin filas: no hay nada que procesar.")
    return df


def _columnas(df: pd.DataFrame, objetivo: str) -> None:
    if objetivo in df.columns:
        return
    cerca = [c for c in df.columns if objetivo.lower() in str(c).lower()]
    pista = f" ¿Quisiste decir «{cerca[0]}»?" if cerca else ""
    raise ValueError(
        f"La columna objetivo «{objetivo}» no está en la tabla.{pista} "
        f"Columnas disponibles: {', '.join(map(str, df.columns[:20]))}"
        + (" …" if len(df.columns) > 20 else ""))


# ──────────────────────────────────────────────────────────── escritura ──────
def _ruta_escribible(destino: str | Path, verbo: str) -> Path:
    texto = str(destino)
    for esquema in REMOTOS:
        if texto.lower().startswith(esquema):
            raise ValueError(
                f"No se puede {verbo} directo en «{texto}»: es una dirección remota, no una "
                "carpeta del sistema de archivos. En un notebook de Fabric usá la ruta montada "
                "del Lakehouse (por ejemplo «/lakehouse/default/Files/mv»); si necesitás dejarlo "
                "en otro workspace, escribí primero en la ruta montada y copiá con "
                "notebookutils.fs.cp a la dirección abfss://.")
    return Path(texto).expanduser()


def _escribir(df: pd.DataFrame, carpeta: Path, nombre: str, formato: str) -> Path:
    destino = carpeta / f"{nombre}.{formato}"
    if formato == "parquet":
        df.to_parquet(destino, index=False)
    else:
        df.to_csv(destino, index=False, encoding="utf-8")
    return destino


def _json_seguro(valor: Any) -> Any:
    if isinstance(valor, np.generic):
        return valor.item()
    if isinstance(valor, np.ndarray):
        return valor.tolist()
    if isinstance(valor, Path):
        return str(valor)
    return str(valor)


# ─────────────────────────────────────────────────────────── entrenamiento ───
def entrenar(datos: Any, objetivo: str, *,
             excluir: Sequence[str] = (),
             tiempo: str | None = None,
             tarea: str = "auto",
             metrica: str | None = None,
             presupuesto_segundos: int = 120,
             max_modelos: int = 6,
             seleccion_de_variables: bool = True,
             explicacion_shap: bool = True,
             progreso: bool = False) -> Resultado:
    """Entrena sobre una tabla del notebook y devuelve el modelo con su informe.

    ``tiempo`` es la columna de fecha: si se declara, las tres ventanas quedan
    consecutivas (walk-forward) en vez de repartidas al azar. Entrenar con el
    futuro y predecir el pasado infla todas las métricas, y en una tabla de
    negocio ese error es la regla, no la excepción.
    """
    df = _tabla(datos, "La tabla de entrenamiento")
    _columnas(df, objetivo)

    # Los topes del nivel se aplican antes de empezar, no después de que el
    # notebook se pasó tres minutos entrenando.
    L.check_rows(len(df))

    if len(df) > settings.max_train_rows:
        df = df.sample(n=settings.max_train_rows, random_state=42).reset_index(drop=True)

    cfg = A.TrainConfig(
        target=objetivo, task=tarea, time_column=tiempo, exclude=list(excluir),
        metric=metrica,
        budget_seconds=L.cap_budget(presupuesto_segundos),
        max_models=L.cap_families(max_modelos) or max_modelos,
        feature_selection=seleccion_de_variables,
        shap=explicacion_shap,
    )

    def avisar(pct: float, msg: str) -> None:
        if progreso:
            print(f"{pct:3.0f}%  {msg}")      # noqa: T201 - en un notebook, la salida es print

    salida = A.train(df, cfg, avisar)
    return Resultado(salida["report"], salida["bundle"])


def cargar(carpeta: str | Path) -> Resultado:
    """Vuelve a levantar un modelo guardado con :meth:`Resultado.guardar`."""
    ruta = _ruta_escribible(carpeta, "leer")
    modelo, ficha = ruta / ARCHIVO_MODELO, ruta / ARCHIVO_FICHA
    if not modelo.exists():
        raise FileNotFoundError(
            f"No hay un modelo guardado en «{ruta}»: falta el archivo {ARCHIVO_MODELO}.")
    informe = {}
    if ficha.exists():
        informe = json.loads(ficha.read_text(encoding="utf-8")).get("informe", {})
    return Resultado(informe, joblib.load(modelo))


def predecir(modelo: Resultado | str | Path, datos: Any,
             conservar: Sequence[str] | None = None) -> pd.DataFrame:
    """Aplica un modelo —ya cargado o guardado en una carpeta— a filas nuevas."""
    res = modelo if isinstance(modelo, Resultado) else cargar(modelo)
    return res.predecir(datos, conservar=conservar)


# ──────────────────────────────────────────────────────────────── resultado ──
class Resultado:
    """El modelo entrenado más su informe, con lo que se necesita en un notebook."""

    def __init__(self, informe: dict[str, Any], bundle: dict[str, Any]) -> None:
        self.informe = informe
        self.bundle = bundle

    def __repr__(self) -> str:                                  # pragma: no cover
        r = self.resumen()
        return (f"<MV AutoML · {r.get('modelo')} · {r.get('metrica')}="
                f"{r.get('holdout')} en holdout ciego>")

    # ── lectura del informe ──────────────────────────────────────────────────
    def resumen(self) -> dict[str, Any]:
        """Lo esencial en un diccionario: qué modelo ganó y cuánto rinde de verdad."""
        inf = self.informe
        campeon = inf.get("champion", {})
        metrica = inf.get("metric")
        veredicto = inf.get("verdict", {}) or {}
        notas = [n.get("text", "") for n in veredicto.get("notes", [])]
        titular = _SEMAFORO.get(veredicto.get("level", ""), "Sin veredicto")
        return {
            "objetivo": inf.get("target"),
            "tarea": inf.get("task_label") or inf.get("task"),
            "modelo": campeon.get("model"),
            "metrica": metrica,
            "seleccion": campeon.get("selection", {}).get(metrica),
            "holdout": campeon.get("holdout", {}).get(metrica),
            "brecha": campeon.get("gap"),
            "filas": inf.get("rows_used"),
            "variables": inf.get("n_features_used"),
            "particion": inf.get("split", {}).get("mode"),
            "segundos": inf.get("seconds"),
            "semaforo": veredicto.get("level"),
            "veredicto": f"{titular}. {notas[0]}" if notas else titular,
            "notas": notas,
        }

    def tabla_modelos(self) -> pd.DataFrame:
        """El leaderboard: qué midió cada familia en selección y en holdout."""
        metrica = self.informe.get("metric")
        filas = [{
            "modelo": b.get("model"),
            "tipo": b.get("type"),
            "seleccion": b.get("selection", {}).get(metrica),
            "holdout": b.get("holdout", {}).get(metrica),
            "calibrado": b.get("calibrated"),
        } for b in self.informe.get("leaderboard", [])]
        return pd.DataFrame(filas, columns=["modelo", "tipo", "seleccion", "holdout", "calibrado"])

    def importancias(self, n: int = 20) -> pd.DataFrame:
        """Qué variables sostienen el modelo, medido sobre el holdout ciego.

        El aporte es la caída de la métrica al romper la relación de esa columna
        con el objetivo (permutación). Cuando no se pudo medir por permutación
        se cae a la importancia nativa del algoritmo, y la columna «fuente» lo
        dice: no es lo mismo y no se disimula.
        """
        filas = []
        for r in self.informe.get("features", {}).get("ranking", [])[:n]:
            perm = r.get("permutation_drop_pct")
            filas.append({
                "variable": r.get("column"),
                "aporte": perm if perm is not None else r.get("native"),
                "fuente": "permutación" if perm is not None else "nativa",
                "direccion": r.get("shap_direction"),
            })
        return pd.DataFrame(filas, columns=["variable", "aporte", "fuente", "direccion"])

    def metricas(self) -> pd.DataFrame:
        """Todas las métricas del campeón, en formato largo (métrica · ventana · valor)."""
        campeon = self.informe.get("champion", {})
        filas = []
        for ventana in ("seleccion", "holdout"):
            clave = "selection" if ventana == "seleccion" else "holdout"
            for nombre, valor in (campeon.get(clave) or {}).items():
                if valor is None or (isinstance(valor, float) and not np.isfinite(valor)):
                    continue
                filas.append({"metrica": nombre, "ventana": ventana, "valor": float(valor),
                              "es_decision": nombre == self.informe.get("metric")})
        return pd.DataFrame(filas, columns=["metrica", "ventana", "valor", "es_decision"])

    # ── uso del modelo ───────────────────────────────────────────────────────
    def predecir(self, datos: Any, conservar: Sequence[str] | None = None) -> pd.DataFrame:
        """Aplica el modelo a filas nuevas; devuelve un DataFrame de pandas."""
        L.require("scoring")
        df = _tabla(datos, "La tabla a predecir").reset_index(drop=True)
        pred = R.predict_frame(self.bundle, df).reset_index(drop=True)
        if not conservar:
            return pred
        faltan = [c for c in conservar if c not in df.columns]
        if faltan:
            raise ValueError(f"No están en la tabla las columnas a conservar: {', '.join(faltan)}")
        return pd.concat([df[list(conservar)], pred], axis=1)

    # ── persistencia ─────────────────────────────────────────────────────────
    def guardar(self, carpeta: str | Path) -> Path:
        """Deja el modelo y su ficha en una carpeta: sobrevive al notebook."""
        ruta = _ruta_escribible(carpeta, "guardar")
        ruta.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.bundle, ruta / ARCHIVO_MODELO, compress=3)
        ficha = {"creado_en": time.time(), "resumen": self.resumen(), "informe": self.informe}
        (ruta / ARCHIVO_FICHA).write_text(
            json.dumps(ficha, ensure_ascii=False, indent=2, default=_json_seguro),
            encoding="utf-8")
        return ruta

    def para_powerbi(self, carpeta: str | Path, datos: Any = None,
                     conservar: Sequence[str] | None = None,
                     formato: str = "parquet") -> dict[str, Path]:
        """Deja los resultados en archivos que Power BI lee directo del Lakehouse.

        Tres tablas, más un resumen de una fila:

        * ``predicciones`` — una fila por caso, con la predicción y su probabilidad.
        * ``metricas`` — formato largo (métrica · ventana · valor): un visual sale
          sin pivotear nada a mano.
        * ``importancias`` — qué variable sostiene al modelo y cuánto aporta.
        * ``resumen`` — una fila con el veredicto, para la tarjeta del tablero.

        ``datos`` es opcional: sin él escribe sólo lo que describe al modelo.
        """
        if formato not in FORMATOS:
            raise ValueError(f"formato «{formato}» desconocido: usá {' o '.join(FORMATOS)}.")
        ruta = _ruta_escribible(carpeta, "guardar")
        ruta.mkdir(parents=True, exist_ok=True)

        salida: dict[str, Path] = {}
        if datos is not None:
            salida["predicciones"] = _escribir(
                self.predecir(datos, conservar=conservar), ruta, "predicciones", formato)
        salida["metricas"] = _escribir(self.metricas(), ruta, "metricas", formato)
        salida["importancias"] = _escribir(self.importancias(n=50), ruta, "importancias", formato)

        r = self.resumen()
        resumen = pd.DataFrame([{
            "objetivo": r["objetivo"], "tarea": r["tarea"], "modelo": r["modelo"],
            "metrica": r["metrica"], "holdout": r["holdout"], "seleccion": r["seleccion"],
            "brecha": r["brecha"], "filas": r["filas"], "variables": r["variables"],
            "semaforo": r["semaforo"], "veredicto": r["veredicto"],
            "entrenado_en": pd.Timestamp.now(tz="UTC").tz_localize(None),
        }])
        salida["resumen"] = _escribir(resumen, ruta, "resumen", formato)
        return salida
