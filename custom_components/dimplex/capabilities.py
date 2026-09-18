"""Local appliance capability helpers (mirrors library matrix when available)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

_lib_capabilities_for: Callable[..., Any] | None = None
try:
    import dimplex_controller as _dc

    _lib_capabilities_for = getattr(_dc, "capabilities_for", None)
except Exception:  # pragma: no cover - older library floor without capabilities
    _lib_capabilities_for = None

# Every flag the library's capability matrix carries. Kept in one place so the
# pass-through below cannot silently drop a field again: this module used to copy
# 10 of the library's 22, which is how an appliance the library marked
# ``setpoint_write=False`` still got a setpoint write, and how ``hot_water`` /
# ``heat_pump`` / ``hygiene`` were unreachable (#199).
_BOOL_FIELDS: tuple[str, ...] = (
    "boost",
    "away",
    "advance",
    "open_window",
    "eco_start",
    "setback_read",
    "setback_write",
    "frost",
    "timer",
    "setpoint_write",
    "energy_meter",
    "storage",
    "hot_water",
    "heat_pump",
    "hygiene",
    "climate",
)

# Defaults for the fields that are not "enabled unless told otherwise". A
# cylinder-only appliance is not room climate, and the four derived families are
# opt-in so a guess never invents support.
_BOOL_DEFAULTS: dict[str, bool] = {
    "energy_meter": False,
    "storage": False,
    "hot_water": False,
    "heat_pump": False,
    "hygiene": False,
}


@dataclass(frozen=True)
class LocalCapabilities:
    """Full-fidelity mirror of the library's capability matrix.

    The field set and defaults match ``dimplex_controller.ApplianceCapabilities``
    so callers can gate on any of them without this module narrowing the answer.
    ``climate`` is the one cross-cutting flag: an appliance the library says is not
    room climate gets no thermostat.
    """

    boost: bool = True
    away: bool = True
    advance: bool = True
    open_window: bool = True
    eco_start: bool = True
    setback_read: bool = True
    setback_write: bool = True  # POST /RemoteControl/SetSetbackTemperature
    frost: bool = True  # ApplianceModeFlag.FROST_PROTECT (the app's "off")
    timer: bool = True
    setpoint_write: bool = True  # POST /RemoteControl/SetApplianceSetpointTemperature
    energy_meter: bool = False
    storage: bool = False
    hot_water: bool = False
    heat_pump: bool = False
    hygiene: bool = False
    climate: bool = True
    # Boost, frost, manual and eco carousels in the official app offer 7-30 °C,
    # and frost protection is always the 7 °C floor. Away is the exception at
    # 7-18 °C — see AWAY_TEMP_MIN/MAX in const.py, and dimplex-controller-py#98
    # for re-reading the remaining per-mode ranges out of the APK.
    min_temp: float = 7.0
    max_temp: float = 30.0
    frost_temp: float = 7.0
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

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable snapshot (for diagnostics / logging)."""
        return {
            **{field: getattr(self, field) for field in _BOOL_FIELDS},
            "min_temp": self.min_temp,
            "max_temp": self.max_temp,
            "frost_temp": self.frost_temp,
            "default_boost_minutes": self.default_boost_minutes,
            "boost_durations": list(self.boost_durations),
            "climate_presets": self.climate_presets(),
        }


def _positive_float(value: Any, default: float) -> float:
    """Coerce a capability temperature, falling back when it is unusable."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _from_library(caps: Any) -> LocalCapabilities:
    """Copy a library capability object field-for-field."""
    return LocalCapabilities(
        **{field: bool(getattr(caps, field, _BOOL_DEFAULTS.get(field, True))) for field in _BOOL_FIELDS},
        min_temp=_positive_float(getattr(caps, "min_temp", None), 7.0),
        max_temp=_positive_float(getattr(caps, "max_temp", None), 30.0),
        frost_temp=_positive_float(getattr(caps, "frost_temp", None), 7.0),
        default_boost_minutes=_positive_int(getattr(caps, "default_boost_minutes", None), 60),
        boost_durations=tuple(getattr(caps, "boost_durations", None) or (30, 60, 120, 180)),
    )


def _normalise(value: Any) -> str:
    return str(value).strip().lower() if value else ""


def product_lookup(products: Iterable[Any] | None) -> dict[str, Any]:
    """Index a product catalogue by model and type name for row lookups.

    ``GET /Appliances/GetProductModels`` is account-wide and static, and an
    appliance row carries no product id to join on — only its own model and type
    strings. Model names win over type names so a specific match is not shadowed
    by the shared family entry (#199).
    """
    by_type: dict[str, Any] = {}
    by_model: dict[str, Any] = {}
    for product in products or []:
        model = _normalise(getattr(product, "ProductModelName", None))
        if model:
            by_model.setdefault(model, product)
        type_name = _normalise(getattr(product, "ProductTypeName", None))
        if type_name:
            by_type.setdefault(type_name, product)
    return {**by_type, **by_model}


def product_for_appliance(lookup: Mapping[str, Any] | None, appliance: Any) -> Any | None:
    """Best-effort join of an appliance to its catalogue product model.

    The appliance's own model is tried before its type: ``AUTOMATIC_PROVISIONING``
    hangs off the catalogue row, and that is what makes ``storage`` /
    ``energy_meter`` derivable at all.
    """
    if not lookup or appliance is None:
        return None
    for attr in ("ApplianceModel", "ApplianceType"):
        key = _normalise(getattr(appliance, attr, None))
        if key and key in lookup:
            return lookup[key]
    return None


def capabilities_for_row(appliance: Any, status: Any = None, product: Any = None) -> LocalCapabilities:
    """Derive capability flags for an appliance row.

    Everything the library knows is passed through, including the product
    catalogue row when one could be matched — without it the derived flags
    (``storage``, ``hot_water``, ``heat_pump``, ``energy_meter``) cannot be
    derived and fall back to string tokens on the appliance itself.
    """
    if _lib_capabilities_for is not None:
        try:
            return _from_library(_lib_capabilities_for(appliance, status=status, product=product))
        except Exception:
            pass

    tokens = " ".join(
        str(getattr(appliance, attr, "") or "") for attr in ("ApplianceType", "ApplianceModel", "FriendlyName")
    ).lower()
    climate = not any(k in tokens for k in ("hot water", "hotwater", "cylinder", "dhw"))
    return LocalCapabilities(climate=climate)
