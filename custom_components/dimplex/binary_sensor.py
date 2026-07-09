"""Binary sensor platform for dimplex_controller."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import DOMAIN
from .entity import DimplexEntity


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup binary_sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices: list[BinarySensorEntity] = [
        DimplexComfortBinarySensor(coordinator, entry, appliance_row)
        for appliance_row in coordinator.data.get("appliances", [])
    ]
    devices.extend(
        DimplexOpenWindowBinarySensor(coordinator, entry, appliance_row)
        for appliance_row in coordinator.data.get("appliances", [])
    )
    devices.extend(
        DimplexSetbackBinarySensor(coordinator, entry, appliance_row)
        for appliance_row in coordinator.data.get("appliances", [])
    )

    seen_hubs: set[str] = set()
    for appliance_row in coordinator.data.get("appliances", []):
        hub = appliance_row["hub"]
        if hub.HubId in seen_hubs:
            continue
        seen_hubs.add(hub.HubId)
        devices.append(DimplexHubConnectedBinarySensor(coordinator, entry, appliance_row))

    async_add_devices(devices)


class DimplexComfortBinarySensor(DimplexEntity, BinarySensorEntity):
    """Comfort status binary sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_comfort"

    @property
    def name(self):
        """Return the name of the binary_sensor."""
        return f"{self._appliance.FriendlyName} Comfort"

    @property
    def icon(self):
        """Return a sofa icon, consistent with the HA climate 'comfort' preset."""
        return "mdi:sofa" if self.is_on else "mdi:sofa-outline"

    @property
    def is_on(self):
        """Return true if the binary_sensor is on."""
        status = self._status
        return bool(status and status.ComfortStatus)


class DimplexOpenWindowBinarySensor(DimplexEntity, BinarySensorEntity):
    """Open-window detection active binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.WINDOW

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_open_window"

    @property
    def name(self):
        return f"{self._appliance.FriendlyName} Open Window"

    @property
    def icon(self):
        return "mdi:window-open" if self.is_on else "mdi:window-closed"

    @property
    def is_on(self):
        status = self._status
        return bool(status and getattr(status, "OpenWindowEnabled", False))


class DimplexSetbackBinarySensor(DimplexEntity, BinarySensorEntity):
    """Setback mode active binary sensor."""

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_setback"

    @property
    def name(self):
        return f"{self._appliance.FriendlyName} Setback"

    @property
    def icon(self):
        return "mdi:thermometer-chevron-down" if self.is_on else "mdi:thermometer"

    @property
    def is_on(self):
        status = self._status
        return bool(status and getattr(status, "SetbackEnabled", False))


class DimplexHubConnectedBinarySensor(DimplexEntity, BinarySensorEntity):
    """Hub connectivity binary sensor.

    Created once per hub. The entity is attached to the first appliance row
    for that hub so it inherits the hub reference from the base entity.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._hub.HubId}_connected"

    @property
    def name(self):
        return f"{getattr(self._hub, 'FriendlyName', None) or self._hub.HubId} Connected"

    @property
    def is_on(self):
        # ConnectionState 1 is observed as connected in the captured traffic.
        return getattr(self._hub, "ConnectionState", None) == 1

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._hub.HubId)},
            "name": getattr(self._hub, "FriendlyName", None) or self._hub.HubId,
            "model": getattr(self._hub, "HubType", None),
            "manufacturer": "Dimplex",
            "sw_version": getattr(self._hub, "FirmwareVersion", None),
        }
