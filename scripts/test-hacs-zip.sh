#!/usr/bin/env bash
# Check that a HACS release asset is installable.
#
# Usage: scripts/test-hacs-zip.sh [zip]
#
#   zip — an asset to check, e.g. one downloaded from a published release. Without it,
#         the script builds one from the working tree first, which is what CI does on
#         a pull request.
#
# Both modes exist because they catch different things: the build keeps
# package-hacs-zip.sh honest, and the download proves the artefact users actually
# install is the one that was checked. A release is immutable once published, so a
# malformed asset can only be replaced by deleting the release — worth catching before
# it ships rather than after.
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

if [ "$#" -gt 0 ]; then
  OUT="$1"
  if [ ! -f "$OUT" ]; then
    echo "error: no such asset to check: ${OUT}" >&2
    exit 1
  fi
  echo "Checking supplied asset ${OUT}"
else
  OUT="${TMP}/dimplex.zip"
  bash "${ROOT}/scripts/package-hacs-zip.sh" "$OUT"
fi

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
