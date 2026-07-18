#!/usr/bin/env python3
"""Canonicalise custom_components/*/manifest.json for release-please + pre-commit.

release-please's JSON updater rewrites manifests with ``json.dumps(..., indent=2)``
(multi-line arrays). Prettier prefers compact single-line arrays for short lists,
so if both tools touch the file they thrash each other on every release PR.

This script is the single formatter for HA manifests:
- keys: domain, name, then alphabetical (hassfest order)
- body: indent=2, trailing newline (same shape release-please emits)

Prettier deliberately ignores these files (see .prettierignore).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def format_manifest(path: Path) -> bool:
    """Rewrite *path* in canonical form. Returns True if the file changed."""
    original = path.read_text(encoding="utf-8")
    data = json.loads(original)

    ordered: dict = {}
    for key in ("domain", "name"):
        if key in data:
            ordered[key] = data.pop(key)
    for key in sorted(data):
        ordered[key] = data[key]

    new = json.dumps(ordered, indent=2) + "\n"
    if new == original:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv[1:]]
    if not paths:
        paths = sorted(Path("custom_components").glob("*/manifest.json"))

    changed = False
    for path in paths:
        if not path.is_file():
            print(f"{path}: not found", file=sys.stderr)
            return 1
        if format_manifest(path):
            print(f"reformatted {path}")
            changed = True

    # pre-commit treats a non-zero exit as "hook modified files / failed"
    # only when the hook is configured as a fixer that leaves dirty trees;
    # return 1 if we rewrote so the user re-stages (same as prettier).
    return 1 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
