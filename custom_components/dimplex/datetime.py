"""Datetime platform: when a hot-water cylinder's holiday ends."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .capabilities import capabilities_for_row
from .entity import DimplexEntity
from .holiday import HolidayManager

# Date writes hit the cloud one at a time.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one holiday-end picker per hot-water cylinder."""
    runtime = entry.runtime_data
    entities: list[DimplexHolidayEnd] = []
    for row in (runtime.status.data or {}).get("appliances", []):
        caps = capabilities_for_row(row["appliance"], row.get("status"), row.get("product"))
        if caps.hot_water:
            entities.append(DimplexHolidayEnd(runtime.status, entry, row, runtime.holiday))
    async_add_entities(entities)


class DimplexHolidayEnd(DimplexEntity, DateTimeEntity, RestoreEntity):
    """The date and time Holiday is switched off."""

    _attr_translation_key = "holiday_end"
    _attr_icon = "mdi:airplane-landing"

    def __init__(
        self,
        coordinator: Any,
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        holiday: HolidayManager,
    ) -> None:
        super().__init__(coordinator, config_entry, appliance_row)
        self._attr_unique_id = f"{config_entry.entry_id}_{self._appliance.ApplianceId}_holiday_end"
        self._holiday = holiday

    @property
    def available(self) -> bool:
        """Choosing an end does not need live status."""
        return True

    @property
    def native_value(self) -> datetime | None:
        return self._holiday.ends.get(self._appliance.ApplianceId)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        appliance_id = self._appliance.ApplianceId
        self.async_on_remove(self._holiday.add_listener(appliance_id, self.async_write_ha_state))
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, "unknown", "unavailable"):
            restored = dt_util.parse_datetime(last.state)
            if restored is not None:
                self._holiday.restore_end(appliance_id, restored)

    async def async_set_value(self, value: datetime) -> None:
        await self._holiday.async_set_end(self._appliance.ApplianceId, value)
