# CLAUDE.md

Guidance for AI coding agents (Claude Code, etc.) working in this repository.

## What this is

A **Home Assistant custom integration** (`custom_components/dimplex`) that controls
Dimplex heating appliances via their cloud API, using the
[`dimplex-controller`](https://pypi.org/project/dimplex-controller/) library.
Distributed via HACS; `iot_class` is cloud polling.

## Architecture

| File               | Responsibility                                                                                                    |
| ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `__init__.py`      | Sets up the `DataUpdateCoordinator`, the API client, and forwards platforms.                                      |
| `api.py`           | `DimplexApiClient` wrapper around the `dimplex-controller` library (auth, fetching hubs/zones/appliances/status). |
| `entity.py`        | `DimplexEntity` base — shared `device_info`, `unique_id`, and per-appliance status lookup.                        |
| `sensor.py`        | Room temperature sensor (`temperature` device class).                                                             |
| `binary_sensor.py` | Comfort status (`mdi:sofa` / `mdi:sofa-outline`).                                                                 |
| `switch.py`        | EcoStart toggle (`mdi:leaf` / `mdi:leaf-off`).                                                                    |
| `config_flow.py`   | UI setup flow.                                                                                                    |
| `const.py`         | Domain, config keys, platforms, update interval.                                                                  |

The coordinator stores a snapshot under `coordinator.data["appliances"]`, a list of
rows `{hub, zone, appliance, status}`. Entities resolve their current value by
matching `ApplianceId` in that list (see `DimplexEntity._status`).

## Commands

```bash
# Environment (uv recommended; any Py3.13 venv works)
uv venv --python 3.13 .venv
uv pip install --python .venv -r requirements_test.txt

# Lint, format, test (mirror CI)
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest tests/
```

Coverage threshold (`fail_under`) lives in `pyproject.toml`; keep it green.

## Conventions

- **Python 3.13**, **ruff** for lint + format (line length 88). All config is in
  `pyproject.toml`. Pre-commit also runs prettier (YAML/JSON/MD) and a manifest
  key-order check.
- **Conventional Commits** for commits and PR titles — `release-please` builds the
  changelog and version bumps from them (`fix:` → patch, `feat:` → minor).
- Every behaviour change needs tests (`pytest-homeassistant-custom-component`).
  Tests build a fake coordinator payload — see `tests/`.

## Workflow / repo rules

- **`main` is protected**: open a feature branch and a PR; do not push to `main`.
  Required checks: `Pre-commit`, `Run tests`, `HACS`, `Hassfest`. Re-apply rules
  with `scripts/setup-branch-protection.sh`.
- Releases are automated by `release-please` (a release PR is opened and tags on
  merge). Dependabot PRs (minor/patch) auto-merge once CI passes.
