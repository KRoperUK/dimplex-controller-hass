"""Water heater platform for Dimplex hot-water cylinders.

Read-only for now: every cylinder control endpoint in the library is still
marked untested, so this entity shows what the Dimplex app shows (mode, target
temperature, hot water available) and offers no controls.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import WaterHeaterEntity, WaterHeaterEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import capabilities_for_row
from .const import HOT_WATER_MODES, hot_water_mode, sane_temperature
from .entity import DimplexEntity

# Read-only platform; the coordinator fetches the data.
PARALLEL_UPDATES = 0

# Cylinder water temperatures; the wide physical band is for room sensors.
WATER_TEMP_MIN = 10.0
WATER_TEMP_MAX = 75.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one water heater per hot-water cylinder."""
    runtime = entry.runtime_data
    entities: list[DimplexWaterHeater] = []
    for row in (runtime.status.data or {}).get("appliances", []):
        caps = capabilities_for_row(row["appliance"], row.get("status"), row.get("product"))
        if caps.hot_water:
            entities.append(DimplexWaterHeater(runtime.status, entry, row))
    async_add_entities(entities)


class DimplexWaterHeater(DimplexEntity, WaterHeaterEntity):
    """A Dimplex hot-water cylinder."""

    _attr_name = None
    _attr_translation_key = "cylinder"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = WaterHeaterEntityFeature(0)
    _attr_operation_list = list(HOT_WATER_MODES)
    _attr_min_temp = WATER_TEMP_MIN
    _attr_max_temp = WATER_TEMP_MAX

    def __init__(self, coordinator: Any, config_entry: ConfigEntry, appliance_row: dict[str, Any]) -> None:
        super().__init__(coordinator, config_entry, appliance_row)
        self._attr_unique_id = f"{config_entry.entry_id}_{self._appliance.ApplianceId}_water_heater"

    @property
    def current_operation(self) -> str | None:
        """The app's mode: standby, timer, holiday, boost or hygiene."""
        return hot_water_mode(self._status)

    @property
    def target_temperature(self) -> float | None:
        """Water target temperature."""
        status = self._status
        if status is None:
            return None
        return sane_temperature(
            getattr(status, "ActiveSetPointTemperature", None), lo=WATER_TEMP_MIN, hi=WATER_TEMP_MAX
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Cylinder readings the water heater card has no slot for."""
        status = self._status
        if status is None:
            return {}
        return {
            "hot_water_available": getattr(status, "AvailableHotWater", None),
            "capacity": getattr(status, "Capacity", None),
            "heating_up": getattr(status, "HeatingUp", None),
            "green_energy_active": getattr(status, "IsGreenEnergyActive", None),
            "appliance_modes": getattr(status, "ApplianceModes", None),
        }
