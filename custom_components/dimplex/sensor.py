"""Sensor platform for dimplex_controller."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from dimplex_controller import summarise_energy
from homeassistant.components.sensor import (
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

from .const import DOMAIN
from .entity import DimplexEntity


@dataclass(frozen=True, kw_only=True)
class DimplexSensorEntityDescription(SensorEntityDescription):
    """Describe a status-backed Dimplex sensor."""

    value_fn: Callable[[Any, Any], Any]
    """``(status, appliance) -> native value``."""

    available_when_no_status: bool = False
    """If True, entity can be available without live overview (provisioning / last telem)."""


def _status_attr(attr: str) -> Callable[[Any, Any], Any]:
    def _fn(status: Any, _appliance: Any) -> Any:
        if status is None:
            return None
        value = getattr(status, attr, None)
        return value if value not in (None, "") else None

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


STATUS_SENSORS: tuple[DimplexSensorEntityDescription, ...] = (
    DimplexSensorEntityDescription(
        key="room_temperature",
        translation_key="room_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_status_attr("RoomTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="target_temperature",
        translation_key="target_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=_status_attr("ActiveSetPointTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="boost_temperature",
        translation_key="boost_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=_status_attr("BoostTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="away_temperature",
        translation_key="away_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=_status_attr("AwayTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="setback_temperature",
        translation_key="setback_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=_status_attr("SetbackTemperature"),
    ),
    DimplexSensorEntityDescription(
        key="error_code",
        translation_key="error_code",
        icon="mdi:alert-circle",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status_attr("ErrorCode"),
    ),
    DimplexSensorEntityDescription(
        key="warning_code",
        translation_key="warning_code",
        icon="mdi:alert",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status_attr("WarningCode"),
    ),
    DimplexSensorEntityDescription(
        key="last_telem",
        translation_key="last_telem",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
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
        icon="mdi:flash",
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
        icon="mdi:battery-high",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_provisioning_attr("charge_capacity"),
        available_when_no_status=True,
    ),
)


@dataclass(frozen=True, kw_only=True)
class DimplexEnergySensorEntityDescription(SensorEntityDescription):
    """Describe an energy history sensor."""

    mode: str  # "daily" | "lifetime"
    register: str  # "t1" | "t2"


ENERGY_SENSORS: tuple[DimplexEnergySensorEntityDescription, ...] = (
    DimplexEnergySensorEntityDescription(
        key="energy",
        translation_key="energy_lifetime",
        icon="mdi:lightning-bolt",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        mode="lifetime",
        register="t1",
    ),
    DimplexEnergySensorEntityDescription(
        key="energy_daily",
        translation_key="energy_today",
        icon="mdi:lightning-bolt",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        mode="daily",
        register="t1",
    ),
    DimplexEnergySensorEntityDescription(
        key="energy_t2",
        translation_key="energy_t2_lifetime",
        icon="mdi:lightning-bolt",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        entity_registry_enabled_default=False,
        mode="lifetime",
        register="t2",
    ),
    DimplexEnergySensorEntityDescription(
        key="energy_t2_daily",
        translation_key="energy_t2_today",
        icon="mdi:lightning-bolt",
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
    runtime = hass.data[DOMAIN][entry.entry_id]
    status = runtime.status
    energy = runtime.energy
    devices: list[SensorEntity] = []
    seen_zones: set[str] = set()
    for appliance_row in (status.data or {}).get("appliances", []):
        devices.extend(DimplexSensor(status, entry, appliance_row, description) for description in STATUS_SENSORS)
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
    _attr_icon = "mdi:calendar-clock"
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
    _attr_icon = "mdi:floor-plan"

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
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> str | None:
        return getattr(self._zone, "ZoneName", None)

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, f"zone_{self._zone.ZoneId}")},
            "name": self._zone.ZoneName,
            "manufacturer": "Dimplex",
            "model": getattr(self._zone, "ZoneType", None) or "Zone",
            "via_device": (DOMAIN, self._hub.HubId),
            "suggested_area": self._zone.ZoneName,
        }


class DimplexEnergySensor(CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]], SensorEntity):
    """Energy sensor backed by the energy coordinator."""

    _attr_has_entity_name = True
    entity_description: DimplexEnergySensorEntityDescription

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
            "via_device": via,
        }
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
        points = self._energy_points
        if not points:
            return None
        return summarise_energy(
            points,
            mode=self.entity_description.mode,  # type: ignore[arg-type]
            now=dt_util.now(),
            tz=self._local_tz(),
        )

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
        return float(summary.total_kwh)

    @property
    def last_reset(self) -> datetime | None:
        """Return window start for TOTAL state class."""
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
            "window_start": summary.start.isoformat() if summary.start else None,
            "window_end": summary.end.isoformat() if summary.end else None,
            "telemetry_points": summary.point_count,
        }
