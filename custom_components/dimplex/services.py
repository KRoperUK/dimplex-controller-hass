"""Domain services for Dimplex control actions."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ATTR_DEVICE_ID = "device_id"
ATTR_ENTITY_ID = "entity_id"
ATTR_TEMPERATURE = "temperature"
ATTR_DURATION = "duration"
ATTR_ENABLE = "enable"

SERVICE_SET_BOOST = "set_boost"
SERVICE_CLEAR_BOOST = "clear_boost"
SERVICE_SET_AWAY = "set_away"
SERVICE_CLEAR_AWAY = "clear_away"
SERVICE_SET_ECO_START = "set_eco_start"
SERVICE_SET_OPEN_WINDOW = "set_open_window_detection"

_DEFAULT_BOOST_TEMP = 25.0
_DEFAULT_BOOST_MINUTES = 60
_DEFAULT_AWAY_TEMP = 16.0


def _target_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(ATTR_DEVICE_ID): cv.string,
            vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
        }
    )


def _appliance_id_from_unique_id(config_entry_id: str, unique_id: str | None) -> str | None:
    """Parse appliance id from ``{entry_id}_{appliance_id}_{suffix}``."""
    if not unique_id:
        return None
    prefix = f"{config_entry_id}_"
    if not unique_id.startswith(prefix):
        return None
    rest = unique_id[len(prefix) :]
    if "_" not in rest:
        return rest
    return rest.rsplit("_", 1)[0]


async def _resolve_appliance(hass: HomeAssistant, call: ServiceCall) -> tuple[str, str, str, Any] | None:
    """Return (entry_id, hub_id, appliance_id, api) from device_id or entity_id."""
    device_id = call.data.get(ATTR_DEVICE_ID)
    entity_id = call.data.get(ATTR_ENTITY_ID)

    appliance_id: str | None = None
    config_entry_id: str | None = None

    if entity_id:
        ent_reg = er.async_get(hass)
        entry = ent_reg.async_get(entity_id)
        if entry is None or entry.config_entry_id is None:
            _LOGGER.error("Unknown entity_id for dimplex service: %s", entity_id)
            return None
        config_entry_id = entry.config_entry_id
        if entry.device_id:
            device_id = entry.device_id
        else:
            appliance_id = _appliance_id_from_unique_id(config_entry_id, entry.unique_id)

    if device_id:
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if device is None or not device.config_entries:
            _LOGGER.error("Unknown device_id for dimplex service: %s", device_id)
            return None
        config_entry_id = next(iter(device.config_entries))
        for domain, ident in device.identifiers:
            if domain == DOMAIN:
                appliance_id = ident
                break
    elif not entity_id:
        _LOGGER.error("dimplex service requires device_id or entity_id")
        return None

    if not appliance_id or not config_entry_id:
        _LOGGER.error("Could not resolve appliance id from service target")
        return None

    runtime = hass.data.get(DOMAIN, {}).get(config_entry_id)
    if runtime is None:
        _LOGGER.error("No runtime for config entry %s", config_entry_id)
        return None

    hub_id: str | None = None
    for row in (runtime.status.data or {}).get("appliances", []):
        if row["appliance"].ApplianceId == appliance_id:
            hub_id = row["hub"].HubId
            break
    if not hub_id:
        _LOGGER.error("Appliance %s not found in coordinator data", appliance_id)
        return None

    return config_entry_id, hub_id, appliance_id, runtime.api


async def _refresh_status(hass: HomeAssistant, config_entry_id: str) -> None:
    """Ask the status coordinator to refresh so state reflects the change quickly.

    Control services mutate appliance state on the cloud; without an explicit
    refresh the new state would not appear until the next scheduled poll.
    """
    runtime = hass.data.get(DOMAIN, {}).get(config_entry_id)
    if runtime is not None:
        await runtime.status.async_request_refresh()


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register dimplex domain services (idempotent)."""
    if hass.data.get(f"{DOMAIN}_services"):
        return
    hass.data[f"{DOMAIN}_services"] = True

    async def handle_set_boost(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_boost(
            hub_id,
            appliance_id,
            temperature=float(call.data.get(ATTR_TEMPERATURE, _DEFAULT_BOOST_TEMP)),
            duration_minutes=int(call.data.get(ATTR_DURATION, _DEFAULT_BOOST_MINUTES)),
            enable=True,
        )
        await _refresh_status(hass, entry_id)

    async def handle_clear_boost(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_boost(
            hub_id,
            appliance_id,
            temperature=float(call.data.get(ATTR_TEMPERATURE, _DEFAULT_BOOST_TEMP)),
            enable=False,
        )
        await _refresh_status(hass, entry_id)

    async def handle_set_away(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_away(
            hub_id,
            appliance_id,
            temperature=float(call.data.get(ATTR_TEMPERATURE, _DEFAULT_AWAY_TEMP)),
            enable=True,
        )
        await _refresh_status(hass, entry_id)

    async def handle_clear_away(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_away(
            hub_id,
            appliance_id,
            temperature=float(call.data.get(ATTR_TEMPERATURE, _DEFAULT_AWAY_TEMP)),
            enable=False,
        )
        await _refresh_status(hass, entry_id)

    async def handle_eco(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_eco_start(hub_id, appliance_id, bool(call.data.get(ATTR_ENABLE, True)))
        await _refresh_status(hass, entry_id)

    async def handle_owd(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_open_window_detection(hub_id, appliance_id, bool(call.data.get(ATTR_ENABLE, True)))
        await _refresh_status(hass, entry_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BOOST,
        handle_set_boost,
        schema=_target_schema().extend(
            {
                vol.Optional(ATTR_TEMPERATURE, default=_DEFAULT_BOOST_TEMP): vol.Coerce(float),
                vol.Optional(ATTR_DURATION, default=_DEFAULT_BOOST_MINUTES): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=24 * 60)
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_BOOST,
        handle_clear_boost,
        schema=_target_schema().extend(
            {vol.Optional(ATTR_TEMPERATURE, default=_DEFAULT_BOOST_TEMP): vol.Coerce(float)}
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AWAY,
        handle_set_away,
        schema=_target_schema().extend({vol.Optional(ATTR_TEMPERATURE, default=_DEFAULT_AWAY_TEMP): vol.Coerce(float)}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_AWAY,
        handle_clear_away,
        schema=_target_schema().extend({vol.Optional(ATTR_TEMPERATURE, default=_DEFAULT_AWAY_TEMP): vol.Coerce(float)}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ECO_START,
        handle_eco,
        schema=_target_schema().extend({vol.Optional(ATTR_ENABLE, default=True): cv.boolean}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_OPEN_WINDOW,
        handle_owd,
        schema=_target_schema().extend({vol.Optional(ATTR_ENABLE, default=True): cv.boolean}),
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Remove domain services when last entry unloads."""
    remaining = hass.data.get(DOMAIN) or {}
    if remaining:
        return
    if not hass.data.get(f"{DOMAIN}_services"):
        return
    for service in (
        SERVICE_SET_BOOST,
        SERVICE_CLEAR_BOOST,
        SERVICE_SET_AWAY,
        SERVICE_CLEAR_AWAY,
        SERVICE_SET_ECO_START,
        SERVICE_SET_OPEN_WINDOW,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    hass.data.pop(f"{DOMAIN}_services", None)
