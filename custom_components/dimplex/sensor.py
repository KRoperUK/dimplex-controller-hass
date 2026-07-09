"""Sensor platform for dimplex_controller."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfTemperature

from .const import DOMAIN, ENERGY_REPORT_DAYS, ENERGY_REPORT_INTERVAL
from .entity import DimplexEntity


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices: list[SensorEntity] = []
    for appliance_row in coordinator.data.get("appliances", []):
        devices.extend(
            [
                DimplexRoomTemperatureSensor(coordinator, entry, appliance_row),
                DimplexTargetTemperatureSensor(coordinator, entry, appliance_row),
                DimplexBoostTemperatureSensor(coordinator, entry, appliance_row),
                DimplexAwayTemperatureSensor(coordinator, entry, appliance_row),
                DimplexSetbackTemperatureSensor(coordinator, entry, appliance_row),
                DimplexErrorCodeSensor(coordinator, entry, appliance_row),
                DimplexWarningCodeSensor(coordinator, entry, appliance_row),
                DimplexLastTelemDateSensor(coordinator, entry, appliance_row),
                DimplexEnergySensor(coordinator, entry, appliance_row),
                DimplexEnergySensorT2(coordinator, entry, appliance_row),
            ]
        )
    async_add_devices(devices)


class DimplexRoomTemperatureSensor(DimplexEntity, SensorEntity):
    """Room temperature sensor for an appliance."""

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_room_temperature"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._appliance.FriendlyName} Room Temperature"

    @property
    def native_value(self):
        """Return the room temperature."""
        status = self._status
        return status.RoomTemperature if status else None

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return SensorDeviceClass.TEMPERATURE


class _DimplexTemperatureSensor(DimplexEntity, SensorEntity):
    """Base class for temperature sensors backed by ApplianceStatus fields."""

    _status_attr: str
    _suffix: str
    _entity_suffix: str

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_{self._entity_suffix}"

    @property
    def name(self):
        return f"{self._appliance.FriendlyName} {self._suffix}"

    @property
    def native_value(self):
        status = self._status
        if status is None:
            return None
        return getattr(status, self._status_attr, None)

    @property
    def native_unit_of_measurement(self):
        return UnitOfTemperature.CELSIUS

    @property
    def device_class(self):
        return SensorDeviceClass.TEMPERATURE


class DimplexTargetTemperatureSensor(_DimplexTemperatureSensor):
    """Active set-point temperature sensor."""

    _status_attr = "ActiveSetPointTemperature"
    _suffix = "Target Temperature"
    _entity_suffix = "target_temperature"


class DimplexBoostTemperatureSensor(_DimplexTemperatureSensor):
    """Boost mode target temperature sensor."""

    _status_attr = "BoostTemperature"
    _suffix = "Boost Temperature"
    _entity_suffix = "boost_temperature"


class DimplexAwayTemperatureSensor(_DimplexTemperatureSensor):
    """Away mode target temperature sensor."""

    _status_attr = "AwayTemperature"
    _suffix = "Away Temperature"
    _entity_suffix = "away_temperature"


class DimplexSetbackTemperatureSensor(_DimplexTemperatureSensor):
    """Setback temperature sensor."""

    _status_attr = "SetbackTemperature"
    _suffix = "Setback Temperature"
    _entity_suffix = "setback_temperature"


class _DimplexDiagnosticSensor(DimplexEntity, SensorEntity):
    """Base class for diagnostic string/code sensors."""

    _status_attr: str
    _suffix: str
    _icon: str
    _entity_suffix: str

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_{self._entity_suffix}"

    @property
    def name(self):
        return f"{self._appliance.FriendlyName} {self._suffix}"

    @property
    def icon(self):
        return self._icon

    @property
    def native_value(self):
        status = self._status
        if status is None:
            return None
        value = getattr(status, self._status_attr, None)
        return value if value not in (None, "") else None

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Diagnostic sensors are disabled by default to avoid clutter."""
        return False


class DimplexErrorCodeSensor(_DimplexDiagnosticSensor):
    """Appliance error code diagnostic sensor."""

    _status_attr = "ErrorCode"
    _suffix = "Error Code"
    _entity_suffix = "error_code"
    _icon = "mdi:alert-circle"


class DimplexWarningCodeSensor(_DimplexDiagnosticSensor):
    """Appliance warning code diagnostic sensor."""

    _status_attr = "WarningCode"
    _suffix = "Warning Code"
    _entity_suffix = "warning_code"
    _icon = "mdi:alert"


class DimplexLastTelemDateSensor(DimplexEntity, SensorEntity):
    """Last telemetry timestamp reported by the appliance."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_last_telem"

    @property
    def name(self):
        return f"{self._appliance.FriendlyName} Last Telemetry"

    @property
    def native_value(self):
        status = self._status
        # ApplianceStatus does not currently include LastTelemDate, so fall
        # back to the static appliance record from the zone listing.
        if status is not None and getattr(status, "LastTelemDate", None) is not None:
            return status.LastTelemDate
        return self._appliance.LastTelemDate

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False


class DimplexEnergySensor(DimplexEntity, SensorEntity):
    """Cumulative kWh energy used by an appliance (primary register).

    The cloud returns daily kWh values (keyed as ``T1``) with Unix-epoch
    timestamps (keyed as ``TS``) covering all available history. This
    sensor sums every value and exposes the earliest timestamp as
    ``last_reset``, so the Home Assistant Energy Dashboard computes
    ``current_total - previous_reset_value`` correctly for the full
    reported period.

    The sensor is unavailable when the hub returns no data for this
    appliance, preventing fabricated zero readings on the dashboard.
    """

    _attr_icon = "mdi:lightning-bolt"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_energy"

    @property
    def name(self):
        return f"{self._appliance.FriendlyName} Energy"

    @property
    def _energy_points(self) -> list[tuple[datetime | None, float]]:
        energy = self.coordinator.data.get("energy") or {}
        hub_points = energy.get(self._hub.HubId) or {}
        return hub_points.get("t1", {}).get(self._appliance.ApplianceId, [])

    @property
    def available(self) -> bool:
        return bool(self._energy_points)

    @property
    def native_value(self) -> float | None:
        points = self._energy_points
        if not points:
            return None
        return round(sum(value for _, value in points), 3)

    @property
    def last_reset(self) -> datetime:
        points = self._energy_points
        if not points:
            return datetime.now(UTC)
        timestamps = [ts for ts, _ in points if ts is not None]
        if not timestamps:
            return datetime.now(UTC)
        return min(timestamps)

    @property
    def extra_state_attributes(self) -> dict:
        points = self._energy_points
        earliest = min((ts for ts, _ in points if ts is not None), default=None)
        return {
            "window_start": earliest.isoformat() if earliest else None,
            "window_days": ENERGY_REPORT_DAYS,
            "interval": ENERGY_REPORT_INTERVAL,
            "telemetry_points": len(points),
        }


class DimplexEnergySensorT2(DimplexEnergySensor):
    """Cumulative kWh for the secondary energy register (``T2``).

    Some Quantum heaters report a secondary energy channel alongside ``T1``.
    This sensor exposes that register independently; it is only available
    when the cloud returns ``T2`` values for the appliance.
    """

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_energy_t2"

    @property
    def name(self):
        return f"{self._appliance.FriendlyName} Energy T2"

    @property
    def _energy_points(self) -> list[tuple[datetime | None, float]]:
        energy = self.coordinator.data.get("energy") or {}
        hub_points = energy.get(self._hub.HubId) or {}
        return hub_points.get("t2", {}).get(self._appliance.ApplianceId, [])
