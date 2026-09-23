#!/usr/bin/env bash
# Instalador automático — all-in-one-tech-team (Claude Code, Linux/Mac)
set -euo pipefail

SKILL_NAME="all-in-one-tech-team"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${HOME}/.claude/skills/${SKILL_NAME}"

echo "[1/4] Origen:  ${SRC}"
echo "[2/4] Destino: ${DEST}"

if [ ! -f "${SRC}/SKILL.md" ]; then
  echo "ERROR: no se encontró SKILL.md en ${SRC} — abortando." >&2
  exit 1
fi

mkdir -p "${DEST}"
cp -R "${SRC}/SKILL.md" "${SRC}/references" "${SRC}/scripts" "${DEST}/"
if [ -d "${SRC}/assets" ]; then
  cp -R "${SRC}/assets" "${DEST}/"
fi

echo "[3/4] Validando instalación..."
if head -1 "${DEST}/SKILL.md" | grep -q -- "---"; then
  echo "      SKILL.md legible y con frontmatter."
else
  echo "ERROR: SKILL.md instalado pero sin frontmatter válido." >&2
  exit 1
fi

N_REFS=$(ls "${DEST}/references" | wc -l | tr -d ' ')
N_ASSETS=0
if [ -d "${DEST}/assets" ]; then
  N_ASSETS=$(find "${DEST}/assets" -type f | wc -l | tr -d ' ')
fi
echo "[4/4] OK — skill instalado (${N_REFS} archivos de referencia, ${N_ASSETS} plantillas en assets)."
echo "Probalo en Claude Code con: \"activá el all-in-one para este proyecto\""
