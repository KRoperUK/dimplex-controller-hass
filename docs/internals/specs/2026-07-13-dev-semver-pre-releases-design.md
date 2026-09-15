# Design: Semver pre-release versions for HACS dev builds

**Issue:** [KRoperUK/dimplex-controller-hass#77](https://github.com/KRoperUK/dimplex-controller-hass/issues/77)
**Date:** 2026-07-13
**Status:** Implementation in progress (Approach A)

## Problem

Dogfood installs of automated pre-releases confuse HACS / the HA update entity:

| Field                | Example (before)                               |
| -------------------- | ---------------------------------------------- |
| Installed (tag / UI) | `dev-v2.1.0-feat-device-registry-metadata-…`   |
| HACS “latest”        | `v2.0.0`                                       |
| Update entity        | `on` (looks like an update / restart required) |

Root causes:

1. **Git tags use a non-semver `dev-` prefix** (`dev-vX.Y.Z-rc.N`, `dev-vX.Y.Z-<branch>-<run_id>`), so HACS and version libraries cannot order them against stable `vX.Y.Z`.
2. **Pre-release tags point at unmodified main/PR commits.** `manifest.json` and `const.py` still carry the last **stable** version (e.g. `2.0.0`), so the tree HACS installs does not advertise “preview of next release”.
3. **Main must stay immutable for release-please.** We must not bump version files on `main` for every RC/PR build.

## Goals

1. Installed integration version is a **valid semver pre-release** of the predicted next version, so:
   - `last_stable` &lt; `X.Y.Z-rc.N` &lt; final `X.Y.Z`
   - HACS/HA stop spuriously offering “update” to an older stable while on a newer RC
   - Shipping the real `X.Y.Z` correctly supersedes RCs
2. **Do not rewrite version files on `main`.** release-please remains the only writer of stable versions on the default branch.
3. **Tags remain immutable** once published (GitHub immutable releases already constrain tag reuse).
4. Document stable vs pre-release install channels and the update-entity behaviour (#77 docs).

## Non-goals

- Changing release-please stable release flow or tag shape (`vX.Y.Z`).
- Migrating or renaming historical `dev-v*` releases (age out via existing cleanup).
- Publishing dev releases for fork PRs (still skipped — no write token).
- Changing HACS default discovery (stable remains default for end users).

## Chosen approach

**Approach A — Synthetic version commits + semver tags (+ optional `dev` branch).**

After CI is green for a component-impacting change:

1. Check out the **tested commit** (main push SHA or PR head SHA).
2. Rewrite only version surfaces on a **new commit** whose parent is that tested SHA.
3. Create an immutable pre-release **tag** on the synthetic commit and publish a GitHub **prerelease**.
4. Optionally force-update long-lived branch `dev` to the latest **main RC** synthetic commit for tip-of-dev installs.

`main` never receives synthetic commits. Tags never move. Only `dev` (if used) may force-move.

## Version scheme

Next version `X.Y.Z` is still predicted by conventional-changelog against `custom_components/dimplex/manifest.json` (existing CI step). If prediction is skipped/empty, fall back to the current manifest version (same as today).

| Kind     | Manifest / `const.VERSION` | Git tag         | Notes                                                                                                                         |
| -------- | -------------------------- | --------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Main RC  | `X.Y.Z-rc.N`               | `vX.Y.Z-rc.N`   | `N` from existing counter (releases + orphaned tags), dotted for numeric order (`rc.10` &gt; `rc.9`)                          |
| PR build | `X.Y.Z-pr.P.S`             | `vX.Y.Z-pr.P.R` | `P` = PR number; `S` = short SHA (7) in **manifest** for readability; `R` = `run_id` in **tag** for uniqueness across re-runs |
| Stable   | `X.Y.Z`                    | `vX.Y.Z`        | Unchanged; release-please only                                                                                                |

Examples:

- Main: version `3.0.0-rc.2`, tag `v3.0.0-rc.2`
- PR #81 run 29215103640 at `a8aa20b`: version `3.0.0-pr.81.a8aa20b`, tag `v3.0.0-pr.81.29215103640`

**Identifier rules (semver pre-release):** only `[0-9A-Za-z-]` in pre-release segments; no leading `dev-` on tags.

**Ordering expectations** (awesomeversion / packaging-style):

- `2.0.0` &lt; `3.0.0-pr.81.a8aa20b` &lt; `3.0.0-rc.1` &lt; `3.0.0-rc.2` &lt; `3.0.0`
  (Exact PR vs RC order among pre-releases is secondary; both must sort **above** the previous stable and **below** the final release.)

## Files rewritten on synthetic commits only

| Path                                      | Change                                                 |
| ----------------------------------------- | ------------------------------------------------------ |
| `custom_components/dimplex/manifest.json` | `"version": "<pre-release>"`                           |
| `custom_components/dimplex/const.py`      | `VERSION = "<pre-release>" # x-release-please-version` |

No other files. Preserve manifest key order (domain, name, then alphabetical) and existing formatting so pre-commit/HACS validation would still pass if re-run on the tree.

## Git / CI flow

```
tested SHA (main or PR head)
        │
        ▼
  patch version files in working tree
        │
        ▼
  commit "chore(dev): set version <pre-release>"
  (parent = tested SHA; not pushed to main)
        │
        ├─► git tag v…  (immutable)
        ├─► gh release create --prerelease --target <synthetic SHA>
        └─► [main RC only] git push origin HEAD:dev --force
```

### Implementation notes for CI

- Configure git identity as the existing bot/`github-actions[bot]` pattern used elsewhere if any; otherwise standard Actions bot.
- Use `git commit` with only the two version files staged.
- Pass `TAG` and `COMMIT_SHA` (synthetic) into `verify-dev-release-target.sh`.
- Release notes body can stay largely as today (WARNING admonition, stable pointer, changelog / PR metadata). Update wording if it still says tag prefix `dev-`.
- **Do not** force-push `dev` for PR builds (avoids clobbering main RC tip with PR noise).
- Creating the synthetic commit requires `contents: write` (already held by `dev-release` / `dev-release-main`).

### Collision / rollover

Keep main RC rollover behaviour: if tag create fails due to existing/immutable tag, bump `N` and retry (existing loop), regenerating the synthetic commit for the new version string each attempt (or amend only if the commit was never pushed — prefer new commit + new tag for simplicity).

If full release `vX.Y.Z` already exists, skip new RCs and prune matching pre-releases for that version (existing behaviour), using the **new** tag patterns.

## Script and workflow inventory

| Artifact                                     | Change                                                                                                                                                                                     |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/compute-dev-tag.sh`                 | Emit tag `v{ver}-rc.{n}` or `v{ver}-pr.{pr}.{run_id}`; optionally also print bare version for file patching (or split into `compute-dev-version.sh`).                                      |
| `scripts/next-main-rc-number.sh`             | Match `^v{ver}-rc\.[0-9]+$` (and git refs under `tags/v{ver}-rc.`), not `dev-v…`.                                                                                                          |
| `scripts/verify-dev-release-target.sh`       | Unchanged contract (`TAG`, `COMMIT_SHA`); callers pass synthetic SHA.                                                                                                                      |
| New helper (recommended)                     | e.g. `scripts/write-dev-version.sh <version>` — sets both version files idempotently for CI.                                                                                               |
| `.github/workflows/ci.yml`                   | `dev-release` and `dev-release-main`: synthetic commit + new tags; force-push `dev` on main RC only.                                                                                       |
| `.github/workflows/cleanup-dev-releases.yml` | Sweep pre-releases whose tags match `^v[0-9]+\.[0-9]+\.[0-9]+-(rc                                                                                                                          | pr)\.`(or`isPrerelease`and not equal to latest stable pattern), not only`dev-`prefix. Keep 30-day age policy. Continue deleting legacy`dev-\*` tags. |
| `.github/workflows/cleanup-pr-release.yml`   | Match `^v[0-9]+\.[0-9]+\.[0-9]+-pr\.{PR}\.[0-9]+$` (PR number is stable across re-runs; prefer PR-based cleanup over branch slug). Branch-slug fallback optional for legacy `dev-v*` tags. |
| `.github/workflows/pr-status-labels.yml`     | Detect new tag shapes for `dev-release-cut` label.                                                                                                                                         |
| Docs                                         | See below.                                                                                                                                                                                 |

## Optional `dev` branch

- **Purpose:** single moving tip for maintainers who install “latest main RC” without picking a tag.
- **Update rule:** force-push only from successful **main** RC job to the synthetic commit for that RC.
- **Not** a second product channel with divergent code — always `main` tip + version files only.
- Document that HACS users should prefer **specific pre-release tags** or stable; branch install is advanced/dogfood.

If force-pushing `dev` is later undesirable, tags alone satisfy #77; the branch is optional polish and can land in the same PR or a follow-up.

## Documentation (#77)

### Getting started / advanced

- **Default:** install via HACS **stable** (non-pre-release).
- **Testers/maintainers:** enable pre-releases in HACS (or install a specific `vX.Y.Z-rc.N` / PR pre-release from GitHub Releases).
- Clarify that automated PR builds are pre-merge and may disappear when the PR closes.

### Troubleshooting

New subsection, e.g. **“HACS shows an update after installing a pre-release”**:

- If installed is `X.Y.Z-rc.*` / `X.Y.Z-pr.*` and “latest” is an older stable, ensure HACS pre-release channel is enabled, or reinstall stable deliberately.
- After this change, a newer RC should not offer a **downgrade** to older stable under correct semver comparison.
- When final `X.Y.Z` ships, updating from RC to stable is expected and correct.
- Point to GitHub Releases for channel/tag clarity.

### README (short)

One line under development/install if it mentions dev builds: tags are `vX.Y.Z-rc.N`, not `dev-v…`.

## Migration

| Item                           | Action                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Existing `dev-v*` pre-releases | Leave; 30-day cleanup + any “full release exists” prune still remove them once patterns are extended.   |
| In-flight PRs                  | Next green CI mints new-shape tags; old branch tags cleaned on PR close if cleanup regex covers legacy. |
| Dogfood HA                     | Reinstall from a new-shaped pre-release once published; no forced migration.                            |

## Testing / verification

1. **Unit/script:** shell tests or dry-run assertions for `compute-dev-tag` / `next-main-rc-number` / `write-dev-version` (if added) with fixtures.
2. **CI dry logic:** on a throwaway PR, confirm:
   - Synthetic commit parent is PR head
   - Manifest + const match
   - Tag is `v…-pr.…` and prerelease
   - Release target SHA equals synthetic commit
3. **Main RC:** after merge (or workflow_dispatch path if any), confirm `vX.Y.Z-rc.N`, optional `dev` tip, and no commit on `main` with the pre-release version.
4. **Ordering smoke:** compare strings with the same library HA/HACS use if available in test env; at least document expected order and manual HACS check on dogfood.
5. **Cleanup:** ensure PR close deletes `v…-pr.{n}.*` for that PR; schedule job still deletes aged pre-releases including legacy `dev-*`.

## Risks and mitigations

| Risk                                     | Mitigation                                                                                 |
| ---------------------------------------- | ------------------------------------------------------------------------------------------ |
| Tag shape collides with release-please   | release-please only cuts exact `vX.Y.Z`; pre-release tags always contain `-rc.` or `-pr.`. |
| Synthetic commits clutter default branch | Never push them to `main`; only tags (+ optional `dev`).                                   |
| `dev` force-push surprises clones        | Document; only main RC updates it; optional feature.                                       |
| HACS still prefers stable when beta off  | Document; expected product behaviour for end users.                                        |
| Immutable tag burns RC numbers           | Keep existing rollover + tag-aware RC counter.                                             |

## Success criteria

1. A main RC install reports version `X.Y.Z-rc.N` in `manifest.json` / diagnostics (`const.VERSION`).
2. That version is **greater than** the previous stable and **less than** the eventual stable `X.Y.Z`.
3. `main` tip’s version files remain release-please-controlled stable (or open release PR values), never sticky RC strings.
4. Docs cover stable vs pre-release and the former false “update available” case (#77).
5. Cleanup and labels work with new tag patterns and still tolerate legacy `dev-v*` until gone.

## Decision log

- **2026-07-13:** User selected version behaviour “semver pre-release on next version”.
- **2026-07-13:** User selected Approach A (synthetic commits + semver tags; optional `dev` branch).
