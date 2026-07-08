#!/usr/bin/env bash
#
# Lint PR titles and commits to ensure they adhere to Conventional Commits.
#
set -euo pipefail

# 1. Validate PR Title (GitHub Actions environment)
if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ] && [ -n "${GITHUB_EVENT_PATH:-}" ]; then
  PR_TITLE=$(jq -r .pull_request.title "$GITHUB_EVENT_PATH")
  echo "Validating PR title: '$PR_TITLE'"
  if ! echo "$PR_TITLE" | grep -iqE '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|deps)(\([a-z0-9_-]+\))?!?: .+$'; then
    echo "ERROR: PR title does not follow Conventional Commits (e.g. 'feat(assets): add icon')."
    exit 1
  fi
  echo "PR title is valid."
fi

# 2. Validate Commits on the feature branch
if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ] && [ -n "${GITHUB_EVENT_PATH:-}" ]; then
  BASE_SHA=$(jq -r .pull_request.base.sha "$GITHUB_EVENT_PATH")
  HEAD_SHA=$(jq -r .pull_request.head.sha "$GITHUB_EVENT_PATH")
  
  echo "Validating commits between $BASE_SHA and $HEAD_SHA..."
  
  # Ensure we have the base commit fetched
  git fetch origin "$BASE_SHA" --depth=100 || git fetch origin "$BASE_SHA"
  
  # Lint each commit message (excluding merge commits)
  FAILED=0
  # Use process substitution to avoid subshell variable loss
  while read -r sha msg; do
    if echo "$msg" | grep -qE '^(Merge branch |Merge pull request |Merge remote-tracking branch )'; then
      echo "Skipping merge commit $sha: '$msg'"
      continue
    fi
    
    echo "Checking commit $sha: '$msg'"
    if ! echo "$msg" | grep -iqE '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|deps)(\([a-z0-9_-]+\))?!?: .+$'; then
      echo "ERROR: Commit '$msg' does not follow Conventional Commits."
      FAILED=1
    fi
  done < <(git log "${BASE_SHA}..${HEAD_SHA}" --format="%H %s")
  
  if [ "$FAILED" -eq 1 ]; then
    exit 1
  fi
  echo "All commits are valid."
else
  # Local validation (diff against target branch, defaults to main)
  TARGET_BRANCH="${1:-main}"
  echo "Local check: validating commits against $TARGET_BRANCH..."
  
  FAILED=0
  while read -r sha msg; do
    if echo "$msg" | grep -qE '^(Merge branch |Merge pull request |Merge remote-tracking branch )'; then
      continue
    fi
    
    if ! echo "$msg" | grep -iqE '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|deps)(\([a-z0-9_-]+\))?!?: .+$'; then
      echo "ERROR: Commit $sha ('$msg') does not follow Conventional Commits."
      FAILED=1
    fi
  done < <(git log "origin/${TARGET_BRANCH}..HEAD" --format="%H %s" 2>/dev/null || git log "${TARGET_BRANCH}..HEAD" --format="%H %s")
  
  if [ "$FAILED" -eq 1 ]; then
    exit 1
  fi
  echo "All local commits follow Conventional Commits."
fi
