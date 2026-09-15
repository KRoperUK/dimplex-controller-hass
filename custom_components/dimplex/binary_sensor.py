"""Binary sensor platform for dimplex_controller."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ADVANCE_FLAG,
    AWAY_FLAG,
    BOOST_FLAG,
    DOMAIN,
    FROST_FLAG,
    has_any_mode,
)
from .entity import DimplexEntity


@dataclass(frozen=True, kw_only=True)
class DimplexBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a Dimplex binary sensor."""

    is_on_fn: Callable[[Any], bool]
    icon_on: str | None = None
    icon_off: str | None = None


APPLIANCE_BINARY_SENSORS: tuple[DimplexBinarySensorEntityDescription, ...] = (
    DimplexBinarySensorEntityDescription(
        key="comfort",
        translation_key="comfort",
        is_on_fn=lambda status: bool(status and status.ComfortStatus),
        icon_on="mdi:sofa",
        icon_off="mdi:sofa-outline",
    ),
    DimplexBinarySensorEntityDescription(
        key="open_window",
        translation_key="open_window",
        device_class=BinarySensorDeviceClass.WINDOW,
        is_on_fn=lambda status: bool(status and getattr(status, "OpenWindowEnabled", False)),
        icon_on="mdi:window-open",
        icon_off="mdi:window-closed",
    ),
    DimplexBinarySensorEntityDescription(
        key="setback",
        translation_key="setback",
        is_on_fn=lambda status: bool(status and getattr(status, "SetbackEnabled", False)),
        icon_on="mdi:thermometer-chevron-down",
        icon_off="mdi:thermometer",
    ),
    # Which mode the appliance is *actually* in. The climate entity folds these
    # into a single preset, which hid the #163 mismatch between the mode asked
    # for and the mode engaged. Diagnostic, so they stay out of the way until
    # someone goes looking.
    DimplexBinarySensorEntityDescription(
        key="boost_active",
        translation_key="boost_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda status: has_any_mode(status, BOOST_FLAG),
        icon_on="mdi:rocket-launch",
        icon_off="mdi:rocket-launch-outline",
    ),
    DimplexBinarySensorEntityDescription(
        key="away_active",
        translation_key="away_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda status: has_any_mode(status, AWAY_FLAG),
        icon_on="mdi:home-export-outline",
        icon_off="mdi:home-outline",
    ),
    DimplexBinarySensorEntityDescription(
        key="frost_protection",
        translation_key="frost_protection",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda status: has_any_mode(status, FROST_FLAG),
        icon_on="mdi:snowflake",
        icon_off="mdi:snowflake-off",
    ),
    DimplexBinarySensorEntityDescription(
        key="advance_active",
        translation_key="advance_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda status: has_any_mode(status, ADVANCE_FLAG),
        icon_on="mdi:fast-forward",
        icon_off="mdi:fast-forward-outline",
    ),
)

HUB_CONNECTED_DESCRIPTION = DimplexBinarySensorEntityDescription(
    key="connected",
    translation_key="connected",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    is_on_fn=lambda hub: getattr(hub, "ConnectionState", None) == 1,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary_sensor platform."""
    runtime = entry.runtime_data
    coordinator: DataUpdateCoordinator[dict[str, Any]] = runtime.status
    rows = (coordinator.data or {}).get("appliances", [])
    entities: list[BinarySensorEntity] = [
        DimplexBinarySensor(coordinator, entry, appliance_row, description)
        for appliance_row in rows
        for description in APPLIANCE_BINARY_SENSORS
    ]

    seen_hubs: set[str] = set()
    for appliance_row in rows:
        hub = appliance_row["hub"]
        if hub.HubId in seen_hubs:
            continue
        seen_hubs.add(hub.HubId)
        entities.append(DimplexHubConnectedBinarySensor(coordinator, entry, appliance_row))

    async_add_entities(entities)


class DimplexBinarySensor(DimplexEntity, BinarySensorEntity):
    """Binary sensor driven by an entity description."""

    entity_description: DimplexBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        description: DimplexBinarySensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, config_entry, appliance_row, description)

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.entity_description.is_on_fn(self._status)

    @property
    def icon(self) -> str | None:
        """Return a state-aware icon when the description provides one."""
        description = self.entity_description
        if description.icon_on is None or description.icon_off is None:
            return super().icon
        return description.icon_on if self.is_on else description.icon_off


class DimplexHubConnectedBinarySensor(DimplexEntity, BinarySensorEntity):
    """Hub connectivity binary sensor (one per hub)."""

    entity_description = HUB_CONNECTED_DESCRIPTION

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
    ) -> None:
        super().__init__(coordinator, config_entry, appliance_row, HUB_CONNECTED_DESCRIPTION)
        # unique_id uses hub id, not appliance id (legacy / one-per-hub).
        self._attr_unique_id = f"{config_entry.entry_id}_{self._hub.HubId}_connected"

    @property
    def available(self) -> bool:
        """Hub connectivity does not require per-appliance overview."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        """Return true when the hub reports connected."""
        return HUB_CONNECTED_DESCRIPTION.is_on_fn(self._hub)

    @property
    def device_info(self) -> DeviceInfo:
        """Return hub device registry metadata."""
        info: DeviceInfo = {
            "identifiers": {(DOMAIN, self._hub.HubId)},
            "name": getattr(self._hub, "FriendlyName", None) or self._hub.HubId,
            "manufacturer": "Dimplex",
            "model": getattr(self._hub, "HubType", None) or "Hub",
            "serial_number": self._hub.HubId,
        }
        firmware = getattr(self._hub, "FirmwareVersion", None)
        if firmware:
            info["sw_version"] = str(firmware)
        bluetooth = getattr(self._hub, "BluetoothName", None)
        if bluetooth:
            info["hw_version"] = str(bluetooth)
        return info
