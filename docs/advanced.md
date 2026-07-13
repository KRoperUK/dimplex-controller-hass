# Advanced usage

## Energy Dashboard

Metered appliances expose `SensorDeviceClass.ENERGY` sensors in **kWh**, split by cloud register:

- **Energy today** / **Energy lifetime** — **T1**, off-peak / cheaper rate (enabled by default).
- **Energy T2 today** / **Energy T2 lifetime** — **T2**, peak / more expensive rate (enable in the entity registry if your heaters report T2).

T1 and T2 are **kept separate**. The integration never sums them into one “total energy” figure.

### Adding to the Energy Dashboard

1. Go to **Settings → Dashboards → Energy**.
2. **Add consumption** → pick **Energy today** for off-peak (T1).
3. If you have dual-rate and T2 data, enable **Energy T2 today** and add it as a second consumption source for peak.
4. Prefer **today** sensors for daily dashboard graphs; use **lifetime** for long-running totals with `last_reset` at the first telemetry day.
5. Map each sensor to the matching tariff stats if you track costs — do not merge T1+T2 into one helper.

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

## Domain services

Prefer these for scripts when climate presets are too coarse:

| Service                                     | Purpose                                          |
| ------------------------------------------- | ------------------------------------------------ |
| `dimplex.set_boost` / `dimplex.clear_boost` | Boost on/off (`temperature`, `duration` minutes) |
| `dimplex.set_away` / `dimplex.clear_away`   | Away on/off                                      |
| `dimplex.set_eco_start`                     | EcoStart (`enable`)                              |
| `dimplex.set_open_window_detection`         | Open-window detection (`enable`)                 |

Target with `device_id` (appliance device) or any `entity_id` on that appliance.

## Repairs

The integration may raise **Settings → System → Repairs** issues when:

- Reauthentication is required (actionable — opens reauth)
- Energy polls succeed but stay empty (seasonal / idle heaters)
- Appliance overview is empty while hubs exist

## Multi-account

See [multi-config.md](multi-config.md).

## Blueprints

Automation blueprints live under `blueprints/automation/dimplex/` in the repository (boost if cold, open-window notify, away when everyone leaves).

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

Requires [`dimplex-controller>=0.10.0`](https://pypi.org/project/dimplex-controller/) (capabilities matrix, schedule helpers, HTTP retry, T1/T2 register separation). Bump `custom_components/dimplex/manifest.json` when adopting a new library floor.

### Local development

1. Clone `dimplex-controller-py` and `dimplex-controller-hass`.
2. Install the library editable into the Home Assistant / test venv.
3. Restart HA or re-run tests after library changes.

### Pre-release (dev) builds

CI publishes **prerelease** GitHub Releases when component-impacting PRs or `main` pushes go green:

| Kind     | Tag             | Installed version (`manifest` / `const`) |
| -------- | --------------- | ---------------------------------------- |
| Main RC  | `vX.Y.Z-rc.N`   | `X.Y.Z-rc.N`                             |
| PR build | `vX.Y.Z-pr.P.R` | `X.Y.Z-pr.P.<shortsha>`                  |
| Stable   | `vX.Y.Z`        | `X.Y.Z` (release-please on `main`)       |

Each pre-release tag points at a **synthetic commit** that only rewrites those version files on top of the tested SHA. **`main` is never rewritten** for RCs. Install release candidates via the GitHub pre-release tag or HACS pre-releases (not a moving branch tip).

Legacy tags of the form `dev-v…` may still appear until they age out of cleanup; new builds use the semver shapes above.

### Known cloud limits

- Empty `GetApplianceOverview` is success when appliances are offline — entities go **unavailable**.
- No reverse-engineered **live wattage** stream; energy is historical daily kWh.
- Full weekly schedule UI is not exposed (setpoint writes rewrite timer periods).
