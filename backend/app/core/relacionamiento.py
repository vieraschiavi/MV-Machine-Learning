"""El «siguiente mejor contenido» para cada persona de la base propia, y sus KPIs.

Es el mismo tipo de algoritmo que usa un marketplace para recomendar («a
quienes les interesó esto también les interesó aquello», más el historial de
cada uno), con dos diferencias que lo hacen legal en salud:

* **Los datos son propios y consentidos.** Sólo lo que pasó en nuestros
  canales (mails, web, programa de pacientes) con gente que eligió entrar.
  Nada de redes ajenas ni de inferir enfermedades.
* **Sólo recomienda lo que se puede enviar.** Antes de puntuar, cada par
  contacto × contenido pasa por las reglas de ``consentimiento``: un
  medicamento bajo receta nunca se le promociona a un paciente; a él le
  llegan concientización sin marca, el programa de pacientes o el beneficio
  del producto que declaró que le recetaron.

La personalización (el historial propio y el «a otros como vos») se usa sólo
con el consentimiento de perfilado; sin él, la persona recibe lo elegible
ordenado por lo que mejor funciona en general.

Interacciones: una fila por evento, con ``id_contacto``, ``id_contenido``,
``fecha`` y ``evento`` (envio, apertura, clic, inscripcion, canje, baja, queja).
"""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd

from . import consentimiento as K

EVENTOS = ("envio", "apertura", "clic", "inscripcion", "canje", "baja", "queja")
INTERES = ("clic", "inscripcion", "canje")
CONVERSION = ("inscripcion", "canje")
# Lo que más le sirve a la persona pesa más que lo comercial.
PESO_TIPO = {"programa_paciente": 3.0, "concientizacion": 2.0, "educacion_medica": 2.0,
             "beneficio": 1.5, "promocion_marca": 1.5}
VENTANA_DIAS = 30
MAX_CELDAS = 3_000_000
COLUMNAS_INTERACCIONES = ["id_contacto", "id_contenido", "fecha", "evento"]


def _div(a: Any, b: Any) -> Any:
    """División que devuelve NaN (y no infinito ni error) cuando no hay base."""
    a = pd.Series(a, dtype=float) if np.ndim(a) else float(a)
    b = pd.Series(b, dtype=float) if np.ndim(b) else float(b)
    if isinstance(b, pd.Series):
        return a / b.where(b > 0)
    return a / b if b > 0 else np.nan


def a_fecha(serie: pd.Series) -> pd.Series:
    """Fechas sin zona horaria: «2026-10-01» y «2026-10-01T13:00:00Z» se comparan entre sí."""
    return pd.to_datetime(serie, errors="coerce", utc=True).dt.tz_localize(None)


def _ventana(inter: pd.DataFrame, hoy: pd.Timestamp) -> pd.DataFrame:
    """Los envíos de los últimos 30 días, hoy entero incluido (un envío de hoy a las 9 cuenta)."""
    fin = hoy.normalize() + pd.Timedelta(days=1)
    return inter[(inter["evento"] == "envio") & (inter["fecha"] >= fin - pd.Timedelta(days=VENTANA_DIAS))
                 & (inter["fecha"] < fin)]


def preparar_interacciones(df: pd.DataFrame | None) -> tuple[pd.DataFrame, list[str]]:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUMNAS_INTERACCIONES), []
    d = df.copy()
    d.columns = [K._clave(c).replace(" ", "_") for c in d.columns]
    faltan = [c for c in COLUMNAS_INTERACCIONES if c not in d.columns]
    if faltan:
        raise ValueError(f"A la tabla de interacciones le faltan columnas: {', '.join(faltan)}.")
    avisos: list[str] = []
    d["evento"] = d["evento"].map(K._clave)
    raros = ~d["evento"].isin(EVENTOS)
    if raros.any():
        avisos.append(f"Se ignoraron {int(raros.sum())} interacción(es) con eventos desconocidos "
                      f"({', '.join(sorted(set(d.loc[raros, 'evento']))[:5])}). Válidos: {', '.join(EVENTOS)}.")
    d["fecha"] = a_fecha(d["fecha"])
    sin_fecha = d["fecha"].isna() & ~raros
    if sin_fecha.any():
        avisos.append(f"Se ignoraron {int(sin_fecha.sum())} interacción(es) sin fecha válida.")
    d = d[~raros & ~sin_fecha]
    d["id_contacto"] = K.normalizar_id(d["id_contacto"])
    d["id_contenido"] = K.normalizar_id(d["id_contenido"])
    return d[COLUMNAS_INTERACCIONES].reset_index(drop=True), avisos


def _bajas_por_evento(contactos: pd.DataFrame, inter: pd.DataFrame, avisos: list[str]) -> pd.DataFrame:
    """Una baja registrada como evento vale aunque el CRM todavía no la tenga."""
    ids = set(inter.loc[inter["evento"] == "baja", "id_contacto"])
    pend = contactos["id_contacto"].isin(ids) & ~contactos["baja"]
    if not pend.any():
        return contactos
    avisos.append(f"{int(pend.sum())} contacto(s) pidieron la baja en un envío y el CRM no la tiene: "
                  "se respeta igual. Hay que registrarla en el CRM.")
    return contactos.assign(baja=contactos["baja"] | pend)


# ── recomendación ───────────────────────────────────────────────────────────
def _similitud(inter: pd.DataFrame) -> pd.DataFrame:
    """Coseno entre contenidos por las personas a las que les interesaron ambos."""
    eng = inter.loc[inter["evento"].isin(INTERES), ["id_contacto", "id_contenido"]].drop_duplicates()
    if eng.empty:
        return pd.DataFrame(columns=["origen", "id_contenido", "sim"])
    n = eng["id_contenido"].value_counts()
    par = eng.merge(eng, on="id_contacto", suffixes=("_o", ""))
    par = par[par["id_contenido_o"] != par["id_contenido"]]
    co = par.groupby(["id_contenido_o", "id_contenido"]).size().rename("co").reset_index()
    co["sim"] = co["co"] / np.sqrt(co["id_contenido_o"].map(n) * co["id_contenido"].map(n))
    # Con una sola persona en común no hay patrón: es una coincidencia.
    co = co[co["co"] >= 2]
    return co.rename(columns={"id_contenido_o": "origen"})[["origen", "id_contenido", "sim"]]


def _popularidad(inter: pd.DataFrame, contenidos: pd.DataFrame) -> pd.Series:
    """Interés por envío de cada contenido, suavizado hacia el promedio (pocos envíos ≈ promedio)."""
    env = inter[inter["evento"] == "envio"].groupby("id_contenido").size()
    intr = inter[inter["evento"].isin(INTERES)].groupby("id_contenido")["id_contacto"].nunique()
    base = float(_div(intr.sum(), env.sum())) if env.sum() else 0.0
    base = 0.0 if np.isnan(base) else min(base, 1.0)
    ids = contenidos["id_contenido"]
    e = ids.map(env).fillna(0)
    i = ids.map(intr).fillna(0)
    return pd.Series(((i + 10 * base) / (e + 10)).clip(0, 1).values, index=ids.values)


def _afinidad(inter: pd.DataFrame, contenidos: pd.DataFrame) -> pd.DataFrame:
    """Para cada persona y tipo de contenido: cuánto le interesa, suavizado (0,5 = sin señal)."""
    tipo = contenidos.set_index("id_contenido")["tipo"]
    d = inter.assign(tipo=inter["id_contenido"].map(tipo)).dropna(subset=["tipo"])
    env = d[d["evento"] == "envio"].groupby(["id_contacto", "tipo"]).size()
    intr = d[d["evento"].isin(INTERES)].groupby(["id_contacto", "tipo"])["id_contenido"].nunique()
    t = pd.concat({"env": env, "int": intr}, axis=1).fillna(0)
    base = t["env"].where(t["env"] > 0, t["int"])      # un clic sin envío registrado cuenta como envío
    t["afinidad"] = (t["int"].clip(upper=base) + 1) / (base + 2)
    return t[["afinidad"]].reset_index()


def recomendar(contactos: pd.DataFrame, contenidos: pd.DataFrame, interacciones: pd.DataFrame,
               *, hoy: pd.Timestamp, ajustes: dict | None = None, por_contacto: int = 3,
               elegibilidad: pd.DataFrame | None = None) -> pd.DataFrame:
    """Hasta `por_contacto` contenidos por persona, sólo entre los que se le pueden enviar."""
    eleg = elegibilidad if elegibilidad is not None else K.matriz_elegibilidad(contactos, contenidos, ajustes)
    cand = eleg.loc[eleg["motivo"] == "", ["id_contacto", "id_contenido"]]
    inter = interacciones
    recientes = _ventana(inter, hoy)
    # Fuera: lo enviado hace poco, en lo que ya se inscribió o canjeó, y lo que motivó una queja.
    fuera = pd.concat([recientes[["id_contacto", "id_contenido"]],
                       inter.loc[inter["evento"].isin(CONVERSION + ("queja",)), ["id_contacto", "id_contenido"]]])
    if not fuera.empty:
        cand = cand.merge(fuera.drop_duplicates().assign(_x=1), how="left", on=["id_contacto", "id_contenido"])
        cand = cand[cand["_x"].isna()].drop(columns="_x")
    # Tope de frecuencia: lo que queda del cupo de 30 días de su país.
    tope = contactos.set_index("id_contacto")["pais"].map(lambda p: K.politica(p, ajustes).frecuencia_max_30d)
    cupo = (tope - recientes.groupby("id_contacto").size().reindex(tope.index).fillna(0)).clip(lower=0)
    cupo = cupo.clip(upper=por_contacto)
    cand = cand[cand["id_contacto"].map(cupo).fillna(0) > 0]
    if cand.empty:
        return pd.DataFrame(columns=["id_contacto", "rango", "id_contenido", "titulo", "tipo",
                                     "puntaje", "personalizado", "motivo"])
    return _puntuar(cand, contactos, contenidos, inter, cupo)


def _puntuar(cand: pd.DataFrame, contactos: pd.DataFrame, contenidos: pd.DataFrame,
             inter: pd.DataFrame, cupo: pd.Series) -> pd.DataFrame:
    cont = contenidos.set_index("id_contenido")
    per = contactos.set_index("id_contacto")
    d = cand.copy()
    d["tipo"] = d["id_contenido"].map(cont["tipo"])
    d["titulo"] = d["id_contenido"].map(cont["titulo"])
    d["personalizado"] = d["id_contacto"].map(per["consiente_perfilado"]).astype(bool)
    area = d["id_contenido"].map(cont["area_clave"])
    areas = d["id_contacto"].map(per["areas_interes"])
    d["declarada"] = [bool(a) and a in s for a, s in zip(area, areas, strict=True)]
    d["pop"] = d["id_contenido"].map(_popularidad(inter, contenidos)).fillna(0)
    d = d.merge(_afinidad(inter, contenidos), how="left", on=["id_contacto", "tipo"])
    d["afinidad"] = d["afinidad"].fillna(0.5)
    # «A quienes les interesó X también les interesó esto», desde lo que le interesó a la persona.
    sim = _similitud(inter)
    suyos = inter.loc[inter["evento"].isin(INTERES), ["id_contacto", "id_contenido"]].drop_duplicates()
    vecinos = suyos.rename(columns={"id_contenido": "origen"}).merge(sim, on="origen")
    if not vecinos.empty:
        vecinos = vecinos.sort_values("sim", ascending=False).drop_duplicates(["id_contacto", "id_contenido"])
        d = d.merge(vecinos, how="left", on=["id_contacto", "id_contenido"])
    else:
        d["sim"], d["origen"] = np.nan, None
    d["sim"] = d["sim"].fillna(0)
    p = d["personalizado"]
    d["puntaje"] = (d["tipo"].map(PESO_TIPO).fillna(1) + 2 * d["declarada"] + 2 * d["pop"]
                    + p * (3 * (d["afinidad"] - 0.5) + 3 * d["sim"])).round(3)
    d["motivo"] = [_por_que(r, cont) for r in d.to_dict("records")]
    d = d.sort_values(["id_contacto", "puntaje", "id_contenido"], ascending=[True, False, True])
    d["rango"] = d.groupby("id_contacto").cumcount() + 1
    d = d[d["rango"] <= d["id_contacto"].map(cupo)]
    return d[["id_contacto", "rango", "id_contenido", "titulo", "tipo", "puntaje", "personalizado",
              "motivo"]].reset_index(drop=True)


def _por_que(r: dict[str, Any], cont: pd.DataFrame) -> str:
    partes = []
    if r["declarada"]:
        partes.append("declaró interés en el área")
    if r["personalizado"] and r["sim"] > 0 and r.get("origen") in cont.index:
        partes.append(f"a quienes les interesó «{cont.at[r['origen'], 'titulo'] or r['origen']}» "
                      "también les interesó")
    if r["personalizado"] and r["afinidad"] > 0.55:
        partes.append("suele abrir este tipo de contenido")
    if r["pop"] >= 0.15:
        partes.append("de lo que mejor funciona")
    return "; ".join(partes) or "elegible y todavía no se le envió"


# ── KPIs y auditoría ────────────────────────────────────────────────────────
def _con_evento(inter: pd.DataFrame, eventos: tuple[str, ...]) -> set[str]:
    return set(inter.loc[inter["evento"].isin(eventos), "id_contacto"])


def embudo(contactos: pd.DataFrame, inter: pd.DataFrame, ajustes: dict | None = None) -> pd.DataFrame:
    """De captados a convertidos, por país, con una fila «Total»."""
    pol = contactos["pais"].map(lambda p: K.politica(p, ajustes))
    contactable = (contactos["consiente_contacto"] & ~contactos["baja"]
                   & (contactos["doble_optin"] | ~pol.map(lambda p: p.doble_optin_obligatorio)))
    ids = contactos["id_contacto"]
    d = pd.DataFrame({
        "pais": contactos["pais"], "captados": 1, "contactables": contactable,
        "con_marketing": contactable & contactos["consiente_marketing"],
        "con_salud": contactable & contactos["consiente_salud"],
        "con_perfilado": contactable & contactos["consiente_perfilado"],
        "alcanzados": ids.isin(_con_evento(inter, ("envio",))),
        "activos": ids.isin(_con_evento(inter, ("apertura", "clic"))),
        "convertidos": ids.isin(_con_evento(inter, CONVERSION)),
        "bajas": contactos["baja"]})
    t = d.groupby("pais").sum(numeric_only=True).astype(int).reset_index()
    total = t.drop(columns="pais").sum().to_frame().T.assign(pais="Total")
    t = pd.concat([t, total[t.columns]], ignore_index=True)
    t["tasa_contactable"] = _div(t["contactables"], t["captados"])
    t["tasa_conversion"] = _div(t["convertidos"], t["alcanzados"])
    return t


def kpis_contenidos(contenidos: pd.DataFrame, inter: pd.DataFrame) -> pd.DataFrame:
    """Envíos, aperturas, clics, conversiones, bajas y quejas por contenido, con sus tasas."""
    n = (inter.drop_duplicates(["id_contacto", "id_contenido", "evento"])
         .pivot_table(index="id_contenido", columns="evento", values="id_contacto", aggfunc="count")
         .reindex(columns=list(EVENTOS)).fillna(0).astype(int))
    t = contenidos[["id_contenido", "titulo", "tipo", "area_terapeutica", "producto"]].merge(
        n, how="left", left_on="id_contenido", right_index=True)
    t[list(EVENTOS)] = t[list(EVENTOS)].fillna(0).astype(int)
    t["conversiones"] = t["inscripcion"] + t["canje"]
    t["tasa_apertura"] = _div(t["apertura"], t["envio"])
    t["ctr"] = _div(t["clic"], t["envio"])
    t["tasa_conversion"] = _div(t["conversiones"], t["envio"])
    t["tasa_baja"] = _div(t["baja"], t["envio"])
    t["tasa_queja"] = _div(t["queja"], t["envio"])
    return t.rename(columns={"envio": "envios", "apertura": "aperturas", "clic": "clics",
                             "baja": "bajas", "queja": "quejas"})


def auditoria(contactos: pd.DataFrame, contenidos: pd.DataFrame, inter: pd.DataFrame,
              eleg: pd.DataFrame, *, hoy: pd.Timestamp, ajustes: dict | None = None) -> dict[str, pd.DataFrame]:
    """Por qué no se envía lo que no se envía, y lo que se envió y hoy no se podría."""
    tipo_ct = contactos.set_index("id_contacto")
    tipo_co = contenidos.set_index("id_contenido")["tipo"]
    b = eleg[eleg["motivo"] != ""]
    bloqueos = (b.assign(pais=b["id_contacto"].map(tipo_ct["pais"]),
                         tipo_contacto=b["id_contacto"].map(tipo_ct["tipo"]),
                         tipo_contenido=b["id_contenido"].map(tipo_co))
                .groupby(["pais", "tipo_contacto", "tipo_contenido", "motivo"]).size()
                .rename("pares").reset_index())
    bloqueos["descripcion"] = bloqueos["motivo"].map(K.MOTIVOS)
    env = inter[inter["evento"] == "envio"].merge(eleg, how="inner", on=["id_contacto", "id_contenido"])
    # Lo enviado antes de que la persona pidiera la baja estaba bien enviado.
    fecha_baja = inter[inter["evento"] == "baja"].groupby("id_contacto")["fecha"].min()
    if len(fecha_baja):
        previo = (env["motivo"] == "baja") & (env["fecha"] <= env["id_contacto"].map(fecha_baja))
        env = env[~previo]
    irregulares = (env[env["motivo"] != ""].groupby(["id_contenido", "motivo"]).size()
                   .rename("envios").reset_index())
    irregulares["descripcion"] = irregulares["motivo"].map(K.MOTIVOS)
    rec = _ventana(inter, hoy)
    por = rec.groupby("id_contacto").size()
    tope = por.index.map(lambda i: K.politica(tipo_ct["pais"].get(i, ""), ajustes).frecuencia_max_30d)
    excedidos = por[por.values > np.asarray(tope)]
    frecuencia = (pd.DataFrame({"pais": excedidos.index.map(tipo_ct["pais"])}).value_counts()
                  .rename("contactos_sobre_el_tope").reset_index()
                  if len(excedidos) else pd.DataFrame(columns=["pais", "contactos_sobre_el_tope"]))
    return {"bloqueos": bloqueos, "envios_no_elegibles": irregulares, "frecuencia_excedida": frecuencia}


COLUMNAS_POLITICAS = ["pais", "ley_datos", "autoridad_sanitaria", "promocion_receta_a_publico",
                      "promocion_venta_libre_a_publico", "doble_optin_obligatorio", "frecuencia_max_30d",
                      "validado_por_legal"]


def politicas_usadas(contactos: pd.DataFrame, ajustes: dict | None = None) -> pd.DataFrame:
    filas = []
    for p in sorted(contactos["pais"].astype(str).unique()):
        q = K.politica(p, ajustes)
        filas.append({"pais": p, "ley_datos": q.ley_datos, "autoridad_sanitaria": q.autoridad_sanitaria,
                      "promocion_receta_a_publico": q.promocion_receta_a_publico,
                      "promocion_venta_libre_a_publico": q.promocion_venta_libre_a_publico,
                      "doble_optin_obligatorio": q.doble_optin_obligatorio,
                      "frecuencia_max_30d": q.frecuencia_max_30d,
                      "validado_por_legal": q.validado_por_legal})
    return pd.DataFrame(filas, columns=COLUMNAS_POLITICAS)


# ── derechos de la persona ──────────────────────────────────────────────────
def huella(id_contacto: Any) -> str:
    """Huella irreversible de un id: la lista de supresión evita que se vuelva a importar."""
    return hashlib.sha256(str(id_contacto).encode()).hexdigest()


def suprimir(contactos: pd.DataFrame, interacciones: pd.DataFrame,
             ids: list[Any]) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Derecho de supresión: borra a las personas y su historial. Devuelve la lista de supresión."""
    quitar = {str(i) for i in ids}
    return (contactos[~contactos["id_contacto"].astype(str).isin(quitar)].reset_index(drop=True),
            interacciones[~interacciones["id_contacto"].astype(str).isin(quitar)].reset_index(drop=True),
            sorted(huella(i) for i in quitar))


def acceso(contactos: pd.DataFrame, interacciones: pd.DataFrame, id_contacto: Any) -> dict[str, Any]:
    """Derecho de acceso: todo lo que la base tiene de una persona, legible."""
    fila = contactos[contactos["id_contacto"].astype(str) == str(id_contacto)]
    if fila.empty:
        raise KeyError(f"No hay ningún contacto con id {id_contacto}.")
    datos = {k: (sorted(v) if isinstance(v, frozenset) else v) for k, v in fila.iloc[0].to_dict().items()}
    hist = interacciones[interacciones["id_contacto"].astype(str) == str(id_contacto)]
    hist = hist.assign(fecha=hist["fecha"].astype(str)).sort_values("fecha")
    return {"datos": datos, "interacciones": hist.to_dict("records")}


# ── todo junto ──────────────────────────────────────────────────────────────
def analizar(contactos: pd.DataFrame, contenidos: pd.DataFrame, interacciones: pd.DataFrame | None = None,
             *, hoy: Any = None, ajustes: dict | None = None, por_contacto: int = 3,
             max_celdas: int = MAX_CELDAS) -> dict[str, Any]:
    """Prepara las tablas y devuelve recomendaciones, embudo, KPIs, auditoría y políticas."""
    ct, avisos = K.preparar_contactos(contactos)
    co = K.preparar_contenidos(contenidos)
    inter, av_i = preparar_interacciones(interacciones)
    avisos += av_i
    celdas = len(ct) * len(co)
    if celdas > max_celdas:
        raise ValueError(f"{len(ct)} contactos × {len(co)} contenidos son {celdas:,} pares; el máximo "
                         f"por análisis es {max_celdas:,}. Partí la base por país.".replace(",", "."))
    ajenos = ~inter["id_contacto"].isin(set(ct["id_contacto"]))
    if ajenos.any():
        avisos.append(f"{int(ajenos.sum())} interacción(es) de contactos que no están en la base "
                      "(¿suprimidos?): no se usan.")
        inter = inter[~ajenos]
    ct = _bajas_por_evento(ct, inter, avisos)
    if hoy:
        hoy = a_fecha(pd.Series([hoy])).iloc[0]
        if pd.isna(hoy):
            raise ValueError("La fecha de hoy no se entiende: usá AAAA-MM-DD.")
    else:
        hoy = inter["fecha"].max() if not inter.empty else pd.Timestamp.today()
    hoy = hoy.normalize()
    eleg = K.matriz_elegibilidad(ct, co, ajustes)
    pol = politicas_usadas(ct, ajustes)
    if not pol["validado_por_legal"].all():
        avisos.append("Las reglas de " + ", ".join(pol.loc[~pol["validado_por_legal"], "pais"])
                      + " son conservadoras por defecto y no las validó legal todavía.")
    rec = recomendar(ct, co, inter, hoy=hoy, ajustes=ajustes, por_contacto=por_contacto, elegibilidad=eleg)
    aud = auditoria(ct, co, inter, eleg, hoy=hoy, ajustes=ajustes)
    if not aud["envios_no_elegibles"].empty:
        avisos.append(f"{int(aud['envios_no_elegibles']['envios'].sum())} envío(s) del historial no cumplen "
                      "las reglas con los consentimientos de hoy (ver la auditoría): revisar con compliance.")
    emb = embudo(ct, inter, ajustes)
    return {
        "hoy": hoy.strftime("%Y-%m-%d"), "avisos": avisos,
        "resumen": {"contactos": len(ct), "contenidos": len(co), "pares": celdas,
                    "pares_elegibles": int((eleg["motivo"] == "").sum()),
                    "recomendaciones": len(rec), "personas_con_recomendacion": int(rec["id_contacto"].nunique()),
                    "personalizadas": int(rec["personalizado"].sum()) if len(rec) else 0},
        "recomendaciones": rec, "embudo": emb, "contenidos": kpis_contenidos(co, inter),
        # Lo que el motor usó de verdad (bajas por evento aplicadas, interacciones de suprimidos fuera):
        # el modelo para Fabric sale de acá y no de volver a preparar las tablas crudas.
        "_preparado": {"contactos": ct, "contenidos": co, "interacciones": inter},
        "bloqueos": aud["bloqueos"], "envios_no_elegibles": aud["envios_no_elegibles"],
        "frecuencia_excedida": aud["frecuencia_excedida"], "politicas": pol,
    }


def a_json(r: dict[str, Any], max_recomendaciones: int = 500) -> dict[str, Any]:
    """El resultado de `analizar` con las tablas como listas (las recomendaciones, recortadas)."""
    out: dict[str, Any] = {}
    for k, v in r.items():
        if k.startswith("_"):
            continue
        if isinstance(v, pd.DataFrame):
            v = v.head(max_recomendaciones) if k == "recomendaciones" else v
            out[k] = v.astype(object).where(v.notna(), None).to_dict("records")
        else:
            out[k] = v
    return out


__all__ = ["EVENTOS", "a_json", "acceso", "analizar", "auditoria", "embudo", "huella",
           "kpis_contenidos", "politicas_usadas", "preparar_interacciones", "recomendar", "suprimir"]
