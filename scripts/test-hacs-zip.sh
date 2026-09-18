#!/usr/bin/env bash
# Smoke-test package-hacs-zip.sh: the release asset has to be installable by HACS.
#
# HACS extracts the asset into custom_components/<domain>/, so the zip must hold the
# *contents* of the integration directory — manifest.json at the root, and no nested
# custom_components/dimplex/ path. A malformed zip still uploads without complaint,
# from both `gh release upload` and `gh release create`, so nothing else in CI would
# notice until somebody tried to install a release.
#
# `unzip -Z1` prints bare entry names, one per line. Parsing `unzip -l` instead means
# matching around its fixed-width columns: the name is preceded by padding, not by
# `/`, so a `(^|/)manifest\.json$` pattern matches nothing and the check passes for
# every possible zip. That is what the first version of this script did.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

OUT="${TMP}/dimplex.zip"
bash "${ROOT}/scripts/package-hacs-zip.sh" "$OUT"

names="${TMP}/names.txt"
unzip -Z1 "$OUT" > "$names"

if ! grep -qx 'manifest.json' "$names"; then
  echo "error: manifest.json is not at the zip root — HACS cannot install this" >&2
  echo "       the archive contains:" >&2
  sed 's/^/         /' "$names" >&2
  exit 1
fi

if grep -q '^custom_components/' "$names"; then
  echo "error: zip contains a nested custom_components/ path; HACS extracts the" >&2
  echo "       asset into custom_components/<domain>/ itself" >&2
  exit 1
fi

unzip -q -o "$OUT" -d "${TMP}/extract"
python3 - "${TMP}/extract/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
assert manifest.get("domain") == "dimplex", manifest.get("domain")
assert manifest.get("version"), "manifest.json has no version"
print("hacs zip smoke ok:", manifest["version"])
PY
