#!/usr/bin/env bash
# Build a HACS release asset zip of the integration package.
#
# Usage: package-hacs-zip.sh [output_path]
#   output_path — default: dimplex.zip in the current directory
#
# The zip contains the contents of custom_components/dimplex/ at the root
# (HACS extracts the asset into custom_components/<domain>/).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/custom_components/dimplex"
OUT="${1:-${ROOT}/dimplex.zip}"

if [ ! -d "$SRC" ]; then
  echo "error: missing integration directory: ${SRC}" >&2
  exit 2
fi
if [ ! -f "${SRC}/manifest.json" ]; then
  echo "error: missing manifest.json in ${SRC}" >&2
  exit 2
fi

rm -f "$OUT"
# -X strips extra file attrs; -q quiet. Paths inside the zip are relative to SRC.
(
  cd "$SRC"
  zip -X -r -q "$OUT" . \
    -x '*__pycache__*' \
    -x '*.pyc' \
    -x '*.pyo' \
    -x '*/.DS_Store' \
    -x '.DS_Store'
)

echo "Wrote ${OUT} ($(wc -c <"$OUT" | tr -d ' ') bytes)"
