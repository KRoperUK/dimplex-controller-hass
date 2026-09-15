---
description: Install the Dimplex Hub integration for Home Assistant via HACS or manually, then verify it loaded.
---

# Install

## Before you start

- Home Assistant **2025.1** or later — the floor this integration declares in `hacs.json`.
- A Dimplex cloud account with at least one registered appliance, working in the official
  Dimplex Control app.
- Internet access from your Home Assistant instance. This is a cloud-polling integration;
  there is no local API.

!!! tip "Check the official app first"

    If your heater does not appear, or shows no temperature, in the Dimplex Control app,
    it will not appear here either. The integration reads the same cloud.

## Install

=== "HACS (recommended)"

    1. Open **HACS** in Home Assistant.
    2. Search for **Dimplex Hub**.
    3. Click **Download**.
    4. Restart Home Assistant.

    Or use the one-click link:
    [:material-home-assistant: Add to HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=KRoperUK&repository=dimplex-controller-hass&category=integration)

    Stay on the **stable** channel for everyday use. Pre-releases (`vX.Y.Z-rc.N` and
    `vX.Y.Z-pr.*`) exist for testers — only enable them in HACS if you intend to run
    unreleased code. See [pre-release builds](../internals/dev-releases.md).

=== "Manual"

    1. Open your Home Assistant configuration directory — the folder containing
       `configuration.yaml`.
    2. Create `custom_components/` if it does not already exist.
    3. Copy `custom_components/dimplex` from
       [the repository](https://github.com/KRoperUK/dimplex-controller-hass) into it.
    4. Restart Home Assistant.

    The Python client [`dimplex-controller`](https://pypi.org/project/dimplex-controller/)
    is declared in `manifest.json` and installed automatically on first load.

## Add the integration

1. Go to **Settings** → **Devices & services**.
2. Click **+ Add integration**.
3. Search for **Dimplex Hub** and select it.
4. Follow the prompts — see [connect your account](connect.md) for the two login methods.

## Check it worked

After setup finishes:

- [ ] **Settings** → **Devices & services** shows a **Dimplex Hub** entry, loaded without
      an error banner.
- [ ] Clicking it lists one device per appliance, plus a hub device and a device per zone.
- [ ] Each appliance device has a `climate` entity reporting a room temperature.
- [ ] **Settings** → **Devices & services** → **Entities**, filtered on `dimplex`, lists
      around 20 entities per appliance — many are diagnostic and disabled by default.

If entities appear but read `unavailable`, that is usually the cloud returning an empty
overview because the heaters have not telemetered recently rather than a setup problem —
see [entities are unavailable](../help/troubleshooting.md#entities-are-unavailable).

## Next

- [Connect your account](connect.md) — the two authentication methods in detail.
- [Options](../reference/options.md) — platform toggles and poll intervals.
- [Temperature & schedules](../use/temperature.md) — how control actually reaches the heater.
- [Entities](../reference/entities.md) — what every entity means.
