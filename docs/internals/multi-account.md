---
description: Running more than one Dimplex cloud account against a single Home Assistant instance with multiple Dimplex Hub config entries.
---

# Multi-account

## What is supported

The integration allows **multiple config entries**. There is no single-instance abort in the
config flow, so you can add it as many times as you have accounts.

- Each entry is its own cloud session, with its own tokens stored on that entry.
- Coordinators, entities and unique IDs are scoped by `config_entry.entry_id`, so two
  accounts cannot collide in the entity registry.
- Each entry appears as a separate **Dimplex Hub** card under **Devices & services**. Give
  them distinct titles.

| Scenario                           | Supported   | Notes                                  |
| ---------------------------------- | ----------- | -------------------------------------- |
| One home, one account              | Yes         | The default                            |
| Second home / second cloud account | Yes         | Add another entry, use distinct titles |
| Same account twice                 | Discouraged | Duplicate devices, no benefit          |

## Adding a second account

Repeat the normal flow: **Settings** → **Devices & services** → **+ Add integration** →
**Dimplex Hub**, and sign in with the other account. See
[connect your account](../start/connect.md).

Options — platform toggles and poll intervals — are per entry, so a test account can poll
slowly without slowing your real one.

## Why it is not locked to one entry

Strict single-instance would be easy to add: take a unique ID from the cloud user ID via
`GetUserContext` and abort duplicates. It has not been done because multi-entry is genuinely
useful for second homes and for testing against a throwaway account.

This was tracked by
[#101](https://github.com/kroperuk/dimplex-controller-hass/issues/101), now closed —
multi-entry is settled behaviour, not a pending decision.
