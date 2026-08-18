#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# MV AutoML Studio — arranque en Linux y macOS
# Crea el entorno virtual si no existe, instala lo que falte y levanta la app.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in python3.12 python3.11 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
  done
fi
if [ -z "$PY" ]; then
  echo "No se encontró Python 3.11 o superior. Instalalo y volvé a ejecutar." >&2
  exit 1
fi

VERSION="$("$PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
echo "Python detectado: $VERSION ($PY)"
"$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' || {
  echo "Se necesita Python 3.11 o superior; se encontró $VERSION." >&2
  exit 1
}

if [ ! -d ".venv" ]; then
  echo "Creando el entorno virtual..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import fastapi, pandas, sklearn, duckdb" >/dev/null 2>&1; then
  echo "Instalando dependencias (la primera vez tarda unos minutos)..."
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -r requirements.txt
fi

export MV_HOST="${MV_HOST:-127.0.0.1}"
export MV_PORT="${MV_PORT:-8000}"

echo
echo "  MV AutoML Studio"
echo "  http://$MV_HOST:$MV_PORT"
echo "  Ctrl+C para detener"
echo

if command -v xdg-open >/dev/null 2>&1; then (sleep 2 && xdg-open "http://$MV_HOST:$MV_PORT" >/dev/null 2>&1 &) ; fi
if command -v open >/dev/null 2>&1; then (sleep 2 && open "http://$MV_HOST:$MV_PORT" >/dev/null 2>&1 &) ; fi

exec python -m uvicorn backend.app.main:app --host "$MV_HOST" --port "$MV_PORT"
