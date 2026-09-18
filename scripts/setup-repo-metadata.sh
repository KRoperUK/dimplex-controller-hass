#!/usr/bin/env bash
#
# Apply repository metadata — description, homepage and topics — for the Dimplex
# repositories.
#
# Requires the GitHub CLI (`gh`) authenticated as an account that can edit the
# repositories. Usage: scripts/setup-repo-metadata.sh [owner]
#
# Metadata has no file in the repository to hold it, so it drifts: the integration's
# description still named the *library* ("Dimplex Controller"), neither repo carried
# the topics that make it findable among Home Assistant integrations, and the library
# had no homepage at all. Keeping it in a script means the change is reviewable in a
# pull request and re-runnable if the settings drift again — the same reason
# setup-branch-protection.sh exists (dimplex-controller-hass#202).
#
set -euo pipefail

OWNER="${1:-KRoperUK}"
HASS_REPO="dimplex-controller-hass"
PY_REPO="dimplex-controller-py"

if ! command -v gh >/dev/null 2>&1; then
  echo "gh (GitHub CLI) is required: https://cli.github.com/" >&2
  exit 1
fi

echo "Applying repository metadata for ${OWNER}..."

# The integration is "Dimplex Hub"; "Dimplex Controller" is the library's name, and
# the description had them the wrong way round. "hass" is kept alongside the more
# standard "home-assistant" topics because it is what HACS-adjacent searches use.
echo "  ${HASS_REPO}"
gh api \
  --method PATCH \
  -H "Accept: application/vnd.github+json" \
  "repos/${OWNER}/${HASS_REPO}" \
  --input - <<'JSON' > /dev/null
{
  "description": "Home Assistant integration for Dimplex Hub — heat and hot water control for Dimplex appliances",
  "homepage": "https://dimplex-hass.kroper.uk/",
  "topics": [
    "cloud-polling",
    "custom-component",
    "dimplex",
    "hacs",
    "hass",
    "home-assistant",
    "home-assistant-integration",
    "heating",
    "iot",
    "smart-home"
  ]
}
JSON

# The library had no homepage and no dependency/async topics, so it was hard to find
# from PyPI or from a topic search. `homepage` points at the PyPI project page, which
# is what a visitor arriving from the package index actually wants.
echo "  ${PY_REPO}"
gh api \
  --method PATCH \
  -H "Accept: application/vnd.github+json" \
  "repos/${OWNER}/${PY_REPO}" \
  --input - <<'JSON' > /dev/null
{
  "description": "Unofficial async Python client for Dimplex (GDHV IoT) heating appliances",
  "homepage": "https://pypi.org/project/dimplex-controller/",
  "topics": [
    "api-client",
    "asyncio",
    "dimplex",
    "hass",
    "heating",
    "home-assistant",
    "iot",
    "python"
  ]
}
JSON

echo
echo "Result:"
for repo in "${HASS_REPO}" "${PY_REPO}"; do
  gh api "repos/${OWNER}/${repo}" \
    --jq '{name, description, homepage, topics, has_discussions}'
done
