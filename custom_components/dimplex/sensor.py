"""Sensor platform for dimplex_controller."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from dimplex_controller import ApplianceModeFlag, summarise_energy
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorExtraStoredData,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower, UnitOfTemperature, UnitOfTime, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .capabilities import capabilities_for_row
from .const import (
    BOOST_FLAG,
    DOMAIN,
    HEAT_DEMAND_FLAGS,
    HOT_WATER_MODES,
    HYGIENE_FREQUENCY_NAMES,
    has_any_mode,
    hot_water_mode,
    sane_temperature,
    schedule_profile,
)
from .entity import DimplexEntity, resolve_via_device_id

# The coordinator fetches the data; entity updates need no limit.
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


@dataclass
class _PeakExtraStoredData(SensorExtraStoredData):
    """Restore data for a held cumulative total: the state plus the peak itself.

    :class:`SensorExtraStoredData` only carries the reported state, which is
    unknown whenever the series was empty at shutdown — so restoring from it
    alone re-accepts a truncated total as growth. The peak rides alongside it
    instead (#281). The base ``from_dict`` still reads the state half, so the
    standard sensor-data restore path keeps working.
    """

    peak_total: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise the state and the peak together."""
        return {**super().as_dict(), "peak_total": self.peak_total}


@dataclass
class _BoostExtraStoredData(SensorExtraStoredData):
    """Restore data for the boost countdown: the state plus the engage record."""

    started_at: str | None = None
    duration_minutes: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serialise the state and the engage record together."""
        return {
            **super().as_dict(),
            "started_at": self.started_at,
            "duration_minutes": self.duration_minutes,
        }


def _restored_peak(last_extra: Any | None) -> float | None:
    """Read the held peak back out of stored extra restore data."""
    if last_extra is None:
        return None
    try:
        saved = last_extra.as_dict()
    except Exception:  # pragma: no cover - unexpected extra shape
        return None
    if not isinstance(saved, dict):
        return None
    raw_peak = saved.get("peak_total")
    if isinstance(raw_peak, bool) or not isinstance(raw_peak, int | float):
        return None
    return float(raw_peak)


@dataclass(frozen=True, kw_only=True)
class DimplexSensorEntityDescription(SensorEntityDescription):
    """Describe a status-backed Dimplex sensor."""

    value_fn: Callable[[Any, Any], Any]
    """``(status, appliance) -> native value``."""

    available_when_no_status: bool = False
    """If True, entity can be available without live overview (provisioning / last telem)."""

    capability: str | None = None
    """Capability flag that must be true for the entity to be created, if any."""


def _status_attr(attr: str) -> Callable[[Any, Any], Any]:
    def _fn(status: Any, _appliance: Any) -> Any:
        if status is None:
            return None
        value = getattr(status, attr, None)
        return value if value not in (None, "") else None

    return _fn


def _status_temp(attr: str) -> Callable[[Any, Any], Any]:
    """Like :func:`_status_attr` but drops the 0xFF (255) sentinel / bad temps.

    The cloud reports 255 for a temperature field when it has no active value
    (idle / EcoStart / between schedule periods); surface "unknown" instead of
    an impossible reading.
    """

    def _fn(status: Any, _appliance: Any) -> Any:
        if status is None:
            return None
        return sane_temperature(getattr(status, attr, None))

    return _fn


def _provisioning_attr(attr: str) -> Callable[[Any, Any], Any]:
    def _fn(_status: Any, appliance: Any) -> Any:
        prop = getattr(type(appliance), "automatic_provisioning", None)
        if isinstance(prop, property):
            prov = appliance.automatic_provisioning
        else:
            prov = getattr(appliance, "automatic_provisioning", None)
        if prov is None:
            return None
        value = getattr(prov, attr, None)
        return float(value) if value is not None else None

    return _fn


def _last_telem(status: Any, appliance: Any) -> Any:
    """Return the appliance's ``LastTelemDate`` — the last cloud contact.

    Read from the appliance, which is the field the library defines
    (``ApplianceStatus`` carries no ``LastTelemDate``). The cloud's .NET
    "unset" value (``0001-01-01T00:00:00``, year 1) maps to unknown rather
    than rendering as year 1 — the library maps it to ``None`` on current
    versions, and this filters it defensively for older ones (#301).
    """
    value = getattr(appliance, "LastTelemDate", None)
    if isinstance(value, datetime) and value.year == 1:
        return None
    return value


def _operating_mode_names(modes: Any) -> list[str] | None:
    """Decode a raw ``ApplianceModes`` bitfield into flag names.

    Returns ``None`` when modes are unknown. Bit 64 intentionally maps to
    ``ECO`` here exactly as the library does — firmware 28 reports 64 while
    the app shows Manual, but that mapping is corrected only by a hardware
    probe, never by guessing in code (#298).
    """
    if modes is None:
        return None
    try:
        raw = int(modes)
    except (TypeError, ValueError):
        return None
    try:
        flags = ApplianceModeFlag(raw)
    except ValueError:
        return None
    return [member.name for member in ApplianceModeFlag if member.value and member in flags and member.name]


def _estimated_power_kw(status: Any, appliance: Any) -> float | None:
    """Heuristic power estimate: rated_kW when heating indicators active, else 0.

    Not a live meter — daily kWh remains the only cloud energy measurement.
    """
    rated = _provisioning_attr("rated_power")(status, appliance)
    if rated is None:
        return None
    heating = False
    if status is not None:
        if getattr(status, "ComfortStatus", None):
            heating = True
        if has_any_mode(status, HEAT_DEMAND_FLAGS):
            heating = True
        duration = getattr(status, "BoostDuration", None)
        if duration is not None and duration > 0:
            heating = True
    return float(rated) if heating else 0.0


STATUS_SENSORS: tuple[DimplexSensorEntityDescription, ...] = (
    DimplexSensorEntityDescription(
        key="room_temperature",
        translation_key="room_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        capability="climate",
        value_fn=_status_temp("RoomTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="target_temperature",
        translation_key="target_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=_status_temp("ActiveSetPointTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="boost_temperature",
        translation_key="boost_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        capability="boost",
        value_fn=_status_temp("BoostTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="away_temperature",
        translation_key="away_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        capability="away",
        value_fn=_status_temp("AwayTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="setback_temperature",
        translation_key="setback_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        capability="setback_read",
        value_fn=_status_temp("SetbackTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status_attr("ErrorCode"),
    ),
    DimplexSensorEntityDescription(
        key="warning_code",
        translation_key="warning_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status_attr("WarningCode"),
    ),
    DimplexSensorEntityDescription(
        key="last_telem",
        translation_key="last_telem",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_last_telem,
        available_when_no_status=True,
    ),
    DimplexSensorEntityDescription(
        key="status_two",
        translation_key="status_two",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status_attr("StatusTwo"),
    ),
    DimplexSensorEntityDescription(
        key="rated_power",
        translation_key="rated_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_provisioning_attr("rated_power"),
        available_when_no_status=True,
    ),
    DimplexSensorEntityDescription(
        key="top_element_power",
        translation_key="top_element_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_provisioning_attr("top_element_power_rating"),
        available_when_no_status=True,
    ),
    DimplexSensorEntityDescription(
        key="bottom_element_power",
        translation_key="bottom_element_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_provisioning_attr("bottom_element_power_rating"),
        available_when_no_status=True,
    ),
    DimplexSensorEntityDescription(
        key="charge_capacity",
        translation_key="charge_capacity",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_provisioning_attr("charge_capacity"),
        available_when_no_status=True,
    ),
    DimplexSensorEntityDescription(
        key="estimated_power",
        translation_key="estimated_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_estimated_power_kw,
    ),
    # Litres of usable hot water: a live ASHW cylinder reports 336 here and the
    # Dimplex app shows "336 L Hot water" for it. Capability-gated so an
    # appliance with no hot water does not get a permanently unknown sensor (#199).
    DimplexSensorEntityDescription(
        key="hot_water_available",
        translation_key="hot_water_available",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        capability="hot_water",
        value_fn=_status_attr("AvailableHotWater"),
    ),
    DimplexSensorEntityDescription(
        key="hot_water_capacity",
        translation_key="hot_water_capacity",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        capability="hot_water",
        value_fn=_status_attr("Capacity"),
    ),
    DimplexSensorEntityDescription(
        key="hot_water_mode",
        translation_key="hot_water_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(HOT_WATER_MODES),
        capability="hot_water",
        value_fn=lambda status, _appliance: hot_water_mode(status),
    ),
    DimplexSensorEntityDescription(
        key="hygiene_frequency",
        translation_key="hygiene_frequency",
        device_class=SensorDeviceClass.ENUM,
        options=list(HYGIENE_FREQUENCY_NAMES.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        capability="hygiene",
        value_fn=lambda status, _appliance: HYGIENE_FREQUENCY_NAMES.get(getattr(status, "HygieneFrequency", -1)),
    ),
    DimplexSensorEntityDescription(
        key="holiday_days",
        translation_key="holiday_days",
        native_unit_of_measurement=UnitOfTime.DAYS,
        entity_category=EntityCategory.DIAGNOSTIC,
        capability="hot_water",
        value_fn=_status_attr("HolidayNumOfDays"),
    ),
)


@dataclass(frozen=True, kw_only=True)
class DimplexEnergySensorEntityDescription(SensorEntityDescription):
    """Describe an energy history sensor."""

    mode: str  # "daily" | "lifetime"
    register: str  # "t1" | "t2"


ENERGY_SENSORS: tuple[DimplexEnergySensorEntityDescription, ...] = (
    # The two cumulative sensors are rising meters over everything the cloud
    # returns, so TOTAL_INCREASING is the correct state class — and the only one
    # that lets the Energy Dashboard use them.
    #
    # 4.1.0 removed the state class from them on the belief that they were rolling
    # 30-day windows. They are not. `summarise_energy(mode="lifetime")` sums every
    # point it is handed, and the cloud returns the full available daily history
    # behind the request's 30-day start date — the library's own
    # `get_tsi_energy_report` docstring says so and warns callers to "filter
    # client-side". A real installation's diagnostics show 183-289 daily points per
    # appliance spanning 12-17 months, each starting at its own first reading
    # (#227).
    #
    # What actually corrupted statistics was a *dip*: when the cloud returns a
    # truncated history the cumulative sum falls, and Home Assistant's
    # `reset_detected` reads a fall of more than 10% as a meter reset and adds the
    # whole total to the statistics again (#196). `DimplexEnergySensor` reports a
    # monotonic value instead, which is what makes this state class safe.
    DimplexEnergySensorEntityDescription(
        key="energy",
        translation_key="energy_lifetime",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        mode="lifetime",
        register="t1",
    ),
    DimplexEnergySensorEntityDescription(
        key="energy_daily",
        translation_key="energy_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        mode="daily",
        register="t1",
    ),
    DimplexEnergySensorEntityDescription(
        key="energy_t2",
        translation_key="energy_t2_lifetime",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_registry_enabled_default=False,
        mode="lifetime",
        register="t2",
    ),
    DimplexEnergySensorEntityDescription(
        key="energy_t2_daily",
        translation_key="energy_t2_today",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_registry_enabled_default=False,
        mode="daily",
        register="t2",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    runtime = entry.runtime_data
    status = runtime.status
    energy = runtime.energy
    devices: list[SensorEntity] = []
    seen_zones: set[str] = set()
    for appliance_row in (status.data or {}).get("appliances", []):
        caps = capabilities_for_row(
            appliance_row["appliance"], appliance_row.get("status"), appliance_row.get("product")
        )
        devices.extend(
            DimplexSensor(status, entry, appliance_row, description)
            for description in STATUS_SENSORS
            if description.capability is None or getattr(caps, description.capability, False)
        )
        # Live mode decoding needs no capability: every overview carries the
        # bitfield, and the unknown-bit path reports the raw integer (#298).
        devices.append(DimplexOperatingModeSensor(status, entry, appliance_row))
        # Countdown only exists where a boost can be started; a boost begun
        # outside Home Assistant reads unknown by design (#302).
        if getattr(caps, "boost", False):
            devices.append(DimplexBoostRemainingSensor(status, entry, appliance_row))
        # Energy history only exists for appliances the cloud meters. Other
        # appliances would get four permanently unavailable entities, two
        # enabled by default, recreated on every reload (#280).
        if getattr(caps, "energy_meter", False):
            devices.extend(
                DimplexEnergySensor(energy, entry, appliance_row, description) for description in ENERGY_SENSORS
            )
        if caps.hot_water and caps.heat_pump:
            devices.append(DimplexHotWaterScheduleSensor(status, entry, appliance_row))
        else:
            devices.append(DimplexScheduleSensor(status, entry, appliance_row))
        zone = appliance_row.get("zone")
        zone_id = getattr(zone, "ZoneId", None) if zone is not None else None
        if zone_id and zone_id not in seen_zones:
            seen_zones.add(zone_id)
            devices.append(DimplexZoneSensor(status, entry, appliance_row))
    async_add_entities(devices)


class DimplexSensor(DimplexEntity, SensorEntity):
    """Status / provisioning sensor driven by an entity description."""

    entity_description: DimplexSensorEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        description: DimplexSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, config_entry, appliance_row, description)

    @property
    def available(self) -> bool:
        """Handle sensors that do not require live overview."""
        if self.entity_description.available_when_no_status:
            if not CoordinatorEntity.available.__get__(self, type(self)):
                return False
            return self.native_value is not None
        return super().available

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self._status, self._appliance)


class DimplexOperatingModeSensor(DimplexEntity, SensorEntity):
    """Live operating mode decoded from the ``ApplianceModes`` bitfield.

    The schedule sensor reports the stored timer mode, which is the mode the
    user left behind — not what the appliance is doing. This sensor reports
    the live bitfield instead: flag names as the state, with the raw integer
    and the decoded list as attributes so a mapping surprise (like firmware
    28 reporting ECO/64 while the app shows Manual) stays visible rather
    than being guessed away in code (#298).
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "operating_mode"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
    ) -> None:
        super().__init__(
            coordinator,
            config_entry,
            appliance_row,
            SensorEntityDescription(
                key="operating_mode",
                translation_key="operating_mode",
            ),
            unique_id_suffix="operating_mode",
        )
        self._attr_unique_id = f"{config_entry.entry_id}_{self._appliance.ApplianceId}_operating_mode"

    @property
    def native_value(self) -> str | None:
        """Comma-joined flag names, the raw integer for unknown bits, else unknown."""
        status = self._status
        if status is None:
            return None
        raw = getattr(status, "ApplianceModes", None)
        if raw is None:
            return None
        try:
            raw_int = int(raw)
        except (TypeError, ValueError):
            return None
        names = _operating_mode_names(raw_int)
        if names:
            return ", ".join(names)
        return str(raw_int)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Decoded list, raw integer and whether the field was known."""
        status = self._status
        raw = getattr(status, "ApplianceModes", None) if status is not None else None
        try:
            raw_int = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            raw_int = None
        names = _operating_mode_names(raw_int) if raw_int is not None else None
        return {
            "active_modes": names if names is not None else [],
            "raw_modes": raw_int,
            "appliance_modes_known": raw_int is not None,
        }


class DimplexBoostRemainingSensor(DimplexEntity, RestoreSensor):
    """Minutes of HA-initiated boost left, synthesised from the engage time.

    The cloud sends no expiry — ``BoostDuration`` is a configured length that
    can outlive the boost itself — so when Home Assistant starts a boost the
    start time and chosen duration are recorded (and restored across
    restarts) and this counts down from there, reaching zero. A boost begun
    on the heater or in the app has no recorded start and reads unknown;
    guessing from ``LastTelemDate`` would invent precision the cloud never
    sent (#302).
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "boost_remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
    ) -> None:
        super().__init__(
            coordinator,
            config_entry,
            appliance_row,
            SensorEntityDescription(
                key="boost_remaining",
                translation_key="boost_remaining",
            ),
            unique_id_suffix="boost_remaining",
        )
        self._attr_unique_id = f"{config_entry.entry_id}_{self._appliance.ApplianceId}_boost_remaining"

    @property
    def _record(self) -> dict[str, Any] | None:
        runtime = getattr(self.config_entry, "runtime_data", None)
        starts = getattr(runtime, "boost_starts", None) if runtime is not None else None
        if not isinstance(starts, dict):
            return None
        record = starts.get(self._appliance.ApplianceId)
        return record if isinstance(record, dict) else None

    @property
    def native_value(self) -> float | None:
        """Minutes remaining, 0.0 once reached, unknown without a recorded start."""
        record = self._record
        if record is None:
            return None
        try:
            duration = float(record["duration_minutes"])
            started_at = dt_util.parse_datetime(str(record["started_at"]))
        except (KeyError, TypeError, ValueError):
            return None
        if started_at is None:
            return None
        elapsed = (dt_util.utcnow() - started_at).total_seconds() / 60
        remaining = duration - elapsed
        if remaining > 0:
            return round(remaining, 1)
        # Countdown reached zero: hold 0.0 while the boost bit is still set
        # (or while the modes are unknown), and retire to unknown once the
        # cloud confirms the boost ended so a stale 0.0 does not linger.
        if has_any_mode(self._status, BOOST_FLAG):
            return 0.0
        if self._status is None or getattr(self._status, "ApplianceModes", None) is None:
            return 0.0
        runtime = getattr(self.config_entry, "runtime_data", None)
        starts = getattr(runtime, "boost_starts", None) if runtime is not None else None
        if isinstance(starts, dict):
            starts.pop(self._appliance.ApplianceId, None)
        return None

    async def async_added_to_hass(self) -> None:
        """Restore the recorded boost start across a restart."""
        await super().async_added_to_hass()
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime is None or self._appliance.ApplianceId in getattr(runtime, "boost_starts", {}):
            return
        last_extra = await self.async_get_last_extra_data()
        if last_extra is None:
            return
        try:
            saved = last_extra.as_dict()
        except Exception:  # pragma: no cover - unexpected extra shape
            return
        if isinstance(saved, dict) and saved.get("started_at") and saved.get("duration_minutes"):
            runtime.boost_starts[self._appliance.ApplianceId] = {
                "started_at": str(saved["started_at"]),
                "duration_minutes": int(saved["duration_minutes"]),
            }

    @property
    def extra_restore_state_data(self) -> SensorExtraStoredData:
        """Persist the recorded boost start itself, next to the state."""
        record = self._record
        started_at = str(record["started_at"]) if record else None
        duration = int(record["duration_minutes"]) if record else None
        return _BoostExtraStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            started_at,
            duration,
        )


_TIMER_MODE_NAMES = {
    0: "user_timer",
    1: "manual",
    2: "frost_protection",
    3: "off",
}


class DimplexScheduleSensor(DimplexEntity, SensorEntity):
    """Read-only timer mode / schedule summary (phase 1)."""

    _attr_translation_key = "schedule"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, config_entry, appliance_row, unique_id_suffix="schedule")
        self._attr_unique_id = f"{config_entry.entry_id}_{self._appliance.ApplianceId}_schedule"

    @property
    def available(self) -> bool:
        if not CoordinatorEntity.available.__get__(self, type(self)):
            return False
        return self._schedule is not None

    @property
    def _schedule(self) -> Any:
        schedules = (self.coordinator.data or {}).get("schedules") or {}
        return schedules.get(self._appliance.ApplianceId)

    @property
    def native_value(self) -> str | None:
        profile = schedule_profile(self._status)
        if profile is not None:
            return profile
        schedule = self._schedule
        if schedule is None:
            return None
        mode = getattr(schedule, "TimerMode", None)
        if mode is None:
            return None
        return _TIMER_MODE_NAMES.get(int(mode), str(mode))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        schedule = self._schedule
        if schedule is None:
            return {}
        periods_out: list[dict[str, Any]] = []
        for period in getattr(schedule, "TimerPeriods", None) or []:
            periods_out.append(
                {
                    "day_of_week": getattr(period, "DayOfWeek", None),
                    "start": getattr(period, "StartTime", None),
                    "end": getattr(period, "EndTime", None),
                    "temperature": getattr(period, "Temperature", None),
                }
            )
        return {
            "timer_mode": getattr(schedule, "TimerMode", None),
            "status_two": getattr(self._status, "StatusTwo", None),
            "period_count": len(periods_out),
            "periods": periods_out,
        }


# .NET DayOfWeek, as the cylinder schedule uses it: 0 = Sunday.
_DAYS = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")
_DAY_ABBR = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
_WEEK_ORDER = (1, 2, 3, 4, 5, 6, 0)  # Monday first, like the app


def _clock(start: Any) -> str | None:
    """Format a cylinder period start as HH:MM.

    The cloud sends an integer; minutes after midnight is assumed (a live
    cylinder only ever showed 0), so the raw value is kept alongside.
    """
    try:
        minutes = int(start)
    except (TypeError, ValueError):
        return None
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class DimplexHotWaterScheduleSensor(DimplexEntity, SensorEntity):
    """Read-only weekly schedule of a heat-pump hot-water cylinder."""

    _attr_translation_key = "hot_water_schedule"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, config_entry, appliance_row)
        # Same id as the room-heater schedule sensor it replaces on cylinders.
        self._attr_unique_id = f"{config_entry.entry_id}_{self._appliance.ApplianceId}_schedule"

    @property
    def available(self) -> bool:
        if not CoordinatorEntity.available.__get__(self, type(self)):
            return False
        return isinstance(self._schedule, dict)

    @property
    def _schedule(self) -> Any:
        schedules = (self.coordinator.data or {}).get("schedules") or {}
        return schedules.get(self._appliance.ApplianceId)

    def _by_day(self) -> dict[int, list[tuple[int, Any]]]:
        days: dict[int, list[tuple[int, Any]]] = {}
        for period in (self._schedule or {}).get("TimerPeriods") or []:
            try:
                day, start = int(period["DayOfWeek"]), int(period["StartTime"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= day <= 6:
                days.setdefault(day, []).append((start, period.get("Mode")))
        return {day: sorted(periods) for day, periods in days.items()}

    @property
    def native_value(self) -> str | None:
        """Compact summary, e.g. ``Mon–Sun 00:00 mode 2``."""
        if not isinstance(self._schedule, dict):
            return None
        by_day = self._by_day()
        if not by_day:
            return "no periods"
        groups: list[tuple[list[int], str]] = []
        for day in _WEEK_ORDER:
            text = ", ".join(f"{_clock(start)} mode {mode}" for start, mode in by_day.get(day, [])) or "none"
            if groups and groups[-1][1] == text:
                groups[-1][0].append(day)
            else:
                groups.append(([day], text))
        parts = []
        for days, text in groups:
            label = _DAY_ABBR[days[0]] if len(days) == 1 else f"{_DAY_ABBR[days[0]]}–{_DAY_ABBR[days[-1]]}"
            parts.append(f"{label} {text}")
        return "; ".join(parts)[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not isinstance(self._schedule, dict):
            return {}
        by_day = self._by_day()
        now = dt_util.now()
        today = (now.weekday() + 1) % 7
        minute = now.hour * 60 + now.minute
        current = None
        for start, mode in by_day.get(today, []):
            if start <= minute:
                current = mode
        attrs: dict[str, Any] = {
            _DAYS[day]: [
                {"start": _clock(start), "start_raw": start, "mode": mode} for start, mode in by_day.get(day, [])
            ]
            for day in _WEEK_ORDER
        }
        attrs["current_mode"] = current
        attrs["period_count"] = sum(len(periods) for periods in by_day.values())
        return attrs


class DimplexZoneSensor(CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]], SensorEntity):
    """Zone device anchor (exposes zone in the device registry)."""

    _attr_has_entity_name = True
    _attr_translation_key = "zone"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._hub = appliance_row["hub"]
        self._zone = appliance_row["zone"]
        self._attr_unique_id = f"{config_entry.entry_id}_zone_{self._zone.ZoneId}"

    @property
    def available(self) -> bool:
        """Unavailable once the zone stops appearing in the appliance snapshot.

        The anchor used to keep reporting after its zone was removed or renamed in
        the Dimplex app, leaving a permanently stale entity behind that could
        never go away by itself (#198).
        """
        if not self.coordinator.last_update_success:
            return False
        zone_ids = {
            getattr(row.get("zone"), "ZoneId", None) for row in (self.coordinator.data or {}).get("appliances", [])
        }
        return self._zone.ZoneId in zone_ids

    @property
    def native_value(self) -> str | None:
        return getattr(self._zone, "ZoneName", None)

    @property
    def device_info(self) -> DeviceInfo:
        info: DeviceInfo = {
            "identifiers": {(DOMAIN, f"zone_{self._zone.ZoneId}")},
            "name": self._zone.ZoneName,
            "manufacturer": "Dimplex",
            "model": getattr(self._zone, "ZoneType", None) or "Zone",
            "suggested_area": self._zone.ZoneName,
        }
        via_device_id = resolve_via_device_id(
            self.hass, (DOMAIN, self._hub.HubId), getattr(self.config_entry, "entry_id", None)
        )
        if via_device_id:
            info["via_device_id"] = via_device_id
        return info


class DimplexEnergySensor(CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]], RestoreSensor):
    """Energy sensor backed by the energy coordinator."""

    _attr_has_entity_name = True
    entity_description: DimplexEnergySensorEntityDescription
    _summary_cached: Any | None = None
    _summary_ts: Any | None = None
    # Highest cumulative total reported, so the sensor is a true rising meter.
    _peak_total: float | None = None
    # Last suppressed raw total already logged, so one ongoing rebase warns once.
    _last_suppressed_total: float | None = None

    def __init__(
        self,
        energy_coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        description: DimplexEnergySensorEntityDescription,
    ) -> None:
        super().__init__(energy_coordinator)
        self.entity_description = description
        self.config_entry = config_entry
        self._appliance = appliance_row["appliance"]
        self._hub = appliance_row["hub"]
        self._zone = appliance_row["zone"]
        self._attr_unique_id = f"{config_entry.entry_id}_{self._appliance.ApplianceId}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return appliance device registry metadata."""
        appliance_type = getattr(self._appliance, "ApplianceType", None)
        model = self._appliance.ApplianceModel
        if appliance_type and model and appliance_type not in str(model):
            model = f"{appliance_type} {model}"
        zone_id = getattr(self._zone, "ZoneId", None)
        via: tuple[str, str] = (DOMAIN, f"zone_{zone_id}") if zone_id else (DOMAIN, self._hub.HubId)
        info: DeviceInfo = {
            "identifiers": {(DOMAIN, self._appliance.ApplianceId)},
            "name": self._appliance.FriendlyName,
            "manufacturer": "Dimplex",
            "model": model,
            "serial_number": self._appliance.ApplianceId,
            "suggested_area": self._zone.ZoneName,
        }
        via_device_id = resolve_via_device_id(self.hass, via, getattr(self.config_entry, "entry_id", None))
        if via_device_id:
            info["via_device_id"] = via_device_id
        firmware = getattr(self._appliance, "FirmwareVersion", None)
        if firmware:
            info["sw_version"] = str(firmware)
        return info

    @property
    def _energy_points(self) -> list[tuple[datetime | None, float]]:
        energy = (self.coordinator.data or {}).get("energy") or {}
        hub_points = energy.get(self._hub.HubId) or {}
        points = hub_points.get(self.entity_description.register, {}).get(self._appliance.ApplianceId, [])
        return list(points)

    def _local_tz(self) -> Any:
        try:
            return dt_util.get_default_time_zone()
        except Exception:
            return ZoneInfo("UTC")

    def _summary(self) -> Any | None:
        """Memoised energy summary — computed once per coordinator update cycle.

        The summary backs ``available``, ``native_value``, ``last_reset`` and
        ``extra_state_attributes``, each of which is read on every state write, so
        recomputing it per property is wasted work: a 30-day series at a 10-minute
        interval is a few thousand points per sensor.

        The cache key is the energy coordinator's ``last_update_success_time``,
        which is why that coordinator is a ``TimestampDataUpdateCoordinator``. A
        plain coordinator does not define the attribute, the key was always
        ``None``, and the memo never hit (#198). ``None`` is treated as "no usable
        key" and recomputes, rather than caching against a key that never changes.
        """
        last_updated = getattr(self.coordinator, "last_update_success_time", None)
        if last_updated is not None and last_updated == getattr(self, "_summary_ts", None):
            return self._summary_cached

        points = self._energy_points
        if not points:
            result = None
        else:
            result = summarise_energy(
                points,
                mode=self.entity_description.mode,  # type: ignore[arg-type]
                now=dt_util.now(),
                tz=self._local_tz(),
            )

        self._summary_cached = result
        self._summary_ts = last_updated
        return result

    @property
    def available(self) -> bool:
        """Available when the energy coordinator has points for this series.

        A daily sensor with a non-empty series but no points yet today reports
        0.0 from local midnight — it must not wait, unavailable, for the
        cloud to publish today's first sample (#281).
        """
        if not super().available:
            return False
        if self.entity_description.mode == "daily":
            return self._summary() is not None
        summary = self._summary()
        return summary is not None and summary.point_count > 0

    @property
    def _raw_total(self) -> float | None:
        """Return the total the cloud actually reported, before the monotonic hold.

        The reported value is deliberately held at the peak (:meth:`_reported_total`),
        so this is the only way to see what the cloud is currently sending. It is
        exposed as an attribute on the cumulative sensors so a suppressed drop is
        inspectable rather than invisible (#234).
        """
        summary = self._summary()
        if summary is None:
            return None
        if summary.point_count == 0:
            # No points for today's window, but the series itself exists: the
            # day simply has no consumption yet, so report 0 rather than
            # unknown (#281). Lifetime sensors stay unknown when empty.
            if self.entity_description.mode == "daily":
                return 0.0
            return None
        return float(summary.total_kwh)

    @property
    def native_value(self) -> float | None:
        """Return kWh for the configured window."""
        total = self._raw_total
        if total is None:
            return None
        return self._reported_total(total)

    def _reported_total(self, total: float) -> float:
        """Return a cumulative total that never falls, and remember the peak.

        The cloud normally returns the appliance's whole history, so the sum only
        grows — but a truncated response makes it fall, and Home Assistant's reset
        detection reads a fall of more than 10% as a new meter cycle and adds the
        entire total to long-term statistics a second time (#196). Holding the
        highest value seen means a short read is simply ignored, and the meter only
        ever moves forward as it should.

        Only the cumulative sensors are clamped: a daily total is expected to drop
        to zero at midnight.

        The peak is restored across restarts because Home Assistant compares
        against the last value in *its* recorder, not against anything held in
        memory — so a dip on the first poll after a restart would still look like a
        reset.

        Holding forever has a cost the issue named: if the cloud's history for an
        appliance is reduced *permanently* — retention trimming, a changed report
        shape, a re-onboarded appliance under the same id — the true total falls and
        nothing notices. The entity then over-reports silently and indefinitely. A
        drop of more than 10% is exactly the case that is both worth suppressing (it
        is what Home Assistant reads as a meter cycle) and the signature of that
        permanent reduction, so it is logged at ``warning``; anything smaller is
        routine noise and stays at ``debug``. The unheld value is published as
        ``raw_total`` alongside it (#234).
        """
        if self.entity_description.mode != "lifetime":
            return total
        peak = self._peak_total
        if peak is None or total > peak:
            self._peak_total = total
            self._last_suppressed_total = None
            return total
        if total < peak and total != self._last_suppressed_total:
            # A held value is re-read on every poll, so logging each time spams
            # thousands of lines for one ongoing rebase. Warn once per distinct
            # lower total instead (#234).
            self._last_suppressed_total = total
            drop_percent = round((peak - total) / peak * 100, 1) if peak else 0.0
            log = _LOGGER.warning if drop_percent > 10 else _LOGGER.debug
            log(
                "%s reported %s kWh, below the %s kWh already seen (%s%% drop); holding the higher value. "
                "Raw total is on the raw_total attribute",
                self.entity_id,
                total,
                peak,
                drop_percent,
            )
        return peak

    async def async_added_to_hass(self) -> None:
        """Restore the highest cumulative total across a restart.

        The peak itself is restored — from extra restore data when present,
        else from the previous state's ``peak_total`` attribute, else from the
        stored native value. Restoring from the state value alone re-accepts a
        truncated total whenever the series was empty at shutdown, because the
        state is then ``None``/unknown and the next poll's lower total looks
        like growth (#281).
        """
        await super().async_added_to_hass()
        if self.entity_description.mode != "lifetime":
            return
        peak = _restored_peak(await self.async_get_last_extra_data())
        if peak is None:
            try:
                last_state = await self.async_get_last_state()
            except Exception:  # pragma: no cover - no state history
                last_state = None
            if last_state is not None:
                attr_peak = last_state.attributes.get("peak_total")
                if not isinstance(attr_peak, bool) and isinstance(attr_peak, int | float):
                    peak = float(attr_peak)
        if peak is None:
            last = await self.async_get_last_sensor_data()
            if last is not None:
                # Our own restored value is always a float; anything else means someone
                # else wrote the attribute, so ignore it rather than guessing.
                restored = last.native_value
                if not isinstance(restored, bool) and isinstance(restored, int | float):
                    peak = float(restored)
        if peak is not None:
            self._peak_total = peak

    @property
    def extra_restore_state_data(self) -> SensorExtraStoredData:
        """Persist the held peak itself, next to the reported state."""
        return _PeakExtraStoredData(
            self.native_value,
            self.native_unit_of_measurement,
            self._peak_total,
        )

    @property
    def last_reset(self) -> datetime | None:
        """Return the window start, which Home Assistant only accepts for TOTAL.

        HA raises if ``last_reset`` is set on any other state class, so this must
        test for TOTAL rather than exclude TOTAL_INCREASING — the window sensors now
        carry no state class at all (#196).
        """
        if self.entity_description.state_class != SensorStateClass.TOTAL:
            return None
        summary = self._summary()
        if summary is None:
            return None
        start = summary.start
        return start if isinstance(start, datetime) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose summary window metadata."""
        summary = self._summary()
        if summary is None:
            return {}
        attributes: dict[str, Any] = {
            "mode": summary.mode,
            "register": self.entity_description.register,
            # No `window_days`: the value covers whatever span the cloud returned,
            # and asserting a fixed 30 days there was simply false — the request's
            # start date does not bound the response (#227). `window_start` and
            # `window_end` are the real span, taken from the points themselves.
            "window_start": summary.start.isoformat() if summary.start else None,
            "window_end": summary.end.isoformat() if summary.end else None,
            "telemetry_points": summary.point_count,
        }
        if self.entity_description.mode == "lifetime":
            # `raw_total` is what the cloud is sending now; the state is the held
            # peak, which can be higher. Together with the warning in
            # `_reported_total` this makes a suppressed drop answerable from a
            # diagnostics download, instead of "is the cloud trimming our history?"
            # being unanswerable without guesswork (#234). Daily totals are not
            # held, so they need neither.
            attributes["raw_total"] = self._raw_total
            attributes["peak_total"] = self._peak_total
        return attributes
