#!/usr/bin/env bash
# Lightweight checks for dev version helper scripts (no network).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
fail=0

assert_eq() {
  local name="$1" expected="$2" actual="$3"
  if [ "$expected" != "$actual" ]; then
    echo "FAIL ${name}: expected '${expected}', got '${actual}'" >&2
    fail=1
  else
    echo "OK   ${name}"
  fi
}

# --- compute-dev-tag: main RC ---
out=$(VERSION=3.0.0 HEAD_BRANCH=main WORKFLOW_EVENT=push RC_NUMBER=2 bash scripts/compute-dev-tag.sh)
assert_eq "main version" "version=3.0.0-rc.2" "$(printf '%s\n' "$out" | sed -n '1p')"
assert_eq "main tag" "tag=v3.0.0-rc.2" "$(printf '%s\n' "$out" | sed -n '2p')"

# --- compute-dev-tag: PR ---
out=$(
  VERSION=3.0.0 HEAD_BRANCH=feat/x WORKFLOW_EVENT=pull_request \
    PR_NUMBER=81 SHORT_SHA=a8aa20bdeadbeef RUN_ID=29215103640-1 \
    bash scripts/compute-dev-tag.sh
)
assert_eq "pr version" "version=3.0.0-pr.81.a8aa20b" "$(printf '%s\n' "$out" | sed -n '1p')"
assert_eq "pr tag" "tag=v3.0.0-pr.81.29215103640-1" "$(printf '%s\n' "$out" | sed -n '2p')"

# --- write-dev-version ---
cp custom_components/dimplex/manifest.json /tmp/dimplex-manifest.bak
cp custom_components/dimplex/const.py /tmp/dimplex-const.bak
trap 'mv /tmp/dimplex-manifest.bak custom_components/dimplex/manifest.json
      mv /tmp/dimplex-const.bak custom_components/dimplex/const.py' EXIT

# write-dev-version must not pollute stdout (used in SHA-capture pipelines).
write_out=$(bash scripts/write-dev-version.sh 3.1.0-rc.4 2>/dev/null)
assert_eq "write-dev-version stdout empty" "" "$write_out"
mv=$(jq -r .version custom_components/dimplex/manifest.json)
cv=$(sed -n 's/^VERSION = "\([^"]*\)".*/\1/p' custom_components/dimplex/const.py | head -1)
assert_eq "manifest version" "3.1.0-rc.4" "$mv"
assert_eq "const VERSION" "3.1.0-rc.4" "$cv"

# Key order: domain, name must remain first two keys.
keys=$(jq -r 'keys_unsorted | @tsv' custom_components/dimplex/manifest.json)
first=$(printf '%s' "$keys" | awk '{print $1}')
second=$(printf '%s' "$keys" | awk '{print $2}')
assert_eq "manifest domain first" "domain" "$first"
assert_eq "manifest name second" "name" "$second"

# Invalid version rejected
if bash scripts/write-dev-version.sh 'not a version' 2>/dev/null; then
  echo "FAIL invalid version should exit non-zero" >&2
  fail=1
else
  echo "OK   invalid version rejected"
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "All script checks passed."
