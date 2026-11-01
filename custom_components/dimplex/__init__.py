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
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import UNDEFINED, ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import CannotConnect, DimplexApiClient, InvalidAuth
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ENERGY_INTERVAL,
    CONF_EXPIRES_AT,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_STATUS_INTERVAL,
    CONF_USERNAME,
    DEFAULT_ENERGY_INTERVAL,
    DEFAULT_STATUS_INTERVAL,
    DOMAIN,
    PLATFORMS,
    STARTUP_MESSAGE,
)
from .coordinator import (
    DimplexEnergyCoordinator,
    DimplexStatusCoordinator,
    _persist_token_data,
    _persist_tokens,
)
from .holiday import HolidayManager
from .repairs import (
    async_update_empty_energy_issue,
    async_update_empty_overview_issue,
)
from .services import async_setup_services

_LOGGER: logging.Logger = logging.getLogger(__package__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# entry_ids for which the next update_listener fire is a token write, not options.
# DEPRECATED: kept only as a comment for history; replaced by options-diff approach.

type DimplexConfigEntry = ConfigEntry[DimplexRuntimeData]


@dataclass
class DimplexRuntimeData:
    """Runtime objects for one config entry."""

    api: DimplexApiClient
    status: DataUpdateCoordinator[dict[str, Any]]
    energy: DataUpdateCoordinator[dict[str, Any]]
    platforms: list[Platform]
    options_snapshot: dict[str, Any]
    # Boost length chosen via the per-appliance boost-duration select, keyed by
    # ApplianceId. The climate boost preset prefers this over the entry-wide
    # ``CONF_BOOST_DURATION`` option so each appliance can use its own duration
    # from the discrete set the cloud offers (#252).
    boost_minutes: dict[str, int] = field(default_factory=dict)
    # HA-initiated boost engagements, keyed by ApplianceId, feeding the
    # boost-remaining countdown sensor. The cloud exposes no expiry field —
    # BoostDuration is a configured length, not a countdown — so the start
    # time and chosen duration are recorded here when Home Assistant starts a
    # boost and restored across restarts by the sensor itself. A boost begun
    # on the heater or in the app has no start time here and reads unknown
    # (#302).
    boost_starts: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Hot-water holiday end times and the timers that clear Holiday at them.
    holiday: HolidayManager | None = None


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
    Appliance entities link to their zone and zone entities link to their hub,
    both via ``via_device_id`` — the parent's *registry id*, which only exists
    once the parent device does. So hubs and zones are registered here,
    synchronously, before forwarding to any platform; platforms then only ever
    create appliance devices, whose parent is guaranteed to exist.

    ``via_device`` (the identifier-tuple form) is deliberately not used: Home
    Assistant deprecated it in 2026.8 because identifiers are only unique per
    config entry, and it is removed in 2027.8. Passing it — even as ``None`` —
    logs a deprecation warning on every setup, because the registry only skips
    the parameter when it is ``UNDEFINED``.
    """
    registry = dr.async_get(hass)
    seen_zones: set[tuple[str, str]] = set()
    hub_device_ids: dict[str, str] = {}
    for row in data.get("appliances") or []:
        hub = row.get("hub")
        zone = row.get("zone")
        hub_id = getattr(hub, "HubId", None) if hub is not None else None
        zone_id = getattr(zone, "ZoneId", None) if zone is not None else None
        if hub_id and hub_id not in hub_device_ids:
            hub_device = registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, hub_id)},
                manufacturer="Dimplex",
                model=getattr(hub, "HubModel", None) or "Dimplex Hub",
                name=getattr(hub, "HubName", None) or "Dimplex Hub",
            )
            # Keep the registry id: it is what via_device_id needs, and reading it
            # from the returned entry avoids a second lookup.
            hub_device_ids[hub_id] = hub_device.id
        if not zone_id:
            continue
        zone_key = (DOMAIN, f"zone_{zone_id}")
        if zone_key in seen_zones:
            continue
        seen_zones.add(zone_key)
        parent_id = hub_device_ids.get(hub_id) if hub_id else None
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={zone_key},
            manufacturer="Dimplex",
            model=getattr(zone, "ZoneType", None) or "Zone",
            name=getattr(zone, "ZoneName", None) or "Zone",
            suggested_area=getattr(zone, "ZoneName", None),
            # UNDEFINED, not None, when there is no hub: the registry skips the
            # parameter only when it is UNDEFINED, and an explicit None still runs
            # its deprecation and self-reference checks.
            via_device_id=parent_id if parent_id else UNDEFINED,
        )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up this integration using YAML is not supported.

    Actions are registered here rather than in ``async_setup_entry`` so they
    exist as soon as the integration loads, even while no config entry is
    loaded. Their handlers validate the target entry themselves and raise a
    translated ``ServiceValidationError`` when it is not available.
    """
    await async_setup_services(hass)
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
    if not hass.config_entries.async_loaded_entries(DOMAIN):
        _LOGGER.info(STARTUP_MESSAGE)

    session = async_get_clientsession(hass)

    def _on_token_update(token_data: Mapping[str, Any]) -> None:
        """Persist rotated tokens the moment the library produces them.

        A refresh happens *inside* a request, so waiting for the poll to succeed
        threw the new pair away whenever that request then failed. The cloud
        invalidates the old refresh token as soon as it rotates, so the retry
        presented one that was already dead and the user had to sign in again
        (dimplex-controller-hass#277). Writing here covers setup and every poll,
        including the ones that fail.
        """
        _persist_token_data(hass, entry, token_data)

    client = DimplexApiClient(
        session=session,
        refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        access_token=entry.data.get(CONF_ACCESS_TOKEN),
        expires_at=entry.data.get(CONF_EXPIRES_AT, 0),
        username=entry.data.get(CONF_USERNAME),
        password=entry.data.get(CONF_PASSWORD),
        on_token_update=_on_token_update,
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
    holiday = HolidayManager(hass, client, status_coordinator)
    runtime = DimplexRuntimeData(
        api=client,
        status=status_coordinator,
        energy=energy_coordinator,
        platforms=platforms,
        options_snapshot=dict(entry.options),
        holiday=holiday,
    )
    entry.runtime_data = runtime
    entry.async_on_unload(holiday.async_shutdown)

    # Register hub and zone devices up front so platform entities can safely
    # reference them via via_device (see dimplex-controller-hass#117).
    _ensure_parent_devices(hass, entry, status_coordinator.data or {})

    # Pre-import the platform modules off the event loop so that the lazy
    # import inside async_forward_entry_setups hits the import cache and
    # does not produce a "Detected blocking call to import_module" warning
    # on a cold start (see dimplex-controller-hass#118).
    await _preload_platforms(platforms)

    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    # Persist tokens after platform setup. Token writes must not trigger a full
    # reload (would loop); options changes do via the listener below.
    _persist_tokens(hass, entry, client)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: DimplexConfigEntry) -> bool:
    """Handle removal of an entry."""
    runtime = entry.runtime_data
    unloaded = await hass.config_entries.async_unload_platforms(entry, runtime.platforms)
    if unloaded:
        # Services stay registered for the lifetime of the integration; only
        # their per-entry state and repairs are cleaned up here.
        async_update_empty_energy_issue(hass, entry.entry_id, empty=False)
        async_update_empty_overview_issue(hass, entry.entry_id, empty=False)
    return unloaded


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: DimplexConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow a device the appliance snapshot no longer reports to be deleted.

    Appliances are re-read from the cloud on every poll, so a device that is no
    longer returned is genuinely gone (removed from the account, or reassigned to
    another hub) and there is nothing left to keep it present for. Home Assistant
    asks this before removing a device from the registry; returning False would
    make the entry permanently un-deletable (dimplex-controller-hass#198).
    """
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return True

    snapshot = runtime.status.data or {}
    rows = snapshot.get("appliances") or []
    present = {(DOMAIN, row["appliance"].ApplianceId) for row in rows}
    present |= {(DOMAIN, f"zone_{row['zone'].ZoneId}") for row in rows if row.get("zone") is not None}
    present |= {(DOMAIN, hub.HubId) for hub in snapshot.get("hubs") or []}

    return not any(identifier in present for identifier in device_entry.identifiers)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry only when options actually changed.

    Token-only data writes fire the update listener too, but should not
    trigger a full reload (that would loop: reload → fetch → new tokens →
    update → reload). By comparing the current options against the snapshot
    taken at setup, we distinguish user option changes (reload needed) from
    token persistence (no reload).
    """
    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None and dict(entry.options) == runtime.options_snapshot:
        return
    await hass.config_entries.async_reload(entry.entry_id)
