# Plan: Migrate Cookie-Cutter Integration to `dimplex-controller`

## Goal
Refactor this Home Assistant custom integration scaffold so all device communication is driven by the new PyPI package `dimplex-controller`, while preserving Home Assistant best practices, config flow UX, and test coverage.

## Assumptions
- PyPI package: `dimplex-controller`
- Import path likely: `dimplex_controller` (confirm from package docs/source)
- Integration domain remains `dimplex`
- Current repo already has entity models for switches/sensors/binary sensors that map to Dimplex capabilities

## Phase 1 — Dependency and API surface alignment
1. Add runtime dependency in `custom_components/dimplex/manifest.json`:
   - Add `requirements` entry for `dimplex-controller` (pin minimally to `dimplex-controller>=0.2.0`)
2. Remove/replace any legacy direct HTTP/session code in `custom_components/dimplex/api.py` with a thin adapter around `dimplex_controller`.
3. Define a single internal client wrapper (still in `api.py` or a new `client.py`) that:
   - Handles auth/session creation
   - Exposes typed, HA-friendly methods for fetch/update
   - Normalizes library exceptions into integration-specific exceptions
4. Keep Home Assistant layer free from low-level transport details.

## Phase 2 — Config flow and setup lifecycle
1. Update `custom_components/dimplex/config_flow.py` to validate credentials/host by making a real lightweight call through the new wrapper.
2. Ensure errors map cleanly to HA config flow reasons (`cannot_connect`, `invalid_auth`, `unknown`).
3. Update `custom_components/dimplex/__init__.py` setup:
   - Create and store one client/coordinator per config entry in `hass.data[DOMAIN][entry_id]`
   - Ensure proper unload and cleanup semantics.
4. If package supports async natively, use async path; otherwise wrap sync calls with `hass.async_add_executor_job`.

## Phase 3 — Entity model wiring
1. Update entity base in `custom_components/dimplex/entity.py` to read from a centralized coordinator/client state object.
2. Update platform files:
   - `custom_components/dimplex/switch.py`
   - `custom_components/dimplex/sensor.py`
   - `custom_components/dimplex/binary_sensor.py`
3. Replace any hardcoded old API field names with values provided by `dimplex-controller` models.
4. Ensure stable `unique_id` strategy based on device identity from the library.
5. Ensure optimistic state updates only where safe; otherwise request refresh after writes.

## Phase 4 — Constants, translations, metadata
1. Update `custom_components/dimplex/const.py` with:
   - Coordinator update interval
   - Shared config keys and default values
   - Any mapped error constants
2. Update translations:
   - `custom_components/dimplex/translations/en.json`
   - `custom_components/dimplex/translations/fr.json`
   - `custom_components/dimplex/translations/nb.json`
3. Ensure `README.md` setup instructions match new dependency behavior and config flow fields.
4. Confirm `hacs.json` and `info.md` still match supported versions and integration metadata.

## Phase 5 — Testing strategy and CI hardening
1. Update/add unit tests for client adapter behavior:
   - `tests/test_api.py`
   - Mock `dimplex_controller` client classes and exceptions
2. Update config flow tests:
   - `tests/test_config_flow.py`
   - Cover success, invalid auth, cannot connect, unknown error
3. Update setup/unload tests:
   - `tests/test_init.py`
4. Update entity tests:
   - `tests/test_switch.py` and add sensor/binary tests if needed
   - Validate state mapping from package models to HA entities
5. Keep tests deterministic by mocking network and time.
6. Ensure GitHub workflow `.github/workflows/tests.yaml` installs the new dependency path consistently.

## Phase 6 — Incremental implementation order
1. Dependency + adapter skeleton
2. Config flow validation via adapter
3. Setup lifecycle + coordinator
4. Switch platform migration (first vertical slice)
5. Sensor/binary migration
6. Tests and CI fixes
7. Docs and translations polish

## Definition of done
- Integration runs using `dimplex-controller` only for device communication
- Config flow works end-to-end with clear user errors
- All entities populate and control correctly
- Test suite passes locally and in CI
- Documentation reflects real setup and troubleshooting flow

## Practical notes for refinement
- Confirm exact import names and exception types from `dimplex-controller`
- Decide minimum supported package version and pin policy
- Decide polling vs push based on package capability
- If package returns rich models, prefer mapping helpers over in-entity parsing
