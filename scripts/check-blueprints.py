#!/usr/bin/env python3
"""Validate the shipped automation blueprints against Home Assistant's own schema.

Blueprints are user-facing artefacts that nothing in CI previously looked at, so a
typo would have shipped and only failed when somebody tried to import it.

Two levels of checking, both using Home Assistant's real validators rather than a
hand-written approximation:

1. ``BLUEPRINT_SCHEMA`` — the blueprint metadata, inputs and selectors.
2. ``automation.config.PLATFORM_SCHEMA`` — the automation that results once the
   inputs are substituted. This is the check that catches a malformed trigger or
   action, which the blueprint schema alone does not look inside.

Note that Home Assistant normalises the legacy ``trigger:`` / ``condition:`` /
``action:`` keys to their modern plural forms during validation, so this script
will not object to the old syntax. It is checking validity, not style.

Usage: python3 scripts/check-blueprints.py
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

from homeassistant.components.automation import config as automation_config
from homeassistant.components.blueprint import models, schemas
from homeassistant.util.yaml import loader

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUEPRINT_DIR = REPO_ROOT / "blueprints"

# Stand-in values for every input the shipped blueprints declare. A new input
# needs an entry here, which is deliberate: it forces a moment's thought about
# what a caller is expected to pass.
SAMPLE_INPUTS: dict[str, Any] = {
    "after": "06:00:00",
    "before": "22:00:00",
    "climate_entity": "climate.test",
    "message": "test message",
    "notify_service": "notify.persistent_notification",
    "open_window_entity": "binary_sensor.test_open_window",
    "presence_entity": "person.test",
    "temperature_sensor": "sensor.test_room_temperature",
    "threshold": 17,
    "title": "test title",
}


def check(path: pathlib.Path) -> list[str]:
    """Return a list of problems with one blueprint file."""
    # Imported here rather than at module scope: Home Assistant swaps in its own
    # voluptuous at import time and warns if anything got there first, and import
    # sorting would otherwise hoist this above the homeassistant imports.
    import voluptuous as vol

    rel = path.relative_to(REPO_ROOT)
    problems: list[str] = []

    try:
        raw = loader.load_yaml(str(path))
    except Exception as err:  # noqa: BLE001 - report, do not crash the run
        return [f"::error file={rel}::could not parse YAML: {err}"]

    if not isinstance(raw, dict):
        return [f"::error file={rel}::expected a YAML mapping at the top level, got {type(raw).__name__}"]

    try:
        blueprint = models.Blueprint(raw, expected_domain="automation", schema=schemas.BLUEPRINT_SCHEMA)
    except Exception as err:  # noqa: BLE001
        return [f"::error file={rel}::invalid blueprint: {err}"]

    missing = sorted(set(blueprint.inputs) - set(SAMPLE_INPUTS))
    if missing:
        problems.append(
            f"::error file={rel}::no sample value for input(s) {', '.join(missing)} — "
            f"add them to SAMPLE_INPUTS in {pathlib.Path(__file__).name}"
        )
        return problems

    supplied = {k: v for k, v in SAMPLE_INPUTS.items() if k in blueprint.inputs}
    try:
        substituted = models.BlueprintInputs(
            blueprint, {"use_blueprint": {"path": path.name, "input": supplied}}
        ).async_substitute()
    except Exception as err:  # noqa: BLE001
        return [f"::error file={rel}::could not substitute inputs: {err}"]

    try:
        automation_config.PLATFORM_SCHEMA(substituted)
    except vol.Invalid as err:
        problems.append(f"::error file={rel}::substituted automation is invalid: {err}")

    return problems


def main() -> int:
    if not BLUEPRINT_DIR.is_dir():
        print(f"::error::no blueprints directory at {BLUEPRINT_DIR}")
        return 1

    files = sorted(BLUEPRINT_DIR.rglob("*.yaml"))
    if not files:
        print(f"::error::found no blueprints under {BLUEPRINT_DIR}")
        return 1

    failed = 0
    for path in files:
        problems = check(path)
        if problems:
            failed += 1
            for line in problems:
                print(line)
        else:
            print(f"✓ {path.relative_to(REPO_ROOT)}")

    if failed:
        print(f"\n{failed} of {len(files)} blueprint(s) failed validation.", file=sys.stderr)
        return 1

    print(f"\n✓ {len(files)} blueprint(s) valid against Home Assistant {_ha_version()}")
    return 0


def _ha_version() -> str:
    try:
        from homeassistant.const import __version__

        return __version__
    except Exception:  # noqa: BLE001
        return "(unknown version)"


if __name__ == "__main__":
    sys.exit(main())
