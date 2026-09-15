---
description: Add Dimplex energy sensors to the Home Assistant Energy Dashboard, with T1 and T2 dual-rate registers kept separate.
---

# Energy monitoring

Metered appliances report **daily kWh history** from the Dimplex cloud — not live watts.
There is no wattage stream to read, so nothing here is a real-time meter.

## T1 and T2 are separate

The cloud exposes two energy registers, and the integration never sums them.

| Register | Sensors                              | Tariff (observed)    | Default  |
| -------- | ------------------------------------ | -------------------- | -------- |
| **T1**   | Energy today / Energy lifetime       | Off-peak, cheaper    | Enabled  |
| **T2**   | Energy T2 today / Energy T2 lifetime | Peak, more expensive | Disabled |

!!! warning "Do not merge them into one helper"

    The whole point of two registers is that the kWh cost different amounts. Adding them
    together throws away the only information that makes them worth having. Map each to its
    matching tariff instead.

Confirm the mapping against your own tariff and the official app — off-peak/peak is what has
been observed, not something the cloud labels explicitly.

## Add to the Energy Dashboard

1. Go to **Settings** → **Dashboards** → **Energy**.
2. **Add consumption** → pick **Energy today** for off-peak (T1).
3. If your heaters report T2, enable **Energy T2 today** in the entity registry and add it
   as a second consumption source for peak.
4. Attach the matching tariff entity to each if you track costs.

Use the **today** sensors for the dashboard. They reset at local midnight and give clean
daily bars.

The **lifetime** sensors are cumulative totals across all history the cloud returns, with
`last_reset` at the first telemetry day. Adding one to the Energy Dashboard imports the
entire history at once, which produces a large pop-in on the first day — useful for a
long-running total, surprising if you expected today's usage.

## Behaviour worth knowing

- **No data means `unavailable`, not `0`.** The dashboard is never fed fake zeros, so a
  gap stays a gap.
- **Energy polls on a slower cadence than status** — 30 minutes by default, against 30
  seconds for temperatures and modes.
- **Empty history backs the poll off automatically.** After three consecutive
  empty-but-successful polls — routine in summer, when nothing is heating — the interval
  stretches to as much as 3 hours, and snaps back when points return or heating activity
  is detected.
- **A repair is raised** if energy polls keep succeeding while staying empty, so a genuinely
  broken meter is distinguishable from a quiet one.

## Energy attributes

Each energy sensor carries the provenance of its total:

| Attribute                     | Meaning                             |
| ----------------------------- | ----------------------------------- |
| `mode`                        | `lifetime` or `daily`               |
| `register`                    | `t1` or `t2` — always separate      |
| `window_start` / `window_end` | Bounds of the points summed         |
| `telemetry_points`            | How many points went into the total |

If a figure looks wrong, `telemetry_points` and the window bounds usually explain it — a
partial day, or a gap in cloud history.

## Power sensors are not meters

Three power-shaped sensors exist and none of them measures consumption:

| Sensor              | What it actually is                                                      |
| ------------------- | ------------------------------------------------------------------------ |
| **Rated power**     | Static nameplate figure from provisioning. A constant.                   |
| **Charge capacity** | Static storage capacity from provisioning. A constant.                   |
| **Estimated power** | `rated_power` when boost or advance looks active, else `0`. A heuristic. |

All three are diagnostic and disabled by default. **Estimated power** in particular is a
guess from mode flags, not a measurement — do not put it in the Energy Dashboard.

## Next

- [Entities](../reference/entities.md#sensors) — the full sensor list
- [Options](../reference/options.md) — change the energy poll interval
- [Energy sensor unavailable in summer](../help/troubleshooting.md#energy-sensor-shows-unavailable-in-summer)
