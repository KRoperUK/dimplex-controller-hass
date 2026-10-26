#!/usr/bin/env bash
#
# Lint PR titles and commits to ensure they adhere to Conventional Commits.
#
set -euo pipefail

# Read "<sha> <subject>" lines for a commit range, failing on an empty one.
#
# `git log BASE..HEAD` prints nothing and exits 0 when the range is empty — a
# wrong base, a fetch that silently did nothing, a shallow checkout — so the
# linting loops below would run zero times and the script would report "All
# commits are valid." having checked nothing (#288). An empty range is never a
# legitimate answer here: a pull request always has at least one commit.
read_commits() {
  local description=$1
  shift
  local commits
  if ! commits=$(git log "$@" --format="%H %s"); then
    echo "ERROR: could not read commits in ${description}." >&2
    return 1
  fi
  if [ -z "${commits}" ]; then
    echo "ERROR: no commits in ${description}." >&2
    echo "       A wrong base, a failed fetch or a shallow checkout looks exactly like this," >&2
    echo "       so an empty range is a failure, not a clean bill of health." >&2
    return 1
  fi
  printf '%s\n' "${commits}"
}

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

  # Ensure we have both endpoints of the range. The checkout in CI is the pull
  # request's *merge* ref, so the head commit is not in the object database at all
  # and `git log BASE..HEAD` fails with "Invalid revision range" rather than an
  # empty list — which is why the fetch has to cover the head sha as well (#288).
  # A failed fetch is left to read_commits to report: it refuses the empty range.
  for sha in "$BASE_SHA" "$HEAD_SHA"; do
    git fetch origin "$sha" --depth=100 || git fetch origin "$sha" || true
  done

  if ! COMMITS=$(read_commits "${BASE_SHA}..${HEAD_SHA}" "${BASE_SHA}..${HEAD_SHA}"); then
    exit 1
  fi

  # Lint each commit message (excluding merge commits)
  FAILED=0
  # A here-string, not a process substitution: the loop then runs in this shell,
  # so FAILED survives it, and the commit list is the one read_commits validated.
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
  done <<<"$COMMITS"

  if [ "$FAILED" -eq 1 ]; then
    exit 1
  fi
  echo "All commits are valid."
else
  # Local validation (diff against target branch, defaults to main)
  TARGET_BRANCH="${1:-main}"
  echo "Local check: validating commits against $TARGET_BRANCH..."

  # Prefer origin/<branch>, fall back to a local branch of that name. Either way
  # an empty range is a hard failure rather than a pass (#288).
  if ! COMMITS=$(read_commits "origin/${TARGET_BRANCH}..HEAD" "origin/${TARGET_BRANCH}..HEAD" 2>/dev/null); then
    if ! COMMITS=$(read_commits "${TARGET_BRANCH}..HEAD" "${TARGET_BRANCH}..HEAD"); then
      exit 1
    fi
  fi

  FAILED=0
  while read -r sha msg; do
    if echo "$msg" | grep -qE '^(Merge branch |Merge pull request |Merge remote-tracking branch )'; then
      continue
    fi

    if ! echo "$msg" | grep -iqE '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert|deps)(\([a-z0-9_-]+\))?!?: .+$'; then
      echo "ERROR: Commit $sha ('$msg') does not follow Conventional Commits."
      FAILED=1
    fi
  done <<<"$COMMITS"

  if [ "$FAILED" -eq 1 ]; then
    exit 1
  fi
  echo "All local commits follow Conventional Commits."
fi
