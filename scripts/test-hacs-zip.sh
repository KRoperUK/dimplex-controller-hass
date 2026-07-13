#!/usr/bin/env bash
# Smoke-test package-hacs-zip.sh: zip exists, manifest at root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
OUT="${TMP}/dimplex.zip"
bash "${ROOT}/scripts/package-hacs-zip.sh" "$OUT"
test -f "$OUT"
unzip -l "$OUT" | grep -E '(^|/)manifest\.json$' >/dev/null
# ensure no nested custom_components/dimplex path
if unzip -l "$OUT" | grep -q 'custom_components/'; then
  echo "error: zip should contain package root files, not custom_components/" >&2
  exit 1
fi
# extract and check version field present
unzip -q -o "$OUT" -d "${TMP}/extract"
python3 - <<PY
import json
from pathlib import Path
manifest = json.loads(Path("${TMP}/extract/manifest.json").read_text())
assert manifest.get("domain") == "dimplex"
assert manifest.get("version")
print("hacs zip smoke ok:", manifest["version"])
PY
