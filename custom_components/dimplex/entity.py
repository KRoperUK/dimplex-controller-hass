"""Base entity class for dimplex integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class DimplexEntity(CoordinatorEntity):
    """Shared entity behavior for status-backed entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry, appliance_row: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._appliance_row = appliance_row
        self._appliance = appliance_row["appliance"]
        self._hub = appliance_row["hub"]
        self._zone = appliance_row["zone"]

    @property
    def _status(self):
        """Return current appliance status from coordinator snapshot."""
        data = self.coordinator.data or {}
        for row in data.get("appliances", []):
            if row["appliance"].ApplianceId == self._appliance.ApplianceId:
                return row.get("status")
        return None

    @property
    def available(self) -> bool:
        """Entities that need live overview are unavailable when status is missing."""
        if not super().available:
            return False
        return self._status is not None

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}"

    @property
    def device_info(self):
        """Return appliance device registry metadata.

        The Dimplex cloud does not expose a local IP/MAC for radiators; the
        appliance id is the stable serial used by the hub API.
        """
        appliance_type = getattr(self._appliance, "ApplianceType", None)
        model = self._appliance.ApplianceModel
        if appliance_type and model and appliance_type not in model:
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
        series = getattr(self._appliance, "SeriesIdentifier", None)
        if series:
            info["hw_version"] = str(series)
        return info
