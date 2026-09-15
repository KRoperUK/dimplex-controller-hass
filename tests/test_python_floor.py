"""Guard the Python syntax floor implied by the declared Home Assistant floor.

The development environment runs a much newer Python than the oldest Home
Assistant release this integration claims to support, and tooling happily
rewrites source to suit the newer one. ruff 0.16 will unparenthesise
``except (TypeError, ValueError)`` per PEP 758 when ``target-version`` allows
it — valid on 3.14, a ``SyntaxError`` on 3.12 and 3.13. Nothing in CI would
notice: lint, mypy and pytest all run on the new interpreter, so the first
sign would be users on an older HA seeing the integration fail to load.

These tests make the coupling executable, so raising one end without the
other fails here rather than in someone's log.

Like tests/test_repo_scripts.py this file exercises no integration code, so
run it via the full suite rather than on its own (see that module's docstring).
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path

import pytest

import custom_components.dimplex  # noqa: F401  (see module docstring)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "dimplex"

# Minimum Python for each Home Assistant floor we have actually verified.
# 2026.9.0 and 2026.8.0 both declare ``Requires-Python >=3.14.2`` on PyPI.
# 2025.1.0 is kept because it was the previous floor and documents the boundary
# that made this test necessary: it was the last HA release running on Python
# 3.12, and 2025.2 raised the requirement to 3.13. Extend this deliberately — a
# wrong entry here re-opens exactly the hole the module docstring describes.
HA_FLOOR_TO_PYTHON: dict[str, tuple[int, int]] = {
    "2025.1.0": (3, 12),
    "2026.8.0": (3, 14),
    "2026.9.0": (3, 14),
}


def _ha_floor() -> str:
    hacs = json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))
    return str(hacs["homeassistant"])


def _minimum_python() -> tuple[int, int]:
    floor = _ha_floor()
    if floor not in HA_FLOOR_TO_PYTHON:
        pytest.fail(
            f"hacs.json now declares Home Assistant {floor}, which this test has no "
            "verified minimum Python for. Look up that release's Requires-Python, add "
            "it to HA_FLOOR_TO_PYTHON, and update [tool.ruff] target-version to match."
        )
    return HA_FLOOR_TO_PYTHON[floor]


def test_ruff_target_version_is_not_newer_than_ha_floor() -> None:
    """ruff must never format for a newer Python than our declared HA floor runs on.

    Equality is not required. Targeting *older* than the floor only forgoes some
    pyupgrade rewrites, and pyproject.toml explains why py312 is kept
    deliberately; targeting *newer* is the bug this guards, because the formatter
    then emits syntax the oldest supported Home Assistant cannot parse.
    """
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    target = pyproject["tool"]["ruff"]["target-version"]
    match = re.fullmatch(r"py(\d)(\d+)", target)
    assert match, f"unrecognised [tool.ruff] target-version {target!r}"
    target_version = (int(match.group(1)), int(match.group(2)))
    floor_version = _minimum_python()
    assert target_version <= floor_version, (
        f"[tool.ruff] target-version is {target} (Python {target_version[0]}.{target_version[1]}) but "
        f"hacs.json declares Home Assistant {_ha_floor()}, which runs on Python "
        f"{floor_version[0]}.{floor_version[1]}. Raise the hacs.json floor first if newer "
        "syntax is genuinely wanted."
    )


def test_component_parses_on_minimum_python() -> None:
    """Every shipped module must be valid syntax on the oldest supported Python."""
    feature_version = _minimum_python()
    sources = sorted(COMPONENT.rglob("*.py"))
    assert sources, "no component sources found — has the layout changed?"
    for path in sources:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path), feature_version=feature_version)
        except SyntaxError as err:  # pragma: no cover - only on real drift
            major, minor = feature_version
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)}:{err.lineno} is not valid Python "
                f"{major}.{minor}: {err.msg}. Home Assistant {_ha_floor()} could not "
                "load this."
            )
