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
    devices: list[SensorEntity] = [
        DimplexRoomTemperatureSensor(coordinator, entry, appliance_row)
        for appliance_row in coordinator.data.get("appliances", [])
    ]
    devices.extend(
        DimplexEnergySensor(coordinator, entry, appliance_row)
        for appliance_row in coordinator.data.get("appliances", [])
    )
    async_add_devices(devices)


class DimplexRoomTemperatureSensor(DimplexEntity, SensorEntity):
    """Room temperature sensor for an appliance."""

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


class DimplexEnergySensor(DimplexEntity, SensorEntity):
    """Cumulative kWh energy used by an appliance.

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
        return hub_points.get(self._appliance.ApplianceId, [])

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
