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
    # The official app's mode carousels (away / boost / frost / manual / eco)
    # all offer 7-30 °C, and frost protection is always the 7 °C floor.
    min_temp: float = 7.0
    max_temp: float = 30.0
    frost_temp: float = 7.0

    def climate_presets(self) -> list[str]:
        presets = ["comfort"]
        if self.boost:
            presets.append("boost")
        if self.away:
            presets.append("away")
        if self.eco_start:
            presets.append("eco")
        return presets


def _positive_float(value: Any, default: float) -> float:
    """Coerce a capability temperature, falling back when it is unusable."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


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
                min_temp=_positive_float(getattr(caps, "min_temp", None), 7.0),
                max_temp=_positive_float(getattr(caps, "max_temp", None), 30.0),
                frost_temp=_positive_float(getattr(caps, "frost_temp", None), 7.0),
            )
        except Exception:
            pass

    tokens = " ".join(
        str(getattr(appliance, attr, "") or "") for attr in ("ApplianceType", "ApplianceModel", "FriendlyName")
    ).lower()
    climate = not any(k in tokens for k in ("hot water", "hotwater", "cylinder", "dhw"))
    return LocalCapabilities(climate=climate)
