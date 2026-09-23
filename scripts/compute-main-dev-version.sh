#!/usr/bin/env bash
# Compute a main-branch RC dev build's outputs for $GITHUB_OUTPUT.
#
# Env inputs:
#   SKIPPED         conventional-changelog-action's "nothing to release" flag
#   NEXT_VERSION    its predicted next version (empty when skipped)
#   MANIFEST        manifest path (default custom_components/dimplex/manifest.json)
#   BASE_SHA        the main commit the RC is built from (github.sha)
#   GITHUB_OUTPUT   Actions output file
#   GH_TOKEN / GITHUB_REPOSITORY   set by Actions
#
# Writes version, tag, base_version, base_sha, rc_number and skip.
#
# When v<VERSION> is already a full release this prunes the leftover RCs of that
# version line and reports skip=true instead of cutting another RC.
#
# Extracted from ci.yml (dimplex-controller-hass#235). test_repo_scripts.py pins
# the output file's exact contents, including that the "Next main RC candidate"
# log line stays on stdout: it used to sit next to the writes it summarises, so
# grouping the redirects for SC2129 would have written it into $GITHUB_OUTPUT.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="${MANIFEST:-${ROOT}/custom_components/dimplex/manifest.json}"

if [ "${SKIPPED:-}" = "true" ] || [ -z "${NEXT_VERSION:-}" ]; then
  VERSION=$(jq -r .version "$MANIFEST")
else
  VERSION="$NEXT_VERSION"
fi

# If this version is already fully released, remove leftover RC pre-releases
# (new vX.Y.Z-rc.N and legacy dev-vX.Y.Z-rc.N) and skip creating a new RC.
if gh release view "v${VERSION}" >/dev/null 2>&1; then
  echo "Full release v${VERSION} exists; deleting matching RC pre-releases."
  gh release list --limit 1000 --json tagName --jq '.[].tagName' \
  | { grep -E "^(dev-)?v${VERSION}-rc\\.[0-9]+$" || true; } \
  | while read -r tag; do
      echo "Deleting stale RC pre-release: ${tag}"
      gh release delete "$tag" --yes --cleanup-tag || true
    done
  echo "skip=true" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
  exit 0
fi

# Next RC: max(releases, git tags) + 1. Tags matter because deleting an
# *immutable* GitHub release still reserves the tag name.
RC_NUMBER=$(bash "${ROOT}/scripts/next-main-rc-number.sh" "${VERSION}")
HEAD_BRANCH=main
WORKFLOW_EVENT=push
export VERSION RC_NUMBER HEAD_BRANCH WORKFLOW_EVENT
mapfile -t _dev_kv < <(bash "${ROOT}/scripts/compute-dev-tag.sh")
{
  echo "${_dev_kv[0]}" # version=
  echo "${_dev_kv[1]}" # tag=
  echo "base_version=${VERSION}"
  echo "base_sha=${BASE_SHA}"
  echo "rc_number=${RC_NUMBER}"
  echo "skip=false"
} >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
# Deliberately outside the block: this one is a log line, not an output.
echo "Next main RC candidate: ${_dev_kv[1]#tag=}"
