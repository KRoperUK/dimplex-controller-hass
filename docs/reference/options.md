---
description: Dimplex Hub configuration options — platform toggles, status and energy poll intervals, boost duration, stored tokens and uninstalling.
---

# Options

Everything is configured through the Home Assistant UI. There is no YAML configuration for
this integration.

**Settings** → **Devices & services** → **Dimplex Hub** → **Configure**

## Options flow

| Option               | Default | Range      | Meaning                                                |
| -------------------- | ------- | ---------- | ------------------------------------------------------ |
| `climate`            | on      | on/off     | Climate entities — target temperature and presets      |
| `sensor`             | on      | on/off     | Room temperature, energy and diagnostic sensors        |
| `binary_sensor`      | on      | on/off     | Comfort, open window, setback, connected, mode sensors |
| `switch`             | on      | on/off     | EcoStart and open-window-detection toggles             |
| Status poll interval | 30 s    | 15–3600 s  | Temperatures and modes                                 |
| Energy poll interval | 1800 s  | 60–86400 s | The daily kWh energy report                            |
| Boost duration       | 60 min  | 1–1440 min | Default for the `boost` **preset**                     |

Changing any option reloads the integration. Disabling a platform removes its entities
without deleting the config entry, so re-enabling brings them back with the same IDs.

The boost duration here applies to the climate `boost` preset only.
[`dimplex.set_boost`](actions.md#dimplexset_boost) takes its own `duration`.

## Polling

Three separate cadences, because the underlying calls cost very different amounts:

| What                         | Default | Why                                                  |
| ---------------------------- | ------- | ---------------------------------------------------- |
| Status — temperatures, modes | 30 s    | Light call, and what you watch on a dashboard        |
| Schedules                    | 15 min  | One call per appliance, and programmes change rarely |
| Energy history               | 30 min  | Heavy call returning up to 30 days of points         |

The schedule interval is not configurable.

Energy polling **backs off automatically** when history stays empty: after three
consecutive empty-but-successful polls the interval stretches to as much as 3 hours, then
returns to the configured value once points reappear or heating activity is detected. This
is normal in summer and keeps idle installations from hammering the cloud.

## What is stored

The config entry's `data` holds:

| Key             | Purpose                                                 |
| --------------- | ------------------------------------------------------- |
| `refresh_token` | Long-lived token used to mint new access tokens         |
| `access_token`  | Short-lived token for API requests                      |
| `expires_at`    | Unix timestamp at which the access token expires        |
| `username`      | Your Dimplex account email — email/password method only |

Tokens live in Home Assistant's config storage and are not written to plain-text files
outside it. Your password is not retained: it is exchanged for tokens during setup and
discarded.

Diagnostics downloads redact these before you can share them.

## Behind a proxy

The integration uses Home Assistant's shared `aiohttp` session, so whatever proxy
configuration Home Assistant honours applies here too. It needs to reach `api.gdhv.io`.

## Entity IDs and unique IDs

Unique IDs derive from the config entry ID, the cloud appliance or hub ID, and a stable
suffix (`_climate`, `_energy`, `_ecostart`, …). They survive renaming entities in the UI and
do not collide across multiple config entries.

## Uninstalling

1. **Settings** → **Devices & services**.
2. Find **Dimplex Hub** and click the overflow menu → **Delete**.
3. Confirm.

This removes the config entry, its devices and its entities. Dashboards, automations and
scripts that referenced those entities are left in place and will need cleaning up by hand.

## Next

- [Entities](entities.md) — what each entity does
- [Actions](actions.md) — the `dimplex.*` actions
- [Multi-account](../internals/multi-account.md) — running more than one Dimplex account
