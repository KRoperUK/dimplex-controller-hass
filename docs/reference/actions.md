---
description: Reference for the dimplex.* Home Assistant actions — set_boost, set_away, set_advance, set_eco_start, set_open_window_detection — with fields and accepted ranges.
---

# Actions

Home Assistant calls these **actions**; the term replaced "service call" in 2024.8, and the
YAML key is `action:`. Use them when the climate presets are too coarse — presets take no
parameters, so they cannot express "boost to 22 °C for 90 minutes".

Every action accepts either `device_id` (the appliance device) or any `entity_id` belonging
to that appliance.

## Summary

| Action                              | Purpose                                         |
| ----------------------------------- | ----------------------------------------------- |
| `dimplex.set_boost`                 | Boost to a target for a fixed number of minutes |
| `dimplex.clear_boost`               | Cancel boost                                    |
| `dimplex.set_away`                  | Hold a setback target until a date you choose   |
| `dimplex.clear_away`                | Cancel away                                     |
| `dimplex.set_advance`               | Bring the next schedule period on early         |
| `dimplex.clear_advance`             | Cancel advance and return to the schedule       |
| `dimplex.set_eco_start`             | Enable or disable EcoStart                      |
| `dimplex.set_open_window_detection` | Enable or disable open-window detection         |

## `dimplex.set_boost`

| Field         | Type   | Default | Range      | Notes               |
| ------------- | ------ | ------- | ---------- | ------------------- |
| `temperature` | number | 25      | 7–30 °C    | Boost target        |
| `duration`    | number | 60      | 1–1440 min | How long to hold it |

```yaml
action: dimplex.set_boost
target:
  entity_id: climate.living_room
data:
  temperature: 22
  duration: 90
```

Boost ends when the timer expires and the appliance returns to its schedule. The default
duration used by the `boost` **preset** is set in [options](options.md), not here.

## `dimplex.clear_boost`

Takes an optional `temperature` (7–30 °C, default 25) because the cloud wants a temperature
on every mode write. It accompanies the clear rather than being applied as a target.

## `dimplex.set_away`

| Field         | Type     | Default | Range       | Notes                               |
| ------------- | -------- | ------- | ----------- | ----------------------------------- |
| `temperature` | number   | 16      | **7–18 °C** | Setback target                      |
| `days`        | number   | —       | 1–365       | Simple day count                    |
| `until`       | datetime | —       | —           | Exact return time; wins over `days` |

```yaml
action: dimplex.set_away
target:
  entity_id: climate.living_room
data:
  temperature: 12
  until: "2026-10-04 18:00:00"
```

Omit both `days` and `until` for an open-ended away.

!!! warning "Away stops at 18 °C, not 30"

    Away is the one mode with a lower ceiling than a normal setpoint. The official app's
    Away picker stops at 18, and the cloud silently reduces anything higher. Rather than
    letting your 21 °C quietly become 18 °C, the integration clamps the value locally and
    logs a warning — so the discrepancy is visible instead of invisible.

Away is a _settable setback_, not frost protection. Frost protection is fixed at 7 °C and
is what [HVAC off](../use/temperature.md#why-off-reports-7-c) engages.

## `dimplex.clear_away`

Takes an optional `temperature` (7–18 °C, default 16) to accompany the clear.

## `dimplex.set_advance`

| Field         | Type   | Default | Range   | Notes                    |
| ------------- | ------ | ------- | ------- | ------------------------ |
| `temperature` | number | —       | 7–30 °C | Optional explicit target |

```yaml
action: dimplex.set_advance
target:
  entity_id: climate.living_room
```

Leave `temperature` empty to use the next schedule period's own target — what the official
app does for Quantum and storage heaters. Advance ends when that period ends; it is not a
fixed-duration override. See [advance vs boost](../use/temperature.md#advance-vs-boost).

## `dimplex.clear_advance`

Cancels an active advance and hands control back to the schedule. No fields beyond the
target.

## `dimplex.set_eco_start`

| Field    | Type    | Default | Notes     |
| -------- | ------- | ------- | --------- |
| `enable` | boolean | `true`  | On or off |

EcoStart is a pre-heat _setting_, not an appliance mode: it learns how long the room takes
to warm and starts early so the target is reached on time. The `eco` climate preset drives
this same setting.

## `dimplex.set_open_window_detection`

| Field    | Type    | Default | Notes     |
| -------- | ------- | ------- | --------- |
| `enable` | boolean | `true`  | On or off |

Equivalent to the **Open window detection** switch entity.

## Not exposed as an action

`SetSetbackTemperature` exists in the underlying library and is confirmed from the official
app, but has never been validated against hardware — so it is deliberately not surfaced
here. Library callers can still reach it.

Schedule writes are not exposed at all; see
[editing the weekly schedule](../use/temperature.md#editing-the-weekly-schedule).

## Next

- [Automations](../use/automations.md) — worked examples using these
- [Entities](entities.md) — the climate presets and diagnostic sensors
- [Options](options.md) — the boost duration used by the preset
