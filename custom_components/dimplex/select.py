"""Select platform for dimplex_controller.

The boost-duration select lets a user pick the boost length from the discrete
set the appliance actually offers (``capabilities.boost_durations``) rather than
typing a free integer, matching the official app's own picker and keeping an
invalid duration from ever reaching the climate boost preset (#252).

It is a *preference* entity: choosing a value does not start a boost, it records
how long the next boost (via the climate boost preset) will run for this
appliance. The climate entity reads the chosen value from ``runtime_data`` and
prefers it over the entry-wide ``CONF_BOOST_DURATION`` option.

The schedule-profile select is a *control* entity: choosing a value applies
that schedule profile (user timer / home all day / out all day) to the heater
through the API, mirroring the official app's schedule picker (#314).

The saved-profile select applies one of the account's named heating profiles
to the heater's active timer slot. The cloud keeps no link between a timer
and the profile it was copied from, so the current option is found by
matching periods, not read back (#336).

The operating-mode select is a *control* entity too: choosing ``manual`` holds
a manual setpoint and choosing ``timer`` returns the heater to its user-timer
schedule. In User Timer a QRAD ignores every setpoint and boost the
integration sends, so without this Home Assistant could never put a heater
back into Manual itself — only the app could (#272, #299).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import DimplexApiClient
from .capabilities import capabilities_for_row
from .const import (
    HYGIENE_FREQUENCY_NAMES,
    MANUAL_FLAG,
    OPTIMISTIC_UPDATES,
    SCHEDULE_PROFILES,
    TIMER_FLAG,
    has_any_mode,
    matching_saved_profile,
    sane_temperature,
    schedule_profile,
    schedule_slot,
)
from .entity import DimplexEntity
from .errors import control_errors

# Select writes hit the cloud one at a time.
PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)

BOOST_DURATION_KEY = "boost_duration"
SCHEDULE_PROFILE_KEY = "schedule_profile"
OPERATING_MODE_KEY = "operating_mode"
HYGIENE_FREQUENCY_KEY = "hygiene_frequency"
SAVED_PROFILE_KEY = "saved_profile"

OPERATING_MODES: tuple[str, ...] = ("manual", "timer")


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
        if getattr(caps, "boost", False):
            entities.append(DimplexBoostDurationSelect(runtime.status, entry, row, caps))
        # The profile switch needs a timer schedule to name and a heater the
        # app's picker covers; cylinders have neither (#314).
        if getattr(caps, "timer", False) and not getattr(caps, "hot_water", False):
            entities.append(DimplexScheduleProfileSelect(runtime.status, entry, row, runtime.api))
            # Home Assistant could never put a heater back into Manual itself —
            # only the app could — which left QRADs stuck ignoring setpoints
            # in User Timer (#272, #299). Same gate: a heater, not a cylinder.
            entities.append(DimplexOperatingModeSelect(runtime.status, entry, row, runtime.api))
            # Saved profiles apply to that same heater timer slot, so the
            # picker lives behind the same gate (#336).
            entities.append(DimplexSavedProfileSelect(runtime.status, entry, row, runtime.api))
        # The anti-legionella cycle belongs to hot-water cylinders (#333).
        if getattr(caps, "hygiene", False):
            entities.append(
                DimplexHygieneFrequencySelect(
                    runtime.status, entry, row, runtime.api, getattr(caps, "heat_pump", False)
                )
            )
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


class DimplexScheduleProfileSelect(DimplexEntity, SelectEntity):
    """Apply the heater's schedule profile (user timer / home all day / out all day)."""

    entity_description: SelectEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        api: DimplexApiClient,
    ) -> None:
        super().__init__(
            coordinator,
            config_entry,
            appliance_row,
            SelectEntityDescription(key=SCHEDULE_PROFILE_KEY, translation_key=SCHEDULE_PROFILE_KEY),
        )
        self._attr_options = list(SCHEDULE_PROFILES)
        self._api = api

    @property
    def current_option(self) -> str | None:
        """Return the profile the heater is following, if known."""
        return schedule_profile(self._status)

    async def async_select_option(self, option: str) -> None:
        """Apply the chosen schedule profile to the appliance."""
        name = getattr(self._appliance, "FriendlyName", None) or "Dimplex appliance"
        if option not in SCHEDULE_PROFILES:
            raise ValueError(f"{option} is not a valid schedule profile for {name}")
        with control_errors(name):
            await self._api.async_set_schedule_profile(
                self._hub.HubId, self._appliance.ApplianceId, SCHEDULE_PROFILES.index(option)
            )
        invalidate = getattr(self.coordinator, "invalidate_schedules", None)
        if callable(invalidate):
            invalidate()
        await self.coordinator.async_request_refresh()


class DimplexHygieneFrequencySelect(DimplexEntity, SelectEntity):
    """Pick the cylinder's anti-legionella cycle frequency.

    The write keeps the overview's hygiene temperature — the app always sends
    a temperature with the frequency, and there is nothing else sensible to
    send (#333).
    """

    entity_description: SelectEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        api: DimplexApiClient,
        heat_pump: bool = False,
    ) -> None:
        super().__init__(
            coordinator,
            config_entry,
            appliance_row,
            SelectEntityDescription(key=HYGIENE_FREQUENCY_KEY, translation_key=HYGIENE_FREQUENCY_KEY),
        )
        self._attr_options = list(HYGIENE_FREQUENCY_NAMES.values())
        self._api = api
        self._heat_pump = heat_pump

    @property
    def current_option(self) -> str | None:
        """The cycle the cylinder reports, if known."""
        try:
            return HYGIENE_FREQUENCY_NAMES.get(int(self._status.HygieneFrequency))
        except (AttributeError, TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        """Write the chosen frequency, keeping the current hygiene temperature."""
        name = getattr(self._appliance, "FriendlyName", None) or "Dimplex appliance"
        if option not in HYGIENE_FREQUENCY_NAMES.values():
            raise ValueError(f"{option} is not a valid hygiene frequency for {name}")
        frequency = next(code for code, label in HYGIENE_FREQUENCY_NAMES.items() if label == option)
        temperature = sane_temperature(getattr(self._status, "HygieneTemperature", None)) or 60.0
        with control_errors(name):
            await self._api.async_set_hot_water_hygiene(
                self._hub.HubId,
                self._appliance.ApplianceId,
                temperature=temperature,
                frequency=frequency,
                enable=option != "off",
                heat_pump=self._heat_pump,
            )
        await self.coordinator.async_request_refresh()


class DimplexOperatingModeSelect(DimplexEntity, SelectEntity):
    """Put a heater into Manual or back to its user-timer schedule.

    A refusal surfaces as an error to the caller rather than a log line:
    silently staying in User Timer is exactly how heaters became
    uncontrollable in the first place (#272).
    """

    entity_description: SelectEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        api: DimplexApiClient,
    ) -> None:
        super().__init__(
            coordinator,
            config_entry,
            appliance_row,
            SelectEntityDescription(key=OPERATING_MODE_KEY, translation_key=OPERATING_MODE_KEY),
        )
        self._attr_options = list(OPERATING_MODES)
        self._api = api
        # Value written but not yet confirmed by a poll, like the climate
        # entity's optimistic hold (#198, #210).
        self._pending: str | None = None
        self._pending_updates_left = 0

    @property
    def current_option(self) -> str | None:
        """Manual/timer from the live mode bits, preferring a pending write."""
        if self._pending is not None:
            return self._pending
        return self._live_option

    @property
    def _live_option(self) -> str | None:
        """Map the live ``ApplianceModes`` bitfield, or ``None`` when unknown."""
        status = self._status
        if status is None:
            return None
        if has_any_mode(status, MANUAL_FLAG):
            return "manual"
        if has_any_mode(status, TIMER_FLAG):
            return "timer"
        return None

    def _handle_coordinator_update(self) -> None:
        """Retire the pending write once the cloud confirms it or it expires."""
        if self._pending is not None:
            if self._live_option == self._pending:
                self._pending = None
            else:
                self._pending_updates_left -= 1
                if self._pending_updates_left <= 0:
                    _LOGGER.debug(
                        "%s never confirmed the operating mode %s; falling back to what it reports",
                        self._appliance.FriendlyName,
                        self._pending,
                    )
                    self._pending = None
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Apply the chosen operating mode to the appliance."""
        name = getattr(self._appliance, "FriendlyName", None) or "Dimplex appliance"
        if option not in OPERATING_MODES:
            raise ValueError(f"{option} is not a valid operating mode for {name}")
        status = self._status
        if option == "manual":
            temperature = sane_temperature(getattr(status, "ActiveSetPointTemperature", None)) if status else None
            if temperature is None and status is not None:
                temperature = sane_temperature(getattr(status, "NormalTemperature", None))
            if temperature is None:
                temperature = 21.0
            with control_errors(name):
                await self._api.async_set_manual(self._hub.HubId, self._appliance.ApplianceId, temperature=temperature)
        else:
            with control_errors(name):
                await self._api.async_set_schedule_profile(
                    self._hub.HubId,
                    self._appliance.ApplianceId,
                    SCHEDULE_PROFILES.index("user_timer"),
                )
        self._pending = option
        self._pending_updates_left = OPTIMISTIC_UPDATES
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()


class DimplexSavedProfileSelect(DimplexEntity, SelectEntity):
    """Apply a saved heating profile to the heater's active timer slot.

    The options are the account's saved profiles from the official app's
    Profiles page. The current option is the profile whose periods exactly
    match the cached schedule — the cloud keeps no link between a timer and
    the profile it was copied from, so a timer edited since applying reads
    unknown rather than a stale name (#336).
    """

    entity_description: SelectEntityDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[dict[str, Any]],
        config_entry: ConfigEntry,
        appliance_row: dict[str, Any],
        api: DimplexApiClient,
    ) -> None:
        super().__init__(
            coordinator,
            config_entry,
            appliance_row,
            SelectEntityDescription(key=SAVED_PROFILE_KEY, translation_key=SAVED_PROFILE_KEY),
        )
        self._api = api
        self._attr_options = self._profile_names()

    def _profile_names(self) -> list[str]:
        """Saved profile names from the coordinator cache, in cloud order."""
        profiles = (self.coordinator.data or {}).get("heating_profiles") or []
        return [str(name) for profile in profiles if (name := getattr(profile, "ProfileName", None))]

    def _handle_coordinator_update(self) -> None:
        """Refresh the options when the slow profile cache turns over."""
        self._attr_options = self._profile_names()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Unavailable while no saved profiles are cached to pick from."""
        if not super().available:
            return False
        return bool(self._profile_names())

    @property
    def current_option(self) -> str | None:
        """The saved profile matching the cached schedule, if any."""
        data = self.coordinator.data or {}
        schedule = (data.get("schedules") or {}).get(self._appliance.ApplianceId)
        return matching_saved_profile(schedule, data.get("heating_profiles"))

    async def async_select_option(self, option: str) -> None:
        """Apply the chosen saved profile to the heater's active timer slot."""
        name = getattr(self._appliance, "FriendlyName", None) or "Dimplex appliance"
        data = self.coordinator.data or {}
        profiles = data.get("heating_profiles") or []
        match = next((profile for profile in profiles if getattr(profile, "ProfileName", None) == option), None)
        if match is None:
            available = ", ".join(self._profile_names()) or "none saved"
            raise ValueError(f"{option} is not a saved heating profile for {name} (available: {available})")
        schedule = (data.get("schedules") or {}).get(self._appliance.ApplianceId)
        slot = schedule_slot(schedule, self._status)
        with control_errors(name):
            await self._api.async_apply_heating_profile(
                self._hub.HubId,
                self._appliance.ApplianceId,
                profile=slot,
                profile_id=str(match.Id),
            )
        invalidate = getattr(self.coordinator, "invalidate_schedules", None)
        if callable(invalidate):
            invalidate()
        await self.coordinator.async_request_refresh()
