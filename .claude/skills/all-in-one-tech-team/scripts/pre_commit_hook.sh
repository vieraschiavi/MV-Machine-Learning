#!/usr/bin/env bash
# pre_commit_hook.sh — Gate local pre-commit del skill all-in-one-tech-team
#
# Corre, ANTES de cada commit, los mismos chequeos que exige el ciclo Coder -> QA -> Executor
# de la skill (ver references/system-instructions.md y references/politicas-error.md):
#   1) Linter del/los stack(s) detectados en el repo (Python/Node/R).
#   2) Tests unitarios si existen (pytest / npm test / testthat).
#   3) Gate de CI/CD (scripts/cicd_check.py) si el repo tiene .github/workflows.
#
# Ningún chequeo se inventa: si la herramienta no está instalada, el check queda OMITIDO
# (no VERDE) y se imprime el comando exacto para instalarla — igual criterio que el resto
# de la skill ante entornos incompletos (marcar PARCIAL, nunca simular éxito).
#
# Uso:
#   bash pre_commit_hook.sh              # audita el repo actual (cwd o -C <ruta>)
#   bash pre_commit_hook.sh -C ruta/al/repo
#   bash pre_commit_hook.sh --strict     # una herramienta faltante (OMITIDO) cuenta como ROJO
#   bash pre_commit_hook.sh --demo       # autotest: repo sano (debe dar VERDE) y repo roto (debe dar ROJO)
#   bash pre_commit_hook.sh --install    # se instala como .git/hooks/pre-commit del repo actual
#
# Exit code: 0 = VERDE (nada bloqueante) · 1 = ROJO (algo falló) · 2 = error de uso.

set -uo pipefail

REPO="."
STRICT=0
MODE="run"

while [ "$#" -gt 0 ]; do
  case "$1" in
    -C) REPO="${2:-.}"; shift 2 ;;
    --strict) STRICT=1; shift ;;
    --demo) MODE="demo"; shift ;;
    --install) MODE="install"; shift ;;
    -h|--help)
      sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "Argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

# ---------- utilidades ----------
declare -a NOMBRES ESTADOS DETALLES
N_ROJO=0
N_OMITIDO=0

registrar() {  # registrar <nombre> <OK|ROJO|OMITIDO> <detalle>
  NOMBRES+=("$1"); ESTADOS+=("$2"); DETALLES+=("$3")
  [ "$2" = "ROJO" ] && N_ROJO=$((N_ROJO + 1))
  [ "$2" = "OMITIDO" ] && N_OMITIDO=$((N_OMITIDO + 1))
}

hay() { command -v "$1" >/dev/null 2>&1; }

imprimir_resumen() {
  echo "============================================================"
  echo " Gate pre-commit — $(cd "$REPO" 2>/dev/null && pwd || echo "$REPO")"
  echo "============================================================"
  local i
  for i in "${!NOMBRES[@]}"; do
    printf "  [%-8s] %-28s %s\n" "${ESTADOS[$i]}" "${NOMBRES[$i]}" "${DETALLES[$i]}"
  done
  echo "------------------------------------------------------------"
  if [ "${#NOMBRES[@]}" -eq 0 ]; then
    echo " Estado final: SIN CHEQUEOS (no se detectó stack Python/Node/R ni CI)"
    return 0
  fi
  if [ "$N_ROJO" -gt 0 ] || { [ "$STRICT" -eq 1 ] && [ "$N_OMITIDO" -gt 0 ]; }; then
    echo " Estado final: ROJO — commit bloqueado. Corregí los ítems ROJO/OMITIDO de arriba."
    return 1
  fi
  if [ "$N_OMITIDO" -gt 0 ]; then
    echo " Estado final: PARCIAL (VERDE con salvedades) — hay checks OMITIDOS por falta de herramienta."
    return 0
  fi
  echo " Estado final: VERDE — todos los checks detectados pasaron."
  return 0
}

# ---------- checks por stack ----------
check_python() {
  local repo="$1"
  local hay_py
  hay_py=$(find "$repo" -maxdepth 4 -name "*.py" -not -path "*/.git/*" -not -path "*/node_modules/*" \
            -print -quit 2>/dev/null)
  { [ -f "$repo/requirements.txt" ] || [ -f "$repo/pyproject.toml" ] || [ -f "$repo/setup.py" ] \
    || [ -n "$hay_py" ]; } || return 0

  # max-line-length 100 y ties E203/W503 (formato black) para no generar ruido contra
  # convenciones ya adoptadas por el proyecto; ajustar via .flake8/pyproject.toml si el
  # repo define otro límite (ruff respeta su propia config automáticamente).
  if hay ruff; then
    if (cd "$repo" && ruff check . > /tmp/_pch_lint.log 2>&1); then
      registrar "lint (ruff)" "OK" "sin hallazgos"
    else
      registrar "lint (ruff)" "ROJO" "$(tail -3 /tmp/_pch_lint.log | tr '\n' ' ')"
    fi
  elif hay flake8; then
    if (cd "$repo" && flake8 --max-line-length=100 --extend-ignore=E203,W503 . \
        > /tmp/_pch_lint.log 2>&1); then
      registrar "lint (flake8)" "OK" "sin hallazgos"
    else
      registrar "lint (flake8)" "ROJO" "$(tail -3 /tmp/_pch_lint.log | tr '\n' ' ')"
    fi
  else
    registrar "lint (python)" "OMITIDO" "instalar: pip install ruff (o flake8)"
  fi

  local hay_test
  hay_test=$(find "$repo" -maxdepth 5 \( -name "test_*.py" -o -name "*_test.py" \) \
              -not -path "*/.git/*" -print -quit 2>/dev/null)
  if [ -n "$hay_test" ] || [ -d "$repo/tests" ]; then
    if hay pytest; then
      if (cd "$repo" && pytest -q > /tmp/_pch_test.log 2>&1); then
        registrar "tests (pytest)" "OK" "$(tail -1 /tmp/_pch_test.log)"
      else
        registrar "tests (pytest)" "ROJO" "$(tail -3 /tmp/_pch_test.log | tr '\n' ' ')"
      fi
    else
      registrar "tests (python)" "OMITIDO" "instalar: pip install pytest"
    fi
  fi
}

check_node() {
  local repo="$1"
  [ -f "$repo/package.json" ] || return 0

  if hay npx && { [ -f "$repo/.eslintrc" ] || [ -f "$repo/.eslintrc.json" ] || [ -f "$repo/.eslintrc.js" ] \
       || [ -f "$repo/eslint.config.js" ] || [ -f "$repo/eslint.config.mjs" ]; }; then
    if (cd "$repo" && npx --yes eslint . > /tmp/_pch_eslint.log 2>&1); then
      registrar "lint (eslint)" "OK" "sin hallazgos"
    else
      registrar "lint (eslint)" "ROJO" "$(tail -3 /tmp/_pch_eslint.log | tr '\n' ' ')"
    fi
  else
    registrar "lint (node)" "OMITIDO" "instalar eslint: npm install -D eslint (y config)"
  fi

  if grep -q '"test"' "$repo/package.json" 2>/dev/null; then
    if (cd "$repo" && npm test --silent > /tmp/_pch_npm.log 2>&1); then
      registrar "tests (npm test)" "OK" "$(tail -1 /tmp/_pch_npm.log)"
    else
      registrar "tests (npm test)" "ROJO" "$(tail -3 /tmp/_pch_npm.log | tr '\n' ' ')"
    fi
  fi
}

check_r() {
  local repo="$1"
  [ -f "$repo/DESCRIPTION" ] || [ -f "$repo/renv.lock" ] || compgen -G "$repo/*.Rproj" > /dev/null 2>&1 \
    || return 0

  if hay Rscript; then
    if (cd "$repo" && Rscript -e 'if (!requireNamespace("lintr", quietly=TRUE)) quit(status=3); print(lintr::lint_dir("."))' \
        > /tmp/_pch_lintr.log 2>&1); then
      if grep -q "^Error" /tmp/_pch_lintr.log; then
        registrar "lint (lintr)" "ROJO" "$(tail -3 /tmp/_pch_lintr.log | tr '\n' ' ')"
      else
        registrar "lint (lintr)" "OK" "sin hallazgos"
      fi
    else
      registrar "lint (lintr)" "OMITIDO" "instalar: install.packages('lintr')"
    fi
    if [ -d "$repo/tests/testthat" ]; then
      if (cd "$repo" && Rscript -e 'testthat::test_dir("tests/testthat")' > /tmp/_pch_testthat.log 2>&1); then
        registrar "tests (testthat)" "OK" "$(tail -1 /tmp/_pch_testthat.log)"
      else
        registrar "tests (testthat)" "ROJO" "$(tail -3 /tmp/_pch_testthat.log | tr '\n' ' ')"
      fi
    fi
  else
    registrar "R" "OMITIDO" "Rscript no está en el PATH"
  fi
}

check_cicd() {
  local repo="$1"
  [ -d "$repo/.github/workflows" ] || return 0
  local checker=""
  for cand in "$(dirname "$0")/cicd_check.py" "$repo/scripts/cicd_check.py"; do
    [ -f "$cand" ] && checker="$cand" && break
  done
  if [ -z "$checker" ]; then
    registrar "CI/CD (cicd_check.py)" "OMITIDO" "no se encontró cicd_check.py junto al hook ni en scripts/"
    return 0
  fi
  if hay python3; then
    if (cd "$repo" && python3 "$checker" .github/workflows > /tmp/_pch_cicd.log 2>&1); then
      registrar "CI/CD (cicd_check.py)" "OK" "sin hallazgos BLOQUEANTE/MAYOR"
    else
      registrar "CI/CD (cicd_check.py)" "ROJO" "$(tail -3 /tmp/_pch_cicd.log | tr '\n' ' ')"
    fi
  else
    registrar "CI/CD (cicd_check.py)" "OMITIDO" "python3 no está en el PATH"
  fi
}

ejecutar_checks() {
  NOMBRES=(); ESTADOS=(); DETALLES=(); N_ROJO=0; N_OMITIDO=0
  check_python "$REPO"
  check_node "$REPO"
  check_r "$REPO"
  check_cicd "$REPO"
}

# ---------- modo install ----------
instalar_hook() {
  local git_root
  git_root="$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null)" || {
    echo "ERROR: '$REPO' no es un repo git (o git no está disponible)." >&2
    return 2
  }
  mkdir -p "$git_root/.git/hooks"
  cp "$0" "$git_root/.git/hooks/pre-commit"
  chmod +x "$git_root/.git/hooks/pre-commit"
  echo "OK — instalado en $git_root/.git/hooks/pre-commit"
  echo "Cada commit va a correr este gate; para saltarlo puntualmente: git commit --no-verify"
}

# ---------- modo demo (autotest, patrón igual a cicd_check.py --demo) ----------
demo() {
  local ok=1
  local tmp
  tmp="$(mktemp -d)"

  # --- repo SANO: función simple, sin lint issues, con test que pasa ---
  mkdir -p "$tmp/sano"
  cat > "$tmp/sano/dividir.py" << 'PYEOF'
def dividir_seguro(numerador, denominador):
    """Divide; devuelve None si denominador es 0 (politica-error.md)."""
    if denominador == 0:
        return None
    return numerador / denominador
PYEOF
  cat > "$tmp/sano/test_dividir.py" << 'PYEOF'
from dividir import dividir_seguro


def test_caso_normal():
    assert dividir_seguro(10, 2) == 5


def test_denominador_cero():
    assert dividir_seguro(10, 0) is None


def test_valor_extremo():
    assert dividir_seguro(1e18, 1) == 1e18
PYEOF

  # --- repo ROTO: lint issue (import sin usar, línea larga) + test que falla ---
  mkdir -p "$tmp/roto"
  cat > "$tmp/roto/dividir.py" << 'PYEOF'
import os
def dividir_seguro(numerador,denominador):
    return numerador/denominador
PYEOF
  cat > "$tmp/roto/test_dividir.py" << 'PYEOF'
from dividir import dividir_seguro


def test_denominador_cero_no_controlado():
    assert dividir_seguro(10, 0) is None
PYEOF

  for caso in sano roto; do
    esperado="VERDE"; [ "$caso" = "roto" ] && esperado="ROJO"
    echo "============================================================"
    echo "DEMO caso '$caso' — esperado: $esperado"
    echo "============================================================"
    REPO="$tmp/$caso"
    ejecutar_checks
    imprimir_resumen
    resultado=$?
    if [ "$caso" = "sano" ] && [ "$resultado" -ne 0 ]; then
      ok=0; echo ">> DEMO FALLÓ: 'sano' debía dar VERDE (exit 0) y dio exit $resultado"
    fi
    if [ "$caso" = "roto" ] && [ "$resultado" -eq 0 ]; then
      ok=0; echo ">> DEMO FALLÓ: 'roto' debía dar ROJO (exit 1) y dio exit $resultado"
    fi
    echo
  done

  rm -rf "$tmp"
  echo "AUTOTEST: $([ "$ok" -eq 1 ] && echo OK || echo FALLÓ)"
  [ "$ok" -eq 1 ]
}

# ---------- main ----------
case "$MODE" in
  install) instalar_hook; exit $? ;;
  demo)
    demo
    exit $?
    ;;
  run)
    ejecutar_checks
    imprimir_resumen
    exit $?
    ;;
esac
