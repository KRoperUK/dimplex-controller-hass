# Dimplex Hub Integration

Welcome to the documentation for the Dimplex Hub custom integration for Home Assistant.

This integration connects Home Assistant to the Dimplex cloud API and exposes core heater telemetry and controls through config entries.

## What you can do

- **Monitor temperatures** — See current room temperature and target setpoints for every Zone.
- **Track energy** — Log energy consumption for metered appliances in the Home Assistant Energy Dashboard (T1/T2 tariffs kept separate).
- **Control heating** — Adjust target temperature and presets via climate entities, toggle EcoStart and open-window detection, and trigger Boost/Away from the dashboard, automations, or the `dimplex.*` [services](advanced.md#domain-services).
- **Stay in sync** — Tokens refresh automatically; re-authentication uses Home Assistant's built-in reauth flow.

## Documentation pages

- [Getting started](getting-started.md) — installation and initial setup.
- [Configuration](configuration.md) — detailed setup steps and options.
- [Entities](entities.md) — entity reference and capabilities.
- [Advanced usage](advanced.md) — energy dashboard, automations and tips.
- [Troubleshooting](troubleshooting.md) — common issues and how to resolve them.

## Quick links

- [GitHub repository](https://github.com/kroperuk/dimplex-controller-hass)
- [Report an issue](https://github.com/kroperuk/dimplex-controller-hass/issues)
- [HACS repository](https://github.com/kroperuk/dimplex-controller-hass)
