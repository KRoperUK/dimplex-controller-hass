# Entities

This page lists every entity type exposed by the Dimplex Hub integration, along with their attributes, device classes and example values.

## Sensor entities

Sensors provide numeric readings for each Zone and Appliance.

| Entity ID pattern           | Name             | Unit | Device class  | Description                                        |
| --------------------------- | ---------------- | ---- | ------------- | -------------------------------------------------- |
| `sensor.<zone>_temperature` | Room Temperature | °C   | `temperature` | Current room temperature.                          |
| `sensor.<appliance>_energy` | Energy           | kWh  | `energy`      | Cumulative energy used in a rolling 30-day window. |

### Sensor attributes

| Attribute                      | Description                           |
| ------------------------------ | ------------------------------------- |
| `active_set_point_temperature` | The current target temperature.       |
| `comfort_status`               | Comfort mode status string.           |
| `eco_start_enabled`            | Whether EcoStart is currently active. |
| `appliance_modes`              | Bitmask of active appliance modes.    |
| `boost_active`                 | Whether Boost is active.              |
| `away_mode_active`             | Whether Away mode is active.          |
| `open_window_detected`         | Whether an open window is detected.   |

> **Note:** Attribute availability depends on your appliance firmware. Not all attributes will be present for every device.

## Binary sensor entities

Binary sensors report on/off or active/inactive states.

| Entity ID pattern                   | Name           | Device class | Description                               |
| ----------------------------------- | -------------- | ------------ | ----------------------------------------- |
| `binary_sensor.<appliance>_comfort` | Comfort Status | `plug`       | Whether the appliance is in Comfort mode. |

## Switch entities

Switches allow you to toggle appliance features.

| Entity ID pattern             | Name     | Description                                   |
| ----------------------------- | -------- | --------------------------------------------- |
| `switch.<appliance>_ecostart` | EcoStart | Toggle EcoStart energy-saving mode on or off. |

### Switch behaviour

When you turn on the EcoStart switch:

1. The integration sends a `set_eco_start` command to the Dimplex cloud.
2. The cloud applies the change to the appliance.
3. The integration refreshes its data and updates the entity state.

If the command fails, the switch will revert to its previous state and an error will appear in the Home Assistant logs.

## Entity unique IDs

Entity unique IDs are derived from the appliance ID provided by the Dimplex cloud. They remain stable across Home Assistant restarts, so you can safely use them in automations and templates.

## Templates and automations

### Example: Alert if room is too cold

```yaml
alias: Living room is too cold
trigger:
  - platform: numeric_state
    entity_id: sensor.living_room_temperature
    below: 18
condition: []
action:
  - service: notify.notify
    data:
      message: "Living room is {{ states('sensor.living_room_temperature') }}°C"
```

### Example: Turn on EcoStart when away

```yaml
alias: Enable EcoStart when away
trigger:
  - platform: state
    entity_id: person.yourself
    to: "not_home"
condition: []
action:
  - service: switch.turn_on
    target:
      entity_id: switch.k_radiator_ecostart
```

### Example: Energy dashboard card

```yaml
type: energy-date-selection
title: Heating energy
```

Use the built-in Energy Dashboard to view daily, weekly and monthly energy consumption.

## Naming and renaming

Entity names are generated from the appliance names reported by the Dimplex cloud. You can rename entities in Home Assistant without breaking the integration:

1. Go to **Settings** > **Devices & Services** > **Entities**.
2. Search for the entity.
3. Click the pencil icon and enter a new name.

Renaming does not affect the unique ID or the integration's ability to communicate with the appliance.
