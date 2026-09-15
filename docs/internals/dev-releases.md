---
description: How the Dimplex Hub integration versions and publishes stable releases, main release candidates and per-PR pre-release builds.
---

# Dev & pre-release builds

Most users want the **stable** channel and can ignore this page. It is here for testers and
for anyone puzzled by a version string.

## Release shapes

CI publishes a prerelease GitHub Release whenever a component-impacting PR or a push to
`main` goes green:

| Kind                   | Tag             | Installed version                         |
| ---------------------- | --------------- | ----------------------------------------- |
| Stable                 | `vX.Y.Z`        | `X.Y.Z` — cut by release-please on `main` |
| Main release candidate | `vX.Y.Z-rc.N`   | `X.Y.Z-rc.N`                              |
| PR build               | `vX.Y.Z-pr.P.R` | `X.Y.Z-pr.P.<shortsha>`                   |

Pre-release versions sort **above** the previous stable and **below** the eventual `X.Y.Z`,
so updating from `4.1.0-rc.3` to `4.1.0` is a normal forward step.

## `main` is never rewritten

Each pre-release tag points at a **synthetic commit** that sits on top of the tested SHA and
changes nothing but the version fields in `manifest.json` and `const.py`. The branch history
is untouched.

Install a release candidate from its GitHub pre-release tag, or by enabling pre-releases for
this repository in HACS — not from a moving branch tip.

## Lifecycle

- PR pre-releases are **deleted when the PR closes**, so do not pin to one.
- Older main RCs are pruned automatically as newer ones supersede them.
- Legacy tags shaped `dev-v…` may still exist until they age out; new builds use the semver
  shapes above.

## If HACS offers you a downgrade

Installing a pre-release and then being offered an older _stable_ usually means pre-releases
are not enabled for the repository in HACS, so "latest" only tracks stable tags. See
[HACS shows an update after installing a pre-release](../help/troubleshooting.md#hacs-shows-an-update-after-installing-a-pre-release).

## Library dependency

The integration requires
[`dimplex-controller>=0.13.0`](https://pypi.org/project/dimplex-controller/) — the release
that corrected the `EApplianceModes` flag values, added the dedicated setpoint and setback
endpoints, the capability matrix, schedule helpers, HTTP retry with timeouts, and T1/T2
register separation.

`custom_components/dimplex/manifest.json` carries the floor. Bump it when adopting a new
library release.

## Working on both repositories

1. Clone `dimplex-controller-py` alongside `dimplex-controller-hass`.
2. Install the library editable into the same venv the tests use.
3. Restart Home Assistant, or re-run `pytest`, after library changes.

See [CONTRIBUTING.md](https://github.com/KRoperUK/dimplex-controller-hass/blob/main/CONTRIBUTING.md)
for the full development setup, including building these docs locally.
