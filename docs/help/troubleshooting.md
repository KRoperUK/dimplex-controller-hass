---
description: Diagnose Dimplex Hub setup failures, unavailable entities, expiring tokens and HACS update oddities in Home Assistant.
---

# Troubleshooting

Find your symptom below, or read the section that matches where it went wrong.

!!! tip "If the heating behaves oddly, check your version first"

    Five separate mode-handling bugs were fixed in **4.1.0**. If you are on 4.0.2 or earlier
    and boost, away or presets do something unexpected, upgrading is very likely the whole
    answer — see [upgrading](upgrading.md).

## Symptom index

| Symptom                                        | Likely cause                                                                                         |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Boost does nothing, or the wrong thing happens | [Boost engages the wrong mode](#boost-does-nothing-or-something-else-happens)                        |
| Away drops the heater to 7 °C                  | [Away engaged frost protection](#away-pins-the-heater-to-7-c)                                        |
| Away will not go above 18 °C                   | [That is the cloud's real limit](#away-will-not-go-above-18-c)                                       |
| Changing the preset appears to do nothing      | [Presets used to stack instead of replace](#changing-the-preset-does-nothing)                        |
| Changing the temperature is rejected           | [Some Quantum heaters refuse remote writes](#changing-the-temperature-is-rejected)                   |
| The heater reports 7 °C after being turned off | [Correct — "off" is frost protection](#the-heater-reports-7-c-after-i-turned-it-off)                 |
| A target on a storage heater had no effect     | [No stored charge to release](#a-target-on-a-storage-heater-did-nothing)                             |
| `preset_mode` disagrees with the mode sensors  | [One preset cannot show several modes](#preset_mode-disagrees-with-the-mode-sensors)                 |
| My timer schedule changed by itself            | [Setpoint writes used to rewrite it](#my-timer-schedule-changed-by-itself)                           |
| Room temperature reads 255 °C                  | [The cloud's "no value" sentinel](#room-temperature-reads-255-c)                                     |
| Energy Dashboard shows far too much energy     | [A window sensor was treated as a meter](#the-energy-dashboard-shows-far-more-than-the-heaters-used) |
| Entities are `unavailable`                     | [Empty cloud overview](#entities-are-unavailable)                                                    |
| Energy sensor `unavailable` in summer          | [Expected](#energy-sensor-shows-unavailable-in-summer)                                               |
| Repeatedly asked to re-authenticate            | [Token refresh](#tokens-keep-expiring)                                                               |
| HACS offers an older version                   | [Pre-release channel](#hacs-shows-an-update-after-installing-a-pre-release)                          |

## Heating behaviour

### Boost does nothing, or something else happens

**Symptom:** You select the `boost` preset or call `dimplex.set_boost`, and the heater either
does nothing visible or brings on the next scheduled period instead.

**Cause:** Releases before 4.1.0 assumed boost was mode bit 16. Bit 16 is **Advance**. The
integration was asking the appliance to advance, which on a scheduled heater looks like
"nothing happened" outside a scheduled window. This was
[#163](https://github.com/kroperuk/dimplex-controller-hass/issues/163).

**Fix:** Upgrade to 4.1.0 or later. Boost is bit 2.

**If you are already on 4.1.0+:** enable the **Boost active** diagnostic sensor and check
whether the appliance reports boost engaged. If it does and the room does not warm, the write
succeeded and the appliance is choosing not to act — likely
[a storage heater with no charge](#a-target-on-a-storage-heater-did-nothing).

### Away pins the heater to 7 °C

**Symptom:** Enabling away drops the target to 7 °C, whatever temperature you asked for.

**Cause:** Before 4.1.0, away was assumed to be mode bit 32. Bit 32 is **FrostProtect**, which
is fixed at 7 °C and ignores any temperature sent with it. Same root cause as above.

**Fix:** Upgrade to 4.1.0 or later, then clear and re-set away once so the appliance leaves
frost protection.

### Away will not go above 18 °C

**Symptom:** You ask for away at 21 °C and get 18 °C, with a warning in the log.

**Cause:** Not a bug. The cloud accepts only **7–18 °C** for away — the official app's away
picker stops at 18 too — and silently reduces anything higher. Rather than let your 21 °C
become 18 °C invisibly, the integration clamps it locally and says so.
[#174](https://github.com/kroperuk/dimplex-controller-hass/issues/174).

**If you want a higher setback:** use a normal setpoint (7–30 °C) on a schedule instead of
away mode.

### Changing the preset does nothing

**Symptom:** You switch from `away` to `eco`, or between any two non-`comfort` presets, and the
entity keeps reporting the old one.

**Cause:** Before 4.1.0 each preset only _added_ its own state without clearing the others.
Selecting `eco` enabled EcoStart but left away engaged, and because the entity resolves away
ahead of EcoStart, it kept reporting `away`.
[#173](https://github.com/kroperuk/dimplex-controller-hass/issues/173).

**Fix:** Upgrade to 4.1.0 or later, where a preset clears the others before engaging its own.

### Changing the temperature is rejected

**Symptom:** `climate.set_temperature` fails, historically as a generic "unknown error" or
HTTP 500.

**Cause:** Some Quantum storage heaters refuse remote setpoint and timer-mode writes with
HTTP 403. Before 4.1.0 the integration only used the schedule-rewrite path, which those units
reject outright. [#149](https://github.com/kroperuk/dimplex-controller-hass/issues/149).

**Fix:** Upgrade. 4.1.0 uses the cloud's dedicated setpoint endpoint first and falls back to
the schedule rewrite only if that is refused. If both are refused you now get a readable error
naming the appliance instead of an opaque failure — that appliance genuinely does not accept
remote setpoint changes, and the official app will not manage it either.

The same wording now covers **every** control, not just the thermostat: switch toggles and all
`dimplex.*` actions used to surface a raw traceback for the identical failure. The message also
distinguishes a refusal, which will never succeed for that appliance, from an unreachable
cloud, which is worth retrying.

### The heater reports 7 °C after I turned it off

**Symptom:** `climate.turn_off` leaves the target at 7 °C rather than blank or off.

**Cause:** Not a bug. Dimplex appliances have **no off mode**. "Off", in the official app and
here, means frost protection: a fixed 7 °C anti-freeze floor. See
[why "off" reports 7 °C](../use/temperature.md#why-off-reports-7-c).

### A target on a storage heater did nothing

**Symptom:** You set 22 °C on a Quantum or other storage heater and nothing happens, with no
error.

**Cause:** Charge-based heaters store heat overnight and release it during the day. With no
stored charge there is nothing to release, so a perfectly successful write has no observable
effect. This is indistinguishable from a failed write unless you check.

**What to do:** Confirm the write landed — the target-temperature sensor should show your
value — and compare against the official app at the same moment. See
[Quantum and other storage heaters](../reference/appliances.md#quantum-and-other-storage-heaters).

### `preset_mode` disagrees with the mode sensors

**Symptom:** **Boost active** and **Away active** are both `on`, but `preset_mode` says
`boost`. Or **Advance active** is `on` and the preset says `comfort`.

**Cause:** Not a bug. The appliance holds a _bitfield_ of modes and several can be engaged at
once; Home Assistant's `preset_mode` is one string and can only show one of them. Advance has
no preset at all.

**What to do:** Trust the diagnostic sensors, and automate on those rather than on
`preset_mode`. See
[why `preset_mode` can disagree with reality](../use/modes.md#why-preset_mode-can-disagree-with-reality).

### My timer schedule changed by itself

**Symptom:** Setting a temperature from Home Assistant altered your weekly programme.

**Cause:** Before 4.1.0, every setpoint write was implemented as a rewrite of the timer
periods — there was no other path.

**Fix:** Upgrade. 4.1.0 writes through `SetApplianceSetpointTemperature`, which leaves the
schedule alone. The rewrite survives only as a fallback for appliances that **refuse** the
dedicated endpoint — HTTP 403, 405 or 501. A timeout or a server error no longer triggers it:
during 4.1.0 development it did, so a single dropped connection while nudging the target could
overwrite every period. When the fallback does run it now logs a warning naming the appliance
and the status, so it is never silent. Repair your programme in the official app once after
upgrading.

### Room temperature reads 255 °C

**Symptom:** The thermostat card shows a current temperature of 255 °C, and history has a spike
to match — while the separate **Room temperature** sensor shows nothing at all.

**Cause:** The cloud reports 0xFF (255) for a temperature field that has no active value. Every
other temperature read filtered it; the climate entity's `current_temperature` was the one that
did not, which is why the sensor and the card disagreed.

**Fix:** Upgrade to 4.1.0. The sentinel now becomes "unknown" on both. Nothing needs repairing
except the recorded history, which you can leave alone or purge for that entity.

### The Energy Dashboard shows far more than the heaters used

**Symptom:** Dimplex consumption on the Energy Dashboard is implausibly high — sometimes a
month of usage appearing repeatedly.

**Cause:** the **Energy lifetime** sensors sum every daily reading the cloud holds for an
appliance, so they rise like a meter. That part is correct. What broke was the _dip_: when the
cloud returned a truncated history the sum fell, and Home Assistant reads a fall of more than
10% on a rising meter as a meter reset — adding the entire total to long-term statistics again
on top of everything already recorded. Routine, because a short read needs no error to happen.

**Fix:** upgrade to **4.1.1**, which holds the highest total seen so the value can no longer
fall, and restores the state class 4.1.0 had removed.

**Then clean up the history**, because statistics do not self-heal:

1. Check **Developer tools** → **Statistics** for the entity.
2. Delete its statistic if the history looks inflated.

The **Energy today** sensors were always correct and need nothing. See
[Energy monitoring](../use/energy.md).

## Setup failures

### The integration cannot connect

**Symptom:** Setup fails with a `CannotConnect` error.

**Possible causes:**

- Your Home Assistant instance has no internet access.
- The GDHV API is temporarily unavailable.
- A firewall or proxy is blocking traffic.

**Steps to resolve:**

1. Confirm your Home Assistant instance can reach the internet.
2. Check the Home Assistant logs (**Settings** > **System** > **Logs**) for details.
3. If behind a proxy, ensure `aiohttp` traffic is allowed.

### Invalid credentials

**Symptom:** Setup fails with `InvalidAuth`.

**Possible causes:**

- Incorrect email or password.
- The auth code has expired.
- The Dimplex account has MFA enabled and the code was not generated correctly.

**Steps to resolve:**

1. If using email/password, verify your credentials in the official Dimplex Control app.
2. If using a manual auth code, capture a fresh one (codes expire quickly).
3. If MFA is enabled, complete the MFA challenge in the browser before copying the redirect URL.
4. Re-run the config flow or re-authenticate from **Settings** > **Devices & Services**.

### Setup fails silently

**Symptom:** The integration does not appear after adding it.

**Steps to resolve:**

1. Restart Home Assistant.
2. Check the logs for tracebacks related to `custom_components.dimplex`.
3. Verify that the `custom_components/dimplex` folder is present in your configuration directory and contains all required files.

## Runtime issues

### Entities are unavailable

**Symptom:** Entities show as `unavailable` in Home Assistant.

**Possible causes:**

- The integration cannot reach the Dimplex cloud.
- Tokens have expired and re-authentication is required.
- Your Dimplex Hub is offline.

**Steps to resolve:**

1. Check **Settings** > **System** > **Logs** for `DimplexConnectionError` or `DimplexAuthError`.
2. If you see `DimplexAuthError`, re-authenticate from **Devices & Services**.
3. If you see `DimplexConnectionError`, verify internet connectivity from your Home Assistant instance.
4. Confirm your Hub is online in the official Dimplex Control app.

### Tokens keep expiring

**Symptom:** You are repeatedly asked to re-authenticate.

**Possible causes:**

- Refresh tokens have expired (Azure B2C refresh tokens typically last 90 days).
- Network interruptions prevent token refresh.

**Steps to resolve:**

1. Use the **Email / password** method — it handles token refresh more reliably.
2. Ensure Home Assistant has consistent internet access.
3. If tokens expire immediately, delete the integration, restart Home Assistant, and add it again.

### Energy sensor shows `unavailable` in summer

This is expected behaviour. See [Energy monitoring](../use/energy.md#behaviour-worth-knowing).

Metered appliances only report energy data when they are actively consuming power. During warmer months, when heating is not running, the sensor is correctly reported as `unavailable` rather than `0`.

## HACS issues

### The integration does not appear in HACS

**Possible causes:**

- You have not added the custom repository in HACS.
- The repository URL is incorrect.

**Steps to resolve:**

1. In HACS, go to **Integrations** > **Explore & Add repositories**.
2. Search for `dimplex-controller-hass` or add the URL directly: `https://github.com/kroperuk/dimplex-controller-hass`.
3. Download and restart Home Assistant.

### HACS reports an update but the update fails

**Steps to resolve:**

1. Check the Home Assistant logs for file permission errors.
2. Ensure Home Assistant has write access to the `custom_components` directory.
3. Restart Home Assistant after the update completes.

### HACS shows an update after installing a pre-release

**Symptom:** You installed a development build (for example `3.0.0-rc.2` or a PR pre-release). HACS or the Home Assistant update entity still shows an “update” to an older **stable** tag (for example `v2.0.0`), sometimes with restart-required messaging.

**What is going on:**

- **Stable** installs use exact tags like `vX.Y.Z` (release-please).
- **Main release candidates** use semver pre-release tags `vX.Y.Z-rc.N` with matching `manifest.json` / `const.VERSION` (`X.Y.Z-rc.N`).
- **PR builds** use `vX.Y.Z-pr.P.R` with version `X.Y.Z-pr.P.<shortsha>`.
- Pre-release versions sort **above** the previous stable and **below** the final `X.Y.Z`.

**Steps to resolve:**

1. If you want the pre-release: enable **pre-releases / beta** for this repository in HACS so “latest” tracks newer RCs instead of only stable. The update entity should not demand a downgrade to an older stable when comparison is correct.
2. If you want production stability: reinstall the latest **stable** release from HACS (or [GitHub Releases](https://github.com/kroperuk/dimplex-controller-hass/releases)) and disable pre-releases.
3. When the real `vX.Y.Z` ships, updating from `X.Y.Z-rc.N` to stable is expected and correct.
4. PR pre-releases may be deleted when the PR closes; do not rely on them long-term.

Prefer tagged pre-releases (`vX.Y.Z-rc.N`) from [GitHub Releases](https://github.com/kroperuk/dimplex-controller-hass/releases) or HACS when dogfooding.

## Repairs

Home Assistant surfaces some conditions under **Settings** → **System** → **Repairs** rather
than in the log:

| Repair                    | Meaning                             | Actionable                               |
| ------------------------- | ----------------------------------- | ---------------------------------------- |
| Reauthentication required | Tokens rejected                     | Yes — opens the reauth flow              |
| Energy polls empty        | Polls succeed but return no points  | No — normal for idle or seasonal heaters |
| Appliance overview empty  | Hubs exist but report no appliances | No — usually stale telemetry             |

The two informational ones can be dismissed. If either persists through a heating season,
that is worth reporting.

## Log analysis

### Where to find logs

1. Go to **Settings** > **System** > **Logs**.
2. Filter for `dimplex` to see integration-specific entries.

### Common log messages

| Log message                      | Meaning                           | Action                              |
| -------------------------------- | --------------------------------- | ----------------------------------- |
| `DimplexAuthError`               | Token expired or invalid.         | Re-authenticate.                    |
| `DimplexConnectionError`         | Cannot reach the API.             | Check network.                      |
| `CannotConnect`                  | HA wrapper for connection errors. | Check network and API status.       |
| `InvalidAuth`                    | HA wrapper for auth errors.       | Re-authenticate.                    |
| `Energy report returned no data` | No metered data for the window.   | Normal in summer; no action needed. |

## Still stuck?

First read [diagnostics & bug reports](diagnostics.md) — attaching a diagnostics download
is the single fastest route to an answer, because it decodes the appliance's engaged modes by
name.

Then [open a GitHub issue](https://github.com/kroperuk/dimplex-controller-hass/issues) with:

1. Your Home Assistant version.
2. The integration version (found in `manifest.json` or HACS).
3. The relevant log entries (redact any personal information such as email addresses).
4. Steps to reproduce the problem.
5. Whether the issue happens consistently or intermittently.

The more detail you provide, the faster we can help.
