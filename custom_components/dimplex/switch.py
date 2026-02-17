"""Switch platform for dimplex_controller."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .entity import DimplexEntity


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices(
        [
            DimplexEcoStartSwitch(coordinator, entry, appliance_row)
            for appliance_row in coordinator.data.get("appliances", [])
        ]
    )


class DimplexEcoStartSwitch(DimplexEntity, SwitchEntity):
    """EcoStart toggle switch."""

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn on the switch."""
        await self.coordinator.api.async_set_eco_start(
            self._hub.HubId,
            self._appliance.ApplianceId,
            True,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn off the switch."""
        await self.coordinator.api.async_set_eco_start(
            self._hub.HubId,
            self._appliance.ApplianceId,
            False,
        )
        await self.coordinator.async_request_refresh()

    @property
    def name(self):
        """Return the name of the switch."""
        return f"{self._appliance.FriendlyName} EcoStart"

    @property
    def is_on(self):
        """Return true if the switch is on."""
        status = self._status
        return bool(status and status.EcoStartEnabled)
