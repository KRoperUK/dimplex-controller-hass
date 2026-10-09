"""Select platform for dimplex_controller.

The boost-duration select lets a user pick the boost length from the discrete
set the appliance actually offers (``capabilities.boost_durations``) rather than
typing a free integer, matching the official app's own picker and keeping an
invalid duration from ever reaching the climate boost preset (#252).

It is a *preference* entity: choosing a value does not start a boost, it records
how long the next boost (via the climate boost preset) will run for this
appliance. The climate entity reads the chosen value from ``runtime_data`` and
prefers it over the entry-wide ``CONF_BOOST_DURATION`` option.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .capabilities import capabilities_for_row
from .entity import DimplexEntity

BOOST_DURATION_KEY = "boost_duration"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    runtime = entry.runtime_data
    entities: list[SelectEntity] = []
    for row in (runtime.status.data or {}).get("appliances", []):
        caps = capabilities_for_row(row["appliance"], row.get("status"), row.get("product"))
        # Only boost-capable appliances have a boost length to choose. A cylinder
        # or any appliance the cloud will not accept a boost for gets no entity,
        # the same way the status sensors gate on their capability flag (#199).
        if not getattr(caps, "boost", False):
            continue
        entities.append(DimplexBoostDurationSelect(runtime.status, entry, row, caps))
    async_add_entities(entities)


class DimplexBoostDurationSelect(DimplexEntity, SelectEntity, RestoreEntity):
    """Pick the boost length from the appliance's discrete ``boost_durations``."""

    entity_description: SelectEntityDescription
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        caps: Any,
    ) -> None:
        super().__init__(
            coordinator,
            config_entry,
            appliance_row,
            SelectEntityDescription(key=BOOST_DURATION_KEY, translation_key=BOOST_DURATION_KEY),
        )
        # Options come straight from the capability matrix, so they always match
        # the durations the cloud will accept for this appliance.
        durations = getattr(caps, "boost_durations", None) or ()
        self._attr_options = [str(int(minutes)) for minutes in durations]
        default = getattr(caps, "default_boost_minutes", None)
        self._default = str(int(default)) if default is not None and str(int(default)) in self._attr_options else None

    @property
    def available(self) -> bool:
        """A preference entity is usable regardless of live overview state.

        ``DimplexEntity.available`` additionally requires a live status row, which a
        boost-duration preference does not need — so this mirrors
        ``CoordinatorEntity.available`` (the coordinator's own success flag) instead.
        """
        return bool(self.coordinator.last_update_success)

    @property
    def current_option(self) -> str | None:
        """The chosen boost length (minutes, as a string option)."""
        chosen = self.config_entry.runtime_data.boost_minutes.get(self._appliance.ApplianceId)
        if chosen is not None:
            option = str(int(chosen))
            if option in self._attr_options:
                return option
        return self._default

    async def async_added_to_hass(self) -> None:
        """Restore the last chosen duration across restarts."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in self._attr_options:
            self.config_entry.runtime_data.boost_minutes[self._appliance.ApplianceId] = int(last.state)

    async def async_select_option(self, option: str) -> None:
        """Record the chosen boost length for this appliance."""
        if option not in self._attr_options:
            raise ValueError(f"{option} is not a valid boost duration for {self._appliance.FriendlyName}")
        self.config_entry.runtime_data.boost_minutes[self._appliance.ApplianceId] = int(option)
        self.async_write_ha_state()
