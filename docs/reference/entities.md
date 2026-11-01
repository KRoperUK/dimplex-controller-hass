---
description: Every entity the Dimplex Hub integration creates — climate, sensors, binary sensors, switches and the diagnostic mode sensors — and which are disabled by default.
---

# Entities

This page lists the entity types exposed by the Dimplex Hub integration.

Entity names use Home Assistant’s `has_entity_name` pattern: the **device** is the appliance (or hub), and each entity has a short name such as “Room temperature” or “EcoStart”.

## Climate

One climate entity per room heater. Hot water cylinders get a [water heater](#water-heater) instead.

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

| Name                 | Unit      | Device class   | Description                                                                                                                                                                                                                                                                                                                                                                     |
| -------------------- | --------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Room temperature     | °C        | temperature    | Current room temperature.                                                                                                                                                                                                                                                                                                                                                       |
| Target temperature   | °C        | temperature    | Active setpoint.                                                                                                                                                                                                                                                                                                                                                                |
| Boost temperature    | °C        | temperature    | Boost mode target.                                                                                                                                                                                                                                                                                                                                                              |
| Away temperature     | °C        | temperature    | Away mode target.                                                                                                                                                                                                                                                                                                                                                               |
| Setback temperature  | °C        | temperature    | Setback target.                                                                                                                                                                                                                                                                                                                                                                 |
| Energy lifetime      | kWh       | energy         | Total across every daily reading the cloud still holds for the appliance — normally its whole history, so it rises like a meter. Translation key stays `energy_lifetime`.                                                                                                                                                                                                       |
| Energy today         | kWh       | energy         | T1 (off-peak) kWh for the current local calendar day.                                                                                                                                                                                                                                                                                                                           |
| Energy T2 lifetime   | kWh       | energy         | As **Energy lifetime**, for register **T2** (peak / more expensive; disabled by default). Translation key stays `energy_t2_lifetime`.                                                                                                                                                                                                                                           |
| Energy T2 today      | kWh       | energy         | T2 (peak) kWh for the current local calendar day (disabled by default).                                                                                                                                                                                                                                                                                                         |
| Rated power          | kW        | power          | Static nameplate power from product provisioning (_disabled by default_).                                                                                                                                                                                                                                                                                                       |
| Top element power    | kW        | power          | Static top-element rating from product provisioning (_diagnostic, disabled by default_). Translation key `top_element_power`.                                                                                                                                                                                                                                                   |
| Bottom element power | kW        | power          | Static bottom-element rating from product provisioning (_diagnostic, disabled by default_). Translation key `bottom_element_power`.                                                                                                                                                                                                                                             |
| Estimated power      | kW        | power          | Heuristic `rated_power` when boost or advance is engaged, else `0` (_diagnostic, disabled by default; not a live meter_).                                                                                                                                                                                                                                                       |
| Operating mode       | —         | —              | Live `ApplianceModes` decoded to flag names (e.g. `TIMER_MODE`, `ECO`), with `active_modes`, `raw_modes` and `appliance_modes_known` attributes (_diagnostic_). The raw integer is reported faithfully — bit 64 stays `ECO` even though QRAD firmware 28 shows Manual in the app while reporting it, until a hardware probe settles the name. Translation key `operating_mode`. |
| Status two           | —         | —              | Raw `StatusTwo` integer from the status frame (_diagnostic_). No read meaning is known, so no heating implication is drawn from it. Translation key `status_two`.                                                                                                                                                                                                               |
| Boost remaining      | min       | duration       | Minutes of boost left, synthesised from the engage time and duration of a boost **started by Home Assistant**; counts down to zero (_diagnostic_). A boost begun on the heater or in the app has no recorded start and reads unknown. Translation key `boost_remaining`.                                                                                                        |
| Charge capacity      | kWh       | energy         | Static storage capacity from provisioning (_disabled by default_).                                                                                                                                                                                                                                                                                                              |
| Error code           | —         | —              | Appliance error code (_disabled by default_).                                                                                                                                                                                                                                                                                                                                   |
| Warning code         | —         | —              | Appliance warning code (_disabled by default_).                                                                                                                                                                                                                                                                                                                                 |
| Last telemetry       | timestamp | timestamp      | The appliance's `LastTelemDate` — the last time the cloud heard from it, used to tell stale data from a failed poll. An unset date reads unknown, never year 1 (_diagnostic_).                                                                                                                                                                                                  |
| Hot water available  | L         | volume_storage | Usable hot water, as the app's "336 L Hot water" — cylinders only.                                                                                                                                                                                                                                                                                                              |

### Energy attributes

| Attribute                     | Description                                                                 |
| ----------------------------- | --------------------------------------------------------------------------- |
| `mode`                        | `lifetime` (everything the cloud returned) or `daily`.                      |
| `register`                    | `t1` or `t2` (always separate).                                             |
| `window_start` / `window_end` | Bounds of points used in the total — the real span.                         |
| `telemetry_points`            | Number of points included.                                                  |
| `raw_total`                   | _Lifetime only._ The total the cloud is sending now, before the hold below. |
| `peak_total`                  | _Lifetime only._ The highest total seen, which the state reports.           |

Energy data is **daily kWh history** from the cloud, not live watts. Sensors are **unavailable** (not `0`) when there are no points, and **T1 and T2 are never combined** — they are separate dual-rate registers.

The lifetime sensors declare `total_increasing` and are held monotonic: the highest value seen is what gets reported, and it is restored across a restart. That exists because a truncated cloud response would otherwise make the total fall, which Home Assistant reads as a meter reset and re-adds to long-term statistics.

A **permanent** reduction of the cloud's history cannot be reported as a lower reading, for that same reason — so on its own the hold would over-report silently and for ever. `raw_total` is what makes that visible: it is the number the cloud is currently sending, so a value below the state (or below `peak_total`) means the hold is suppressing something, and a suppressed drop of more than 10% logs a warning naming both figures. If `raw_total` stays below the state across consecutive polls, the cloud has lost history for that appliance — see [troubleshooting](../help/troubleshooting.md#the-energy-total-stays-above-what-the-cloud-is-sending).

See [Energy monitoring](../use/energy.md) for adding these to the Energy Dashboard, the
tariff mapping, and the automatic poll back-off when history stays empty.

## Binary sensors

| Name        | Device class | Description                                                                                                                                                                |
| ----------- | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Comfort     | —            | Comfort status from overview.                                                                                                                                              |
| Open window | —            | Whether open-window **detection is enabled** — the writable setting, not a physical open/closed event (a `window` device class would read permanently open while enabled). |
| Setback     | —            | Setback currently in effect: `SetbackEnabledInStatusFrame` when the cloud sends it, else the `SetbackEnabled` setting.                                                     |
| Connected   | connectivity | Hub connection (one per hub).                                                                                                                                              |

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

## Water heater

One per hot water cylinder, **read-only**: the cylinder control endpoints other than holiday
are untested, so it offers no controls. Translation key `cylinder`.

| State / attribute     | Description                                                           |
| --------------------- | --------------------------------------------------------------------- |
| state                 | The app's mode: `standby`, `timer`, `holiday`, `boost` or `hygiene`.  |
| `temperature`         | Water target (`ActiveSetPointTemperature`).                           |
| `hot_water_available` | Litres of usable hot water.                                           |
| `capacity`            | Tank size in litres.                                                  |
| `heating_up`          | The cylinder is heating now.                                          |
| `green_energy_active` | Green energy (heat pump) mode.                                        |
| `appliance_modes`     | The raw mode bitfield. `Normal` (8192) is what the app calls "Timer". |

Cylinder sensors (created only for hot water appliances):

| Name               | Unit | Description                                                                                         |
| ------------------ | ---- | --------------------------------------------------------------------------------------------------- |
| Hot water capacity | L    | Tank size (_diagnostic_). Translation key `hot_water_capacity`.                                     |
| Hot water mode     | —    | `standby` / `timer` / `holiday` / `boost` / `hygiene`. Translation key `hot_water_mode`.            |
| Hygiene recurrence | —    | Anti-legionella cycle: `off`, `daily`, `weekly`, `monthly` (_diagnostic_). Key `hygiene_frequency`. |
| Holiday days       | d    | Days of holiday the cylinder has left (_diagnostic_). Translation key `holiday_days`.               |

| Binary sensor | Description                                                                 |
| ------------- | --------------------------------------------------------------------------- |
| Heating water | `HeatingUp` — the cylinder is heating. Translation key `hot_water_heating`. |
| Green energy  | `IsGreenEnergyActive`. Translation key `green_energy`.                      |
| Holiday       | The `Holiday` mode bit is set. Translation key `holiday_active`.            |

The room-heater entities — climate, room temperature, open window, EcoStart, setback, comfort,
away, frost, advance, boost duration — are not created for a cylinder.

## Holiday

| Entity       | Platform | Description                                                                                                  |
| ------------ | -------- | ------------------------------------------------------------------------------------------------------------ |
| Holiday      | switch   | Puts the cylinder on holiday (standby) until **Holiday ends**; off clears it now. Translation key `holiday`. |
| Holiday ends | datetime | When Holiday is switched off. Defaults to a week ahead if unset; must be in the future. Key `holiday_end`.   |

The cylinder only counts whole days, so the integration clears Holiday itself at the chosen
time. The end time survives a restart, and if it passed while Home Assistant was down, Holiday
is cleared on start.

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

## Selects

| Name             | Description                                                                                                                                                                                                                                                                                                                                              |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Boost duration   | How long the `boost` **preset** runs for this appliance. The options are the discrete durations the appliance's capability matrix offers (`boost_durations`, e.g. 30/60/120/180 minutes), matching the official app's own picker. Translation key `boost_duration`.                                                                                      |
| Operating mode   | A **control**: `manual` holds a manual setpoint through the dedicated Manual write, `timer` returns the heater to its user-timer schedule. Without this, Home Assistant could never put a QRAD back into Manual itself — in User Timer the heater ignores every setpoint and boost. A refused write surfaces an error. Translation key `operating_mode`. |
| Schedule profile | Which schedule programme the heater follows: `user_timer`, `home_all_day` or `out_all_day`. A **control** — choosing a value applies that profile through the API, mirroring the official app's schedule picker. Translation key `schedule_profile`.                                                                                                     |

A configuration entity (not shown by default on the main card), created only for
boost-capable appliances (`boost` in the capability matrix). It is a **preference** — choosing a
value does not start a boost, it sets how long the next boost preset will run. A per-appliance
choice here takes precedence over the entry-wide **Boost duration** option, so each appliance can
use its own duration, and the choice survives a restart.

## Schedule

Diagnostic **Schedule** sensor per appliance. While the heater is following its timer
its state is the active schedule profile — `user_timer`, `home_all_day` or `out_all_day`,
taken from the live overview exactly as the official app names it — and otherwise it falls
back to the timer mode (`manual`, `user_timer`, `frost_protection` or `off`). Its `periods`
attribute lists the programme as day / start / end / temperature.

The sensor is read-only. The programme can be copied to other appliances, and one period's
target edited, through actions — see
[edit the weekly schedule](../use/temperature.md#editing-the-weekly-schedule).

### Hot water schedule

Heat-pump cylinders get a read-only **Hot water schedule** sensor instead (translation key
`hot_water_schedule`). Its state summarises the week, e.g. `Mon–Sun 00:00 mode 2`, and its
attributes list each day's periods (`start`, `start_raw`, `mode`) and the `current_mode`.
`Mode` is shown as the cloud's number because its meaning is not yet known, and start times
assume minutes after midnight.

## Zones

Zone devices appear in the device registry (`via` hub; appliances `via` zone when zone id is known). A disabled diagnostic zone sensor anchors each zone device.

## Automations

Worked examples using these entities live in
[Automations & blueprints](../use/automations.md). The diagnostic mode sensors are usually a
better trigger than `preset_mode`, because the appliance can hold several modes at once
while the preset can only report one.
