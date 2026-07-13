"""Climate platform for Dimplex appliances (Path A control surface)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import DimplexApiClient
from .capabilities import capabilities_for_row
from .const import CONF_BOOST_DURATION, DEFAULT_BOOST_DURATION, DOMAIN
from .entity import DimplexEntity

_LOGGER = logging.getLogger(__name__)

PRESET_COMFORT = "comfort"
PRESET_BOOST = "boost"
PRESET_AWAY = "away"
PRESET_ECO = "eco"

DEFAULT_BOOST_TEMP = 25.0
DEFAULT_BOOST_MINUTES = DEFAULT_BOOST_DURATION
DEFAULT_AWAY_TEMP = 16.0
_BOOST_FLAG = 16
_AWAY_FLAG = 32


def _is_boost_active(status: Any) -> bool:
    """Return True when boost appears active (model property or raw fields)."""
    if status is None:
        return False
    prop = getattr(type(status), "is_boost_active", None)
    if isinstance(prop, property):
        return bool(status.is_boost_active)
    duration = getattr(status, "BoostDuration", None)
    if duration is not None and duration > 0:
        return True
    modes = getattr(status, "ApplianceModes", None) or 0
    return bool(modes & _BOOST_FLAG)


def _is_away_active(status: Any) -> bool:
    """Return True when away appears active (model property or raw fields)."""
    if status is None:
        return False
    prop = getattr(type(status), "is_away_active", None)
    if isinstance(prop, property):
        return bool(status.is_away_active)
    away_dt = getattr(status, "AwayDateTime", None)
    if away_dt and away_dt not in ("", "0001-01-01T00:00:00"):
        return True
    modes = getattr(status, "ApplianceModes", None) or 0
    return bool(modes & _AWAY_FLAG)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate platform."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for row in (runtime.status.data or {}).get("appliances", []):
        caps = capabilities_for_row(row["appliance"], row.get("status"))
        if not caps.climate:
            _LOGGER.debug(
                "Skipping climate for non-room appliance %s",
                getattr(row["appliance"], "FriendlyName", None),
            )
            continue
        entities.append(DimplexClimate(runtime.status, entry, row, runtime.api))
    async_add_entities(entities)


class DimplexClimate(DimplexEntity, ClimateEntity):
    """Thermostat-style control for a Dimplex appliance.

    HVAC OFF clears boost/away only — the cloud has no confirmed true power-off
    mapping for all models. Use timer/frost modes (future) for deeper off.
    """

    _attr_name = None  # device name is the climate entity name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 0.5

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        api: DimplexApiClient,
    ) -> None:
        super().__init__(coordinator, config_entry, appliance_row)
        self._api = api

    @property
    def _caps(self) -> Any:
        return capabilities_for_row(self._appliance, self._status)

    @property
    def unique_id(self) -> str:
        return f"{self.config_entry.entry_id}_{self._appliance.ApplianceId}_climate"

    @property
    def preset_modes(self) -> list[str] | None:
        return list(self._caps.climate_presets())

    @property
    def _boost_minutes(self) -> int:
        raw = self.config_entry.options.get(CONF_BOOST_DURATION, DEFAULT_BOOST_MINUTES)
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_BOOST_MINUTES
        return max(1, min(minutes, 24 * 60))

    @property
    def current_temperature(self) -> float | None:
        status = self._status
        return status.RoomTemperature if status else None

    @property
    def target_temperature(self) -> float | None:
        status = self._status
        if status is None:
            return None
        if _is_boost_active(status) and status.BoostTemperature is not None:
            return float(status.BoostTemperature)
        if _is_away_active(status) and status.AwayTemperature is not None:
            return float(status.AwayTemperature)
        if status.ActiveSetPointTemperature is not None:
            return float(status.ActiveSetPointTemperature)
        if status.NormalTemperature is not None:
            return float(status.NormalTemperature)
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        status = self._status
        if status is None:
            return HVACMode.OFF
        # Without a clear "off" bit in overview, treat missing temps as off.
        if status.RoomTemperature is None and status.ActiveSetPointTemperature is None:
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        status = self._status
        if status is None:
            return HVACAction.OFF
        if status.ComfortStatus:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        status = self._status
        if status is None:
            return None
        if _is_boost_active(status):
            return PRESET_BOOST
        if _is_away_active(status):
            return PRESET_AWAY
        if status.EcoStartEnabled:
            return PRESET_ECO
        return PRESET_COMFORT

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self._api.async_set_target_temperature(
            self._hub.HubId,
            self._appliance.ApplianceId,
            float(temperature),
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode.

        Full off/on mapping depends on timer modes; for now OFF clears boost/away
        and HEAT is a no-op refresh (setpoint via set_temperature).
        """
        if hvac_mode == HVACMode.OFF:
            status = self._status
            temp = float(status.ActiveSetPointTemperature or status.NormalTemperature or 16.0) if status else 16.0
            if _is_boost_active(status):
                await self._api.async_set_boost(
                    self._hub.HubId,
                    self._appliance.ApplianceId,
                    temperature=temp,
                    enable=False,
                )
            if _is_away_active(status):
                await self._api.async_set_away(
                    self._hub.HubId,
                    self._appliance.ApplianceId,
                    temperature=temp,
                    enable=False,
                )
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Apply a climate preset (gated by appliance capabilities)."""
        allowed = self.preset_modes or []
        if preset_mode not in allowed and preset_mode != PRESET_COMFORT:
            _LOGGER.warning(
                "Preset %s not supported for %s (allowed: %s)",
                preset_mode,
                self._appliance.FriendlyName,
                allowed,
            )
            return

        status = self._status
        comfort_temp = 21.0
        if status and status.ActiveSetPointTemperature is not None:
            comfort_temp = float(status.ActiveSetPointTemperature)
        elif status and status.NormalTemperature is not None:
            comfort_temp = float(status.NormalTemperature)

        hub_id = self._hub.HubId
        appliance_id = self._appliance.ApplianceId
        caps = self._caps

        if preset_mode == PRESET_BOOST:
            if not caps.boost:
                return
            boost_temp = float(status.BoostTemperature) if status and status.BoostTemperature else DEFAULT_BOOST_TEMP
            await self._api.async_set_boost(
                hub_id,
                appliance_id,
                temperature=boost_temp,
                duration_minutes=self._boost_minutes,
                enable=True,
            )
        elif preset_mode == PRESET_AWAY:
            if not caps.away:
                return
            away_temp = float(status.AwayTemperature) if status and status.AwayTemperature else DEFAULT_AWAY_TEMP
            await self._api.async_set_away(hub_id, appliance_id, temperature=away_temp, enable=True)
        elif preset_mode == PRESET_ECO:
            if not caps.eco_start:
                return
            await self._api.async_set_eco_start(hub_id, appliance_id, True)
        elif preset_mode == PRESET_COMFORT:
            if _is_boost_active(status):
                await self._api.async_set_boost(hub_id, appliance_id, temperature=comfort_temp, enable=False)
            if _is_away_active(status):
                await self._api.async_set_away(hub_id, appliance_id, temperature=comfort_temp, enable=False)
            if status and status.EcoStartEnabled:
                await self._api.async_set_eco_start(hub_id, appliance_id, False)
        else:
            _LOGGER.warning("Unsupported preset mode: %s", preset_mode)
            return

        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
