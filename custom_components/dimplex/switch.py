"""Switch platform for dimplex_controller."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import DimplexEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up switch platform."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            DimplexEcoStartSwitch(runtime.status, entry, appliance_row, runtime.api)
            for appliance_row in (runtime.status.data or {}).get("appliances", [])
        ]
    )


class DimplexEcoStartSwitch(DimplexEntity, SwitchEntity):
    """EcoStart toggle switch."""

    _attr_name = "EcoStart"

    def __init__(self, coordinator, config_entry, appliance_row, api) -> None:
        super().__init__(coordinator, config_entry, appliance_row)
        self._api = api

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn on the switch."""
        await self._api.async_set_eco_start(
            self._hub.HubId,
            self._appliance.ApplianceId,
            True,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn off the switch."""
        await self._api.async_set_eco_start(
            self._hub.HubId,
            self._appliance.ApplianceId,
            False,
        )
        await self.coordinator.async_request_refresh()

    @property
    def icon(self):
        """Return a leaf icon reflecting the EcoStart state."""
        return "mdi:leaf" if self.is_on else "mdi:leaf-off"

    @property
    def is_on(self):
        """Return true if the switch is on."""
        status = self._status
        return bool(status and status.EcoStartEnabled)
