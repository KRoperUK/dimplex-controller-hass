"""Binary sensor platform for dimplex_controller."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN
from .entity import DimplexEntity


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup binary_sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices(
        [
            DimplexComfortBinarySensor(coordinator, entry, appliance_row)
            for appliance_row in coordinator.data.get("appliances", [])
        ]
    )


class DimplexComfortBinarySensor(DimplexEntity, BinarySensorEntity):
    """Comfort status binary sensor."""

    @property
    def name(self):
        """Return the name of the binary_sensor."""
        return f"{self._appliance.FriendlyName} Comfort"

    @property
    def is_on(self):
        """Return true if the binary_sensor is on."""
        status = self._status
        return bool(status and status.ComfortStatus)
