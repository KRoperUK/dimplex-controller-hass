# Dimplex Hub

[![GitHub Release](https://img.shields.io/github/v/release/KRoperUK/dimplex-controller-hass)](https://github.com/KRoperUK/dimplex-controller-hass/releases/latest)
[![CI](https://img.shields.io/github/actions/workflow/status/KRoperUK/dimplex-controller-hass/ci.yml?branch=main&label=CI)](https://github.com/KRoperUK/dimplex-controller-hass/actions/workflows/ci.yml)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/KRoperUK/dimplex-controller-hass)](https://github.com/KRoperUK/dimplex-controller-hass/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![HACS Install](https://img.shields.io/badge/HACS-Install-41BDF5?logo=homeassistant&logoColor=white)](https://my.home-assistant.io/redirect/hacs_repository/?owner=KRoperUK&repository=dimplex-controller-hass&category=integration)
[![Docs](https://img.shields.io/badge/docs-dimplex--hass.kroper.uk-d62945)](https://dimplex-hass.kroper.uk/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen)](https://github.com/pre-commit/pre-commit)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Maintainer](https://img.shields.io/badge/maintainer-%40KRoperUK-blue)](https://github.com/KRoperUK)
[![Buy me a coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow)](https://buymeacoffee.com/kroperukc)
[![Discord](https://img.shields.io/discord/330944238910963714)](https://discord.gg/Qa5fW2R)
[![Community Forum](https://img.shields.io/badge/community-forum-brightgreen)](https://community.home-assistant.io/)

<p align="center">
  <strong>Custom Home Assistant integration for Glen Dimplex Heating &amp; Ventilation (GDHV) electric heating appliances.</strong>
</p>

---

> [!IMPORTANT]
> **Unofficial project.** This integration is not affiliated with, endorsed by, or supported
> by Dimplex, Glen Dimplex Heating & Ventilation, or the Glen Dimplex Group. It is an
> independent community project built by **reverse-engineering** the official Dimplex Control
> Android app and the private cloud API it talks to.
>
> There is no public or documented API. Dimplex can change or withdraw that API at any time
> and without notice, which may break this integration. Use it at your own risk.
>
> Please do not contact Dimplex support about this integration —
> [open an issue here](https://github.com/KRoperUK/dimplex-controller-hass/issues) instead.
> "Dimplex", "Quantum", "QRAD" and related marks belong to their respective owners and are
> used here only to describe compatibility.

Connects Home Assistant to the Dimplex cloud, discovers your hub, zones and appliances, and
exposes them as native entities — a thermostat per heater, the appliance's engaged modes
broken out as sensors, and dual-rate energy history for the Energy Dashboard.

Built on the [`dimplex-controller`](https://github.com/KRoperUK/dimplex-controller-py) Python
client and distributed via [HACS](https://hacs.xyz).

## 📖 Documentation

**Full documentation: [dimplex-hass.kroper.uk](https://dimplex-hass.kroper.uk/)**

|                                                                            |                                                            |
| -------------------------------------------------------------------------- | ---------------------------------------------------------- |
| [Install](https://dimplex-hass.kroper.uk/start/)                           | HACS or manual, and how to check it worked                 |
| [Connect your account](https://dimplex-hass.kroper.uk/start/connect/)      | Email/password or a browser auth code                      |
| [Temperature & schedules](https://dimplex-hass.kroper.uk/use/temperature/) | How control reaches the heater, and what the cloud refuses |
| [Energy monitoring](https://dimplex-hass.kroper.uk/use/energy/)            | T1/T2 registers and the Energy Dashboard                   |
| [Entities](https://dimplex-hass.kroper.uk/reference/entities/)             | Every entity, and which are disabled by default            |
| [Actions](https://dimplex-hass.kroper.uk/reference/actions/)               | `dimplex.*` actions, fields and ranges                     |
| [Options](https://dimplex-hass.kroper.uk/reference/options/)               | Platform toggles and poll intervals                        |
| [Troubleshooting](https://dimplex-hass.kroper.uk/help/troubleshooting/)    | Setup failures, unavailable entities, HACS oddities        |
| [Upgrading](https://dimplex-hass.kroper.uk/help/upgrading/)                | Version-by-version migration notes                         |

## ✨ Features

- **Climate control** — a thermostat per appliance: target temperature, heat/off, and boost /
  away / eco presets. Setting a target uses the cloud's dedicated setpoint endpoint, so your
  timer schedule is left alone.
- **Mode visibility** — the appliance holds a bitfield of modes and several can be engaged at
  once. Boost, away, frost protection and advance are each exposed as a diagnostic sensor, so
  a mismatch cannot hide behind a single preset.
- **Dual-rate energy** — daily kWh history per register, in the Energy Dashboard. T1 and T2
  are never summed.
- **EcoStart and open-window detection** — both toggleable from Home Assistant.
- **Stays connected** — tokens refresh automatically, polling backs off when heaters are
  idle, and re-authentication uses Home Assistant's built-in reauth flow.

## 🚀 Install

### HACS (recommended)

[![Add to HACS](https://img.shields.io/badge/HACS-Add%20repository-41BDF5?logo=homeassistant&logoColor=white)](https://my.home-assistant.io/redirect/hacs_repository/?owner=KRoperUK&repository=dimplex-controller-hass&category=integration)

1. Open **HACS**, search for **Dimplex Hub**, click **Download**.
2. Restart Home Assistant.
3. **Settings** → **Devices & services** → **+ Add integration** → **Dimplex Hub**.

### Manual

Copy `custom_components/dimplex` into your Home Assistant `custom_components/` directory,
restart, then add the integration as above.

Requires Home Assistant **2026.9** or later. Full instructions, including the two
authentication methods, are in
[Getting started](https://dimplex-hass.kroper.uk/start/).

## ⚠️ Appliance support

Panel heaters and QRAD are exercised regularly. Quantum storage heaters behave differently —
a target does nothing until there is stored charge — and hot water cylinder support exists in
the underlying library but has never been run against hardware.

Some Quantum heaters also reject remote setpoint and timer-mode writes with HTTP 403; the
integration falls back to a schedule rewrite where it can, and reports a readable error
where it cannot.

## 🤝 Contributing

Contributions are welcome — please read the [contribution guidelines](CONTRIBUTING.md) first.

- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
  `chore:` …); this drives the automated changelog and release.
- Run `ruff check`, `ruff format --check` and `pytest` before pushing, or install the hooks
  with `pre-commit install`.
- Documentation changes: `zensical build` reports broken links and missing anchors.
- CI publishes pre-releases as semver tags (`vX.Y.Z-rc.N` on main, `vX.Y.Z-pr.P.R` for PRs).
  See [dev & pre-release builds](https://dimplex-hass.kroper.uk/internals/dev-releases/).

## 🐛 Reporting a problem

[Open an issue](https://github.com/KRoperUK/dimplex-controller-hass/issues/new/choose) with
your Home Assistant version, the integration version, the relevant log lines (redacted), and
steps to reproduce. Attaching a **diagnostics download** is the fastest route to an answer —
it decodes the appliance's engaged modes by name.

## 🙏 Credits

Generated from [@oncleben31](https://github.com/oncleben31)'s
[Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component)
template, with code templates from [@Ludeeus](https://github.com/ludeeus)'s
[integration_blueprint](https://github.com/custom-components/integration_blueprint).
