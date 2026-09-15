---
description: Home Assistant integration for Glen Dimplex electric heating — climate control, mode visibility and dual-rate energy monitoring for QRAD, Quantum and other GDHV appliances.
hide:
  - navigation
---

# Dimplex Hub for Home Assistant

Control and monitor Glen Dimplex electric heating from Home Assistant. The integration
talks to the Dimplex cloud, discovers your hub, zones and appliances, and exposes them as
native entities — a thermostat per heater, dual-rate energy for the Energy Dashboard, and
the appliance's engaged modes broken out so you can see what the heater is actually doing.

[Install it](start/index.md){ .md-button .md-button--primary }
[Browse the entities](reference/entities.md){ .md-button }

## Start here

<div class="grid cards" markdown>

- :material-download: **[Install](start/index.md)**

  ***

  HACS or manual, then restart and add the integration.

- :material-key: **[Connect your account](start/connect.md)**

  ***

  Email and password, or a browser auth code if that fails.

- :material-thermostat: **[Temperature & schedules](use/temperature.md)**

  ***

  How a setpoint is written, why "off" reports 7 °C, and what the cloud
  will not let you change.

- :material-lightning-bolt: **[Energy monitoring](use/energy.md)**

  ***

  Daily kWh history with T1 and T2 tariffs kept apart.

</div>

## What you get

<div class="grid cards" markdown>

- :material-home-thermometer: **Climate control**

  ***

  A thermostat per appliance: target temperature, heat/off, and boost / away /
  eco presets. Setting a target uses the cloud's dedicated setpoint endpoint,
  so your timer schedule is left alone.

- :material-eye: **Mode visibility**

  ***

  The appliance holds a bitfield of modes and several can be engaged at once.
  Four diagnostic sensors surface boost, away, frost protection and advance
  individually, so a mismatch cannot hide behind a single preset.

- :material-chart-line: **Dual-rate energy**

  ***

  Daily kWh history per register. T1 and T2 are never summed, so off-peak and
  peak stay separate in the Energy Dashboard.

- :material-refresh-auto: **Stays connected**

  ***

  Tokens refresh automatically, polling backs off when heaters are idle, and
  re-authentication uses Home Assistant's built-in reauth flow.

</div>

## Reference

<div class="grid cards" markdown>

- :material-format-list-bulleted: **[Entities](reference/entities.md)**

  ***

  Every entity, what it reads, and which are disabled by default.

- :material-play-circle: **[Actions](reference/actions.md)**

  ***

  The `dimplex.*` actions, their fields and accepted ranges.

- :material-tune: **[Options](reference/options.md)**

  ***

  Platform toggles, poll intervals and what is stored in the config entry.

- :material-lifebuoy: **[Troubleshooting](help/troubleshooting.md)**

  ***

  Setup failures, unavailable entities, and symptoms with known causes.

</div>

!!! warning "Not every appliance family is equally tested"

    Panel heaters and QRAD are exercised regularly. Quantum storage heaters behave
    differently — a target does nothing until there is stored charge — and hot water
    cylinder support exists in the underlying library but has never been run against
    hardware.

## Links

- [GitHub repository](https://github.com/KRoperUK/dimplex-controller-hass)
- [Report an issue](https://github.com/KRoperUK/dimplex-controller-hass/issues/new/choose)
- [Install via HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=KRoperUK&repository=dimplex-controller-hass&category=integration)
- [`dimplex-controller` on PyPI](https://pypi.org/project/dimplex-controller/) — the Python client underneath
