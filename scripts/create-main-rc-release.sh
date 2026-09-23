#!/usr/bin/env bash
# Create the main-branch RC pre-release, rolling the RC number over on tag collisions.
#
# Env inputs:
#   BASE_VERSION   X.Y.Z the RC previews
#   BASE_SHA       main commit the RC is built from
#   RC_NUMBER      first RC number to try
#   CHANGELOG      release-please's rendered changelog (may be empty)
#   GITHUB_OUTPUT  Actions output file (receives created_tag)
#   GH_TOKEN / GITHUB_REPOSITORY   set by Actions
#
# Runs from the repository root: it rewrites the version files in a synthetic
# commit, tags it and pushes the tag. On success it writes created_tag=<tag>.
#
# Extracted verbatim from ci.yml (dimplex-controller-hass#235) so the rollover
# loop can be exercised without touching a real repository — see
# tests/test_repo_scripts.py, which drives it against a throwaway git remote
# with a stubbed `gh`. Moved as-is: the collision detection (git push rejection,
# gh's "already exists"/422 responses) is what has to keep working when a tag
# x.y.z-rc.N is already reserved by a deleted immutable release.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

latest_stable=$(gh api "repos/${GITHUB_REPOSITORY}/releases/latest" --jq '.tag_name' 2>/dev/null || true)
if [ -n "$latest_stable" ]; then
  stable_line="For everyday use, install the latest **stable** release instead: [\`${latest_stable}\`](https://github.com/${GITHUB_REPOSITORY}/releases/tag/${latest_stable})."
else
  stable_line="No stable release has been published yet."
fi

max_attempts=25
attempt=0
while [ "${attempt}" -lt "${max_attempts}" ]; do
  attempt=$((attempt + 1))
  # Recompute tag/version from RC_NUMBER each attempt.
  VERSION="$BASE_VERSION"
  HEAD_BRANCH=main
  WORKFLOW_EVENT=push
  export VERSION RC_NUMBER HEAD_BRANCH WORKFLOW_EVENT
  mapfile -t _dev_kv < <(bash "${ROOT}/scripts/compute-dev-tag.sh")
  DEV_VERSION="${_dev_kv[0]#version=}"
  TAG="${_dev_kv[1]#tag=}"
  export TAG DEV_VERSION

  if gh release view "$TAG" >/dev/null 2>&1; then
    existing_target=$(gh api "repos/${GITHUB_REPOSITORY}/git/ref/tags/${TAG}" --jq '.object.sha' 2>/dev/null || true)
    object_type=$(gh api "repos/${GITHUB_REPOSITORY}/git/ref/tags/${TAG}" --jq '.object.type' 2>/dev/null || true)
    if [ "$object_type" = "tag" ] && [ -n "$existing_target" ]; then
      existing_target=$(gh api "repos/${GITHUB_REPOSITORY}/git/tags/${existing_target}" --jq '.object.sha' 2>/dev/null || true)
    fi
    parent=$(gh api "repos/${GITHUB_REPOSITORY}/git/commits/${existing_target}" --jq '.parents[0].sha' 2>/dev/null || true)
    if [ -n "$existing_target" ] && [ "$parent" = "$BASE_SHA" ]; then
      echo "Release ${TAG} already built from ${BASE_SHA}; keeping."
      echo "created_tag=${TAG}" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
      exit 0
    fi
    echo "Release/tag ${TAG} exists (target ${existing_target:-unknown}); rolling over."
    RC_NUMBER=$((RC_NUMBER + 1))
    continue
  fi

  git reset --hard "$BASE_SHA"
  SYNTHETIC_SHA=$(bash "${ROOT}/scripts/create-dev-version-commit.sh" "$DEV_VERSION")
  export COMMIT_SHA="$SYNTHETIC_SHA"

  {
    echo "> [!WARNING]"
    echo "> **This is an automated release-candidate build, not an official release.**"
    echo "> It previews the upcoming **v${BASE_VERSION}** release from \`main\` (base commit \`${BASE_SHA}\`) and may be unstable."
    echo "> Integration version in this tree: \`${DEV_VERSION}\` (semver pre-release)."
    echo "> ${stable_line}"
    echo ""
    echo "## What's changed for v${BASE_VERSION}"
    echo ""
    if [ -n "${CHANGELOG}" ]; then
      printf '%s\n' "${CHANGELOG}"
    else
      echo "_No user-facing changes detected since the last release._"
    fi
  } > rc-notes.md

  git tag -f "$TAG" "$SYNTHETIC_SHA"
  set +e
  push_out=$(git push origin "refs/tags/${TAG}" 2>&1)
  push_status=$?
  set -e
  if [ "${push_status}" -ne 0 ]; then
    echo "git push tag failed for ${TAG} (attempt ${attempt}):"
    printf '%s\n' "${push_out}"
    if printf '%s\n' "${push_out}" | grep -qiE 'already exists|rejected|cannot lock'; then
      RC_NUMBER=$((RC_NUMBER + 1))
      echo "Tag push collision; next RC_NUMBER=${RC_NUMBER}"
      continue
    fi
    exit "${push_status}"
  fi

  # HACS zip_release asset: package from the synthetic tree (version files set).
  bash "${ROOT}/scripts/package-hacs-zip.sh" dimplex.zip

  set +e
  create_out=$(gh release create "$TAG" \
    --prerelease \
    --title "$TAG" \
    --target "$SYNTHETIC_SHA" \
    --notes-file rc-notes.md \
    dimplex.zip 2>&1)
  create_status=$?
  set -e
  if [ "${create_status}" -eq 0 ]; then
    export TAG COMMIT_SHA
    bash "${ROOT}/scripts/verify-dev-release-target.sh"
    echo "Created ${TAG} -> ${SYNTHETIC_SHA} (base ${BASE_SHA}, version ${DEV_VERSION})"
    # Publish the tag actually created (RC_NUMBER may have rolled over on
    # collision) so the follow-up prune keeps the right one.
    echo "created_tag=${TAG}" >> "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
    exit 0
  fi
  echo "gh release create failed for ${TAG} (attempt ${attempt}):"
  printf '%s\n' "${create_out}"
  if ! printf '%s\n' "${create_out}" | grep -qiE \
    'already exists|immutable|Validation Failed|Reference already exists|tag_name was used|Unprocessable Entity|HTTP 422'; then
    exit "${create_status}"
  fi
  echo "Tag collision / immutable reservation for ${TAG}; rolling over."
  git push origin ":refs/tags/${TAG}" 2>/dev/null || true
  RC_NUMBER=$((RC_NUMBER + 1))
done
echo "Exhausted ${max_attempts} RC tag attempts without creating a release." >&2
exit 1
