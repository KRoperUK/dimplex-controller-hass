"""Coordinators for the Dimplex integration.

Kept in ``coordinator.py`` per the integration quality scale's
``common-modules`` rule, so the polling logic has the same home in this
integration as in every other one.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    TimestampDataUpdateCoordinator,
    UpdateFailed,
)

from .api import CannotConnect, DimplexApiClient, InvalidAuth
from .capabilities import capabilities_for_row
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    DEFAULT_ENERGY_BACKOFF_INTERVAL,
    DEFAULT_SCHEDULE_INTERVAL,
    DOMAIN,
    ENERGY_EMPTY_BACKOFF_THRESHOLD,
    HEAT_DEMAND_FLAGS,
    SCHEDULE_PROFILES,
    has_any_mode,
    schedule_profile,
)
from .repairs import (
    async_update_empty_energy_issue,
    async_update_empty_overview_issue,
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


def _coordinator_error(exception: Exception, context: str) -> Exception:
    """Translate an adapter failure into the coordinator's own error type.

    One rule, used by both coordinators so reads and writes answer the same way.
    Only the adapter's :class:`InvalidAuth` — which it raises solely when the
    library itself reports that a re-login is required — becomes
    ``ConfigEntryAuthFailed`` and starts the reauth flow. Everything else, the
    adapter's :class:`CannotConnect` included, becomes ``UpdateFailed`` so polling
    keeps retrying: a 503 or timeout on the token endpoint says nothing about the
    stored credential and must not cost the user their session (#276).
    """
    if isinstance(exception, InvalidAuth):
        _LOGGER.warning("Authentication expired — surfacing reauth")
        return ConfigEntryAuthFailed("Authentication expired")
    if isinstance(exception, CannotConnect):
        detail = f": {exception}" if str(exception) else ""
        return UpdateFailed(f"Cannot connect to the Dimplex cloud{detail}")
    return UpdateFailed(f"Unexpected error {context}: {exception}")


class DimplexStatusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll hubs, zones, and live appliance overview."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: DimplexApiClient,
        update_interval: timedelta,
    ) -> None:
        """Initialize."""
        self.api = client
        self._entry = entry
        # Timer schedules are cached and refreshed on a slow cadence so the
        # frequent status poll does not make one extra API call per appliance
        # every cycle. ``None`` timestamp forces a fetch on the first poll.
        self._schedules_cache: dict[str, Any] = {}
        self._schedules_fetched_at: float | None = None
        # Profile each cached schedule was fetched for, by appliance id. The
        # active profile can change between slow refreshes (picked in the app),
        # so a change forces a targeted re-fetch (#328).
        self._schedules_profile: dict[str, int] = {}
        # Saved heating profiles (``GetProfiles``) are account-wide and change
        # only when the user edits them in the app, so they ride the same slow
        # cadence as the schedules. A failed fetch keeps the previous list:
        # profiles feed entity options, and wiping them on a blip would flap
        # the saved-profile select in and out of availability.
        self._heating_profiles_cache: list[Any] = []
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_status",
            update_interval=update_interval,
        )

    def _schedules_due(self) -> bool:
        """True when the cached schedules should be refreshed."""
        if self._schedules_fetched_at is None:
            return True
        elapsed = self.hass.loop.time() - self._schedules_fetched_at
        return elapsed >= DEFAULT_SCHEDULE_INTERVAL.total_seconds()

    def invalidate_schedules(self) -> None:
        """Force the next status poll to re-fetch timer schedules.

        Call after writes that change ``TimerMode`` so climate/schedule entities
        do not keep a stale mode for the full schedule poll interval.
        """
        self._schedules_fetched_at = None

    def _schedule_request(self, row: dict[str, Any]) -> tuple[str, str, bool, int] | None:
        """Return ``(hub_id, appliance_id, cylinder, profile)`` for a schedule fetch.

        ``profile`` is the overview's active schedule profile for timer
        heaters — profile 0 carries the user-timer periods even when another
        profile is active, so the fetch must name the profile the status
        frame does (#328). Anything else (manual, frost, legacy rows without
        live modes, and cylinders on their own profile-less endpoint) keeps
        the user-timer default, so a profile echo never reaches the legacy
        climate fallback disguised as an operation mode.
        """
        appliance = row.get("appliance")
        hub = row.get("hub")
        if appliance is None or hub is None:
            return None
        appliance_id = getattr(appliance, "ApplianceId", None)
        hub_id = getattr(hub, "HubId", None)
        if not appliance_id or not hub_id:
            return None
        status = row.get("status")
        caps = capabilities_for_row(appliance, status, row.get("product"))
        # Heat-pump cylinders have their own schedule endpoint; the
        # room-heater one returns an empty schedule for them.
        cylinder = caps.hot_water and caps.heat_pump
        profile = 0
        if not cylinder:
            named = schedule_profile(status)
            if named is not None:
                profile = SCHEDULE_PROFILES.index(named)
        return (hub_id, appliance_id, cylinder, profile)

    def _schedule_stale(self, row: dict[str, Any]) -> bool:
        """True when the row needs a schedule (re-)fetch outside the cadence.

        A missing entry or an active-profile change since the cached fetch
        forces a targeted re-fetch; the fifteen-minute cadence otherwise
        stands.
        """
        request = self._schedule_request(row)
        if request is None:
            return False
        _, appliance_id, _, profile = request
        if appliance_id not in self._schedules_cache:
            return True
        return self._schedules_profile.get(appliance_id) != profile

    async def _async_fetch_schedules(self, appliances: list[dict[str, Any]]) -> dict[str, Any]:
        """Fetch timer schedules for appliances concurrently (best-effort)."""
        targets = [request for row in appliances if (request := self._schedule_request(row))]

        async def _one(hub_id: str, appliance_id: str, cylinder: bool, profile: int) -> Any:
            if cylinder:
                return await self.api.async_get_hot_water_schedule(hub_id, appliance_id)
            return await self.api.async_get_schedule(hub_id, appliance_id, timer_mode=profile)

        results = await asyncio.gather(
            *(_one(*target) for target in targets),
            return_exceptions=True,
        )

        schedules: dict[str, Any] = {}
        for (_, appliance_id, _, profile), result in zip(targets, results, strict=False):
            if isinstance(result, Exception):
                _LOGGER.debug("Schedule unavailable for %s: %s", appliance_id, result)
                schedules[appliance_id] = None
            else:
                schedules[appliance_id] = result
            # Record the attempted profile either way: a failed fetch retries
            # on the slow cadence, not on every hot status poll.
            self._schedules_profile[appliance_id] = profile
        return schedules

    async def _async_fetch_heating_profiles(self) -> list[Any]:
        """Fetch saved heating profiles, keeping the previous list on failure."""
        try:
            return list(await self.api.async_get_heating_profiles() or [])
        except Exception as exception:
            _LOGGER.debug("Saved heating profiles unavailable: %s", exception)
            return self._heating_profiles_cache

    async def _async_update_data(self) -> dict[str, Any]:
        """Update status data via library."""
        try:
            data = await self.api.async_get_status_data()
        except Exception as exception:
            raise _coordinator_error(exception, "fetching status") from exception

        # Timer schedules (read-only) are refreshed on a slow cadence and cached
        # in between so the hot status poll stays a single API call. A missing
        # schedule leaves the entry as ``None`` (schedule sensor unavailable).
        # A changed active profile re-fetches that appliance at once, so the
        # periods follow a schedule picked in the app without waiting out the
        # cache (#328).
        appliances = data.get("appliances") or []
        if self._schedules_due():
            self._schedules_cache = await self._async_fetch_schedules(appliances)
            self._schedules_fetched_at = self.hass.loop.time()
            for appliance_id in list(self._schedules_profile):
                if appliance_id not in self._schedules_cache:
                    del self._schedules_profile[appliance_id]
            self._heating_profiles_cache = await self._async_fetch_heating_profiles()
        else:
            changed = [row for row in appliances if self._schedule_stale(row)]
            if changed:
                self._schedules_cache.update(await self._async_fetch_schedules(changed))
        data["schedules"] = self._schedules_cache
        data["heating_profiles"] = self._heating_profiles_cache

        _persist_tokens(self.hass, self._entry, self.api)
        has_status = any(row.get("status") is not None for row in appliances)
        async_update_empty_overview_issue(
            self.hass,
            self._entry.entry_id,
            empty=bool(appliances) and not has_status,
        )
        return data


class DimplexEnergyCoordinator(TimestampDataUpdateCoordinator[dict[str, Any]]):
    """Poll TSI energy reports on a slower cadence.

    Timestamp variant deliberately: the energy sensors memoise their summary on
    ``last_update_success_time``, which only exists here. As a plain
    ``DataUpdateCoordinator`` the attribute was always absent, so the memo never
    hit and ``summarise_energy`` was recomputed on every property read (#198).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: DimplexApiClient,
        status_coordinator: DimplexStatusCoordinator,
        update_interval: timedelta,
    ) -> None:
        """Initialize."""
        self.api = client
        self._entry = entry
        self._status = status_coordinator
        self._base_interval = update_interval
        # Single counter for both the backoff and the repair decision: a failed
        # report raises UpdateFailed and never reaches here, so only a
        # genuinely empty (but successful) result increments it (#279).
        # Heating resets it, so neither backoff nor the repair fires while a
        # heater is boosting.
        self._empty_polls = 0
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_energy",
            update_interval=update_interval,
        )

    @staticmethod
    def _energy_is_empty(data: dict[str, Any]) -> bool:
        """True when every appliance series has zero points."""
        energy = data.get("energy") or {}
        if not energy:
            return True
        for registers in energy.values():
            for by_app in (registers or {}).values():
                for points in (by_app or {}).values():
                    if points:
                        return False
        return True

    def _any_heating_active(self) -> bool:
        """Restore normal polling when status suggests active heating."""
        for row in (self._status.data or {}).get("appliances", []):
            status = row.get("status")
            if status is None:
                continue
            if getattr(status, "ComfortStatus", None):
                return True
            if has_any_mode(status, HEAT_DEMAND_FLAGS):
                return True
            duration = getattr(status, "BoostDuration", None)
            if duration is not None and duration > 0:
                return True
        return False

    def _adapt_interval(self, data: dict[str, Any]) -> None:
        """Back off when history is empty; restore when points or heating return."""
        if self._energy_is_empty(data) and not self._any_heating_active():
            self._empty_polls += 1
        else:
            self._empty_polls = 0

        if self._empty_polls >= ENERGY_EMPTY_BACKOFF_THRESHOLD:
            target = max(self._base_interval, DEFAULT_ENERGY_BACKOFF_INTERVAL)
        else:
            target = self._base_interval

        if self.update_interval != target:
            _LOGGER.debug(
                "Energy poll interval %s → %s (empty_polls=%s)",
                self.update_interval,
                target,
                self._empty_polls,
            )
            self.update_interval = target

    async def _async_update_data(self) -> dict[str, Any]:
        """Update energy data via library."""
        status = self._status.data or {}
        hubs = status.get("hubs") or []
        hub_ids = [hub.HubId for hub in hubs]
        if not hub_ids:
            # Fall back to appliance rows if hubs list missing.
            hub_ids = list({row["hub"].HubId for row in status.get("appliances", [])})

        try:
            data = await self.api.async_get_energy_for_hubs(hub_ids)
        except Exception as exception:
            raise _coordinator_error(exception, "fetching energy") from exception

        _persist_tokens(self.hass, self._entry, self.api)
        self._adapt_interval(data)
        async_update_empty_energy_issue(
            self.hass,
            self._entry.entry_id,
            empty=self._empty_polls >= ENERGY_EMPTY_BACKOFF_THRESHOLD,
        )
        return data


def _persist_tokens(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: DimplexApiClient,
) -> None:
    """Write the client's current tokens back to the config entry if they changed."""
    _persist_token_data(hass, entry, client.token_data)


def _persist_token_data(
    hass: HomeAssistant,
    entry: ConfigEntry,
    token_data: Mapping[str, Any],
) -> None:
    """Write a token payload back to the config entry if it changed.

    Split out from :func:`_persist_tokens` because the client's token-update
    callback hands over the payload directly, without a client to read it from.
    """
    if not token_data.get(CONF_REFRESH_TOKEN):
        return
    current = {
        CONF_REFRESH_TOKEN: token_data.get(CONF_REFRESH_TOKEN),
        CONF_ACCESS_TOKEN: token_data.get(CONF_ACCESS_TOKEN),
        CONF_EXPIRES_AT: token_data.get(CONF_EXPIRES_AT, 0),
    }
    # ``expires_at`` is part of the comparison: an entry stored with 0 gets the
    # expiry derived from the access token's own JWT claim on the next start
    # (``DimplexApiClient.async_initialize``), and comparing only the tokens left
    # that drift unpersisted, so it was recomputed on every restart (#198).
    if (
        entry.data.get(CONF_REFRESH_TOKEN) != current[CONF_REFRESH_TOKEN]
        or entry.data.get(CONF_ACCESS_TOKEN) != current[CONF_ACCESS_TOKEN]
        or entry.data.get(CONF_EXPIRES_AT, 0) != current[CONF_EXPIRES_AT]
    ):
        _LOGGER.debug("Persisting refreshed tokens")
        data = {**entry.data, **current}
        hass.config_entries.async_update_entry(entry, data=data)
