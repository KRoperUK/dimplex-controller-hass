#!/usr/bin/env bash
# Create a synthetic commit that only rewrites integration version files.
#
# Usage: create-dev-version-commit.sh <version>
#   Parent is the current HEAD (tested SHA). Does not push.
#
# Prints the new commit SHA on stdout.
set -euo pipefail

VERSION="${1:?version required}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

bash scripts/write-dev-version.sh "$VERSION"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

git add custom_components/dimplex/manifest.json custom_components/dimplex/const.py

if git diff --cached --quiet; then
  echo "error: no version file changes staged (already at ${VERSION}?)" >&2
  exit 1
fi

# Bot-only synthetic commit (version files); skip hooks so local pre-commit
# pins cannot block CI when hooks are not installed the same way.
git commit --no-verify -m "chore(dev): set version ${VERSION}"
git rev-parse HEAD
