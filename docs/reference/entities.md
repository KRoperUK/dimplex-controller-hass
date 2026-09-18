---
description: Every entity the Dimplex Hub integration creates — climate, sensors, binary sensors, switches and the diagnostic mode sensors — and which are disabled by default.
---

# Entities

This page lists the entity types exposed by the Dimplex Hub integration.

Entity names use Home Assistant’s `has_entity_name` pattern: the **device** is the appliance (or hub), and each entity has a short name such as “Room temperature” or “EcoStart”.

## Climate

One climate entity per appliance.

| Name            | Entity ID pattern     | Description                                                                                                                                                                                                                    |
| --------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| _(device name)_ | `climate.<appliance>` | Thermostat: current room temperature, target setpoint, HVAC heat/off, presets. HVAC **off** is frost protection — the appliance has no off mode, only the 7 °C anti-freeze floor, which is exactly what the official app does. |

### Presets

A preset is a single, mutually exclusive state: selecting one engages what that preset owns
and clears the others, so switching straight from `away` to `eco` works as you would expect.
Why a preset cannot always show what the appliance is doing:
[Modes & presets](../use/modes.md#why-preset_mode-can-disagree-with-reality).

| Preset    | Behaviour                                                                                                          |
| --------- | ------------------------------------------------------------------------------------------------------------------ |
| `comfort` | Clears boost, away and EcoStart — follow the schedule.                                                             |
| `boost`   | Enables boost (default ~60 minutes, boost temperature when known).                                                 |
| `away`    | Enables away mode at the appliance away temperature when known, clamped to the 7-18 °C the cloud accepts for Away. |
| `eco`     | Enables EcoStart. This is the EcoStart pre-heat setting, **not** the cloud's separate Eco mode, which is unused.   |

### Actions

- `climate.set_temperature` — writes the target through the cloud's dedicated setpoint endpoint, so your schedule is left intact. Appliances that reject it fall back to a schedule rewrite. See [setting a target](../use/temperature.md#setting-a-target).
- `climate.set_preset_mode` — boost / away / eco / comfort.
- `climate.turn_on` / `climate.turn_off` — off engages frost protection and clears boost/away; on clears it again. See [why "off" reports 7 °C](../use/temperature.md#why-off-reports-7-c).
- `dimplex.set_advance` / `dimplex.clear_advance` — skip forward to the next schedule period, bringing its setpoint on early.

Full field reference: [Actions](actions.md).

> Climate (and most status entities) are **unavailable** when the cloud returns an empty appliance overview (common when heaters have not telemetered recently).

## Sensors

| Name                   | Unit      | Device class | Description                                                                                                                                                                            |
| ---------------------- | --------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Room temperature       | °C        | temperature  | Current room temperature.                                                                                                                                                              |
| Target temperature     | °C        | temperature  | Active setpoint.                                                                                                                                                                       |
| Boost temperature      | °C        | temperature  | Boost mode target.                                                                                                                                                                     |
| Away temperature       | °C        | temperature  | Away mode target.                                                                                                                                                                      |
| Setback temperature    | °C        | temperature  | Setback target.                                                                                                                                                                        |
| Energy last 30 days    | kWh       | energy       | Rolling 30-day sum for register **T1** only (off-peak / cheaper rate). No state class — not a meter, so it never enters long-term statistics. Translation key stays `energy_lifetime`. |
| Energy today           | kWh       | energy       | T1 (off-peak) kWh for the current local calendar day.                                                                                                                                  |
| Energy T2 last 30 days | kWh       | energy       | Rolling 30-day sum for register **T2** only (peak / more expensive; disabled by default). No state class. Translation key stays `energy_t2_lifetime`.                                  |
| Energy T2 today        | kWh       | energy       | T2 (peak) kWh for the current local calendar day (disabled by default).                                                                                                                |
| Rated power            | kW        | power        | Static nameplate power from product provisioning (_disabled by default_).                                                                                                              |
| Estimated power        | kW        | power        | Heuristic `rated_power` when boost or advance is engaged, else `0` (_diagnostic, disabled by default; not a live meter_).                                                              |
| Charge capacity        | kWh       | energy       | Static storage capacity from provisioning (_disabled by default_).                                                                                                                     |
| Error code             | —         | —            | Appliance error code (_disabled by default_).                                                                                                                                          |
| Warning code           | —         | —            | Appliance warning code (_disabled by default_).                                                                                                                                        |
| Last telemetry         | timestamp | timestamp    | Last cloud telemetry time (_disabled by default_).                                                                                                                                     |

### Energy attributes

| Attribute                     | Description                                           |
| ----------------------------- | ----------------------------------------------------- |
| `mode`                        | `lifetime` (the 30-day window) or `daily`.            |
| `register`                    | `t1` or `t2` (always separate).                       |
| `window_days`                 | Days summed — 30 for the window sensors, 1 for today. |
| `window_start` / `window_end` | Bounds of points used in the total.                   |
| `telemetry_points`            | Number of points included.                            |

Energy data is **daily kWh history** from the cloud, not live watts. Sensors are **unavailable** (not `0`) when there are no points, and **T1 and T2 are never combined** — they are separate dual-rate registers.

See [Energy monitoring](../use/energy.md) for adding these to the Energy Dashboard, the
tariff mapping, and the automatic poll back-off when history stays empty.

## Binary sensors

| Name        | Device class | Description                                                 |
| ----------- | ------------ | ----------------------------------------------------------- |
| Comfort     | —            | Comfort status from overview.                               |
| Open window | window       | Open-window detection **status** (enabled flag from cloud). |
| Setback     | —            | Setback mode active.                                        |
| Connected   | connectivity | Hub connection (one per hub).                               |

The appliance mode bitfield is also broken out as four **diagnostic** binary
sensors — Boost active, Away active, Frost protection, Advance active.

| Name             | Mode bit             | Meaning                                       |
| ---------------- | -------------------- | --------------------------------------------- |
| Boost active     | `BOOST` (2)          | A timed boost is running                      |
| Away active      | `AWAY` (4)           | Away setback is engaged                       |
| Advance active   | `ADVANCE` (16)       | The next schedule period was brought on early |
| Frost protection | `FROST_PROTECT` (32) | The 7 °C floor — what "off" means             |

These exist because the climate entity folds the whole bitfield into one preset, which is
precisely what hid the mode mismatch behind
[#163](https://github.com/kroperuk/dimplex-controller-hass/issues/163): the integration
asked for Boost and the heater engaged Advance, with nothing on the dashboard to say so.

Several bits can be set at once, so these four sensors can disagree with `preset_mode` —
the sensors are the appliance's actual state and are the better thing to automate on. See
[Modes & presets](../use/modes.md) for the whole model. A
[diagnostics download](../help/diagnostics.md) also lists the engaged modes by name.

## Switches

| Name                  | Description                                                                   |
| --------------------- | ----------------------------------------------------------------------------- |
| EcoStart              | Toggle EcoStart energy-saving mode.                                           |
| Open window detection | Enable/disable open-window detection (control; pairs with the binary sensor). |

## Numbers

| Name           | Description                                                                                                                                                                                                                     |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Setback target | The reduced ("setback") temperature the appliance falls back to when setback mode is active. Writing it also marks the setback ACTIVE, which is what the official app's setback control does. Translation key `setback_target`. |

Created only for appliances whose capability matrix says both `setback_read` and `setback_write` —
a write that could never be read back would leave the entity showing a stale number forever. The
Setback **binary sensor** reports whether setback is currently engaged, and the Setback
**temperature** sensor reports the same value read-only.

The range offered is the capability matrix's own 7-30 °C. That range is **inferred** from the
app rather than measured — see [appliance support](appliances.md#temperature-ranges).

## Schedule

Diagnostic **Schedule** sensor per appliance. Its state is the timer mode — `manual`,
`user_timer`, `frost_protection` or `off` — and its `periods` attribute lists the programme
as day / start / end / temperature.

The sensor is read-only. The programme can be copied to other appliances, and one period's
target edited, through actions — see
[edit the weekly schedule](../use/temperature.md#editing-the-weekly-schedule).

## Zones

Zone devices appear in the device registry (`via` hub; appliances `via` zone when zone id is known). A disabled diagnostic zone sensor anchors each zone device.

## Automations

Worked examples using these entities live in
[Automations & blueprints](../use/automations.md). The diagnostic mode sensors are usually a
better trigger than `preset_mode`, because the appliance can hold several modes at once
while the preset can only report one.
