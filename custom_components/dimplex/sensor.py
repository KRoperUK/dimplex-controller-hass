"""Sensor platform for dimplex_controller."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from dimplex_controller import summarise_energy
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import DimplexEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up sensor platform."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    status = runtime.status
    energy = runtime.energy
    devices: list[SensorEntity] = []
    for appliance_row in (status.data or {}).get("appliances", []):
        devices.extend(
            [
                DimplexRoomTemperatureSensor(status, entry, appliance_row),
                DimplexTargetTemperatureSensor(status, entry, appliance_row),
                DimplexBoostTemperatureSensor(status, entry, appliance_row),
                DimplexAwayTemperatureSensor(status, entry, appliance_row),
                DimplexSetbackTemperatureSensor(status, entry, appliance_row),
                DimplexErrorCodeSensor(status, entry, appliance_row),
                DimplexWarningCodeSensor(status, entry, appliance_row),
                DimplexLastTelemDateSensor(status, entry, appliance_row),
                DimplexEnergyLifetimeSensor(energy, status, entry, appliance_row, register="t1"),
                DimplexEnergyDailySensor(energy, status, entry, appliance_row, register="t1"),
                DimplexEnergyLifetimeSensor(energy, status, entry, appliance_row, register="t2"),
                DimplexEnergyDailySensor(energy, status, entry, appliance_row, register="t2"),
            ]
        )
    async_add_entities(devices)


class DimplexRoomTemperatureSensor(DimplexEntity, SensorEntity):
    """Room temperature sensor for an appliance."""

    _attr_name = "Room temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_room_temperature"

    @property
    def native_value(self):
        """Return the room temperature."""
        status = self._status
        return status.RoomTemperature if status else None


class _DimplexTemperatureSensor(DimplexEntity, SensorEntity):
    """Base class for temperature sensors backed by ApplianceStatus fields."""

    _status_attr: str
    _entity_suffix: str
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_{self._entity_suffix}"

    @property
    def native_value(self):
        status = self._status
        if status is None:
            return None
        return getattr(status, self._status_attr, None)


class DimplexTargetTemperatureSensor(_DimplexTemperatureSensor):
    """Active set-point temperature sensor."""

    _status_attr = "ActiveSetPointTemperature"
    _entity_suffix = "target_temperature"
    _attr_name = "Target temperature"


class DimplexBoostTemperatureSensor(_DimplexTemperatureSensor):
    """Boost mode target temperature sensor."""

    _status_attr = "BoostTemperature"
    _entity_suffix = "boost_temperature"
    _attr_name = "Boost temperature"


class DimplexAwayTemperatureSensor(_DimplexTemperatureSensor):
    """Away mode target temperature sensor."""

    _status_attr = "AwayTemperature"
    _entity_suffix = "away_temperature"
    _attr_name = "Away temperature"


class DimplexSetbackTemperatureSensor(_DimplexTemperatureSensor):
    """Setback temperature sensor."""

    _status_attr = "SetbackTemperature"
    _entity_suffix = "setback_temperature"
    _attr_name = "Setback temperature"


class _DimplexDiagnosticSensor(DimplexEntity, SensorEntity):
    """Base class for diagnostic string/code sensors."""

    _status_attr: str
    _entity_suffix: str
    _attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_{self._entity_suffix}"

    @property
    def native_value(self):
        status = self._status
        if status is None:
            return None
        value = getattr(status, self._status_attr, None)
        return value if value not in (None, "") else None


class DimplexErrorCodeSensor(_DimplexDiagnosticSensor):
    """Appliance error code diagnostic sensor."""

    _status_attr = "ErrorCode"
    _entity_suffix = "error_code"
    _attr_name = "Error code"
    _attr_icon = "mdi:alert-circle"


class DimplexWarningCodeSensor(_DimplexDiagnosticSensor):
    """Appliance warning code diagnostic sensor."""

    _status_attr = "WarningCode"
    _entity_suffix = "warning_code"
    _attr_name = "Warning code"
    _attr_icon = "mdi:alert"


class DimplexLastTelemDateSensor(DimplexEntity, SensorEntity):
    """Last telemetry timestamp reported by the appliance."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"
    _attr_name = "Last telemetry"
    _attr_entity_registry_enabled_default = False

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_last_telem"

    @property
    def available(self) -> bool:
        """Available when we have a last-telem value even if overview is empty."""
        if not CoordinatorEntity.available.__get__(self, type(self)):
            return False
        return self.native_value is not None

    @property
    def native_value(self):
        status = self._status
        if status is not None and getattr(status, "LastTelemDate", None) is not None:
            return status.LastTelemDate
        return getattr(self._appliance, "LastTelemDate", None)


class _DimplexEnergySensorBase(CoordinatorEntity, SensorEntity):
    """Energy sensor backed by the energy coordinator."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    _mode: str  # "daily" | "lifetime"
    _register: str  # "t1" | "t2"
    _entity_suffix: str

    def __init__(
        self,
        energy_coordinator,
        status_coordinator,
        config_entry,
        appliance_row: dict[str, Any],
        *,
        register: str,
    ) -> None:
        super().__init__(energy_coordinator)
        self._status_coordinator = status_coordinator
        self.config_entry = config_entry
        self._appliance = appliance_row["appliance"]
        self._hub = appliance_row["hub"]
        self._zone = appliance_row["zone"]
        self._register = register

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_{self._entity_suffix}"

    @property
    def device_info(self):
        appliance_type = getattr(self._appliance, "ApplianceType", None)
        model = self._appliance.ApplianceModel
        if appliance_type and model and appliance_type not in str(model):
            model = f"{appliance_type} {model}"
        info = {
            "identifiers": {(DOMAIN, self._appliance.ApplianceId)},
            "name": self._appliance.FriendlyName,
            "manufacturer": "Dimplex",
            "model": model,
            "serial_number": self._appliance.ApplianceId,
            "suggested_area": self._zone.ZoneName,
            "via_device": (DOMAIN, self._hub.HubId),
        }
        firmware = getattr(self._appliance, "FirmwareVersion", None)
        if firmware:
            info["sw_version"] = str(firmware)
        return info

    @property
    def _energy_points(self) -> list[tuple[datetime | None, float]]:
        energy = (self.coordinator.data or {}).get("energy") or {}
        hub_points = energy.get(self._hub.HubId) or {}
        return hub_points.get(self._register, {}).get(self._appliance.ApplianceId, [])

    def _local_tz(self):
        try:
            return dt_util.get_default_time_zone()
        except Exception:
            return ZoneInfo("UTC")

    def _summary(self):
        points = self._energy_points
        if not points:
            return None
        return summarise_energy(
            points,
            mode=self._mode,  # type: ignore[arg-type]
            now=dt_util.now(),
            tz=self._local_tz(),
        )

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        summary = self._summary()
        return summary is not None and summary.point_count > 0

    @property
    def native_value(self) -> float | None:
        summary = self._summary()
        if summary is None or summary.point_count == 0:
            return None
        return summary.total_kwh

    @property
    def last_reset(self) -> datetime | None:
        summary = self._summary()
        if summary is None:
            return None
        return summary.start

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        summary = self._summary()
        if summary is None:
            return {}
        return {
            "mode": summary.mode,
            "register": self._register,
            "window_start": summary.start.isoformat() if summary.start else None,
            "window_end": summary.end.isoformat() if summary.end else None,
            "telemetry_points": summary.point_count,
        }


class DimplexEnergyLifetimeSensor(_DimplexEnergySensorBase):
    """Cumulative lifetime kWh (sum of all known daily points)."""

    _mode = "lifetime"

    def __init__(self, energy_coordinator, status_coordinator, config_entry, appliance_row, *, register: str) -> None:
        super().__init__(energy_coordinator, status_coordinator, config_entry, appliance_row, register=register)
        if register == "t1":
            # Keep legacy unique_id for primary lifetime so existing entities migrate cleanly.
            self._entity_suffix = "energy"
            self._attr_name = "Energy lifetime"
        else:
            self._entity_suffix = "energy_t2"
            self._attr_name = "Energy T2 lifetime"
            self._attr_entity_registry_enabled_default = False


class DimplexEnergyDailySensor(_DimplexEnergySensorBase):
    """kWh for the current local calendar day (from midnight)."""

    _mode = "daily"

    def __init__(self, energy_coordinator, status_coordinator, config_entry, appliance_row, *, register: str) -> None:
        super().__init__(energy_coordinator, status_coordinator, config_entry, appliance_row, register=register)
        if register == "t1":
            self._entity_suffix = "energy_daily"
            self._attr_name = "Energy today"
        else:
            self._entity_suffix = "energy_t2_daily"
            self._attr_name = "Energy T2 today"
            self._attr_entity_registry_enabled_default = False
