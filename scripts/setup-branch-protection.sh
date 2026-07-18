#!/usr/bin/env bash
#
# Configure branch protection + rulesets for the default branch.
#
# Requires the GitHub CLI (`gh`) authenticated as a repo admin.
# Usage: scripts/setup-branch-protection.sh [owner/repo] [branch]
#
# The single required status check is the aggregate `ci` job from
# `.github/workflows/ci.yml`. That job always runs:
#   - component PRs: fails unless lint/mypy/pre-commit/test/hacs/scripts/…
#     succeed (and conventional_commits on pull_request)
#   - docs-only / release-please version bumps: still reports success so
#     path-filtered skips cannot block merge
#
set -euo pipefail

REPO="${1:-KRoperUK/dimplex-controller-hass}"
BRANCH="${2:-main}"

echo "Applying classic branch protection to ${REPO}@${BRANCH}..."

gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "repos/${REPO}/branches/${BRANCH}/protection" \
  --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["ci"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON

echo "Updating repository rulesets..."

# Resolve ruleset IDs by name (stable across re-runs).
MAIN_RULESET_ID=$(
  gh api "repos/${REPO}/rulesets" \
    --jq '.[] | select(.name=="main") | .id' | head -n1
)
GENERAL_RULESET_ID=$(
  gh api "repos/${REPO}/rulesets" \
    --jq '.[] | select(.name=="general") | .id' | head -n1
)

if [ -z "${MAIN_RULESET_ID}" ]; then
  echo "Creating ruleset 'main'..."
  gh api \
    --method POST \
    -H "Accept: application/vnd.github+json" \
    "repos/${REPO}/rulesets" \
    --input - <<'JSON'
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "required_signatures" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "required_review_thread_resolution": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_reviewers": [],
        "allowed_merge_methods": ["squash"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "ci" }
        ]
      }
    }
  ]
}
JSON
else
  echo "Updating ruleset 'main' (id=${MAIN_RULESET_ID})..."
  gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    "repos/${REPO}/rulesets/${MAIN_RULESET_ID}" \
    --input - <<'JSON'
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "required_signatures" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "required_review_thread_resolution": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_reviewers": [],
        "allowed_merge_methods": ["squash"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "ci" }
        ]
      }
    }
  ]
}
JSON
fi

if [ -z "${GENERAL_RULESET_ID}" ]; then
  echo "Creating ruleset 'general'..."
  gh api \
    --method POST \
    -H "Accept: application/vnd.github+json" \
    "repos/${REPO}/rulesets" \
    --input - <<'JSON'
{
  "name": "general",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~ALL"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "required_signatures" }
  ]
}
JSON
else
  echo "Updating ruleset 'general' (id=${GENERAL_RULESET_ID})..."
  gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    "repos/${REPO}/rulesets/${GENERAL_RULESET_ID}" \
    --input - <<'JSON'
{
  "name": "general",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~ALL"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "required_signatures" }
  ]
}
JSON
fi

echo
echo "Done. Classic protection summary:"
gh api "repos/${REPO}/branches/${BRANCH}/protection" \
  --jq '{
    required_checks: .required_status_checks.contexts,
    strict: .required_status_checks.strict,
    linear: .required_linear_history.enabled,
    force_pushes: .allow_force_pushes.enabled,
    deletions: .allow_deletions.enabled,
    conversation_resolution: .required_conversation_resolution.enabled
  }'

echo
echo "Rulesets:"
gh api "repos/${REPO}/rulesets" --jq '.[] | {id, name, enforcement}'
echo
echo "Main ruleset detail:"
MAIN_RULESET_ID=$(
  gh api "repos/${REPO}/rulesets" \
    --jq '.[] | select(.name=="main") | .id' | head -n1
)
gh api "repos/${REPO}/rulesets/${MAIN_RULESET_ID}" \
  --jq '{name, rules: [.rules[].type]}'
