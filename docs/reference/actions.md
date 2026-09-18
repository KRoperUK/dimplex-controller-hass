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
| `dimplex.copy_schedule`             | Apply one appliance's schedule to others        |
| `dimplex.set_period_setpoint`       | Change one schedule period's target temperature |
| `dimplex.set_hot_water_temperature` | Set a cylinder's normal or boost target         |
| `dimplex.set_hot_water_hygiene`     | Configure a cylinder's anti-legionella cycle    |

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

Refused for appliances whose capability matrix reports `advance: false` — a cylinder has no
"next comfort period" to bring on, so there is nothing for it to mean.

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

It is **not** the cloud's separate Eco mode, which this integration does not use — see
[the `eco` preset is not Eco mode](../use/modes.md#the-eco-preset-is-not-eco-mode).

## `dimplex.set_open_window_detection`

| Field    | Type    | Default | Notes     |
| -------- | ------- | ------- | --------- |
| `enable` | boolean | `true`  | On or off |

Equivalent to the **Open window detection** switch entity.

## `dimplex.copy_schedule`

Applies the schedule of the appliance you target to other appliances **on the same hub**. The
source's timer mode travels with it, so the targets end up in the same mode rather than only
holding the same periods.

| Field               | Type               | Default | Notes                                                    |
| ------------------- | ------------------ | ------- | -------------------------------------------------------- |
| `target_device_ids` | list of device ids | —       | Required. One or more appliances to receive the schedule |

```yaml
action: dimplex.copy_schedule
target:
  entity_id: climate.hallway_heater
data:
  target_device_ids:
    - 1f2c… # the device id of each heater to update
```

Every target is checked before anything is written: an unresolvable device, or one on a
different hub, aborts the whole action rather than copying to some of them. If a target is the
source appliance it is skipped.

## `dimplex.set_period_setpoint`

Changes **one existing** schedule period's target temperature, leaving the rest of the
programme alone. Periods are matched on day and start time, so the period has to exist already
— this edits a programme, it does not create one. List an appliance's periods with its
**Schedule** sensor, whose `periods` attribute is the day / start / end / temperature of each.

| Field         | Type   | Default | Notes                                                        |
| ------------- | ------ | ------- | ------------------------------------------------------------ |
| `day`         | string | —       | `sunday` … `saturday` (the cloud numbers Sunday as 0)        |
| `start_time`  | time   | —       | Start of the period to edit, as the Schedule sensor lists it |
| `temperature` | number | —       | New target for that period                                   |
| `end_time`    | time   | —       | Optional new end time for the period                         |

```yaml
action: dimplex.set_period_setpoint
target:
  entity_id: climate.hallway_heater
data:
  day: monday
  start_time: "06:00:00"
  temperature: 21
```

A day and start time that match no period raises an error naming the appliance and the time,
rather than silently doing nothing.

## Not exposed as an action

Schedule writes are limited to copying a programme and editing one of its periods. There is no
action to create a period, delete one, or rewrite a whole week — see
[editing the weekly schedule](../use/temperature.md#editing-the-weekly-schedule).

## Hot water

!!! warning "Untested against hardware"

    Every cylinder endpoint below is confirmed from the official app and none of it has
    been run against a real cylinder. If you own one, what you report back is the point —
    see [appliance support](appliances.md#hot-water-cylinders).

Both actions refuse an appliance the capability matrix does not identify as a cylinder
(`hot_water`, or `hygiene` for the hygiene action), naming the appliance and the flag, rather
than sending a cylinder write somewhere it was never meant to go.

### `dimplex.set_hot_water_temperature`

| Field         | Type    | Default | Notes                                     |
| ------------- | ------- | ------- | ----------------------------------------- |
| `mode`        | string  | —       | `normal` or `boost` — which target to set |
| `temperature` | number  | —       | Target temperature (°C)                   |
| `enable`      | boolean | `true`  | Engage the mode as well as writing it     |

```yaml
action: dimplex.set_hot_water_temperature
target:
  entity_id: sensor.hot_water_cylinder_hot_water_available
data:
  mode: normal
  temperature: 50
```

There is no **number** entity for these targets, deliberately: nothing reads them back. The
cloud's only hot-water reading is `AvailableHotWater`, so a number entity could be set and
could never show what it is actually set to — see
[appliance support](appliances.md#hot-water-cylinders).

### `dimplex.set_hot_water_hygiene`

| Field         | Type    | Default | Notes                                          |
| ------------- | ------- | ------- | ---------------------------------------------- |
| `temperature` | number  | —       | Temperature the anti-legionella cycle heats to |
| `frequency`   | string  | —       | `off`, `daily`, `weekly` or `monthly`          |
| `enable`      | boolean | `true`  | Engage hygiene mode as well as writing it      |

The endpoint variant follows the appliance: an ASHW heat pump gets
`SetHygieneSettingsHeatPumpHwc`, a plain cylinder `SetHygieneSettingsHwc`. That is derived from
the capability matrix rather than asked of you, because the two endpoints are not
interchangeable. This is the hot-water call most likely to be refused outright by a hub.

## Next

- [Automations](../use/automations.md) — worked examples using these
- [Entities](entities.md) — the climate presets and diagnostic sensors
- [Options](options.md) — the boost duration used by the preset
