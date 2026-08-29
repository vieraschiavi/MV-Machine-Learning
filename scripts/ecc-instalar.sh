#!/usr/bin/env bash
# ecc-instalar.sh — Instala/actualiza el layer ECC (https://github.com/affaan-m/ECC)
# dentro de este repo, bajo .claude/rules/ecc/ y .claude/skills/.
#
# Uso:
#   ./scripts/ecc-instalar.sh                 # detecta el stack solo
#   ./scripts/ecc-instalar.sh python web      # fuerza los stacks
#   ECC_SRC=/ruta/a/ECC ./scripts/ecc-instalar.sh   # usa un clon local en vez de bajarlo
#
# Idempotente: se puede correr N veces. Reemplaza .claude/rules/ecc/ completo.

set -euo pipefail

REPO_RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ECC_REMOTO="${ECC_REMOTO:-https://github.com/affaan-m/ECC.git}"
DESTINO_RULES="$REPO_RAIZ/.claude/rules/ecc"
DESTINO_SKILLS="$REPO_RAIZ/.claude/skills"

# Skills de ECC que se vendorizan siempre (núcleo de calidad y salida a producción).
SKILLS_BASE=(
  production-audit
  security-review
  verification-loop
  tdd-workflow
  e2e-testing
  error-handling
  deployment-patterns
  coding-standards
  repo-scan
  ecc-guide
)

# Skills adicionales por stack.
skills_de_stack() {
  case "$1" in
    python)     echo "python-patterns python-testing fastapi-patterns" ;;
    typescript) echo "api-design" ;;
    web)        echo "frontend-patterns react-patterns" ;;
    golang)     echo "golang-patterns golang-testing" ;;
    rust)       echo "rust-patterns rust-testing" ;;
    *)          echo "" ;;
  esac
}

detectar_stacks() {
  local stacks=()
  if [ -f "$REPO_RAIZ/requirements.txt" ] || [ -f "$REPO_RAIZ/pyproject.toml" ] || [ -f "$REPO_RAIZ/setup.py" ]; then
    stacks+=(python)
  fi
  if [ -f "$REPO_RAIZ/package.json" ]; then
    stacks+=(typescript)
    # Si hay superficie web (HTML/JSX/Vue) sumamos las reglas de front.
    if [ -d "$REPO_RAIZ/public" ] || [ -d "$REPO_RAIZ/src/components" ] \
       || find "$REPO_RAIZ" -maxdepth 3 -name '*.html' -not -path '*/node_modules/*' -print -quit | grep -q .; then
      stacks+=(web)
    fi
  fi
  [ -f "$REPO_RAIZ/go.mod" ] && stacks+=(golang)
  [ -f "$REPO_RAIZ/Cargo.toml" ] && stacks+=(rust)
  [ ${#stacks[@]} -eq 0 ] && return 0
  printf '%s\n' "${stacks[@]}"
}

obtener_fuente() {
  if [ -n "${ECC_SRC:-}" ]; then
    [ -d "$ECC_SRC/rules/common" ] || { echo "[ECC] ECC_SRC=$ECC_SRC no parece un clon de ECC" >&2; exit 1; }
    echo "$ECC_SRC"
    return
  fi
  local tmp
  tmp="$(mktemp -d)"
  echo "[ECC] Clonando $ECC_REMOTO ..." >&2
  git clone --depth 1 --quiet "$ECC_REMOTO" "$tmp/ECC" >&2
  echo "$tmp/ECC"
}

main() {
  local stacks=("$@")
  if [ ${#stacks[@]} -eq 0 ]; then
    mapfile -t stacks < <(detectar_stacks)
  fi
  if [ ${#stacks[@]} -eq 0 ]; then
    echo "[ECC] No se detectó stack. Pasalo a mano: ./scripts/ecc-instalar.sh python" >&2
    exit 1
  fi

  local fuente; fuente="$(obtener_fuente)"
  local version; version="$(cat "$fuente/VERSION" 2>/dev/null || echo desconocida)"

  echo "[ECC] Versión $version · stacks: ${stacks[*]}"

  rm -rf "$DESTINO_RULES"
  mkdir -p "$DESTINO_RULES" "$DESTINO_SKILLS"

  cp -R "$fuente/rules/common" "$DESTINO_RULES/"
  local skills=("${SKILLS_BASE[@]}")
  for stack in "${stacks[@]}"; do
    if [ -d "$fuente/rules/$stack" ]; then
      cp -R "$fuente/rules/$stack" "$DESTINO_RULES/"
      echo "[ECC]   reglas: $stack"
    else
      echo "[ECC]   aviso: ECC no tiene reglas para '$stack', se omite" >&2
    fi
    # shellcheck disable=SC2206
    local extra=($(skills_de_stack "$stack"))
    skills+=("${extra[@]:-}")
  done

  for skill in "${skills[@]}"; do
    [ -n "$skill" ] || continue
    if [ -d "$fuente/skills/$skill" ]; then
      rm -rf "${DESTINO_SKILLS:?}/$skill"
      cp -R "$fuente/skills/$skill" "$DESTINO_SKILLS/"
    else
      echo "[ECC]   aviso: skill '$skill' no existe en ECC, se omite" >&2
    fi
  done

  cat > "$DESTINO_RULES/PROCEDENCIA.md" <<EOF
# Procedencia de estas reglas

Copiadas de [ECC](https://github.com/affaan-m/ECC) (MIT), versión **$version**.
Stacks instalados: ${stacks[*]}

No edites estos archivos a mano: los pisa \`scripts/ecc-instalar.sh\`.
Si una regla no aplica a este repo, anotá la excepción en \`.claude/skills/ecc/SKILL.md\`.

Actualizar: \`./scripts/ecc-instalar.sh ${stacks[*]}\`
EOF

  echo "[ECC] Listo → $DESTINO_RULES"
  echo "[ECC] Skills vendorizadas: ${skills[*]}"
}

main "$@"
