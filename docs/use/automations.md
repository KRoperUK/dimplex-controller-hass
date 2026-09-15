---
description: Blueprints and worked automation examples for Dimplex heaters in Home Assistant — boost when cold, away when everyone leaves, open-window alerts.
---

# Automations & blueprints

All examples use the current Home Assistant syntax (`triggers:` / `conditions:` /
`actions:`, and `action:` rather than `service:`). Entity IDs come from your appliance
names — check **Settings** → **Devices & services** → **Entities** and adjust.

## Blueprints

Three blueprints ship in the repository under `blueprints/automation/dimplex/`:

| Blueprint                        | Does                                                                           |
| -------------------------------- | ------------------------------------------------------------------------------ |
| `boost_if_cold.yaml`             | Boost an appliance when its room drops below a threshold, within a time window |
| `notify_open_window.yaml`        | Notify when open-window detection trips                                        |
| `away_when_everyone_leaves.yaml` | Set away mode when the last tracked person leaves                              |

Import one by copying it into `<config>/blueprints/automation/dimplex/` and reloading
automations, then **Settings** → **Automations & scenes** → **Create automation** → **Use a
blueprint**.

All three declare a minimum Home Assistant of 2025.1.0, matching the integration, and are
validated in CI against Home Assistant's own blueprint and automation schemas.

!!! note "`away_when_everyone_leaves` does not clear away again"

    It engages away when presence drops, and nothing turns it off. Pair it with a second
    automation selecting the `comfort` preset on return, which clears away, boost and
    EcoStart together.

## Boost when a room gets cold

```yaml
alias: Boost if living room is cold
triggers:
  - trigger: numeric_state
    entity_id: sensor.living_room_room_temperature
    below: 17
conditions:
  - condition: time
    after: "06:00:00"
    before: "22:00:00"
actions:
  - action: climate.set_preset_mode
    target:
      entity_id: climate.living_room
    data:
      preset_mode: boost
```

The time condition matters: without it a cold night triggers a boost at 03:00. Boost runs
for the duration configured in [options](../reference/options.md) — 60 minutes by default.

For explicit control over target and duration, use the action rather than the preset:

```yaml
actions:
  - action: dimplex.set_boost
    target:
      entity_id: climate.living_room
    data:
      temperature: 22
      duration: 90
```

## Away while you are on holiday

```yaml
alias: Away until Sunday evening
triggers:
  - trigger: state
    entity_id: input_boolean.holiday
    to: "on"
actions:
  - action: dimplex.set_away
    target:
      entity_id: climate.living_room
    data:
      temperature: 12
      until: "2026-10-04 18:00:00"
```

`until` gives an exact return time and takes precedence over `days`. Omit both for an
open-ended away. Remember the [18 °C ceiling](temperature.md#what-the-cloud-will-not-let-you-do)
— a higher value is clamped and logged.

## Start the evening's heating early

```yaml
alias: Advance heating when I get home early
triggers:
  - trigger: state
    entity_id: person.yourself
    to: "home"
conditions:
  - condition: time
    after: "15:00:00"
    before: "17:00:00"
actions:
  - action: dimplex.set_advance
    target:
      entity_id: climate.living_room
```

No `temperature`, so the appliance uses the next schedule period's own target — which is
what you usually want, and what the official app does for storage heaters.

## Alert when a room is too cold

```yaml
alias: Living room is too cold
triggers:
  - trigger: numeric_state
    entity_id: sensor.living_room_room_temperature
    below: 18
actions:
  - action: notify.notify
    data:
      message: "Living room is {{ states('sensor.living_room_room_temperature') }} °C"
```

## Notify on open window

```yaml
alias: Notify on open window
triggers:
  - trigger: state
    entity_id: binary_sensor.living_room_open_window
    to: "on"
actions:
  - action: notify.notify
    data:
      message: "Open window detected on {{ trigger.to_state.name }}"
```

## React to the mode the heater is actually in

The diagnostic mode sensors are more reliable to trigger on than `preset_mode`, because the
appliance can hold several modes at once while the preset can only report one — see
[Modes & presets](modes.md#why-preset_mode-can-disagree-with-reality).

```yaml
alias: Warn if away mode is still on after we are back
triggers:
  - trigger: state
    entity_id: binary_sensor.living_room_away_active
    to: "on"
    for: "01:00:00"
conditions:
  - condition: state
    entity_id: person.yourself
    state: "home"
actions:
  - action: notify.notify
    data:
      message: "Away mode is still engaged on the living room heater"
```

## Set a target at a fixed time

```yaml
alias: Evening setpoint
triggers:
  - trigger: time
    at: "18:00:00"
actions:
  - action: climate.set_temperature
    target:
      entity_id: climate.living_room
    data:
      temperature: 21
```

This writes the setpoint without disturbing the stored schedule — see
[setting a target](temperature.md#setting-a-target).

## Targeting

Every `dimplex.*` action accepts either `device_id` for the appliance device, or any
`entity_id` belonging to that appliance. Both resolve to the same heater, so use whichever
is more convenient.

## Next

- [Actions](../reference/actions.md) — every field and its range
- [Entities](../reference/entities.md) — what you can trigger on
- [Temperature & schedules](temperature.md) — what actually reaches the heater
