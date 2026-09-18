"""Number platform for dimplex_controller — appliance values that are a plain number."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import DimplexApiClient
from .capabilities import capabilities_for_row
from .const import OPTIMISTIC_UPDATES, sane_temperature
from .entity import DimplexEntity
from .errors import control_errors


@dataclass(frozen=True, kw_only=True)
class DimplexNumberEntityDescription(NumberEntityDescription):
    """Describe a writable numeric appliance value.

    ``capability`` names the flag on the resolved capability matrix that has to be
    true for the entity to be created at all — the library's capability data is
    what decides whether the cloud will accept the write (#199).
    """

    capability: str
    read_capability: str
    value_fn: Callable[[Any], float | None]
    set_fn: Callable[[DimplexApiClient, str, str, float], Awaitable[None]]


async def _set_setback_temperature(api: DimplexApiClient, hub_id: str, appliance_id: str, value: float) -> None:
    await api.async_set_setback_temperature(hub_id, appliance_id, value)


NUMBER_ENTITIES: tuple[DimplexNumberEntityDescription, ...] = (
    DimplexNumberEntityDescription(
        key="setback_target",
        translation_key="setback_target",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_step=0.5,
        mode=NumberMode.BOX,
        # Setback was read-only: the cloud reports SetbackTemperature and accepts
        # SetSetbackTemperature, but nothing wrote it, so it could be seen and not
        # changed (#199).
        capability="setback_write",
        read_capability="setback_read",
        value_fn=lambda status: sane_temperature(getattr(status, "SetbackTemperature", None)),
        set_fn=_set_setback_temperature,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    runtime = entry.runtime_data
    entities: list[NumberEntity] = []
    for row in (runtime.status.data or {}).get("appliances", []):
        caps = capabilities_for_row(row["appliance"], row.get("status"), row.get("product"))
        for description in NUMBER_ENTITIES:
            # Both flags, deliberately: a write we could perform but never read back
            # would leave the entity showing a stale number forever.
            if not getattr(caps, description.capability, False) or not getattr(
                caps, description.read_capability, False
            ):
                continue
            entities.append(DimplexNumber(runtime.status, entry, row, runtime.api, description))
    async_add_entities(entities)


class DimplexNumber(DimplexEntity, NumberEntity):
    """A writable numeric value driven by an entity description."""

    entity_description: DimplexNumberEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        api: DimplexApiClient,
        description: DimplexNumberEntityDescription,
    ) -> None:
        super().__init__(coordinator, config_entry, appliance_row, description)
        self._api = api
        # A value written but not yet reflected by a poll. Same rationale as the
        # climate entity's optimistic state: the debounced refresh usually lands
        # before the cloud has applied the write, and the entity snapping back reads
        # as "my change didn't take" (#210).
        self._pending: float | None = None
        self._pending_updates_left = 0

    @property
    def _caps(self) -> Any:
        return capabilities_for_row(self._appliance, self._status, self._product)

    @property
    def native_min_value(self) -> float:
        """Lowest value the cloud accepts, from the capability matrix."""
        return float(self._caps.min_temp)

    @property
    def native_max_value(self) -> float:
        """Highest value the cloud accepts, from the capability matrix."""
        return float(self._caps.max_temp)

    @property
    def native_value(self) -> float | None:
        """The reported value, or one written but not yet polled back."""
        if self._pending is not None:
            return self._pending
        return self.entity_description.value_fn(self._status)

    def _handle_coordinator_update(self) -> None:
        """Drop the pending value once the poll agrees, or once it expires."""
        if self._pending is not None:
            reported = self.entity_description.value_fn(self._status)
            if reported is not None and abs(reported - self._pending) <= 0.01:
                self._pending = None
            else:
                self._pending_updates_left -= 1
                if self._pending_updates_left <= 0:
                    self._pending = None
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Write the value to the appliance."""
        name = getattr(self._appliance, "FriendlyName", None) or "Dimplex appliance"
        with control_errors(name):
            await self.entity_description.set_fn(
                self._api,
                self._hub.HubId,
                self._appliance.ApplianceId,
                float(value),
            )
        self._pending = float(value)
        self._pending_updates_left = OPTIMISTIC_UPDATES
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
