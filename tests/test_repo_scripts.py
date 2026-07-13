"""Tests for repo maintenance scripts in scripts/.

These tests do not exercise any integration code, so when this file is run
on its own (`pytest tests/test_repo_scripts.py`) the project's 80% coverage
gate will fail with a misleading 0% report. Always run via the full suite
(`pytest tests/`) in CI and locally, or pass `--no-cov` explicitly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import custom_components.dimplex  # noqa: F401  (see module docstring)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_check_ruff_pin_passes() -> None:
    """The pinned ruff version in requirements_test.txt must match .pre-commit-config.yaml."""
    result = _run("check-ruff-pin.sh")
    assert result.returncode == 0, f"ruff pin drift:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "consistent" in result.stdout


def test_check_translation_parity_runs() -> None:
    """Parity script must run and either pass or fail with a clear message.

    The dev tree may legitimately have parity drift (e.g. when adding a new
    translation key in en.json before back-porting it). The test asserts the
    script runs cleanly (exit 0 or 1, well-formed output) rather than
    crashing. Concrete parity enforcement is the CI step's job.
    """
    result = _run("check-translation-parity.sh")
    assert result.returncode in (0, 1), (
        f"unexpected exit code {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # The script should always print a per-language line that starts with ✓ or ✗.
    assert any(line.startswith(("✓", "✗")) for line in result.stdout.splitlines()), (
        f"no per-language status line in output:\n{result.stdout}"
    )


@pytest.mark.parametrize("script", ["check-ruff-pin.sh", "check-translation-parity.sh"])
def test_scripts_are_executable(script: str) -> None:
    """Maintenance scripts must have the executable bit set so CI can run them."""
    path = REPO_ROOT / "scripts" / script
    assert path.exists(), f"missing {path}"
    assert path.stat().st_mode & 0o111, f"{path} is not executable"
