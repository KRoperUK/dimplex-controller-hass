"""Guard against importing Home Assistant platform internals.

Home Assistant's supported import surface for a platform's enums is the platform
package itself: ``homeassistant.components.binary_sensor`` re-exports
``BinarySensorDeviceClass``. The ``homeassistant.components.<platform>.const``
submodules are implementation details, and they do not all exist on every
release we claim to support — ``binary_sensor/const.py`` first appeared in
2026.10, while ``hacs.json`` declares a 2026.9.0 floor. An import from it
therefore passes every CI check (pinned to 2026.10.3) and fails in a user's log
at startup with ``ModuleNotFoundError: No module named
'homeassistant.components.binary_sensor.const'``.

Like ``tests/test_python_floor.py``, this makes the coupling executable: the
fix for a failure here is always to import from the platform package root.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT = REPO_ROOT / "custom_components" / "dimplex"

# ``homeassistant.const`` is core's public module and deliberately not matched.
_PLATFORM_INTERNALS = re.compile(r"^homeassistant\.components\.[^.]+\.const$")


def _platform_internal_imports(path: Path) -> list[str]:
    """Return a description of every platform-``const`` import in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _PLATFORM_INTERNALS.match(node.module):
            found.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} imports {node.module}")
        elif isinstance(node, ast.Import):
            found.extend(
                f"{path.relative_to(REPO_ROOT)}:{node.lineno} imports {alias.name}"
                for alias in node.names
                if _PLATFORM_INTERNALS.match(alias.name)
            )
    return found


def test_no_platform_const_submodule_imports() -> None:
    """Component modules must import platform enums from the package root.

    The ``.const`` submodules are private and version-dependent, so importing
    from them can pass CI and still break on a Home Assistant release inside our
    declared support range.
    """
    sources = sorted(COMPONENT.rglob("*.py"))
    assert sources, "no component sources found — has the layout changed?"
    offenders = [issue for path in sources for issue in _platform_internal_imports(path)]
    assert not offenders, (
        "Import platform enums from the platform package root, not its private `.const` "
        "submodule — the submodule does not exist on every supported Home Assistant "
        "release:\n  " + "\n  ".join(offenders)
    )
