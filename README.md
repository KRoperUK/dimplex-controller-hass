# Dimplex Hub

[![GitHub Release](https://img.shields.io/github/release/kroperuk/dimplex-controller-hass.svg)](https://github.com/kroperuk/dimplex-controller-hass/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/kroperuk/dimplex-controller-hass.svg?style=for-the-badge)](https://github.com/kroperuk/dimplex-controller-hass/commits/main)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=for-the-badge)](https://github.com/pre-commit/pre-commit)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge)](https://github.com/astral-sh/ruff)
[![Maintainer](https://img.shields.io/badge/maintainer-%40kroperuk-blue.svg?style=for-the-badge)](https://github.com/kroperuk)
[![Buy me a coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge)](https://www.buymeacoffee.com/kroperuk)
[![Discord](https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge)](https://discord.gg/Qa5fW2R)
[![Community Forum](https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge)](https://community.home-assistant.io/)
[![HACS Install](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kroperuk&repository=dimplex-controller-hass&category=integration)

<p align="center">
  <strong>Custom Home Assistant integration for Glen Dimplex Heating &amp; Ventilation (GDHV) electric heating appliances.</strong>
</p>

---

## What does this do?

`dimplex-controller-hass` connects Home Assistant to the Dimplex cloud API. It discovers your Dimplex Hub, Zones and Appliances, and exposes them as native Home Assistant entities so you can monitor temperatures, track energy usage and control EcoStart — all from the Home Assistant dashboard.

It is distributed via [HACS](https://hacs.xyz) and built on top of the [`dimplex-controller-py`](https://github.com/KRoperUK/dimplex-controller-py) Python client.

## Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Energy monitoring](#energy-monitoring)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Credits](#credits)

## Features

- **Temperature monitoring** — View current room temperature and active target temperature setpoints for each Zone.
- **Comfort status** — Monitor whether your heating is in Comfort mode.
- **EcoStart control** — Toggle the EcoStart energy-saving feature from Home Assistant.
- **Energy telemetry** — Monitor and log energy consumption for metered appliances directly in the Home Assistant Energy Dashboard.
- **Automatic re-authentication** — The integration refreshes tokens automatically and prompts you to re-authenticate when necessary.

## Installation

### Via HACS (recommended)

1. Open **HACS** in Home Assistant.
2. Search for **Dimplex Hub**.
3. Click **Download**.
4. Restart Home Assistant.
5. Go to **Settings** > **Devices & Services** > **Add Integration** and search for **Dimplex Hub**.

### Manual installation

1. Open your Home Assistant configuration directory (the folder containing `configuration.yaml`).
2. Create `custom_components` if it does not already exist.
3. Copy the `custom_components/dimplex` folder from this repository into your Home Assistant `custom_components` directory.
4. Restart Home Assistant.
5. Go to **Settings** > **Devices & Services**.
6. Click **+ Add Integration** and search for **Dimplex Hub**.

## Configuration

Configuration is handled entirely through the Home Assistant UI. No YAML editing is required.

### Step 1: Choose an authentication method

When you add the integration, you are asked to choose one of two login methods:

| Method                             | When to use                                                                                   |
| ---------------------------------- | --------------------------------------------------------------------------------------------- |
| **Email / password (recommended)** | Use your Dimplex cloud account email and password.                                            |
| **Manual auth code**               | Use this if password login fails or if you prefer not to enter credentials in Home Assistant. |

### Step 2: Email / password

1. Enter your Dimplex account email and password.
2. Click **Submit**.

The integration signs in to the Dimplex cloud in the background and stores the resulting tokens securely.

### Step 3: Manual auth code

If you choose the manual auth code method:

1. The integration shows a login URL. Open it in a new browser tab.
2. **Before** entering your credentials, open Developer Tools (`F12`) and go to the **Network** tab.
3. Enable **Preserve log** (or your browser's equivalent).
4. Log in with your Dimplex credentials.
5. The final redirect will fail or show a "cannot open page" error — this is expected.
6. In the Network tab, find the last request that includes `?code=...` in its URL.
7. Copy either the full redirect URL or just the `code` value.
8. Paste it into the integration's **Redirect URL or code** field.
9. Click **Submit**.

> **Tip:** If the code expires, repeat the steps and capture a fresh one. Auth codes are short-lived.

### Options flow

After installation, you can adjust which platforms are enabled:

1. Go to **Settings** > **Devices & Services**.
2. Find **Dimplex Hub** and click **Configure**.
3. Toggle `sensor`, `binary_sensor` and `switch` platforms on or off.

## Entities

| Platform        | Description                                 | Example entity                     |
| --------------- | ------------------------------------------- | ---------------------------------- |
| `sensor`        | Room temperature per Zone.                  | `sensor.living_room_temperature`   |
| `sensor`        | Cumulative energy used per Appliance (kWh). | `sensor.k radiator_energy`         |
| `binary_sensor` | Comfort status per Appliance.               | `binary_sensor.k_radiator_comfort` |
| `switch`        | EcoStart toggle per Appliance.              | `switch.k_radiator_ecostart`       |

> Entity IDs are generated from your appliance names. You can rename them in Home Assistant as usual.

## Energy monitoring

Each metered Appliance exposes two energy sensors (primary register):

| Sensor              | Meaning                                                                              |
| ------------------- | ------------------------------------------------------------------------------------ |
| **Energy today**    | kWh for the current local calendar day (from midnight).                              |
| **Energy lifetime** | Cumulative sum of all daily kWh points returned by the cloud (from first telemetry). |

A secondary register (**Energy T2**) is available as diagnostic entities when the appliance reports `T2`.

**Important behaviour:**

- Energy data is hardware-dependent — metered appliances (QRAD, Quantum storage heaters, etc.) report daily kWh telemetry, not live watts.
- When the hub returns no points for a register, the sensor is **unavailable** rather than `0`.
- Status polls every ~30s; energy polls on a slower cadence (default 30 minutes) to avoid hammering the cloud.

## Climate control

Each appliance is exposed as a `climate` entity with:

- current room temperature and target temperature
- presets: `comfort`, `boost`, `away`, `eco` (EcoStart)
- `climate.set_temperature` / `climate.set_preset_mode`

Schedule editing beyond setpoint rewrites is still limited by the cloud API.

## Upgrading to 3.0.0

This is a **major** release relative to 2.0.0. After updating via HACS, **restart Home Assistant**.

### Requirements

- Home Assistant (current supported version for this integration)
- [`dimplex-controller>=0.10.0`](https://pypi.org/project/dimplex-controller/) (installed automatically from the integration requirements)

### Breaking / behavioural changes

- **Climate entities** are created per appliance. Prefer climate for setpoints and boost/away/eco presets.
- **Energy** is no longer a single mislabelled “30-day” total:
  - **Energy lifetime** — cumulative cloud daily history
  - **Energy today** — local calendar day from midnight
    Prefer **Energy today** for the Energy Dashboard when you want daily usage without a large historical pop-in on first add.
- **Entity unique IDs / names** may change (for example EcoStart now has a stable `_ecostart` suffix; open-window detection is a switch as well as a binary sensor). You may see renamed entities or need to clean orphans once.
- **Polling** is split: status on a short interval, energy on a longer interval (configurable in options).
- **Diagnostics** (error/warning/last telem, rated power, charge capacity, energy T2 today) exist but may be **disabled by default** — enable in the entity registry if you need them.

### After upgrade checklist

1. Confirm Dimplex Hub config entry is **loaded** (no import / requirement errors in logs).
2. Review new `climate.*` entities and energy sensors.
3. Re-point automations that used old entity IDs.
4. For Energy Dashboard, use **Energy today** (or statistics) rather than dumping multi-year **lifetime** into the dashboard unless you intend that.

## Known limitations

- Full weekly schedule UI is not exposed yet (setpoint writes update timer periods).
- Away mode bitmasks are best-effort across appliance families.

## Troubleshooting

### The integration fails to set up

**Symptom:** Setup fails with an authentication or connectivity error.

**Steps to resolve:**

1. Check **Settings** > **System** > **Logs** for detailed error messages.
2. If you see `InvalidAuth`, re-authenticate via the config flow.
3. If you see `CannotConnect`, verify your internet connection and that `api.gdhv.io` is reachable from your Home Assistant instance.

### Tokens keep expiring

**Symptom:** You are repeatedly asked to re-authenticate.

**Steps to resolve:**

1. Use the **Email / password** method — it obtains a fresh refresh token automatically.
2. If using the manual auth code method, capture a fresh code each time.
3. Ensure Home Assistant has reliable internet access; intermittent connectivity can cause token refresh failures.

### Entities are missing

**Symptom:** Some entities do not appear after setup.

**Steps to resolve:**

1. Check the options flow and make sure the relevant platform is toggled on.
2. Restart Home Assistant.
3. Check the logs for errors during platform setup.

### Energy sensor shows `unavailable` in summer

This is expected. See the [Energy monitoring](#energy-monitoring) section above.

### Still stuck?

If you cannot resolve your issue, please [open a GitHub issue](https://github.com/kroperuk/dimplex-controller-hass/issues) with:

1. Your Home Assistant version.
2. The integration version.
3. The relevant log entries (redact any personal information).
4. Steps to reproduce the problem.

## Contributing

Contributions are welcome! Please read the [contribution guidelines](CONTRIBUTING.md) before opening a pull request.

Key points:

- Use **Conventional Commits** (`feat:`, `fix:`, `chore:`, etc.) — this drives the automated changelog and release process.
- Run `ruff check`, `ruff format --check` and `pytest` locally before pushing.
- Pre-commit hooks are available — run `pre-commit install` once.
- CI publishes pre-releases as semver tags (`vX.Y.Z-rc.N` on main, `vX.Y.Z-pr.P.R` for PRs) with matching `manifest` versions; stable remains `vX.Y.Z`. See [docs/advanced.md](docs/advanced.md#pre-release-dev-builds).

## Credits

This project was generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Code template was mainly taken from [@Ludeeus](https://github.com/ludeeus)'s [integration_blueprint](https://github.com/custom-components/integration_blueprint) template.
