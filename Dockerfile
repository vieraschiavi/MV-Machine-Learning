# ─────────────────────────────────────────────────────────────────────────────
#  MV AutoML Studio — modo servidor
#
#  Para el caso en que el programa no puede correr en la máquina de quien lo
#  usa: un consultor externo trabajando con datos de un cliente que no pueden
#  salir de la infraestructura del cliente, desde una laptop corporativa que
#  además tiene bloqueada la ejecución de .exe y .bat.
#
#  Esta imagen corre en el servidor o la VM del cliente. Los datasets, los
#  modelos y los informes quedan en el volumen `/datos`, que es disco de ESE
#  servidor. Por el navegador de la laptop pasan pedidos y píxeles, nunca el
#  dataset.
#
#  Se construye desde la raíz del repositorio:
#      docker build -t mv-automl-studio .
#
#  Y se levanta con `docker-compose.yml`, que es donde van la credencial y la
#  licencia. Ver `docs/modo-servidor.md`.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm

# Sin .pyc y con la salida sin buffer: en un contenedor los logs se leen con
# `docker logs`, y un buffer los esconde justo cuando hacen falta.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MV_MODO=servidor \
    MV_DATA_DIR=/datos \
    MV_FRONTEND_DIR=/app/frontend \
    MV_PORT=8000

WORKDIR /app

# Las dependencias primero y solas: cambian mucho menos que el código, así que
# esta capa se reaprovecha en cada reconstrucción.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "uvicorn[standard]"

COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Nunca como root. Si alguien encuentra un agujero en el programa, que no se
# encuentre además con la máquina del cliente entera.
RUN useradd --create-home --shell /usr/sbin/nologin mv \
    && mkdir -p /datos \
    && chown -R mv:mv /app /datos
USER mv

EXPOSE 8000

# El contenedor se declara sano cuando el programa responde, no cuando el
# proceso existe: un backend que arrancó y se colgó no sirve de nada.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
