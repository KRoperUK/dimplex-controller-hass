"""
Custom integration to integrate dimplex_controller with Home Assistant.

For more details about this integration, please refer to
https://github.com/kroperuk/dimplex-controller-hass
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CannotConnect, DimplexApiClient, InvalidAuth
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ENERGY_INTERVAL,
    CONF_EXPIRES_AT,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_STATUS_INTERVAL,
    CONF_USERNAME,
    DEFAULT_ENERGY_BACKOFF_INTERVAL,
    DEFAULT_ENERGY_INTERVAL,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    ENERGY_EMPTY_BACKOFF_THRESHOLD,
    PLATFORMS,
    STARTUP_MESSAGE,
)
from .repairs import (
    async_update_empty_energy_issue,
    async_update_empty_overview_issue,
)
from .services import async_setup_services, async_unload_services

_LOGGER: logging.Logger = logging.getLogger(__package__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# entry_ids for which the next update_listener fire is a token write, not options.
_SKIP_RELOAD_ENTRY_IDS: set[str] = set()

type DimplexConfigEntry = ConfigEntry[DimplexRuntimeData]


@dataclass
class DimplexRuntimeData:
    """Runtime objects for one config entry."""

    api: DimplexApiClient
    status: DataUpdateCoordinator[dict[str, Any]]
    energy: DataUpdateCoordinator[dict[str, Any]]
    platforms: list[Platform]


async def _preload_platforms(platforms: list[Platform]) -> None:
    """Import every platform module off the event loop.

    `async_forward_entry_setups` performs a lazy ``import_module`` for each
    platform on the event loop, which on a cold start produces
    ``Detected blocking call to import_module`` warnings in the HA log
    (dimplex-controller-hass#118). Pre-importing the modules in an executor
    means the subsequent ``async_forward_entry_setups`` call hits the
    import cache and completes without blocking the loop.
    """
    if not platforms:
        return
    module_names = [f"custom_components.{DOMAIN}.{platform.value}" for platform in platforms]

    def _import_all() -> None:
        for name in module_names:
            importlib.import_module(name)

    await asyncio.to_thread(_import_all)


def _ensure_parent_devices(hass: HomeAssistant, entry: DimplexConfigEntry, data: dict[str, Any]) -> None:
    """Pre-register hub and zone devices before platforms set up.

    The Dimplex device tree is three levels deep: Hub → Zone → Appliance.
    Appliance entities declare ``via_device`` pointing at the zone they
    belong to, and zone entities declare ``via_device`` pointing at the
    hub. To avoid Home Assistant's 2025.12 hard-failure on
    ``via_device`` references whose target does not yet exist, we
    register hubs and zones here, synchronously, before forwarding to
    any platform. Platforms then only ever need to create appliance
    devices — which always have an existing parent.
    """
    registry = dr.async_get(hass)
    seen_zones: set[tuple[str, str]] = set()
    seen_hubs: set[str] = set()
    for row in data.get("appliances") or []:
        hub = row.get("hub")
        zone = row.get("zone")
        hub_id = getattr(hub, "HubId", None) if hub is not None else None
        zone_id = getattr(zone, "ZoneId", None) if zone is not None else None
        if hub_id and hub_id not in seen_hubs:
            seen_hubs.add(hub_id)
            registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, hub_id)},
                manufacturer="Dimplex",
                model=getattr(hub, "HubModel", None) or "Dimplex Hub",
                name=getattr(hub, "HubName", None) or "Dimplex Hub",
            )
        if not zone_id:
            continue
        zone_key = (DOMAIN, f"zone_{zone_id}")
        if zone_key in seen_zones:
            continue
        seen_zones.add(zone_key)
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={zone_key},
            manufacturer="Dimplex",
            model=getattr(zone, "ZoneType", None) or "Zone",
            name=getattr(zone, "ZoneName", None) or "Zone",
            suggested_area=getattr(zone, "ZoneName", None),
            via_device=(DOMAIN, hub_id) if hub_id else None,
        )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up this integration using YAML is not supported."""
    return True


def _interval_from_options(options: Mapping[str, Any], key: str, default: timedelta) -> timedelta:
    """Read a seconds value from options, falling back to ``default``."""
    raw = options.get(key)
    if raw is None:
        return default
    try:
        seconds = int(raw)
    except ValueError:
        return default
    except TypeError:
        return default
    if seconds < 15:
        return default
    return timedelta(seconds=seconds)


async def async_setup_entry(hass: HomeAssistant, entry: DimplexConfigEntry) -> bool:
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    session = async_get_clientsession(hass)
    client = DimplexApiClient(
        session=session,
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        expires_at=entry.data.get(CONF_EXPIRES_AT, 0),
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
    )

    try:
        await client.async_initialize()
    except InvalidAuth as exception:
        # ConfigEntryAuthFailed makes Home Assistant auto-start the reauth flow
        # for this config entry. See dimplex-controller-hass#114.
        raise ConfigEntryAuthFailed("Authentication failed during setup") from exception
    except CannotConnect as exception:
        raise ConfigEntryNotReady from exception

    status_interval = _interval_from_options(entry.options, CONF_STATUS_INTERVAL, DEFAULT_STATUS_INTERVAL)
    energy_interval = _interval_from_options(entry.options, CONF_ENERGY_INTERVAL, DEFAULT_ENERGY_INTERVAL)

    status_coordinator = DimplexStatusCoordinator(hass, entry, client, status_interval)
    energy_coordinator = DimplexEnergyCoordinator(hass, entry, client, status_coordinator, energy_interval)

    await status_coordinator.async_config_entry_first_refresh()

    if not status_coordinator.last_update_success:
        raise ConfigEntryNotReady

    # Energy is best-effort at setup — failures leave sensors unavailable.
    await energy_coordinator.async_refresh()

    platforms = [platform for platform in PLATFORMS if entry.options.get(platform, True)]
    runtime = DimplexRuntimeData(
        api=client,
        status=status_coordinator,
        energy=energy_coordinator,
        platforms=platforms,
    )
    entry.runtime_data = runtime
    hass.data[DOMAIN][entry.entry_id] = runtime

    # Register hub and zone devices up front so platform entities can safely
    # reference them via via_device (see dimplex-controller-hass#117).
    _ensure_parent_devices(hass, entry, status_coordinator.data or {})

    # Pre-import the platform modules off the event loop so that the lazy
    # import inside async_forward_entry_setups hits the import cache and
    # does not produce a "Detected blocking call to import_module" warning
    # on a cold start (see dimplex-controller-hass#118).
    await _preload_platforms(platforms)

    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    await async_setup_services(hass)

    # Persist tokens after platform setup. Token writes must not trigger a full
    # reload (would loop); options changes do via the listener below.
    _persist_tokens(hass, entry, client)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


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
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_status",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update status data via library."""
        try:
            data = await self.api.async_get_status_data()
        except InvalidAuth as exception:
            _LOGGER.warning("Authentication expired — surfacing reauth")
            raise ConfigEntryAuthFailed("Authentication expired") from exception
        except CannotConnect as exception:
            raise UpdateFailed("Cannot connect") from exception
        except Exception as exception:
            raise UpdateFailed() from exception

        # Best-effort timer schedules (read-only). Failures leave schedule=None.
        schedules: dict[str, Any] = {}
        for row in data.get("appliances") or []:
            appliance = row.get("appliance")
            hub = row.get("hub")
            if appliance is None or hub is None:
                continue
            appliance_id = getattr(appliance, "ApplianceId", None)
            hub_id = getattr(hub, "HubId", None)
            if not appliance_id or not hub_id:
                continue
            try:
                schedules[appliance_id] = await self.api.async_get_schedule(hub_id, appliance_id)
            except Exception as exception:  # noqa: BLE001 — schedule is optional
                _LOGGER.debug("Schedule unavailable for %s: %s", appliance_id, exception)
                schedules[appliance_id] = None
        data["schedules"] = schedules

        _persist_tokens(self.hass, self._entry, self.api)
        appliances = data.get("appliances") or []
        has_status = any(row.get("status") is not None for row in appliances)
        async_update_empty_overview_issue(
            self.hass,
            self._entry.entry_id,
            empty=bool(appliances) and not has_status,
        )
        return data


class DimplexEnergyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll TSI energy reports on a slower cadence."""

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
        self._empty_successes = 0
        self._base_interval = update_interval
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
            modes = getattr(status, "ApplianceModes", None) or 0
            if modes & 16:
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
        except InvalidAuth as exception:
            _LOGGER.warning("Authentication expired during energy poll — surfacing reauth")
            raise ConfigEntryAuthFailed("Authentication expired") from exception
        except CannotConnect as exception:
            raise UpdateFailed("Cannot connect") from exception
        except Exception as exception:
            raise UpdateFailed() from exception

        _persist_tokens(self.hass, self._entry, self.api)
        self._adapt_interval(data)
        if self._energy_is_empty(data):
            self._empty_successes += 1
        else:
            self._empty_successes = 0
        async_update_empty_energy_issue(
            self.hass,
            self._entry.entry_id,
            empty=self._empty_successes >= ENERGY_EMPTY_BACKOFF_THRESHOLD,
        )
        return data


def _persist_tokens(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: DimplexApiClient,
) -> None:
    """Write current tokens back to the config entry if they changed."""
    token_data = client.token_data
    if not token_data.get(CONF_REFRESH_TOKEN):
        return
    current = {
        CONF_REFRESH_TOKEN: token_data.get(CONF_REFRESH_TOKEN),
        CONF_ACCESS_TOKEN: token_data.get(CONF_ACCESS_TOKEN),
        CONF_EXPIRES_AT: token_data.get(CONF_EXPIRES_AT, 0),
    }
    if (
        entry.data.get(CONF_REFRESH_TOKEN) != current[CONF_REFRESH_TOKEN]
        or entry.data.get(CONF_ACCESS_TOKEN) != current[CONF_ACCESS_TOKEN]
    ):
        _LOGGER.debug("Persisting refreshed tokens")
        data = {**entry.data, **current}
        # Token writes fire the options update listener; skip the reload so we
        # do not loop (reload → fetch → new tokens → update → reload …).
        _SKIP_RELOAD_ENTRY_IDS.add(entry.entry_id)
        hass.config_entries.async_update_entry(entry, data=data)


async def async_unload_entry(hass: HomeAssistant, entry: DimplexConfigEntry) -> bool:
    """Handle removal of an entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    unloaded = await hass.config_entries.async_unload_platforms(entry, runtime.platforms)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        await async_unload_services(hass)
        async_update_empty_energy_issue(hass, entry.entry_id, empty=False)
        async_update_empty_overview_issue(hass, entry.entry_id, empty=False)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change (not on token-only writes)."""
    if entry.entry_id in _SKIP_RELOAD_ENTRY_IDS:
        _SKIP_RELOAD_ENTRY_IDS.discard(entry.entry_id)
        return
    await hass.config_entries.async_reload(entry.entry_id)
