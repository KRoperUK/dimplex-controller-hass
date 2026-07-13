#!/usr/bin/env bash
# Set integration version in manifest.json and const.py for a synthetic dev commit.
#
# Usage: write-dev-version.sh <version>
#   version — bare semver or pre-release (e.g. 3.0.0-rc.2, 3.0.0-pr.81.abc1234)
#
# Does not commit. Run from repository root. Preserves manifest key order
# (in-place value replace only).
set -euo pipefail

VERSION="${1:?version required (e.g. 3.0.0-rc.2)}"
MANIFEST="custom_components/dimplex/manifest.json"
CONST="custom_components/dimplex/const.py"

if [ ! -f "$MANIFEST" ] || [ ! -f "$CONST" ]; then
  echo "error: run from repository root (missing ${MANIFEST} or ${CONST})" >&2
  exit 2
fi

# Reject empty / obviously invalid; keep charset compatible with semver pre-release.
if ! printf '%s' "$VERSION" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$'; then
  echo "error: invalid version string: ${VERSION}" >&2
  exit 2
fi

if ! grep -qE '"version": "' "$MANIFEST"; then
  echo "error: version field not found in ${MANIFEST}" >&2
  exit 2
fi

# Version charset is constrained above (no sed metacharacters in replacement).
sed -i.bak -E "s|\"version\": \"[^\"]+\"|\"version\": \"${VERSION}\"|" "$MANIFEST"
rm -f "${MANIFEST}.bak"

if grep -qE '^VERSION = "' "$CONST"; then
  sed -i.bak -E "s|^VERSION = \"[^\"]*\"|VERSION = \"${VERSION}\"|" "$CONST"
  rm -f "${CONST}.bak"
else
  echo "error: VERSION assignment not found in ${CONST}" >&2
  exit 2
fi

echo "Wrote version ${VERSION} to ${MANIFEST} and ${CONST}"
