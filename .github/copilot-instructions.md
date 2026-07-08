# GitHub Copilot instructions

This repo is a **Home Assistant custom integration** that controls Dimplex heating
appliances via their cloud API (the `dimplex-controller` library). Code lives in
`custom_components/dimplex/`.

## Module map

- `__init__.py` — coordinator + API client setup, platform forwarding.
- `api.py` — `DimplexApiClient` wrapper around `dimplex-controller`.
- `entity.py` — `DimplexEntity` base (device_info, unique_id, status lookup).
- `sensor.py` / `binary_sensor.py` / `switch.py` — Room Temperature / Comfort / EcoStart.
- `config_flow.py` — UI setup flow.
- `const.py` — domain, config keys, platforms, update interval.

The coordinator snapshot is `coordinator.data["appliances"]` — a list of
`{hub, zone, appliance, status}` rows; entities match on `ApplianceId`.

## Must-follow rules

1. **Conventional Commits** for PR titles and all commit messages — `release-please` drives
   versioning/changelog (`fix:` → patch, `feat:` → minor). Every PR title and commit on a feature branch must follow this format, and this is enforced in CI.
2. **Add/update tests** for any behaviour change (`pytest-homeassistant-custom-component`).
3. **`main` is protected** — work on a branch and open a PR. CI runs conventional commit validation,
   ruff (lint + format via pre-commit), pytest with coverage, and HACS/Hassfest.
4. Keep coverage at or above the `fail_under` threshold in `pyproject.toml`.

## Local checks (match CI)

```bash
ruff check .
ruff format --check .
pytest
```

Style: Python 3.13, ruff line length 88, all config in `pyproject.toml`. See
`CLAUDE.md` for the full guide.
