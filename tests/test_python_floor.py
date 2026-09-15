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
import tomllib
from pathlib import Path

import pytest

import custom_components.dimplex  # noqa: F401  (see module docstring)

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "dimplex"

# Minimum Python for each Home Assistant floor we have actually verified.
# 2025.1.0 is the last HA release that ran on Python 3.12 (its sdist declares
# ``Requires-Python >=3.12``); 2025.2 raised the requirement to 3.13. Extend
# this deliberately — a wrong entry here re-opens exactly the hole the module
# docstring describes.
HA_FLOOR_TO_PYTHON: dict[str, tuple[int, int]] = {
    "2025.1.0": (3, 12),
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


def test_ruff_target_version_matches_ha_floor() -> None:
    """ruff must format for the oldest Python our declared HA floor runs on."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    target = pyproject["tool"]["ruff"]["target-version"]
    major, minor = _minimum_python()
    expected = f"py{major}{minor}"
    assert target == expected, (
        f"[tool.ruff] target-version is {target} but hacs.json declares Home Assistant "
        f"{_ha_floor()}, which runs on Python {major}.{minor} ({expected}). Raise the "
        "hacs.json floor first if newer syntax is genuinely wanted."
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
