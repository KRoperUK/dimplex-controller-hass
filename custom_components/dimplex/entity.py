"""Base entity class for dimplex integration."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class DimplexEntity(CoordinatorEntity):
    """Shared entity behavior."""

    def __init__(self, coordinator, config_entry, appliance_row):
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._appliance_row = appliance_row
        self._appliance = appliance_row["appliance"]
        self._hub = appliance_row["hub"]
        self._zone = appliance_row["zone"]

    @property
    def _status(self):
        """Return current appliance status from coordinator snapshot."""
        for row in self.coordinator.data.get("appliances", []):
            if row["appliance"].ApplianceId == self._appliance.ApplianceId:
                return row.get("status")
        return None

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._appliance.ApplianceId)},
            "name": self._appliance.FriendlyName,
            "model": self._appliance.ApplianceModel,
            "manufacturer": "Dimplex",
            "suggested_area": self._zone.ZoneName,
        }
