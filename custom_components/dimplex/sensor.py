"""Sensor platform for dimplex_controller."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from dimplex_controller import summarise_energy
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .capabilities import capabilities_for_row
from .const import DOMAIN, HEAT_DEMAND_FLAGS, has_any_mode, sane_temperature
from .entity import DimplexEntity, resolve_via_device_id

_LOGGER = logging.getLogger(__name__)


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
    if status is not None and getattr(status, "LastTelemDate", None) is not None:
        return status.LastTelemDate
    return getattr(appliance, "LastTelemDate", None)


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
        value_fn=_status_temp("BoostTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="away_temperature",
        translation_key="away_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=_status_temp("AwayTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="setback_temperature",
        translation_key="setback_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
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
        entity_registry_enabled_default=False,
        value_fn=_last_telem,
        available_when_no_status=True,
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
    # The only hot-water value the cloud reports back. Deliberately a diagnostic,
    # disabled-by-default sensor with no unit or device class: the field is a bare
    # number and nothing in the app or the API reference says what it measures —
    # °C and litres are both plausible. Shipping it as a temperature entity would be
    # inventing a unit; shipping it unitless and off by default lets a cylinder owner
    # turn it on and report what it shows (#199).
    DimplexSensorEntityDescription(
        key="hot_water_available",
        translation_key="hot_water_available",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        # Capability-gated, so an appliance the library says has no hot water does
        # not get a permanently unknown hot-water sensor (#199).
        capability="hot_water",
        value_fn=_status_attr("AvailableHotWater"),
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
        devices.extend(DimplexEnergySensor(energy, entry, appliance_row, description) for description in ENERGY_SENSORS)
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
            "period_count": len(periods_out),
            "periods": periods_out,
        }


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
        """Available when the energy coordinator has points for this series."""
        if not super().available:
            return False
        summary = self._summary()
        return summary is not None and summary.point_count > 0

    @property
    def native_value(self) -> float | None:
        """Return kWh for the configured window."""
        summary = self._summary()
        if summary is None or summary.point_count == 0:
            return None
        return self._reported_total(float(summary.total_kwh))

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
        """
        if self.entity_description.mode != "lifetime":
            return total
        peak = self._peak_total
        if peak is None or total > peak:
            self._peak_total = total
            return total
        if total < peak:
            _LOGGER.debug(
                "%s reported %s kWh, below the %s kWh already seen; holding the higher value",
                self.entity_id,
                total,
                peak,
            )
        return peak

    async def async_added_to_hass(self) -> None:
        """Restore the highest cumulative total across a restart."""
        await super().async_added_to_hass()
        if self.entity_description.mode != "lifetime":
            return
        last = await self.async_get_last_sensor_data()
        if last is None:
            return
        # Our own restored value is always a float; anything else means someone
        # else wrote the attribute, so ignore it rather than guessing.
        restored = last.native_value
        if isinstance(restored, bool) or not isinstance(restored, int | float):
            return
        self._peak_total = float(restored)

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
        return {
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
