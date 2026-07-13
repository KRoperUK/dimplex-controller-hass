"""Switch platform for dimplex_controller."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import DimplexApiClient
from .const import DOMAIN
from .entity import DimplexEntity


@dataclass(frozen=True, kw_only=True)
class DimplexSwitchEntityDescription(SwitchEntityDescription):
    """Describe a Dimplex toggle switch."""

    is_on_fn: Callable[[Any], bool]
    set_fn: Callable[[DimplexApiClient, str, str, bool], Awaitable[None]]
    icon_on: str
    icon_off: str


async def _set_eco_start(api: DimplexApiClient, hub_id: str, appliance_id: str, enabled: bool) -> None:
    await api.async_set_eco_start(hub_id, appliance_id, enabled)


async def _set_open_window(api: DimplexApiClient, hub_id: str, appliance_id: str, enabled: bool) -> None:
    await api.async_set_open_window_detection(hub_id, appliance_id, enabled)


SWITCHES: tuple[DimplexSwitchEntityDescription, ...] = (
    DimplexSwitchEntityDescription(
        key="ecostart",
        translation_key="ecostart",
        is_on_fn=lambda status: bool(status and status.EcoStartEnabled),
        set_fn=_set_eco_start,
        icon_on="mdi:leaf",
        icon_off="mdi:leaf-off",
    ),
    DimplexSwitchEntityDescription(
        key="open_window_detection",
        translation_key="open_window_detection",
        is_on_fn=lambda status: bool(status and getattr(status, "OpenWindowEnabled", False)),
        set_fn=_set_open_window,
        icon_on="mdi:window-open",
        icon_off="mdi:window-closed",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch platform."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    rows = (runtime.status.data or {}).get("appliances", [])
    entities = [
        DimplexSwitch(runtime.status, entry, appliance_row, runtime.api, description)
        for appliance_row in rows
        for description in SWITCHES
    ]
    async_add_entities(entities)


class DimplexSwitch(DimplexEntity, SwitchEntity):
    """Toggle switch driven by an entity description."""

    entity_description: DimplexSwitchEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        api: DimplexApiClient,
        description: DimplexSwitchEntityDescription,
    ) -> None:
        super().__init__(coordinator, config_entry, appliance_row, description)
        self._api = api

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self.entity_description.is_on_fn(self._status)

    @property
    def icon(self) -> str:
        """Return a state-aware icon."""
        description = self.entity_description
        return description.icon_on if self.is_on else description.icon_off

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.entity_description.set_fn(
            self._api,
            self._hub.HubId,
            self._appliance.ApplianceId,
            True,
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.entity_description.set_fn(
            self._api,
            self._hub.HubId,
            self._appliance.ApplianceId,
            False,
        )
        await self.coordinator.async_request_refresh()
