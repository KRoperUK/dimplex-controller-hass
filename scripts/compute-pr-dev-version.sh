#!/usr/bin/env bash
# Compute a PR dev build's version, tag, base_version and base_sha for $GITHUB_OUTPUT.
#
# Env inputs:
#   SKIPPED         conventional-changelog-action's "nothing to release" flag
#   NEXT_VERSION    its predicted next version (empty when skipped)
#   MANIFEST        manifest path (default custom_components/dimplex/manifest.json)
#   HEAD_BRANCH     PR source branch
#   PR_NUMBER       pull request number
#   SHORT_SHA       PR head SHA (also the release's base commit)
#   RUN_ID          run id + attempt, so a re-run mints a unique tag
#   GITHUB_OUTPUT   Actions output file
#
# Extracted from ci.yml (dimplex-controller-hass#235). The outputs are written
# one redirect per line rather than grouped behind a single `>>`, so a stray log
# line cannot be captured as an output without the test noticing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="${MANIFEST:-${ROOT}/custom_components/dimplex/manifest.json}"

if [ "${SKIPPED:-}" = "true" ] || [ -z "${NEXT_VERSION:-}" ]; then
  VERSION=$(jq -r .version "$MANIFEST")
else
  VERSION="$NEXT_VERSION"
fi

WORKFLOW_EVENT=pull_request
export VERSION HEAD_BRANCH PR_NUMBER SHORT_SHA RUN_ID WORKFLOW_EVENT
mapfile -t _dev_kv < <(bash "${ROOT}/scripts/compute-dev-tag.sh")

{
  echo "${_dev_kv[0]}" # version=
  echo "${_dev_kv[1]}" # tag=
  echo "base_version=${VERSION}"
  echo "base_sha=${SHORT_SHA}"
} >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
