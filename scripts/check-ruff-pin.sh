#!/usr/bin/env bash
# Verify the ruff version pinned in requirements_test.txt matches the
# ruff-pre-commit rev in .pre-commit-config.yaml.
#
# The two pins must stay in sync: pre-commit installs its own copy of ruff
# via ruff-pre-commit (pinned by the `rev:`), while CI installs ruff from
# requirements_test.txt. If they diverge, lint and format can disagree on
# what's "correct" output (this bit us with the ruff 0.15 except-clause
# formatter bug, see PR #112).
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
req_pin=""
precommit_rev=""

if [[ -f "$repo_root/requirements_test.txt" ]]; then
  req_pin=$(grep -E '^ruff==' "$repo_root/requirements_test.txt" | head -1 | sed -E 's/^ruff==//; s/[[:space:]]*$//' || true)
fi

if [[ -f "$repo_root/.pre-commit-config.yaml" ]]; then
  # The pre-commit config lists ruff-pre-commit under a `repo:` URL and pins
  # the revision on the next line as `    rev: vX.Y.Z`. Extract that value.
  precommit_rev=$(awk '
    /repo: https:\/\/github\.com\/astral-sh\/ruff-pre-commit/ {found = 1; next}
    found && /^[[:space:]]*rev:[[:space:]]*/ {
      sub(/^[[:space:]]*rev:[[:space:]]*/, "")
      sub(/[[:space:]]*#.*$/, "")
      print
      exit
    }
  ' "$repo_root/.pre-commit-config.yaml" || true)
fi

# Normalise: requirements_test.txt uses plain "0.14.14", pre-commit uses "v0.14.14".
precommit_rev_norm="${precommit_rev#v}"

if [[ -z "$req_pin" ]]; then
  echo "✗ No 'ruff==X.Y.Z' pin found in requirements_test.txt" >&2
  exit 1
fi
if [[ -z "$precommit_rev_norm" ]]; then
  echo "✗ No 'rev: vX.Y.Z' found for ruff-pre-commit in .pre-commit-config.yaml" >&2
  exit 1
fi
if [[ "$req_pin" != "$precommit_rev_norm" ]]; then
  cat >&2 <<EOF
✗ Ruff pin drift detected:
    requirements_test.txt:       ruff==${req_pin}
    .pre-commit-config.yaml:     rev: v${precommit_rev_norm}
  Update both to the same version. They are intentionally pinned together
  so the linter and formatter cannot disagree.
EOF
  exit 1
fi

echo "✓ Ruff pin consistent: ${req_pin} (requirements_test.txt == .pre-commit-config.yaml)"
