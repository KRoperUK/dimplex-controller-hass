"""Keep user-facing exceptions and repairs translatable.

The Gold ``exception-translations`` and ``repair-issues`` rules both require the
key used in code to exist in ``translations/en.json``. A missing key does not
fail at import time — Home Assistant falls back to showing the raw key — so this
test makes the coupling executable.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "dimplex"
TRANSLATIONS = COMPONENT / "translations" / "en.json"

_EXCEPTION_CLASSES = {"HomeAssistantError", "ServiceValidationError"}


def _translations() -> dict[str, dict[str, dict[str, str]]]:
    return json.loads(TRANSLATIONS.read_text(encoding="utf-8"))


def _keyword(node: ast.Call, name: str) -> str | None:
    for keyword in node.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_exception_translation_keys_exist() -> None:
    """Every translated exception raised by the integration has a message."""
    messages = _translations().get("exceptions", {})
    missing: list[str] = []
    for path in sorted(COMPONENT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _called_name(node) not in _EXCEPTION_CLASSES:
                continue
            key = _keyword(node, "translation_key")
            if key and key not in messages:
                missing.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} -> exceptions.{key}")
    assert not missing, "Add these keys to translations/en.json:\n  " + "\n  ".join(missing)


def test_issue_translation_keys_exist() -> None:
    """Every repair issue raised by the integration has a title and description."""
    from custom_components.dimplex.repairs import (
        ISSUE_EMPTY_ENERGY,
        ISSUE_EMPTY_OVERVIEW,
    )

    issues = _translations().get("issues", {})
    missing = [key for key in (ISSUE_EMPTY_ENERGY, ISSUE_EMPTY_OVERVIEW) if key not in issues]
    assert not missing, "Add these keys to translations/en.json:\n  " + "\n  ".join(missing)
