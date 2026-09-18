"""Base entity class for dimplex integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import DOMAIN


def resolve_via_device_id(
    hass: HomeAssistant | None,
    identifier: tuple[str, str],
    config_entry_id: str | None,
) -> str | None:
    """Resolve a parent device identifier to its registry ``via_device_id``.

    Home Assistant deprecated the ``via_device`` (identifier tuple) ``DeviceInfo``
    key in favour of ``via_device_id`` (the parent's registry id). Parent hub /
    zone devices are pre-registered in ``async_setup_entry`` before platforms are
    forwarded, so the lookup succeeds by the time appliance/zone entities publish
    their device info. Returns ``None`` when the parent cannot be resolved (e.g.
    the entity has not been added to hass yet in unit tests); callers then simply
    omit the link.
    """
    if hass is None or not config_entry_id:
        return None
    registry = dr.async_get(hass)
    parent = registry.async_get_device_by_identifier(identifier, config_entry_id)
    return parent.id if parent else None


class DimplexEntity(CoordinatorEntity[DataUpdateCoordinator[dict[str, Any]]]):
    """Shared entity behavior for status-backed entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        description: EntityDescription | None = None,
        *,
        unique_id_suffix: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._appliance_row = appliance_row
        self._appliance = appliance_row["appliance"]
        self._hub = appliance_row["hub"]
        self._zone = appliance_row["zone"]
        # Catalogue row for this appliance, when the account-wide product list
        # could be matched to it. Feeds capability derivation (#199).
        self._product = appliance_row.get("product")
        if description is not None:
            self.entity_description = description
            suffix = unique_id_suffix if unique_id_suffix is not None else description.key
            self._attr_unique_id = f"{config_entry.entry_id}_{self._appliance.ApplianceId}_{suffix}"

    @property
    def _status(self) -> Any:
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
    def device_info(self) -> DeviceInfo:
        """Return appliance device registry metadata.

        The Dimplex cloud does not expose a local IP/MAC for radiators; the
        appliance id is the stable serial used by the hub API.
        """
        appliance_type = getattr(self._appliance, "ApplianceType", None)
        model = self._appliance.ApplianceModel
        if appliance_type and model and appliance_type not in model:
            model = f"{appliance_type} {model}"

        zone_id = getattr(self._zone, "ZoneId", None)
        via: tuple[str, str] = (DOMAIN, f"zone_{zone_id}") if zone_id else (DOMAIN, self._hub.HubId)

        info: DeviceInfo = {
            "identifiers": {(DOMAIN, self._appliance.ApplianceId)},
            "name": self._appliance.FriendlyName,
            "manufacturer": "Dimplex",
            "model": model,
            "serial_number": self._appliance.ApplianceId,
            "suggested_area": self._zone.ZoneName,
        }
        via_device_id = resolve_via_device_id(self.hass, via, getattr(self.config_entry, "entry_id", None))
        if via_device_id:
            info["via_device_id"] = via_device_id
        firmware = getattr(self._appliance, "FirmwareVersion", None)
        if firmware:
            info["sw_version"] = str(firmware)
        series = getattr(self._appliance, "SeriesIdentifier", None)
        if series:
            info["hw_version"] = str(series)
        return info
