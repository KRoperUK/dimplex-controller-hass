"""Local appliance capability helpers (mirrors library matrix when available)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_lib_capabilities_for: Callable[..., Any] | None = None
try:
    import dimplex_controller as _dc

    _lib_capabilities_for = getattr(_dc, "capabilities_for", None)
except Exception:  # pragma: no cover - older library floor without capabilities
    _lib_capabilities_for = None


@dataclass(frozen=True)
class LocalCapabilities:
    boost: bool = True
    away: bool = True
    eco_start: bool = True
    open_window: bool = True
    climate: bool = True
    default_boost_minutes: int = 60
    boost_durations: tuple[int, ...] = (30, 60, 120, 180)

    def climate_presets(self) -> list[str]:
        presets = ["comfort"]
        if self.boost:
            presets.append("boost")
        if self.away:
            presets.append("away")
        if self.eco_start:
            presets.append("eco")
        return presets


def capabilities_for_row(appliance: Any, status: Any = None) -> LocalCapabilities:
    """Derive capability flags for an appliance row."""
    if _lib_capabilities_for is not None:
        try:
            caps = _lib_capabilities_for(appliance, status=status)
            return LocalCapabilities(
                boost=bool(getattr(caps, "boost", True)),
                away=bool(getattr(caps, "away", True)),
                eco_start=bool(getattr(caps, "eco_start", True)),
                open_window=bool(getattr(caps, "open_window", True)),
                climate=bool(getattr(caps, "climate", True)),
                default_boost_minutes=int(getattr(caps, "default_boost_minutes", 60)),
                boost_durations=tuple(getattr(caps, "boost_durations", (30, 60, 120, 180))),
            )
        except Exception:
            pass

    tokens = " ".join(
        str(getattr(appliance, attr, "") or "") for attr in ("ApplianceType", "ApplianceModel", "FriendlyName")
    ).lower()
    climate = not any(k in tokens for k in ("hot water", "hotwater", "cylinder", "dhw"))
    return LocalCapabilities(climate=climate)
