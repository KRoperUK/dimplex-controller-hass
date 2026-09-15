"""Climate platform for Dimplex appliances (Path A control surface)."""

from __future__ import annotations

import functools
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

from .api import ControlRejected, DimplexApiClient
from .capabilities import capabilities_for_row
from .const import (
    AWAY_FLAG,
    AWAY_TEMP_MAX,
    AWAY_TEMP_MIN,
    BOOST_FLAG,
    CONF_BOOST_DURATION,
    DEFAULT_BOOST_DURATION,
    FROST_FLAG,
    TIMER_OFF_LIKE,
    TIMER_USER,
    sane_temperature,
)
from .entity import DimplexEntity
from .errors import control_errors

_LOGGER = logging.getLogger(__name__)

PRESET_COMFORT = "comfort"
PRESET_BOOST = "boost"
PRESET_AWAY = "away"
PRESET_ECO = "eco"

DEFAULT_BOOST_TEMP = 25.0
DEFAULT_BOOST_MINUTES = DEFAULT_BOOST_DURATION
DEFAULT_AWAY_TEMP = 16.0

# The appliance-side states each preset owns. Home Assistant treats a preset as a
# single mutually-exclusive state, so selecting one engages exactly these and clears
# the rest — otherwise switching between two non-comfort presets does nothing
# visible (#173).
_MODE_BOOST = "boost"
_MODE_AWAY = "away"
_MODE_ECO_START = "eco_start"

_PRESET_STATES: dict[str, frozenset[str]] = {
    PRESET_COMFORT: frozenset(),
    PRESET_BOOST: frozenset({_MODE_BOOST}),
    PRESET_AWAY: frozenset({_MODE_AWAY}),
    PRESET_ECO: frozenset({_MODE_ECO_START}),
}

# Capability flag gating each state, so an unsupported one is never engaged.
_MODE_CAPABILITY: dict[str, str] = {
    _MODE_BOOST: "boost",
    _MODE_AWAY: "away",
    _MODE_ECO_START: "eco_start",
}


def _mode_bit(status: Any, flag: int) -> bool | None:
    """Return whether ``flag`` is engaged, or ``None`` if modes are unknown."""
    modes = getattr(status, "ApplianceModes", None)
    if modes is None:
        return None
    try:
        return bool(int(modes) & flag)
    except (TypeError, ValueError):
        return None


def _is_boost_active(status: Any) -> bool:
    """Return True when boost appears active (model property or raw fields).

    Prefers the library's property, then the Boost mode bit, and only falls back
    to ``BoostDuration`` when the appliance reported no modes at all — a
    configured duration can outlive the mode itself.
    """
    if status is None:
        return False
    prop = getattr(type(status), "is_boost_active", None)
    if isinstance(prop, property):
        return bool(status.is_boost_active)
    bit = _mode_bit(status, BOOST_FLAG)
    if bit is not None:
        return bit
    duration = getattr(status, "BoostDuration", None)
    return duration is not None and duration > 0


def _is_away_active(status: Any) -> bool:
    """Return True when away appears active (model property or raw fields).

    As with boost, the Away mode bit wins over ``AwayDateTime``, which can hold
    a stale away-until date after the mode has been cleared.
    """
    if status is None:
        return False
    prop = getattr(type(status), "is_away_active", None)
    if isinstance(prop, property):
        return bool(status.is_away_active)
    bit = _mode_bit(status, AWAY_FLAG)
    if bit is not None:
        return bit
    away_dt = getattr(status, "AwayDateTime", None)
    return bool(away_dt and away_dt not in ("", "0001-01-01T00:00:00"))


def _is_frost_protect_active(status: Any) -> bool:
    """Return True when frost protection is engaged (the app's "off" state)."""
    if status is None:
        return False
    prop = getattr(type(status), "is_frost_protect_active", None)
    if isinstance(prop, property):
        return bool(status.is_frost_protect_active)
    return bool(_mode_bit(status, FROST_FLAG))


def _timer_mode_from_schedule(schedule: Any) -> int | None:
    """Return the integer TimerMode from a schedule payload, if present."""
    if schedule is None:
        return None
    mode = getattr(schedule, "TimerMode", None)
    if mode is None:
        return None
    try:
        return int(mode)
    except (TypeError, ValueError):
        return None


def _is_timer_off_like(timer_mode: int | None) -> bool:
    """True for frost protection / off timer modes (app 'off' for most heaters)."""
    return timer_mode in TIMER_OFF_LIKE


def _translate_control_errors(func: Any) -> Any:
    """Surface Dimplex control failures on this entity as a clear HomeAssistantError.

    Thin wrapper over :func:`.errors.control_errors`, which switch entities and the
    ``dimplex.*`` actions share, so the same failure reads the same way wherever the
    user triggered it (dimplex-controller-hass#149).
    """

    @functools.wraps(func)
    async def _wrapper(self: DimplexClimate, *args: Any, **kwargs: Any) -> Any:
        name = getattr(self._appliance, "FriendlyName", None) or "Dimplex appliance"
        with control_errors(name):
            return await func(self, *args, **kwargs)

    return _wrapper


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate platform."""
    runtime = entry.runtime_data
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

    HVAC OFF engages frost protection, which is how the official app turns a
    heater off — there is no "off" mode, only the 7 °C anti-freeze floor. HEAT
    clears it. Boost/away remain climate presets.
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
    def min_temp(self) -> float:
        """Lowest settable target, from the appliance capability matrix.

        The cloud's own pickers stop at 7 °C — the frost-protection floor — so
        offering less than that just produces rejected writes.
        """
        return float(self._caps.min_temp)

    @property
    def max_temp(self) -> float:
        return float(self._caps.max_temp)

    @property
    def _timer_mode(self) -> int | None:
        schedules = (self.coordinator.data or {}).get("schedules") or {}
        return _timer_mode_from_schedule(schedules.get(self._appliance.ApplianceId))

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

    def _invalidate_schedules(self) -> None:
        invalidate = getattr(self.coordinator, "invalidate_schedules", None)
        if callable(invalidate):
            invalidate()

    @property
    def current_temperature(self) -> float | None:
        """Return the room temperature, ignoring the cloud's 0xFF sentinel.

        The cloud reports 255 for a temperature field with no active value (see
        ``sane_temperature``). Without this filter the thermostat card showed
        255 °C and the recorder stored it.
        """
        status = self._status
        if status is None:
            return None
        return sane_temperature(getattr(status, "RoomTemperature", None))

    @property
    def target_temperature(self) -> float | None:
        status = self._status
        if status is None:
            return None
        if _is_boost_active(status):
            boost = sane_temperature(status.BoostTemperature)
            if boost is not None:
                return boost
        if _is_away_active(status):
            away = sane_temperature(status.AwayTemperature)
            if away is not None:
                return away
        active = sane_temperature(status.ActiveSetPointTemperature)
        if active is not None:
            return active
        return sane_temperature(status.NormalTemperature)

    @property
    def hvac_mode(self) -> HVACMode:
        status = self._status
        if status is None:
            return HVACMode.OFF
        # Frost protection is the app's "off". Appliances left in the legacy
        # frost/off *timer* mode by earlier releases must still read as off.
        if _is_frost_protect_active(status) or _is_timer_off_like(self._timer_mode):
            return HVACMode.OFF
        # Without a clear "off" bit in overview, treat missing temps as off.
        if status.RoomTemperature is None and status.ActiveSetPointTemperature is None:
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        status = self._status
        if status is None or _is_frost_protect_active(status) or _is_timer_off_like(self._timer_mode):
            return HVACAction.OFF
        if status.ComfortStatus:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        status = self._status
        if status is None:
            return None
        # Frost/off is expressed as HVACMode.OFF — do not also surface away/boost.
        if _is_frost_protect_active(status) or _is_timer_off_like(self._timer_mode):
            return None
        if _is_boost_active(status):
            return PRESET_BOOST
        if _is_away_active(status):
            return PRESET_AWAY
        if status.EcoStartEnabled:
            return PRESET_ECO
        return PRESET_COMFORT

    @_translate_control_errors
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature.

        Uses ``SetApplianceSetpointTemperature`` — the endpoint the official app
        uses. It applies immediately and does not touch the stored schedule.
        Appliances that reject it fall back to the legacy schedule rewrite, which
        is what this integration used to do unconditionally and which Quantum
        answers with HTTP 403 (#149).
        """
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        hub_id = self._hub.HubId
        appliance_id = self._appliance.ApplianceId
        try:
            await self._api.async_set_appliance_setpoint(hub_id, appliance_id, float(temperature))
        except ControlRejected as err:
            # Only a refusal (403/405/501) earns the destructive path. A timeout or
            # 5xx raises plain CannotConnect and propagates, because rewriting every
            # timer period over a dropped connection would silently destroy the
            # user's schedule (#197).
            _LOGGER.warning(
                "%s refused the dedicated setpoint endpoint (%s); rewriting its timer "
                "schedule to %s °C instead, which overwrites every period",
                self._appliance.FriendlyName,
                getattr(err, "status", None) or "rejected",
                temperature,
            )
            await self._api.async_set_target_temperature(hub_id, appliance_id, float(temperature))
        await self.coordinator.async_request_refresh()

    @_translate_control_errors
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode.

        OFF → frost protection at 7 °C, which is how the official app turns a
        heater off, plus clearing boost/away. HEAT → clear frost protection, and
        restore user-timer mode for appliances an earlier release parked in the
        frost/off *timer* mode.
        """
        hub_id = self._hub.HubId
        appliance_id = self._appliance.ApplianceId
        status = self._status
        temp = sane_temperature(status.ActiveSetPointTemperature) if status else None
        if temp is None and status is not None:
            temp = sane_temperature(status.NormalTemperature)
        if temp is None:
            temp = DEFAULT_AWAY_TEMP

        if hvac_mode == HVACMode.OFF:
            if _is_boost_active(status):
                await self._api.async_set_boost(
                    hub_id,
                    appliance_id,
                    temperature=temp,
                    enable=False,
                )
            if _is_away_active(status):
                await self._api.async_set_away(
                    hub_id,
                    appliance_id,
                    temperature=temp,
                    enable=False,
                )
            await self._api.async_set_frost_protect(hub_id, appliance_id, enable=True)
        elif hvac_mode == HVACMode.HEAT:
            if _is_frost_protect_active(status):
                await self._api.async_set_frost_protect(hub_id, appliance_id, enable=False)
            if _is_timer_off_like(self._timer_mode):
                # Legacy state: an earlier release wrote the frost/off timer
                # mode, so the schedule needs restoring as well.
                await self._api.async_set_timer_mode(hub_id, appliance_id, TIMER_USER)
                self._invalidate_schedules()

        await self.coordinator.async_request_refresh()

    @_translate_control_errors
    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Apply a climate preset (gated by appliance capabilities).

        A preset is a single mutually-exclusive state, so this engages the states the
        requested preset owns and clears the others. Previously each branch only
        *added* its own state, which made switching between two non-comfort presets a
        no-op — `eco` enabled EcoStart but left Away engaged, and because
        :attr:`preset_mode` resolves boost before away before EcoStart, the entity
        kept reporting ``away`` and nothing appeared to happen (#173).
        """
        allowed = self.preset_modes or []
        if preset_mode not in allowed and preset_mode != PRESET_COMFORT:
            _LOGGER.warning(
                "Preset %s not supported for %s (allowed: %s)",
                preset_mode,
                self._appliance.FriendlyName,
                allowed,
            )
            return

        wanted = _PRESET_STATES.get(preset_mode)
        if wanted is None:
            _LOGGER.warning("Unsupported preset mode: %s", preset_mode)
            return

        status = self._status
        # Temperature to accompany a clear. The cloud wants one on every mode write,
        # so fall back through the appliance's own setpoints before a fixed default.
        fallback_temp = sane_temperature(status.ActiveSetPointTemperature) if status else None
        if fallback_temp is None and status is not None:
            fallback_temp = sane_temperature(status.NormalTemperature)
        if fallback_temp is None:
            fallback_temp = 21.0

        hub_id = self._hub.HubId
        appliance_id = self._appliance.ApplianceId
        caps = self._caps

        # Clear first, so the appliance never holds two conflicting modes at once.
        if _MODE_BOOST not in wanted and _is_boost_active(status):
            await self._api.async_set_boost(hub_id, appliance_id, temperature=fallback_temp, enable=False)
        if _MODE_AWAY not in wanted and _is_away_active(status):
            await self._api.async_set_away(hub_id, appliance_id, temperature=fallback_temp, enable=False)
        if _MODE_ECO_START not in wanted and status and status.EcoStartEnabled:
            await self._api.async_set_eco_start(hub_id, appliance_id, False)

        for state in wanted:
            if not getattr(caps, _MODE_CAPABILITY[state], True):
                _LOGGER.debug("Appliance %s does not support %s", self._appliance.FriendlyName, state)
                continue
            if state == _MODE_BOOST:
                boost_temp = (
                    float(status.BoostTemperature) if status and status.BoostTemperature else DEFAULT_BOOST_TEMP
                )
                await self._api.async_set_boost(
                    hub_id,
                    appliance_id,
                    temperature=boost_temp,
                    duration_minutes=self._boost_minutes,
                    enable=True,
                )
            elif state == _MODE_AWAY:
                away_temp = float(status.AwayTemperature) if status and status.AwayTemperature else DEFAULT_AWAY_TEMP
                # Away tops out well below the setpoint range (#174).
                away_temp = min(max(away_temp, AWAY_TEMP_MIN), AWAY_TEMP_MAX)
                await self._api.async_set_away(hub_id, appliance_id, temperature=away_temp, enable=True)
            elif state == _MODE_ECO_START:
                await self._api.async_set_eco_start(hub_id, appliance_id, True)

        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
