"""
Custom integration to integrate dimplex_controller with Home Assistant.

For more details about this integration, please refer to
https://github.com/kroperuk/dimplex-controller-hass
"""

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import CannotConnect
from .api import DimplexApiClient
from .api import InvalidAuth
from .const import CONF_ACCESS_TOKEN
from .const import CONF_EXPIRES_AT
from .const import CONF_PASSWORD
from .const import CONF_REFRESH_TOKEN
from .const import CONF_USERNAME
from .const import COORDINATOR_UPDATE_INTERVAL
from .const import DOMAIN
from .const import PLATFORMS
from .const import STARTUP_MESSAGE

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up this integration using YAML is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
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
    except (CannotConnect, InvalidAuth) as exception:
        raise ConfigEntryNotReady from exception

    coordinator = DimplexDataUpdateCoordinator(hass, client=client)
    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = coordinator

    token_data = client.token_data
    if token_data.get(CONF_REFRESH_TOKEN):
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_REFRESH_TOKEN: token_data.get(CONF_REFRESH_TOKEN),
                CONF_ACCESS_TOKEN: token_data.get(CONF_ACCESS_TOKEN),
                CONF_EXPIRES_AT: token_data.get(CONF_EXPIRES_AT, 0),
            },
        )

    coordinator.platforms = [
        platform for platform in PLATFORMS if entry.options.get(platform, True)
    ]
    await hass.config_entries.async_forward_entry_setups(entry, coordinator.platforms)

    entry.add_update_listener(async_reload_entry)
    return True


class DimplexDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DimplexApiClient,
    ) -> None:
        """Initialize."""
        self.api = client
        self.platforms = []

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=COORDINATOR_UPDATE_INTERVAL,
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            return await self.api.async_get_data()
        except InvalidAuth as exception:
            raise UpdateFailed("Authentication failed") from exception
        except CannotConnect as exception:
            raise UpdateFailed("Cannot connect") from exception
        except Exception as exception:
            raise UpdateFailed() from exception


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
