"""Sensor platform for dimplex_controller."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature

from .const import DOMAIN
from .entity import DimplexEntity


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices(
        [
            DimplexRoomTemperatureSensor(coordinator, entry, appliance_row)
            for appliance_row in coordinator.data.get("appliances", [])
        ]
    )


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
        """Return de device class of the sensor."""
        return SensorDeviceClass.TEMPERATURE
