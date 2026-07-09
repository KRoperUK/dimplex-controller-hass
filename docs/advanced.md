# Advanced usage

This page covers advanced topics for users who want to get more from the Dimplex Hub integration.

## Energy Dashboard

The integration exposes metered appliances as `SensorDeviceClass.ENERGY` sensors with `kWh` units. These integrate natively with the Home Assistant Energy Dashboard.

### Adding to the Energy Dashboard

1. Go to **Settings** > **Dashboards** > **Energy**.
2. Click **+ Add consumption**.
3. Select **From an integration** and choose your Dimplex energy sensor.
4. Click **Done**.

### Understanding the data

The Dimplex cloud provides a rolling 30-day window of daily kWh values. The integration maps these to Home Assistant's expected `state` and `last_reset` format so the Energy Dashboard can plot them correctly.

| Field                 | Value     | Description                                         |
| --------------------- | --------- | --------------------------------------------------- |
| `state`               | kWh       | Total energy consumed in the current 30-day window. |
| `unit_of_measurement` | kWh       | Unit of measurement.                                |
| `device_class`        | `energy`  | Marks the sensor as an energy meter.                |
| `last_reset`          | Timestamp | Start of the current 30-day window.                 |

### Limitations

- Only metered appliances (for example, QRAD radiators) report energy data.
- During warmer months, when heaters are not running, the sensor will be **unavailable**. This is correct behaviour — the Energy Dashboard ignores `unavailable` readings.

## Automations

### Example: Boost heating when temperature drops

```yaml
alias: Boost if temperature drops too low
trigger:
  - platform: numeric_state
    entity_id: sensor.living_room_temperature
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

### Example: Notify on open window detection

```yaml
alias: Notify on open window
trigger:
  - platform: state
    entity_id: binary_sensor.k_radiator_open_window
    to: "on"
action:
  - service: notify.notify
    data:
      message: "Window detected as open — heating paused for {{ state_attr('binary_sensor.k_radiator_open_window', 'friendly_name') }}"
```

## Developer notes

### PyPI dependency

This integration depends on [`dimplex-controller>=0.5.0`](https://pypi.org/project/dimplex-controller/). When a new version of the library is released, bump the version requirement in `manifest.json`.

### Local development

If you want to test changes to the Python client alongside the integration:

1. Clone both repositories.
2. Install the local `dimplex-controller-py` in editable mode in the same environment as Home Assistant.
3. Restart Home Assistant.

> **Note:** Running local development code on a production Home Assistant instance is not recommended. Use a test instance instead.

### Data coordinator

The integration uses a `DataUpdateCoordinator` to fetch appliance data every 30 seconds. The coordinator stores the latest snapshot in `coordinator.data["appliances"]`. Platform entities read from this snapshot rather than making individual API calls.

If you are developing new platforms or entities, access data through the coordinator:

```python
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

class MyEntity(CoordinatorEntity):
    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
```

## Support and feedback

- [GitHub Issues](https://github.com/kroperuk/dimplex-controller-hass/issues)
- [Home Assistant Community Forum](https://community.home-assistant.io/)
- [Discord](https://discord.gg/Qa5fW2R)
