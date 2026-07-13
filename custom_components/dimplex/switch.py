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
    rows = (runtime.status.data or {}).get("appliances", [])
    entities: list[SwitchEntity] = []
    for appliance_row in rows:
        entities.append(DimplexEcoStartSwitch(runtime.status, entry, appliance_row, runtime.api))
        entities.append(DimplexOpenWindowSwitch(runtime.status, entry, appliance_row, runtime.api))
    async_add_entities(entities)


class _DimplexToggleSwitch(DimplexEntity, SwitchEntity):
    """Base toggle that calls a boolean API helper."""

    _entity_suffix: str

    def __init__(self, coordinator, config_entry, appliance_row, api) -> None:
        super().__init__(coordinator, config_entry, appliance_row)
        self._api = api

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_{self._entity_suffix}"


class DimplexEcoStartSwitch(_DimplexToggleSwitch):
    """EcoStart toggle switch."""

    _attr_name = "EcoStart"
    _entity_suffix = "ecostart"

    async def async_turn_on(self, **kwargs) -> None:  # pylint: disable=unused-argument
        """Turn on EcoStart."""
        await self._api.async_set_eco_start(self._hub.HubId, self._appliance.ApplianceId, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:  # pylint: disable=unused-argument
        """Turn off EcoStart."""
        await self._api.async_set_eco_start(self._hub.HubId, self._appliance.ApplianceId, False)
        await self.coordinator.async_request_refresh()

    @property
    def icon(self) -> str:
        """Return a leaf icon reflecting the EcoStart state."""
        return "mdi:leaf" if self.is_on else "mdi:leaf-off"

    @property
    def is_on(self) -> bool:
        """Return true if EcoStart is enabled."""
        status = self._status
        return bool(status and status.EcoStartEnabled)


class DimplexOpenWindowSwitch(_DimplexToggleSwitch):
    """Open Window Detection enable/disable switch."""

    _attr_name = "Open window detection"
    _entity_suffix = "open_window_detection"

    async def async_turn_on(self, **kwargs) -> None:  # pylint: disable=unused-argument
        """Enable open-window detection."""
        await self._api.async_set_open_window_detection(self._hub.HubId, self._appliance.ApplianceId, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:  # pylint: disable=unused-argument
        """Disable open-window detection."""
        await self._api.async_set_open_window_detection(self._hub.HubId, self._appliance.ApplianceId, False)
        await self.coordinator.async_request_refresh()

    @property
    def icon(self) -> str:
        """Return a window icon reflecting detection state."""
        return "mdi:window-open" if self.is_on else "mdi:window-closed"

    @property
    def is_on(self) -> bool:
        """Return true if open-window detection is enabled."""
        status = self._status
        return bool(status and getattr(status, "OpenWindowEnabled", False))
