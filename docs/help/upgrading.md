---
description: Version-by-version upgrade notes for the Dimplex Hub Home Assistant integration, including behavioural changes and post-upgrade checklists.
---

# Upgrading

Restart Home Assistant after any HACS update. Notes are newest first; you only need to read
the entries between your current version and the one you are moving to.

## To 4.1.0

Behaviour fixes, no configuration changes. Everything here is a correction — if you were
working around any of it, stop.

!!! warning "The declared Home Assistant floor is now 2026.9"

    Earlier releases claimed 2025.1 in `hacs.json`. That was wrong, not conservative: since
    the appliance-to-hub device links moved to the device-registry APIs introduced in
    Home Assistant 2026.8 (`via_device_id` and `async_get_device_by_identifier`), setting up
    the integration on an older release creates **no entities at all**. HACS will now hold
    the update back on Home Assistant below 2026.9 instead of offering an install that
    cannot work.

!!! danger "Check your Energy Dashboard if you used an \"Energy lifetime\" sensor"

    Those sensors were a rolling 30-day window declared `total_increasing`, so every time the
    window dipped by more than 10% — routine in spring and autumn — Home Assistant read it as
    a meter reset and added the whole 30-day total to long-term statistics again. Your
    dashboard may show considerably more energy than the heaters used.

    They are renamed **Energy last 30 days** and now carry no state class, so Home Assistant
    will not offer them as a consumption source at all. Existing entities keep their old
    entity ID; only the display name changes. To clean up inflated history, go to
    **Developer tools** → **Statistics**, find the entity and delete its statistic. The
    **Energy today** sensors were always correct and need nothing.

- **Setting a target no longer rewrites your schedule.** Writes go through the cloud's
  dedicated setpoint endpoint, with the old schedule rewrite kept only as a fallback for
  appliances that reject it. See
  [setting a target](../use/temperature.md#setting-a-target).
- **HVAC off engages frost protection** at 7 °C, which is how the official app turns a
  heater off. The entity will report a 7 °C target when off — this is correct. See
  [why "off" reports 7 °C](../use/temperature.md#why-off-reports-7-c).
- **Boost and away actually engage the right modes.** Earlier releases assumed boost was
  mode bit 16 and away bit 32; those are in fact Advance and FrostProtect. Asking for boost
  engaged advance instead. The corrected values are listed in
  [Modes & presets](../use/modes.md#what-the-appliance-reports).
- **Presets are mutually exclusive.** Selecting one now clears the others, so switching
  straight from `away` to `eco` works. Previously each preset only added its own state, and
  because the entity resolves boost before away before EcoStart, the change appeared to do
  nothing.
- **Away is capped at 18 °C**, the range the cloud actually accepts. Values above 18 are
  clamped with a log warning instead of being silently reduced.
- **Away accepts a duration** — `days` or `until`.
- **Advance is controllable** via `dimplex.set_advance` / `dimplex.clear_advance`.
- **Four new diagnostic sensors** expose the engaged modes individually: boost, away, frost
  protection, advance.

### After upgrading

- [ ] Confirm the config entry loaded without requirement errors in the log.
- [ ] If you had automations working around boost engaging the wrong mode, remove the
      workaround.
- [ ] If any appliance is stuck reporting off, toggle it on once — this restores user-timer
      mode on appliances an earlier release parked in the frost/off timer mode.
- [ ] Enable the new mode binary sensors if you want them on a dashboard; they are
      diagnostic and off by default.
- [ ] If an **Energy lifetime** sensor was a consumption source, remove it, add **Energy
      today** instead, and delete the old statistic if the history looks inflated.

## To 3.0.0

A major release relative to 2.0.0.

### Breaking and behavioural changes

- **Climate entities are created per appliance.** Prefer them for setpoints and for the
  boost / away / eco presets.
- **Energy is no longer a single mislabelled "30-day" total.** It is now two sensors:
  **Energy lifetime** (cumulative cloud daily history) and **Energy today** (local calendar
  day from midnight). Prefer **Energy today** for the Energy Dashboard unless you
  deliberately want the full history imported at once.
- **Entity unique IDs and names may change.** EcoStart gained a stable `_ecostart` suffix,
  and open-window detection became a switch as well as a binary sensor. Expect some renamed
  entities and a one-off orphan cleanup.
- **Polling is split** into a short status interval and a longer energy interval, both
  configurable in [options](../reference/options.md).
- **Diagnostic entities** — error and warning codes, last telemetry, rated power, charge
  capacity, Energy T2 — exist but are **disabled by default**. Enable them in the entity
  registry if you need them.

### After upgrading

- [ ] Confirm the config entry is loaded, with no import or requirement errors in the log.
- [ ] Review the new `climate.*` entities and the energy sensors.
- [ ] Re-point automations that used old entity IDs.
- [ ] For the Energy Dashboard use **Energy today** rather than dumping multi-year
      **lifetime** history in, unless that is what you want.

## Requirements

Any recent version needs:

- Home Assistant **2026.9** or later.
- [`dimplex-controller>=0.13.0`](https://pypi.org/project/dimplex-controller/), installed
  automatically from the integration requirements.

## If an upgrade goes wrong

- Entities missing → check the platform is enabled in [options](../reference/options.md),
  then restart.
- Entities `unavailable` → usually the cloud returning an empty overview, not the upgrade.
  See [entities are unavailable](troubleshooting.md#entities-are-unavailable).
- HACS offering an older version → see
  [HACS shows an update after installing a pre-release](troubleshooting.md#hacs-shows-an-update-after-installing-a-pre-release).

Full detail for every release is in the
[changelog](https://github.com/KRoperUK/dimplex-controller-hass/blob/main/CHANGELOG.md).
