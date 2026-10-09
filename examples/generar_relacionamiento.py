"""Genera la base de relacionamiento sintética y las fuentes públicas que la complementan.

Propias: contactos, contenidos e interacciones. Públicas y agregadas: un censo
(población por ciudad, barrio, sexo, edad y nivel socioeconómico), prevalencias
como las de una encuesta nacional de salud, y una exportación de escucha social.

Todo es inventado. Los contactos tienen un id seudónimo y ningún dato que
identifique a nadie (ni mail, ni teléfono, ni nombre): así vive la base en la
analítica; el contacto real queda en el CRM. Las marcas son ficticias
(Vasotril y Glucofin, de venta bajo receta; Vitalix y Calcimar D, de venta libre).

Los posteos de la escucha son plantillas inventadas con autores ficticios y
URL de ejemplo: están para mostrar que el análisis los descarta.

El historial simula seis meses de envíos que en su mayoría respetaron las
reglas, más unos pocos que no (un 1 %), para que la auditoría tenga algo que
mostrar.

    python examples/generar_relacionamiento.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "backend"))
from app.core import consentimiento as K  # noqa: E402

SEMILLA = 20261009
N = 1500
PAISES = {"México": 0.30, "Argentina": 0.20, "Colombia": 0.15, "Chile": 0.12, "Uruguay": 0.08,
          "Brasil": 0.10, "Perú": 0.05}
AREAS = ["Cardiometabólica", "Diabetes", "Salud ósea", "Bienestar"]
CIUDADES = {  # país: {ciudad: [barrios]} (sólo Montevideo trae barrios, como un censo por segmento)
    "México": {"Ciudad de México": [], "Guadalajara": [], "Monterrey": []},
    "Argentina": {"Buenos Aires": [], "Córdoba": [], "Rosario": []},
    "Colombia": {"Bogotá": [], "Medellín": []},
    "Chile": {"Santiago": [], "Valparaíso": []},
    "Uruguay": {"Montevideo": ["Pocitos", "Cordón", "Malvín", "Cerro", "Piedras Blancas"]},
    "Brasil": {"São Paulo": [], "Rio de Janeiro": []},
    "Perú": {"Lima": []},
}
SEXOS = ["Mujeres", "Hombres"]
EDADES = ["18-39", "40-59", "60+"]
# Prevalencia ficticia por área, sexo y edad (el estilo de una encuesta nacional de salud).
PREVALENCIA = {
    "Cardiometabólica": {"Mujeres": (0.07, 0.27, 0.55), "Hombres": (0.09, 0.32, 0.58)},
    "Diabetes": {"Mujeres": (0.02, 0.10, 0.20), "Hombres": (0.03, 0.12, 0.22)},
    "Salud ósea": {"Mujeres": (0.01, 0.09, 0.28), "Hombres": (0.005, 0.03, 0.09)},
}
# Barrios con un nivel socioeconómico marcado; el resto, mezcla.
NSE_BARRIO = {"Pocitos": (0.55, 0.40, 0.05), "Malvín": (0.35, 0.55, 0.10), "Cordón": (0.20, 0.60, 0.20),
              "Cerro": (0.03, 0.37, 0.60), "Piedras Blancas": (0.02, 0.33, 0.65)}
CONTENIDOS = [  # id, título, tipo, área, producto, condición, audiencia
    ("K-01", "Conocé tu presión arterial", "concientizacion", "Cardiometabólica", "", "", "publico"),
    ("K-02", "Diabetes: señales que conviene consultar", "concientizacion", "Diabetes", "", "", "publico"),
    ("K-03", "Huesos fuertes después de los 50", "concientizacion", "Salud ósea", "", "", "publico"),
    ("K-04", "Programa Vasotril Contigo (adherencia)", "programa_paciente", "Cardiometabólica",
     "Vasotril", "receta", "paciente"),
    ("K-05", "Programa Glucofin Acompaña", "programa_paciente", "Diabetes", "Glucofin", "receta", "paciente"),
    ("K-06", "Descuento en farmacia para Vasotril", "beneficio", "Cardiometabólica", "Vasotril",
     "receta", "paciente"),
    ("K-07", "Vasotril AM: nueva presentación", "promocion_marca", "Cardiometabólica", "Vasotril",
     "receta", "todos"),
    ("K-08", "Glucofin XR: estudio de eficacia", "educacion_medica", "Diabetes", "Glucofin", "receta",
     "profesional"),
    ("K-09", "Guía de hipertensión resistente", "educacion_medica", "Cardiometabólica", "", "", "profesional"),
    ("K-10", "Vitalix: energía para tu día", "promocion_marca", "Bienestar", "Vitalix", "venta_libre", "todos"),
    ("K-11", "2x1 en Vitalix", "beneficio", "Bienestar", "Vitalix", "venta_libre", "paciente"),
    ("K-12", "Calcimar D: calcio con vitamina D", "promocion_marca", "Salud ósea", "Calcimar D",
     "venta_libre", "todos"),
    ("K-13", "Recetas bajas en sal", "concientizacion", "Cardiometabólica", "", "", "publico"),
    ("K-14", "Moverse 30 minutos al día", "concientizacion", "", "", "", "publico"),
]
PROB_APERTURA = 0.38
PROB_CLIC = {"concientizacion": 0.25, "programa_paciente": 0.35, "beneficio": 0.40,
             "promocion_marca": 0.15, "educacion_medica": 0.30}
PROB_CONVERSION = {"programa_paciente": 0.30, "beneficio": 0.35}


def contactos(rng: np.random.Generator) -> pd.DataFrame:
    pais = rng.choice(list(PAISES), N, p=list(PAISES.values()))
    ciudad = np.array([rng.choice(list(CIUDADES[p])) for p in pais], dtype=object)
    barrio = np.array([rng.choice(CIUDADES[p][c]) if CIUDADES[p][c] else "" for p, c in zip(pais, ciudad, strict=True)],
                      dtype=object)
    tipo = rng.choice(["paciente", "cuidador", "profesional"], N, p=[0.70, 0.15, 0.15])
    si = lambda p: np.where(rng.random(N) < p, "si", "no")  # noqa: E731
    contacto = si(0.92)
    salud = np.where(contacto == "si", si(0.70), "no")
    areas = []
    for _ in range(N):
        k = rng.choice([0, 1, 1, 2])
        areas.append(";".join(rng.choice(AREAS, k, replace=False, p=[0.40, 0.30, 0.15, 0.15])))
    areas = np.array(areas, dtype=object)
    recetados = np.where(np.char.find(areas.astype(str), "Cardiometabólica") >= 0,
                         np.where(rng.random(N) < 0.4, "Vasotril", ""), "")
    recetados = np.where((np.char.find(areas.astype(str), "Diabetes") >= 0) & (rng.random(N) < 0.35),
                         np.char.add(recetados.astype(str), ";Glucofin"), recetados).astype(object)
    return pd.DataFrame({
        "id_contacto": [f"C-{i:05d}" for i in range(1, N + 1)], "pais": pais, "ciudad": ciudad,
        "barrio": barrio, "sexo": rng.choice(SEXOS, N, p=[0.58, 0.42]),
        "rango_edad": rng.choice(EDADES, N, p=[0.25, 0.40, 0.35]), "tipo": tipo,
        "canal_captacion": rng.choice(["landing", "programa", "evento médico", "farmacia"], N),
        "fecha_alta": pd.to_datetime("2025-10-01") + pd.to_timedelta(rng.integers(0, 365, N), "D"),
        "consiente_contacto": contacto, "consiente_marketing": np.where(contacto == "si", si(0.55), "no"),
        "consiente_salud": salud, "consiente_perfilado": np.where(contacto == "si", si(0.60), "no"),
        "doble_optin": si(0.85), "baja": si(0.03),
        "areas_interes": areas, "productos_recetados": recetados,
        "canal_preferido": rng.choice(["email", "whatsapp", "sms"], N, p=[0.6, 0.3, 0.1]),
    })


def contenidos() -> pd.DataFrame:
    return pd.DataFrame(CONTENIDOS, columns=["id_contenido", "titulo", "tipo", "area_terapeutica",
                                             "producto", "condicion_venta", "audiencia"]).assign(
        paises="*", canal="email")


def interacciones(rng: np.random.Generator, ct: pd.DataFrame, co: pd.DataFrame) -> pd.DataFrame:
    eleg = K.matriz_elegibilidad(K.preparar_contactos(ct)[0], K.preparar_contenidos(co))
    ok = eleg[eleg["motivo"] == ""]
    malos = eleg[eleg["motivo"] != ""].sample(frac=0.01, random_state=SEMILLA)
    tipos = co.set_index("id_contenido")["tipo"]
    # Gusto oculto de cada persona: a quien le interesa un tema le interesa lo del mismo tema.
    gusto = {c: rng.uniform(0.4, 1.6) for c in ct["id_contacto"]}
    filas = []
    for mes in range(6):
        envios = pd.concat([ok.sample(frac=0.18, random_state=SEMILLA + mes),
                            malos.sample(frac=1 / 6, random_state=SEMILLA + mes)])
        for r in envios.itertuples():
            fecha = pd.Timestamp("2026-04-01") + pd.Timedelta(days=30 * mes + int(rng.integers(0, 28)))
            filas.append((r.id_contacto, r.id_contenido, fecha, "envio"))
            if rng.random() > PROB_APERTURA * gusto[r.id_contacto]:
                if rng.random() < 0.004:
                    filas.append((r.id_contacto, r.id_contenido, fecha, "baja"))
                continue
            filas.append((r.id_contacto, r.id_contenido, fecha, "apertura"))
            tipo = tipos[r.id_contenido]
            if rng.random() > PROB_CLIC[tipo] * gusto[r.id_contacto]:
                if rng.random() < 0.003:
                    filas.append((r.id_contacto, r.id_contenido, fecha, "queja"))
                continue
            filas.append((r.id_contacto, r.id_contenido, fecha, "clic"))
            if tipo in PROB_CONVERSION and rng.random() < PROB_CONVERSION[tipo]:
                evento = "inscripcion" if tipo == "programa_paciente" else "canje"
                filas.append((r.id_contacto, r.id_contenido, fecha + pd.Timedelta(days=2), evento))
    d = pd.DataFrame(filas, columns=["id_contacto", "id_contenido", "fecha", "evento"])
    return d.sort_values(["fecha", "id_contacto"]).reset_index(drop=True)


def poblacion(rng: np.random.Generator) -> pd.DataFrame:
    """Un censo inventado: personas adultas por zona, sexo, edad y nivel socioeconómico."""
    filas = []
    for pais, ciudades in CIUDADES.items():
        for ciudad, barrios in ciudades.items():
            for barrio in barrios or [""]:
                total = rng.integers(60_000, 180_000) if barrio else rng.integers(800_000, 4_000_000)
                nse = NSE_BARRIO.get(barrio, (0.15, 0.50, 0.35))
                for sexo, ps in zip(SEXOS, (0.52, 0.48), strict=True):
                    for edad, pe in zip(EDADES, (0.42, 0.33, 0.25), strict=True):
                        for nivel, pn in zip(("alto", "medio", "bajo"), nse, strict=True):
                            filas.append((pais, ciudad, barrio, sexo, edad, nivel, int(total * ps * pe * pn)))
    return pd.DataFrame(filas, columns=["pais", "ciudad", "barrio", "sexo", "rango_edad", "nse", "poblacion"])


def prevalencias() -> pd.DataFrame:
    filas = [(pais, area, sexo, edad, prev[i], "Sintético (estilo encuesta nacional de salud)")
             for pais in CIUDADES for area, por_sexo in PREVALENCIA.items()
             for sexo, prev in por_sexo.items() for i, edad in enumerate(EDADES)]
    return pd.DataFrame(filas, columns=["pais", "area_terapeutica", "sexo", "rango_edad", "prevalencia", "fuente"])


ESCUCHA = [  # plantilla, tono
    ("me diagnosticaron presión alta y no sé qué comer", 0), ("caminar todos los días me ayudó con la presión", 1),
    ("la hipertensión es un problema grave y nadie habla", -1), ("buenísimo el programa para controlar la diabetes", 1),
    ("con la diabetes el control de glucosa es un problema", -1), ("mi vieja tiene osteoporosis y le duele todo", -1),
    ("Vitalix me encanta, excelente para arrancar el día", 1), ("Vitalix está carísimo", -1),
    ("Vasotril me hizo mal, tuve mareos", -1), ("el Vasotril funciona bien, la presión mejoró", 1),
    ("no hay Glucofin en la farmacia, desabastecimiento otra vez", -1), ("Calcimar D recomendado por mi médica", 1),
]


def escucha(rng: np.random.Generator, n: int = 3000) -> pd.DataFrame:
    """Una exportación de escucha inventada, con columnas de autor que el análisis tiene que descartar."""
    idx = rng.integers(0, len(ESCUCHA), n)
    pais = rng.choice(list(PAISES), n, p=list(PAISES.values()))
    fecha = pd.Timestamp("2026-07-01") + pd.to_timedelta(rng.integers(0, 84, n), "D")
    texto = [ESCUCHA[i][0] + (" https://ejemplo.invalid/p/" + str(k) if k % 3 == 0 else "")
             + (" @cuenta_ficticia" if k % 5 == 0 else "") for k, i in enumerate(idx)]
    return pd.DataFrame({"fecha": fecha.strftime("%Y-%m-%d"), "pais": pais, "texto": texto,
                         "autor": [f"@usuario_ficticio_{k % 400}" for k in range(n)],
                         "url": [f"https://ejemplo.invalid/p/{k}" for k in range(n)]})


def main() -> None:
    rng = np.random.default_rng(SEMILLA)
    ct, co = contactos(rng), contenidos()
    it = interacciones(rng, ct, co)
    ct.assign(fecha_alta=ct["fecha_alta"].dt.strftime("%Y-%m-%d")).to_csv(
        AQUI / "relacionamiento_contactos.csv", index=False)
    co.to_csv(AQUI / "relacionamiento_contenidos.csv", index=False)
    it.assign(fecha=it["fecha"].dt.strftime("%Y-%m-%d")).to_csv(
        AQUI / "relacionamiento_interacciones.csv", index=False)
    poblacion(rng).to_csv(AQUI / "censo_sintetico.csv", index=False)
    prevalencias().to_csv(AQUI / "prevalencias_sinteticas.csv", index=False)
    escucha(rng).to_csv(AQUI / "escucha_social_sintetica.csv", index=False)
    print(f"{len(ct)} contactos, {len(co)} contenidos, {len(it)} interacciones, más censo, "
          "prevalencias y escucha")


if __name__ == "__main__":
    main()
