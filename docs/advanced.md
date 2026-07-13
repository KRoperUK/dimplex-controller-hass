# Advanced usage

## Energy Dashboard

Metered appliances expose `SensorDeviceClass.ENERGY` sensors in **kWh**:

- **Energy lifetime** — cumulative sum of daily cloud points (best for long-term totals).
- **Energy today** — local calendar-day total (midnight → now).

### Adding to the Energy Dashboard

1. Go to **Settings → Dashboards → Energy**.
2. **Add consumption** → pick your Dimplex energy sensor(s).
3. Prefer **Energy today** for daily dashboard graphs if the sensor has points; use **lifetime** for long-running totals with `last_reset` at the first telemetry day.

### Behaviour notes

- Points are **daily kWh** from the Dimplex cloud, not continuous live meters.
- No data → sensor is **unavailable** (not `0`), so the dashboard is not fed fake zeros.
- Energy is polled less often than status (default **30 minutes**).

### Static power (diagnostics)

**Rated power** and **charge capacity** (from `AUTOMATIC_PROVISIONING`) are optional diagnostic sensors. They are **not** live consumption. Enable them under the entity registry if useful for reference.

## Options

**Settings → Devices & services → Dimplex Hub → Configure**:

| Option               | Default | Meaning                                               |
| -------------------- | ------- | ----------------------------------------------------- |
| Platform toggles     | all on  | Enable/disable climate, sensor, binary_sensor, switch |
| Status poll interval | 30 s    | Overview / temperatures / modes                       |
| Energy poll interval | 1800 s  | TSI energy report                                     |

Changing options reloads the integration.

## Automations

### Boost when temperature drops

```yaml
alias: Boost if living room is cold
trigger:
  - platform: numeric_state
    entity_id: sensor.living_room_room_temperature
    below: 17
condition:
  - condition: time
    after: "06:00:00"
    before: "22:00:00"
action:
  - service: climate.set_preset_mode
    target:
      entity_id: climate.living_room
    data:
      preset_mode: boost
```

### Notify on open window

```yaml
alias: Notify on open window
trigger:
  - platform: state
    entity_id: binary_sensor.living_room_open_window
    to: "on"
action:
  - service: notify.notify
    data:
      message: "Open window detection active on {{ trigger.to_state.name }}"
```

### Set target temperature

```yaml
alias: Evening setpoint
trigger:
  - platform: time
    at: "18:00:00"
action:
  - service: climate.set_temperature
    target:
      entity_id: climate.living_room
    data:
      temperature: 21
```

## Developer notes

### PyPI dependency

Requires [`dimplex-controller>=0.8.0`](https://pypi.org/project/dimplex-controller/). Bump `custom_components/dimplex/manifest.json` when adopting a new library floor.

### Local development

1. Clone `dimplex-controller-py` and `dimplex-controller-hass`.
2. Install the library editable into the Home Assistant / test venv.
3. Restart HA or re-run tests after library changes.

### Known cloud limits

- Empty `GetApplianceOverview` is success when appliances are offline — entities go **unavailable**.
- No reverse-engineered **live wattage** stream; energy is historical daily kWh.
- Full weekly schedule UI is not exposed (setpoint writes rewrite timer periods).
