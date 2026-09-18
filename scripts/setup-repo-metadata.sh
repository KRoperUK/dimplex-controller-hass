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
# Topics go through `PUT /repos/{owner}/{repo}/topics`, NOT through the repository
# PATCH. The PATCH endpoint accepts a `topics` key without complaint and then ignores
# it, so sending them that way appears to work, reports the old values back and
# changes nothing — which is exactly what the first version of this script did. The
# two calls are separate for that reason, and the end of the script asserts the result
# rather than printing it, because a `gh api` call that discards half its input still
# exits 0.
#
set -euo pipefail

OWNER="${1:-KRoperUK}"
HASS_REPO="dimplex-controller-hass"
PY_REPO="dimplex-controller-py"

HASS_TOPICS=(
  cloud-polling
  custom-component
  dimplex
  hacs
  hass
  heating
  home-assistant
  home-assistant-integration
  iot
  smart-home
)
PY_TOPICS=(
  api-client
  asyncio
  dimplex
  hass
  heating
  home-assistant
  iot
  python
)

if ! command -v gh >/dev/null 2>&1; then
  echo "gh (GitHub CLI) is required: https://cli.github.com/" >&2
  exit 1
fi

echo "Applying repository metadata for ${OWNER}..."

# Replaces the topic list wholesale: the endpoint takes the complete set, so a topic
# dropped from the list above is removed rather than left behind.
set_topics() {
  local repo=$1
  shift
  local args=()
  local topic
  for topic in "$@"; do
    args+=(-f "names[]=${topic}")
  done
  gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    "repos/${OWNER}/${repo}/topics" \
    "${args[@]}" > /dev/null
}

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
  "homepage": "https://dimplex-hass.kroper.uk/"
}
JSON
set_topics "${HASS_REPO}" "${HASS_TOPICS[@]}"

# The library had no homepage and no dependency/async topics, so it was hard to find
# from PyPI or from a topic search. `homepage` points at the PyPI project page, which
# is what a visitor arriving from the package index actually wants. The description is
# the one pyproject.toml publishes, so the two agree.
echo "  ${PY_REPO}"
gh api \
  --method PATCH \
  -H "Accept: application/vnd.github+json" \
  "repos/${OWNER}/${PY_REPO}" \
  --input - <<'JSON' > /dev/null
{
  "description": "Unofficial async Python client for Dimplex (GDHV IoT) heating appliances",
  "homepage": "https://pypi.org/project/dimplex-controller/"
}
JSON
set_topics "${PY_REPO}" "${PY_TOPICS[@]}"

echo
echo "Result:"
for repo in "${HASS_REPO}" "${PY_REPO}"; do
  gh api "repos/${OWNER}/${repo}" \
    --jq '{name, description, homepage, topics}'
done

status=0
check_topics() {
  local repo=$1 expected=$2
  local actual
  actual=$(gh api "repos/${OWNER}/${repo}" --jq '.topics | sort | join(" ")')
  if [ "${actual}" != "${expected}" ]; then
    echo "error: ${repo} topics are '${actual}'" >&2
    echo "       expected '${expected}'" >&2
    status=1
  fi
}
check_topics "${HASS_REPO}" "$(printf '%s\n' "${HASS_TOPICS[@]}" | sort | paste -sd' ' -)"
check_topics "${PY_REPO}" "$(printf '%s\n' "${PY_TOPICS[@]}" | sort | paste -sd' ' -)"

if [ "${status}" -ne 0 ]; then
  echo "One or more repositories do not hold the expected topics." >&2
fi
exit "${status}"
