# Entities

This page lists the entity types exposed by the Dimplex Hub integration.

Entity names use Home Assistant’s `has_entity_name` pattern: the **device** is the appliance (or hub), and each entity has a short name such as “Room temperature” or “EcoStart”.

## Climate

One climate entity per appliance.

| Name            | Entity ID pattern     | Description                                                                    |
| --------------- | --------------------- | ------------------------------------------------------------------------------ |
| _(device name)_ | `climate.<appliance>` | Thermostat: current room temperature, target setpoint, HVAC heat/off, presets. |

### Presets

| Preset    | Behaviour                                                          |
| --------- | ------------------------------------------------------------------ |
| `comfort` | Clears boost/away and turns EcoStart off when active.              |
| `boost`   | Enables boost (default ~60 minutes, boost temperature when known). |
| `away`    | Enables away mode at the appliance away temperature when known.    |
| `eco`     | Enables EcoStart.                                                  |

### Services

- `climate.set_temperature` — writes the target via the cloud timer schedule.
- `climate.set_preset_mode` — boost / away / eco / comfort.
- `climate.turn_on` / `climate.turn_off` — heat mode; off clears boost/away.

> Climate (and most status entities) are **unavailable** when the cloud returns an empty appliance overview (common when heaters have not telemetered recently).

## Sensors

| Name                | Unit      | Device class | Description                                                                                                              |
| ------------------- | --------- | ------------ | ------------------------------------------------------------------------------------------------------------------------ |
| Room temperature    | °C        | temperature  | Current room temperature.                                                                                                |
| Target temperature  | °C        | temperature  | Active setpoint.                                                                                                         |
| Boost temperature   | °C        | temperature  | Boost mode target.                                                                                                       |
| Away temperature    | °C        | temperature  | Away mode target.                                                                                                        |
| Setback temperature | °C        | temperature  | Setback target.                                                                                                          |
| Energy lifetime     | kWh       | energy       | Sum of all known daily cloud points (primary register).                                                                  |
| Energy today        | kWh       | energy       | kWh for the current local calendar day.                                                                                  |
| Energy T2 lifetime  | kWh       | energy       | Secondary energy register (when present).                                                                                |
| Energy T2 today     | kWh       | energy       | Secondary register, today only.                                                                                          |
| Rated power         | kW        | power        | Static nameplate power from product provisioning (_disabled by default_).                                                |
| Estimated power     | kW        | power        | Heuristic `rated_power` when comfort/boost looks active, else `0` (_diagnostic, disabled by default; not a live meter_). |
| Charge capacity     | kWh       | energy       | Static storage capacity from provisioning (_disabled by default_).                                                       |
| Error code          | —         | —            | Appliance error code (_disabled by default_).                                                                            |
| Warning code        | —         | —            | Appliance warning code (_disabled by default_).                                                                          |
| Last telemetry      | timestamp | timestamp    | Last cloud telemetry time (_disabled by default_).                                                                       |

### Energy attributes

| Attribute                     | Description                         |
| ----------------------------- | ----------------------------------- |
| `mode`                        | `lifetime` or `daily`.              |
| `register`                    | `t1` (primary) or `t2`.             |
| `window_start` / `window_end` | Bounds of points used in the total. |
| `telemetry_points`            | Number of points included.          |

Energy data is **daily kWh history** from the cloud, not live watts. Sensors are **unavailable** (not `0`) when there are no points.

When energy history is empty for several successful polls (common in summer), the integration **backs off** the energy poll interval (default up to 3 hours) and restores the configured interval when points return or heating activity is detected.

## Binary sensors

| Name        | Device class | Description                                                 |
| ----------- | ------------ | ----------------------------------------------------------- |
| Comfort     | —            | Comfort status from overview.                               |
| Open window | window       | Open-window detection **status** (enabled flag from cloud). |
| Setback     | —            | Setback mode active.                                        |
| Connected   | connectivity | Hub connection (one per hub).                               |

## Switches

| Name                  | Description                                                                   |
| --------------------- | ----------------------------------------------------------------------------- |
| EcoStart              | Toggle EcoStart energy-saving mode.                                           |
| Open window detection | Enable/disable open-window detection (control; pairs with the binary sensor). |

## Unique IDs

Unique IDs are derived from the config entry id and the cloud appliance (or hub) id, plus a stable suffix (`_climate`, `_energy`, `_ecostart`, …). They remain stable across renames in the UI.

## Templates and automations

### Alert if room is too cold

```yaml
alias: Living room is too cold
trigger:
  - platform: numeric_state
    entity_id: sensor.living_room_room_temperature
    below: 18
action:
  - service: notify.notify
    data:
      message: "Living room is {{ states('sensor.living_room_room_temperature') }} °C"
```

### Boost via climate preset

```yaml
alias: Boost living room
trigger:
  - platform: state
    entity_id: input_boolean.boost_living_room
    to: "on"
action:
  - service: climate.set_preset_mode
    target:
      entity_id: climate.living_room
    data:
      preset_mode: boost
```

### EcoStart when away

```yaml
alias: Enable EcoStart when away
trigger:
  - platform: state
    entity_id: person.yourself
    to: "not_home"
action:
  - service: switch.turn_on
    target:
      entity_id: switch.living_room_ecostart
```

Entity IDs depend on your appliance names; adjust to match **Settings → Devices & services → Entities**.
