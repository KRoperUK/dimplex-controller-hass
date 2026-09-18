---
description: Download a Dimplex Hub diagnostics file from Home Assistant, understand what it contains, and attach it to a bug report.
---

# Diagnostics & bug reports

A diagnostics download is the fastest route to an answer. It decodes the appliance's engaged
modes **by name**, so a maintainer can see what the heater is actually doing instead of
inferring it from a description.

## Download one

1. **Settings** → **Devices & services** → **Dimplex Hub**.
2. Click the **⋮** overflow menu on the integration card, or on a specific device.
3. **Download diagnostics**.

Home Assistant saves a JSON file. Attach it to your issue.

## What it contains

| Section                      | Contents                                                                 |
| ---------------------------- | ------------------------------------------------------------------------ |
| `entry`                      | Title, version, your options, and the entry data with secrets redacted   |
| `versions`                   | Integration version and the resolved `dimplex-controller` version        |
| `hubs`                       | Hub ID, name, connection state, firmware, hub type                       |
| `appliances`                 | Per appliance: ID, friendly name, model, type, firmware, zone            |
| `appliances[].status`        | The full status snapshot the cloud returned                              |
| `appliances[].active_modes`  | **The mode bitfield decoded into names**                                 |
| `appliances[].provisioning`  | Rated power and charge capacity, where reported                          |
| `appliances[].capabilities`  | **Every resolved capability flag the controls are gated on**             |
| `appliances[].product_model` | The catalogue row this appliance was matched to, if any                  |
| `energy`                     | Point counts and time windows per register — not the readings themselves |

### `capabilities` is the useful bit when something is missing

An appliance that has no thermostat, no setback write or no hot water control is one the
library's capability matrix said does not support it. The resolved flags are listed per
appliance, so the reason a control is absent is visible rather than guessed at. See
[Appliance support](../reference/appliances.md#how-capabilities-are-decided).

### `active_modes` is the useful bit

Instead of `"ApplianceModes": 8198` you get:

```json
"active_modes": ["BOOST", "AWAY", "NORMAL"]
```

This exists specifically because a mode-mapping bug went unnoticed for a long time —
[#163](https://github.com/kroperuk/dimplex-controller-hass/issues/163), where the integration
asked for boost and the appliance engaged advance. Nobody reading a diagnostics file should
have to decode a bitfield by hand. See [Modes & presets](../use/modes.md).

## What is redacted

Removed or hashed before the file is written:

- `access_token`, `refresh_token`, `password`
- `username`, `email`, `PrimaryUserEmail` — the hub's primary email appears only as a
  truncated SHA-256 hash, so two hubs can be told apart without exposing the address
- `SecurityCode`

Appliance IDs, hub IDs, model names and firmware versions **are** included — they are needed
to make sense of anything, and are not secrets. Have a skim before attaching if you would
rather not share a friendly name like "Nursery".

## A good bug report

- [ ] Your Home Assistant version
- [ ] The integration version — HACS, or `manifest.json`
- [ ] **A diagnostics download**
- [ ] What you did, what you expected, what happened
- [ ] Relevant log lines (see below), with personal details redacted
- [ ] Whether it happens every time or intermittently
- [ ] The appliance family — panel heater, QRAD, Quantum storage. Behaviour differs; see
      [appliance support](../reference/appliances.md)
- [ ] Whether the official Dimplex app does the same thing

That last one separates "this integration is wrong" from "the cloud is behaving this way",
and it is the single most useful line you can add.

[Open an issue](https://github.com/kroperuk/dimplex-controller-hass/issues/new/choose)

## Getting the logs

Add this to `configuration.yaml` and restart to capture detail:

```yaml
logger:
  default: info
  logs:
    custom_components.dimplex: debug
    dimplex_controller: debug
```

Then **Settings** → **System** → **Logs** → **Load full logs**, and filter on `dimplex`.

!!! warning "Debug logging is verbose"

    It records every cloud call. Turn it back to `info` once you have captured the problem,
    and check the excerpt you paste for tokens or email addresses — the logger does not
    redact the way diagnostics does.

## Before filing

Worth ruling out first:

- **Does the official app show the same?** If so, it is the cloud or the appliance, not this
  integration.
- **Are you on the latest release?** Several long-standing mode bugs were fixed in 4.1.0 —
  see [upgrading](upgrading.md).
- **Is the heater a storage heater?** A target does nothing until there is stored charge, which
  looks identical to a failed write. See
  [Quantum and other storage heaters](../reference/appliances.md#quantum-and-other-storage-heaters).
- **Are entities `unavailable` rather than wrong?** That is usually an empty cloud overview,
  not a bug. See
  [entities are unavailable](troubleshooting.md#entities-are-unavailable).

## Next

- [Troubleshooting](troubleshooting.md) — symptoms with known causes
- [Appliance support](../reference/appliances.md) — verified, inferred and untested
- [Modes & presets](../use/modes.md) — reading `active_modes`
