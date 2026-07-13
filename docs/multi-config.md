# Multi-account / multi-config-entry support

## Current topology

- The integration **allows multiple config entries** (there is no hard `async_set_unique_id` single-instance abort in the flow today).
- Each entry is a separate cloud session (tokens stored on that entry).
- Coordinators, entities, and unique IDs are **scoped by `config_entry.entry_id`**, so two accounts do not collide in the entity registry.

## Recommended use

| Scenario                           | Supported?  | Notes                                         |
| ---------------------------------- | ----------- | --------------------------------------------- |
| One home, one Dimplex account      | Yes         | Default                                       |
| Second home / second cloud account | Yes         | Add another config entry; use distinct titles |
| Same account twice                 | Discouraged | Duplicate devices; no benefit                 |

## Future options

If product needs strict single-instance, we can set a unique id from cloud user id (`GetUserContext`) and abort duplicates. Until then, multi-entry remains available for power users and test accounts.

Tracked by issue #101.
