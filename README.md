# Dimplex Hub

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![pre-commit][pre-commit-shield]][pre-commit]
[![Ruff][ruff-shield]][ruff]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.][hacs-install-badge]][hacs-install]

Custom Home Assistant integration for Dimplex electric heating appliances.

## Overview

This integration connects Home Assistant to the Dimplex cloud API and exposes core heater telemetry and controls through config entries.

## Supported entities

| Platform        | Description                                     |
| --------------- | ----------------------------------------------- |
| `sensor`        | Room temperature and energy used per appliance. |
| `binary_sensor` | Comfort status per appliance.                   |
| `switch`        | EcoStart toggle per appliance.                  |

### Energy monitoring

Each appliance that the Dimplex Hub reports energy for exposes a
`SensorDeviceClass.ENERGY` sensor with kWh as the unit. The value is the
total energy used in a rolling 30-day window; `last_reset` is set to the
start of that window so the Home Assistant Energy Dashboard can plot it
correctly.

Energy data is hardware-dependent — only metered appliances (e.g. QRAD
radiators) report telemetry. When the hub returns no data, the sensor is
**unavailable** rather than `0`, so the Energy Dashboard never sees
fabricated zero readings. During the warmer months, when heaters are not
running, you should expect to see the energy sensor as `unavailable` — this
is correct behaviour, not a bug.

## Installation (manual)

1. Open your Home Assistant configuration directory (the folder containing `configuration.yaml`).
2. Create `custom_components` if it does not exist.
3. Copy `custom_components/dimplex` from this repository into your Home Assistant config.
4. Restart Home Assistant.
5. In Home Assistant, go to **Configuration** -> **Integrations**.
6. Click **+** and search for `Dimplex Hub`.

## Configuration

Configuration is done in the UI through the integration config flow.

### Getting the OAuth callback URL or code

During setup, the config flow shows a login URL.

1. Open that login URL in your browser.
2. **Before** entering your credentials, open Developer Tools (`F12`) and go to the **Network** tab.
3. Enable **Preserve log** (or equivalent "keep log" option).
4. Submit your login details.
5. The final mobile-app redirect will fail/cancel, which is expected.
6. In Network, find the last redirect/cancelled request (or the request URL) that includes `?code=...`.
7. Copy either:
   - the full callback URL (starts with `msal...://auth/?code=...`), or
   - just the `code` value.
8. Paste that into the integration form field **Redirect URL or code**.

If the code expires, repeat the steps and capture a fresh one.

## Known limitations

- Target temperature controls are not exposed yet.
- Schedules/timer editing is not exposed yet.

## Troubleshooting

- Check Home Assistant logs for authentication or connectivity errors.
- Re-authenticate in the config flow if your token has expired.
- If setup fails, create an issue with logs and reproduction steps.

## Contributions are welcome!

If you want to contribute, please read the [Contribution guidelines](CONTRIBUTING.md).

## Credits

This project was generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Code template was mainly taken from [@Ludeeus](https://github.com/ludeeus)'s [integration_blueprint][integration_blueprint] template

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[ruff]: https://github.com/astral-sh/ruff
[ruff-shield]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge
[buymecoffee]: https://www.buymeacoffee.com/kroperuk
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/kroperuk/dimplex-controller-hass.svg?style=for-the-badge
[commits]: https://github.com/kroperuk/dimplex-controller-hass/commits/main
[hacs]: https://hacs.xyz
[hacs-install]: https://my.home-assistant.io/redirect/hacs_repository/?owner=kroperuk&repository=dimplex-controller-hass&category=integration
[hacs-install-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/kroperuk/dimplex-controller-hass.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40kroperuk-blue.svg?style=for-the-badge
[pre-commit]: https://github.com/pre-commit/pre-commit
[pre-commit-shield]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/kroperuk/dimplex-controller-hass.svg?style=for-the-badge
[releases]: https://github.com/kroperuk/dimplex-controller-hass/releases
[user_profile]: https://github.com/kroperuk
