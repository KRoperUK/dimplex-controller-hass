"""Domain services for Dimplex control actions."""

from __future__ import annotations

import functools
import logging
from typing import Any

import voluptuous as vol
from dimplex_controller import HygieneFrequency
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .capabilities import capabilities_for_row
from .const import AWAY_TEMP_MAX, AWAY_TEMP_MIN, DOMAIN, SETPOINT_TEMP_MAX, SETPOINT_TEMP_MIN, TIMER_USER
from .errors import control_errors

_LOGGER = logging.getLogger(__name__)

ATTR_DEVICE_ID = "device_id"
ATTR_ENTITY_ID = "entity_id"
ATTR_TEMPERATURE = "temperature"
ATTR_DURATION = "duration"
ATTR_DAYS = "days"
ATTR_UNTIL = "until"
ATTR_ENABLE = "enable"
ATTR_DAY = "day"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_TARGET_DEVICE_IDS = "target_device_ids"
ATTR_MODE = "mode"
ATTR_FREQUENCY = "frequency"

SERVICE_SET_BOOST = "set_boost"
SERVICE_CLEAR_BOOST = "clear_boost"
SERVICE_SET_AWAY = "set_away"
SERVICE_CLEAR_AWAY = "clear_away"
SERVICE_SET_ADVANCE = "set_advance"
SERVICE_CLEAR_ADVANCE = "clear_advance"
SERVICE_SET_ECO_START = "set_eco_start"
SERVICE_SET_OPEN_WINDOW = "set_open_window_detection"
SERVICE_COPY_SCHEDULE = "copy_schedule"
SERVICE_SET_PERIOD_SETPOINT = "set_period_setpoint"
SERVICE_SET_HOT_WATER_TEMPERATURE = "set_hot_water_temperature"
SERVICE_SET_HOT_WATER_HYGIENE = "set_hot_water_hygiene"

# Hot-water cylinder modes the temperature action writes, and the hygiene cycle
# frequencies. Both are names rather than the wire values because neither the
# endpoint nor the enum is anything a user should have to look up.
HOT_WATER_MODES: tuple[str, ...] = ("normal", "boost")
HYGIENE_FREQUENCIES: dict[str, int] = {
    "off": int(HygieneFrequency.OFF),
    "daily": int(HygieneFrequency.DAILY),
    "weekly": int(HygieneFrequency.WEEKLY),
    "monthly": int(HygieneFrequency.MONTHLY),
}

# ``DayOfWeek`` is 0 = Sunday … 6 = Saturday. The service accepts the day name so
# nobody has to remember that, or guess whether the week starts on Sunday.
DAY_NAMES: dict[str, int] = {
    "sunday": 0,
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
}

_DEFAULT_BOOST_TEMP = 25.0
_DEFAULT_BOOST_MINUTES = 60
_DEFAULT_AWAY_TEMP = 16.0
_MAX_AWAY_DAYS = 365


def _mode_temperature(
    call: ServiceCall,
    default: float,
    *,
    minimum: float = SETPOINT_TEMP_MIN,
    maximum: float = SETPOINT_TEMP_MAX,
) -> float:
    """Return the requested mode temperature, clamped to what the cloud accepts.

    Out-of-range values are clamped rather than rejected so existing automations keep
    working, but the clamp is logged — the appliance would otherwise apply something
    the user did not ask for with no explanation. Away has a lower ceiling than the
    other modes, so callers pass its own bounds.
    """
    requested = float(call.data.get(ATTR_TEMPERATURE, default))
    clamped = min(max(requested, minimum), maximum)
    if clamped != requested:
        _LOGGER.warning(
            "Requested %.1f °C is outside the %.0f-%.0f °C range the Dimplex cloud accepts; using %.1f °C",
            requested,
            minimum,
            maximum,
            clamped,
        )
    return clamped


def _away_temperature(call: ServiceCall) -> float:
    """Away target, clamped to the cloud's 7-18 °C Away range (#174)."""
    return _mode_temperature(
        call,
        _DEFAULT_AWAY_TEMP,
        minimum=AWAY_TEMP_MIN,
        maximum=AWAY_TEMP_MAX,
    )


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


def _runtime_for(hass: HomeAssistant, config_entry_id: str) -> Any | None:
    """Return the runtime of a loaded config entry, or ``None``.

    Runtime lives on the config entry itself. Home Assistant *deletes*
    ``runtime_data`` when an entry unloads, so this reads it with ``getattr``
    rather than assuming it is still attached — and an action aimed at a device
    belonging to an unloaded entry then reports the same "no runtime" error as
    before.
    """
    entry = hass.config_entries.async_get_entry(config_entry_id)
    if entry is None:
        return None
    return getattr(entry, "runtime_data", None)


def _hub_for_appliance(runtime: Any, appliance_id: str) -> str | None:
    """Return the hub an appliance belongs to, from the coordinator snapshot."""
    for row in (runtime.status.data or {}).get("appliances", []):
        if row["appliance"].ApplianceId == appliance_id:
            return str(row["hub"].HubId)
    return None


def _appliance_name(hass: HomeAssistant, config_entry_id: str, appliance_id: str) -> str:
    """Return an appliance's friendly name, falling back to its id."""
    runtime = _runtime_for(hass, config_entry_id)
    if runtime is not None:
        for row in (runtime.status.data or {}).get("appliances", []):
            if row["appliance"].ApplianceId == appliance_id:
                name = getattr(row["appliance"], "FriendlyName", None)
                if name:
                    return str(name)
    return appliance_id


def _capabilities_for(hass: HomeAssistant, config_entry_id: str, appliance_id: str) -> Any | None:
    """Return the resolved capability matrix for one appliance, or None."""
    runtime = _runtime_for(hass, config_entry_id)
    if runtime is None:
        return None
    for row in (runtime.status.data or {}).get("appliances", []):
        if row["appliance"].ApplianceId == appliance_id:
            return capabilities_for_row(row["appliance"], row.get("status"), row.get("product"))
    return None


def _resolve_appliance_id(
    hass: HomeAssistant,
    config_entry_id: str,
    appliance_id: str,
) -> tuple[str, str, str, Any] | None:
    """Return (entry_id, hub_id, appliance_id, api) for a known appliance id."""
    runtime = _runtime_for(hass, config_entry_id)
    if runtime is None:
        _LOGGER.error("No runtime for config entry %s", config_entry_id)
        return None
    hub_id = _hub_for_appliance(runtime, appliance_id)
    if not hub_id:
        _LOGGER.error("Appliance %s not found in coordinator data", appliance_id)
        return None
    return config_entry_id, hub_id, appliance_id, runtime.api


def _resolve_device_id(hass: HomeAssistant, device_id: str) -> tuple[str, str, str, Any] | None:
    """Return (entry_id, hub_id, appliance_id, api) for a device registry id."""
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(device_id)
    if device is None or not device.config_entries:
        _LOGGER.error("Unknown device_id for dimplex service: %s", device_id)
        return None
    config_entry_id = next(iter(device.config_entries))
    appliance_id: str | None = None
    for domain, ident in device.identifiers:
        if domain == DOMAIN:
            appliance_id = ident
            break
    if not appliance_id:
        _LOGGER.error("Could not resolve an appliance id from device %s", device_id)
        return None
    return _resolve_appliance_id(hass, config_entry_id, appliance_id)


async def _resolve_appliance(hass: HomeAssistant, call: ServiceCall) -> tuple[str, str, str, Any] | None:
    """Return (entry_id, hub_id, appliance_id, api) from device_id or entity_id."""
    device_id = call.data.get(ATTR_DEVICE_ID)
    entity_id = call.data.get(ATTR_ENTITY_ID)

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
            if not appliance_id:
                _LOGGER.error("Could not resolve appliance id from service target")
                return None
            return _resolve_appliance_id(hass, config_entry_id, appliance_id)

    if not device_id:
        _LOGGER.error("dimplex service requires device_id or entity_id")
        return None

    return _resolve_device_id(hass, device_id)


async def _refresh_status(hass: HomeAssistant, config_entry_id: str) -> None:
    """Ask the status coordinator to refresh so state reflects the change quickly.

    Control services mutate appliance state on the cloud; without an explicit
    refresh the new state would not appear until the next scheduled poll.
    """
    runtime = _runtime_for(hass, config_entry_id)
    if runtime is not None:
        await runtime.status.async_request_refresh()


def _invalidate_schedules(hass: HomeAssistant, config_entry_id: str) -> None:
    """Force the next status poll to re-fetch timer schedules.

    Schedules are cached for fifteen minutes, so without this a schedule write would
    not show up on the Schedule sensor (or on climate's off-like detection, which
    reads the timer mode) for up to that long.
    """
    runtime = _runtime_for(hass, config_entry_id)
    if runtime is None:
        return
    invalidate = getattr(runtime.status, "invalidate_schedules", None)
    if callable(invalidate):
        invalidate()


def _source_timer_mode(hass: HomeAssistant, config_entry_id: str, appliance_id: str) -> int:
    """Return the source appliance's timer mode, or user-timer when unknown."""
    runtime = _runtime_for(hass, config_entry_id)
    if runtime is None:
        return TIMER_USER
    schedules = (runtime.status.data or {}).get("schedules") or {}
    mode = getattr(schedules.get(appliance_id), "TimerMode", None)
    if mode is None:
        return TIMER_USER
    try:
        return int(mode)
    except (TypeError, ValueError):
        return TIMER_USER


def _require_capability(
    hass: HomeAssistant,
    config_entry_id: str,
    appliance_id: str,
    capability: str,
    target: str,
) -> Any:
    """Return the capability matrix, refusing the action if the flag is false.

    Checked before the write rather than letting the cloud answer, because for the
    hot-water endpoints a wrong guess is not harmless: an appliance that has no
    cylinder would be sent a cylinder write, and the failure mode of these untested
    endpoints is unknown (#199).
    """
    caps = _capabilities_for(hass, config_entry_id, appliance_id)
    if caps is not None and not getattr(caps, capability, False):
        raise HomeAssistantError(
            f"{_appliance_name(hass, config_entry_id, appliance_id)} does not support this "
            f"control ({capability} is false for it), so {target} was not sent."
        )
    return caps


def _normalise_clock(value: Any) -> str:
    """Coerce a clock value to the cloud's ``HH:MM:SS`` shape.

    The cloud matches a period on the exact ``StartTime`` string, and Home Assistant's
    time selector already produces ``HH:MM:SS`` — but a hand-written YAML literal is
    usually ``06:00``, which would otherwise never match.
    """
    text = str(value).strip()
    return f"{text}:00" if text.count(":") == 1 else text


def _translated(handler: Any) -> Any:
    """Translate adapter failures raised by an action handler.

    Every ``dimplex.*`` action called the API bare, so a refusal or a dropped
    connection surfaced as a raw adapter exception with a traceback — the same
    failure the climate entity has reported readably since #149. The action name is
    used as the target because an action may be aimed at an entity, a device or an
    area, so there is not always a single appliance name to quote (#198).
    """

    @functools.wraps(handler)
    async def _wrapper(call: ServiceCall) -> None:
        with control_errors(f"{DOMAIN}.{call.service}"):
            await handler(call)

    return _wrapper


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register dimplex domain services (idempotent)."""
    if hass.data.get(f"{DOMAIN}_services"):
        return
    hass.data[f"{DOMAIN}_services"] = True

    @_translated
    async def handle_set_boost(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_boost(
            hub_id,
            appliance_id,
            temperature=_mode_temperature(call, _DEFAULT_BOOST_TEMP),
            duration_minutes=int(call.data.get(ATTR_DURATION, _DEFAULT_BOOST_MINUTES)),
            enable=True,
        )
        await _refresh_status(hass, entry_id)

    @_translated
    async def handle_clear_boost(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_boost(
            hub_id,
            appliance_id,
            temperature=_mode_temperature(call, _DEFAULT_BOOST_TEMP),
            enable=False,
        )
        await _refresh_status(hass, entry_id)

    @_translated
    async def handle_set_away(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_away(
            hub_id,
            appliance_id,
            temperature=_away_temperature(call),
            enable=True,
            until=call.data.get(ATTR_UNTIL),
            number_of_days=int(call.data.get(ATTR_DAYS, 0)),
        )
        await _refresh_status(hass, entry_id)

    @_translated
    async def handle_clear_away(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_away(
            hub_id,
            appliance_id,
            temperature=_away_temperature(call),
            enable=False,
        )
        await _refresh_status(hass, entry_id)

    @_translated
    async def handle_set_advance(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        # A cylinder has no "next comfort period" to jump to, and the capability
        # matrix says so. Advancing one is meaningless rather than merely refused
        # (#199).
        _require_capability(hass, entry_id, appliance_id, "advance", f"{DOMAIN}.{call.service}")
        await api.async_set_advance(
            hub_id,
            appliance_id,
            enable=True,
            temperature=call.data.get(ATTR_TEMPERATURE),
        )
        await _refresh_status(hass, entry_id)

    @_translated
    async def handle_clear_advance(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        _require_capability(hass, entry_id, appliance_id, "advance", f"{DOMAIN}.{call.service}")
        await api.async_set_advance(hub_id, appliance_id, enable=False)
        await _refresh_status(hass, entry_id)

    @_translated
    async def handle_eco(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        await api.async_set_eco_start(hub_id, appliance_id, bool(call.data.get(ATTR_ENABLE, True)))
        await _refresh_status(hass, entry_id)

    @_translated
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
        schema=_target_schema().extend(
            {
                vol.Optional(ATTR_TEMPERATURE, default=_DEFAULT_AWAY_TEMP): vol.Coerce(float),
                vol.Optional(ATTR_DAYS): vol.All(vol.Coerce(int), vol.Range(min=1, max=_MAX_AWAY_DAYS)),
                vol.Optional(ATTR_UNTIL): cv.datetime,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_AWAY,
        handle_clear_away,
        schema=_target_schema().extend({vol.Optional(ATTR_TEMPERATURE, default=_DEFAULT_AWAY_TEMP): vol.Coerce(float)}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ADVANCE,
        handle_set_advance,
        schema=_target_schema().extend({vol.Optional(ATTR_TEMPERATURE): vol.Coerce(float)}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_ADVANCE,
        handle_clear_advance,
        schema=_target_schema(),
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

    @_translated
    async def handle_copy_schedule(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved

        targets: list[str] = []
        for target_device_id in call.data[ATTR_TARGET_DEVICE_IDS]:
            target = _resolve_device_id(hass, target_device_id)
            if target is None:
                # Named individually: a silent partial copy would leave some heaters
                # on the old programme with nothing saying which.
                raise HomeAssistantError(
                    f"Could not resolve {target_device_id} as a Dimplex appliance; no schedule was copied."
                )
            target_hub, target_appliance = target[1], target[2]
            if target_hub != hub_id:
                # One API call carries one HubId, so a cross-hub target cannot work.
                raise HomeAssistantError(
                    "Every target appliance must be on the same hub as the source; no schedule was copied."
                )
            if target_appliance != appliance_id:
                targets.append(target_appliance)

        if not targets:
            _LOGGER.warning("dimplex.copy_schedule had no target other than the source appliance")
            return

        # The source's own mode travels with the schedule: copying the periods but
        # leaving the targets in a different timer mode would not reproduce it.
        await api.async_copy_schedule(
            hub_id, appliance_id, targets, timer_mode=_source_timer_mode(hass, entry_id, appliance_id)
        )
        _invalidate_schedules(hass, entry_id)
        await _refresh_status(hass, entry_id)

    @_translated
    async def handle_set_period_setpoint(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        day_of_week = DAY_NAMES[str(call.data[ATTR_DAY]).lower()]
        start_time = _normalise_clock(call.data[ATTR_START_TIME])
        end_time = _normalise_clock(call.data[ATTR_END_TIME]) if call.data.get(ATTR_END_TIME) else None
        try:
            await api.async_set_period_setpoint(
                hub_id,
                appliance_id,
                day_of_week=day_of_week,
                start_time=start_time,
                temperature=float(call.data[ATTR_TEMPERATURE]),
                end_time=end_time,
            )
        except ValueError as err:
            # The library matches periods on day + start time and raises ValueError
            # when nothing matches. Uncaught that is an opaque traceback; the useful
            # answer is "there is no such period", with what to check.
            raise HomeAssistantError(
                f"{_appliance_name(hass, entry_id, appliance_id)} has no schedule period starting "
                f"{start_time} on {call.data[ATTR_DAY]}. Check that appliance's Schedule sensor for "
                "its actual periods — this action edits an existing period, it does not create one."
            ) from err
        _invalidate_schedules(hass, entry_id)
        await _refresh_status(hass, entry_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_COPY_SCHEDULE,
        handle_copy_schedule,
        schema=_target_schema().extend({vol.Required(ATTR_TARGET_DEVICE_IDS): vol.All(cv.ensure_list, [cv.string])}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PERIOD_SETPOINT,
        handle_set_period_setpoint,
        schema=_target_schema().extend(
            {
                vol.Required(ATTR_DAY): vol.In(list(DAY_NAMES)),
                vol.Required(ATTR_START_TIME): cv.string,
                vol.Required(ATTR_TEMPERATURE): vol.Coerce(float),
                vol.Optional(ATTR_END_TIME): cv.string,
            }
        ),
    )

    @_translated
    async def handle_hot_water_temperature(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        _require_capability(hass, entry_id, appliance_id, "hot_water", f"{DOMAIN}.{call.service}")
        # The temperature endpoints have no ASHW variant, so unlike the mode and
        # hygiene writes this one needs no heat-pump flag.
        await api.async_set_hot_water_temperature(
            hub_id,
            appliance_id,
            mode=str(call.data[ATTR_MODE]),
            temperature=float(call.data[ATTR_TEMPERATURE]),
            enable=bool(call.data.get(ATTR_ENABLE, True)),
        )
        await _refresh_status(hass, entry_id)

    @_translated
    async def handle_hot_water_hygiene(call: ServiceCall) -> None:
        resolved = await _resolve_appliance(hass, call)
        if resolved is None:
            return
        entry_id, hub_id, appliance_id, api = resolved
        caps = _require_capability(hass, entry_id, appliance_id, "hygiene", f"{DOMAIN}.{call.service}")
        # Endpoint selection, not a user choice: SetHygieneSettingsHwc and
        # SetHygieneSettingsHeatPumpHwc are not interchangeable.
        await api.async_set_hot_water_hygiene(
            hub_id,
            appliance_id,
            temperature=float(call.data[ATTR_TEMPERATURE]),
            frequency=HYGIENE_FREQUENCIES[str(call.data[ATTR_FREQUENCY])],
            enable=bool(call.data.get(ATTR_ENABLE, True)),
            heat_pump=bool(getattr(caps, "heat_pump", False)),
        )
        await _refresh_status(hass, entry_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HOT_WATER_TEMPERATURE,
        handle_hot_water_temperature,
        schema=_target_schema().extend(
            {
                vol.Required(ATTR_MODE): vol.In(list(HOT_WATER_MODES)),
                vol.Required(ATTR_TEMPERATURE): vol.Coerce(float),
                vol.Optional(ATTR_ENABLE, default=True): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HOT_WATER_HYGIENE,
        handle_hot_water_hygiene,
        schema=_target_schema().extend(
            {
                vol.Required(ATTR_TEMPERATURE): vol.Coerce(float),
                vol.Required(ATTR_FREQUENCY): vol.In(list(HYGIENE_FREQUENCIES)),
                vol.Optional(ATTR_ENABLE, default=True): cv.boolean,
            }
        ),
    )


async def async_unload_services(hass: HomeAssistant, unloading_entry_id: str | None = None) -> None:
    """Remove domain services once the last config entry has unloaded.

    ``unloading_entry_id`` names the entry being unloaded right now: its
    ``runtime_data`` is still attached at this point, because Home Assistant only
    deletes it after ``async_unload_entry`` returns. Without excluding it the
    "no entries left" test would never be true and the services would be
    registered forever.
    """
    still_loaded = any(
        candidate.entry_id != unloading_entry_id and getattr(candidate, "runtime_data", None) is not None
        for candidate in hass.config_entries.async_entries(DOMAIN)
    )
    if still_loaded:
        return
    if not hass.data.get(f"{DOMAIN}_services"):
        return
    for service in (
        SERVICE_SET_BOOST,
        SERVICE_CLEAR_BOOST,
        SERVICE_SET_AWAY,
        SERVICE_CLEAR_AWAY,
        SERVICE_SET_ADVANCE,
        SERVICE_CLEAR_ADVANCE,
        SERVICE_SET_ECO_START,
        SERVICE_SET_OPEN_WINDOW,
        SERVICE_COPY_SCHEDULE,
        SERVICE_SET_PERIOD_SETPOINT,
        SERVICE_SET_HOT_WATER_TEMPERATURE,
        SERVICE_SET_HOT_WATER_HYGIENE,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
    hass.data.pop(f"{DOMAIN}_services", None)
