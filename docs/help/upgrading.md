---
description: Version-by-version upgrade notes for the Dimplex Hub Home Assistant integration, including behavioural changes and post-upgrade checklists.
---

# Upgrading

Restart Home Assistant after any HACS update. Notes are newest first; you only need to read
the entries between your current version and the one you are moving to.

## To 4.1.1

A fix for energy statistics, and nothing else. **If you are on 4.1.0, upgrade** — that release
took the **Energy lifetime** sensors off the Energy Dashboard and raises a repair for each one.

- **The lifetime sensors are meters again.** 4.1.0 removed their state class on the belief that
  they were rolling 30-day windows. They are not: the cloud returns the appliance's full
  available history, so the figure rises like a meter and `total_increasing` was right. The
  state class is restored, they are selectable on the Energy Dashboard again, and the repairs
  clear themselves once Home Assistant resumes recording.
- **The value can no longer fall.** A truncated cloud response used to make the sum dip, and
  Home Assistant reads a fall of more than 10% on a rising meter as a meter reset — adding the
  whole total to statistics again. The highest value seen is now what gets reported, and it
  survives a restart.
- **The names go back**: **Energy lifetime** / **Energy T2 lifetime**. The misleading
  `window_days` attribute is gone — it claimed a fixed 30 days the data never matched — but
  `window_start` and `window_end` still show the real span.

If your recorded history was inflated under the older bug it stays inflated; see
[the 4.1.0 notes below](#to-410) for how to delete it.

## To 4.1.0

Behaviour fixes plus new control surface. Everything in the first list is a correction — if
you were working around any of it, stop. The new entities and actions at the end change no
existing configuration.

!!! warning "The declared Home Assistant floor is now 2026.9"

    Earlier releases claimed 2025.1 in `hacs.json`. That was wrong, not conservative: since
    the appliance-to-hub device links moved to the device-registry APIs introduced in
    Home Assistant 2026.8 (`via_device_id` and `async_get_device_by_identifier`), setting up
    the integration on an older release creates **no entities at all**. HACS will now hold
    the update back on Home Assistant below 2026.9 instead of offering an install that
    cannot work.

!!! danger "If your Energy Dashboard history looks inflated"

    The **Energy lifetime** sensors sum every daily reading the cloud holds for an appliance, so
    they rise like a meter — which is what they are. What went wrong is a *dip*: when the cloud
    returned a truncated history the sum fell, and Home Assistant reads a fall of more than 10%
    on a rising meter as a meter reset, adding the entire total to long-term statistics again on
    top of everything already recorded. Your dashboard may show considerably more energy than
    the heaters used. Fixed in 4.1.1.

    The recorded history does not correct itself. To clean it up, go to **Developer tools** →
    **Statistics**, find the entity and delete its statistic — but only if the history looks
    inflated. The **Energy today** sensors were always correct and need nothing.

!!! warning "4.1.0 also removed the state class from those sensors"

    4.1.0 renamed them **Energy last 30 days** and took them off long-term statistics entirely,
    on the belief that they were rolling 30-day windows. They never were. If you are on 4.1.0
    you will see a **repair per appliance** saying an entity *no longer has a state class*, and
    the sensors cannot be used on the Energy Dashboard at all. **4.1.1 restores the state class
    and the lifetime names, and holds the total monotonic so the dip above cannot recur.** See
    [troubleshooting](../help/troubleshooting.md#a-repair-says-a-sensor-no-longer-has-a-state-class).

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
- **A dropped connection can no longer wipe your schedule.** The schedule-rewrite fallback now
  runs only when the appliance genuinely _refuses_ the setpoint endpoint (HTTP 403, 405, 501).
  A timeout or a server error is reported as an error and writes nothing, and when the fallback
  does run it says so in the log. See [setting a target](../use/temperature.md#setting-a-target).
- **Room temperature no longer shows 255 °C.** The cloud's 0xFF "no value" sentinel was being
  passed through by the climate entity, while the room-temperature sensor beside it correctly
  showed nothing.
- **Failed switches and actions explain themselves.** A refused EcoStart toggle or
  `dimplex.set_boost` used to surface a raw traceback; every control now produces the same
  readable message the thermostat has given since 4.0.2, and distinguishes "this appliance
  will not do this" from "the cloud was unreachable".

### New entities and actions

New control surface; no configuration changes, and nothing existing is removed.

- **Controls are gated on the cloud's own capability matrix.** The integration now fetches
  the account's product catalogue, so an appliance the library says cannot take a control no
  longer offers it — and the hot-water / heat-pump flags are derivable for the first time.
  An appliance affected by this gains or loses an entity it could not have used anyway;
  [diagnostics](../help/diagnostics.md) list the resolved flags per appliance, which is the
  place to look if a control is missing.
- **Setback is writable.** A new **Setback target** number entity per capable appliance writes
  the reduced temperature instead of only reporting it. See
  [Entities](../reference/entities.md#numbers).
- **The weekly schedule can be edited from Home Assistant**, through two actions:
  `dimplex.copy_schedule` applies one appliance's programme to others, and
  `dimplex.set_period_setpoint` changes one period's target. See
  [Actions](../reference/actions.md#dimplexcopy_schedule).
- **Hot water cylinders have a control surface for the first time.** Two actions,
  `dimplex.set_hot_water_temperature` and `dimplex.set_hot_water_hygiene`, plus a
  disabled-by-default diagnostic sensor. All of it is untested against real hardware — see
  [appliance support](../reference/appliances.md#hot-water-cylinders).
- **The Boost preset's length now follows the appliance** when the Boost duration option has
  never been set, instead of always using a fixed 60 minutes. If you set that option, nothing
  changes.

### After upgrading

- [ ] Confirm the config entry loaded without requirement errors in the log.
- [ ] If you had automations working around boost engaging the wrong mode, remove the
      workaround.
- [ ] If any appliance is stuck reporting off, toggle it on once — this restores user-timer
      mode on appliances an earlier release parked in the frost/off timer mode.
- [ ] Enable the new mode binary sensors if you want them on a dashboard; they are
      diagnostic and off by default.
- [ ] And if you have a **hot water cylinder**: enable its **Hot water available** diagnostic
      sensor and compare the number it shows against the official app. It is deliberately
      unitless because nothing documents what that field measures, so what it reports is
      genuinely useful — please say so on the issue rather than assuming.
- [ ] If an **Energy lifetime** sensor was a consumption source, remove it, add **Energy
      today** instead, and delete the old statistic if the history looks inflated.

## To 3.0.0

A major release relative to 2.0.0.

### Breaking and behavioural changes

- **Climate entities are created per appliance.** Prefer them for setpoints and for the
  boost / away / eco presets.
- **Energy became two sensors:** **Energy lifetime** and **Energy today** (local calendar day
  from midnight). Prefer **Energy today** for the Energy Dashboard.

  The three-year detour: 4.1.0 briefly renamed the lifetime sensor to **Energy last 30 days**
  and removed its state class, on the belief that it was a rolling window. It never was — the
  cloud returns the appliance's full history — and 4.1.1 put the name and the state class back.
  If you are coming from 3.x, both are as they should be.

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
- [ ] For the Energy Dashboard use **Energy today**. (In 4.1.0 the window sensors can no
      longer be selected as a consumption source at all.)

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
