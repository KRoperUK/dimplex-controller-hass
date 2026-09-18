"""Tests for domain services."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import AWAY_TEMP_MAX, DOMAIN
from custom_components.dimplex.services import (
    SERVICE_CLEAR_ADVANCE,
    SERVICE_COPY_SCHEDULE,
    SERVICE_SET_ADVANCE,
    SERVICE_SET_AWAY,
    SERVICE_SET_BOOST,
    SERVICE_SET_HOT_WATER_HYGIENE,
    SERVICE_SET_HOT_WATER_TEMPERATURE,
    SERVICE_SET_PERIOD_SETPOINT,
    _appliance_id_from_unique_id,
    async_setup_services,
)

from .const import MOCK_ENTRY_DATA


def test_parse_unique_id():
    assert _appliance_id_from_unique_id("entry1", "entry1_app-1_climate") == "app-1"
    assert _appliance_id_from_unique_id("entry1", "entry1_app-1_boost") == "app-1"
    # Fallback path only (services prefer device registry when entity has a device).
    assert _appliance_id_from_unique_id("entry1", "entry1_app-1_room_temperature") == "app-1_room"


async def test_set_boost_service_by_device(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="svc-entry")
    entry.add_to_hass(hass)

    api = MagicMock()
    api.async_set_boost = AsyncMock()
    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(ApplianceId="app-1")
    status_coord = MagicMock()
    status_coord.async_request_refresh = AsyncMock()
    status_coord.data = {
        "appliances": [{"hub": hub, "zone": SimpleNamespace(ZoneName="Z"), "appliance": appliance, "status": None}]
    }
    runtime = SimpleNamespace(api=api, status=status_coord)
    entry.runtime_data = runtime

    await async_setup_services(hass)

    # Register a fake device in the device registry
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "app-1")},
        name="Heater",
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_BOOST,
        {"device_id": device.id, "temperature": 24.0, "duration": 30},
        blocking=True,
    )
    api.async_set_boost.assert_awaited_once()
    kwargs = api.async_set_boost.await_args
    assert kwargs.args[0] == "hub-1"
    assert kwargs.args[1] == "app-1"
    assert kwargs.kwargs["temperature"] == 24.0
    assert kwargs.kwargs["duration_minutes"] == 30
    assert kwargs.kwargs["enable"] is True
    # State change is reflected promptly via a coordinator refresh.
    status_coord.async_request_refresh.assert_awaited_once()


def _make_runtime():
    """Build a runtime whose api records calls and whose status refresh is awaitable."""
    api = MagicMock()
    api.async_set_boost = AsyncMock()
    api.async_set_away = AsyncMock()
    api.async_set_eco_start = AsyncMock()
    api.async_set_open_window_detection = AsyncMock()
    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(ApplianceId="app-1")
    status_coord = MagicMock()
    status_coord.async_request_refresh = AsyncMock()
    status_coord.data = {
        "appliances": [{"hub": hub, "zone": SimpleNamespace(ZoneName="Z"), "appliance": appliance, "status": None}]
    }
    return SimpleNamespace(api=api, status=status_coord)


async def _register_entry(hass: HomeAssistant, runtime, entry_id: str = "svc-entry"):
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id=entry_id)
    entry.add_to_hass(hass)
    entry.runtime_data = runtime
    await async_setup_services(hass)
    return entry


async def _device_id(hass: HomeAssistant, entry, appliance_id: str = "app-1") -> str:
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, appliance_id)},
        name="Heater",
    )
    return device.id


@pytest.mark.parametrize(
    ("service", "api_attr", "extra_data"),
    [
        ("clear_boost", "async_set_boost", {}),
        ("set_away", "async_set_away", {"temperature": 12.0}),
        ("clear_away", "async_set_away", {}),
        ("set_eco_start", "async_set_eco_start", {"enable": True}),
        ("set_open_window_detection", "async_set_open_window_detection", {"enable": False}),
    ],
)
async def test_control_services_call_api_and_refresh(hass: HomeAssistant, service, api_attr, extra_data) -> None:
    """Each control service invokes the API and requests a status refresh."""
    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        service,
        {"device_id": device_id, **extra_data},
        blocking=True,
    )

    getattr(runtime.api, api_attr).assert_awaited_once()
    runtime.status.async_request_refresh.assert_awaited_once()


async def test_set_away_disable_flag(hass: HomeAssistant) -> None:
    """clear_away disables Away mode."""
    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(DOMAIN, "clear_away", {"device_id": device_id}, blocking=True)
    assert runtime.api.async_set_away.await_args.kwargs["enable"] is False


async def test_service_resolves_by_entity_id(hass: HomeAssistant) -> None:
    """A service target given as entity_id resolves through the entity registry."""
    from homeassistant.helpers import entity_registry as er

    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "climate",
        DOMAIN,
        f"{entry.entry_id}_app-1_climate",
        config_entry=entry,
        device_id=device_id,
    )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_BOOST,
        {"entity_id": "climate.heater"},
        blocking=True,
    )
    # entity_id may differ; assert the resolution reached the API regardless.
    runtime.api.async_set_boost.assert_awaited_once()


async def test_service_unknown_appliance_is_noop(hass: HomeAssistant) -> None:
    """A device not present in coordinator data resolves to no API call."""
    runtime = _make_runtime()
    runtime.status.data = {"appliances": []}  # appliance not known to the coordinator
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_BOOST,
        {"device_id": device_id},
        blocking=True,
    )
    runtime.api.async_set_boost.assert_not_awaited()
    runtime.status.async_request_refresh.assert_not_awaited()


async def test_set_away_accepts_a_duration_in_days(hass: HomeAssistant) -> None:
    """#163: the app requires an away duration, so the service must accept one."""
    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_AWAY,
        {"device_id": device_id, "temperature": 18.0, "days": 3},
        blocking=True,
    )

    kwargs = runtime.api.async_set_away.await_args.kwargs
    assert kwargs["temperature"] == 18.0
    assert kwargs["number_of_days"] == 3
    assert kwargs["until"] is None
    assert kwargs["enable"] is True


async def test_set_away_accepts_an_until_datetime(hass: HomeAssistant) -> None:
    """An explicit come-home moment is passed through as the away-until date."""
    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_AWAY,
        {"device_id": device_id, "until": "2026-12-24 09:30:00"},
        blocking=True,
    )

    kwargs = runtime.api.async_set_away.await_args.kwargs
    assert kwargs["until"] == datetime(2026, 12, 24, 9, 30)
    assert kwargs["number_of_days"] == 0


async def test_mode_temperature_is_clamped_to_the_cloud_range(hass: HomeAssistant) -> None:
    """Out-of-range targets are clamped rather than silently misapplied."""
    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_AWAY,
        {"device_id": device_id, "temperature": 4.0},
        blocking=True,
    )
    assert runtime.api.async_set_away.await_args.kwargs["temperature"] == 7.0

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_BOOST,
        {"device_id": device_id, "temperature": 45.0},
        blocking=True,
    )
    assert runtime.api.async_set_boost.await_args.kwargs["temperature"] == 30.0


async def test_away_has_a_lower_ceiling_than_a_setpoint(hass: HomeAssistant) -> None:
    """Away tops out at 18 °C; the cloud silently reduces anything higher (#174)."""
    runtime = _make_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    # The reported case: 25 was accepted locally and became 18 at the appliance.
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_AWAY,
        {"device_id": device_id, "temperature": 25.0},
        blocking=True,
    )
    assert runtime.api.async_set_away.await_args.kwargs["temperature"] == AWAY_TEMP_MAX == 18.0

    # A value inside the Away range passes through untouched.
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_AWAY,
        {"device_id": device_id, "temperature": 17.0},
        blocking=True,
    )
    assert runtime.api.async_set_away.await_args.kwargs["temperature"] == 17.0

    # Boost keeps the wider setpoint range — only Away is known to differ.
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_BOOST,
        {"device_id": device_id, "temperature": 25.0},
        blocking=True,
    )
    assert runtime.api.async_set_boost.await_args.kwargs["temperature"] == 25.0


async def test_advance_services(hass: HomeAssistant) -> None:
    """Advance brings the next comfort period on early; clear cancels it."""
    runtime = _make_runtime()
    runtime.api.async_set_advance = AsyncMock()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_ADVANCE,
        {"device_id": device_id},
        blocking=True,
    )
    kwargs = runtime.api.async_set_advance.await_args.kwargs
    assert kwargs["enable"] is True
    # No explicit target -> the library sends the "follow the schedule" sentinel.
    assert kwargs["temperature"] is None

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_ADVANCE,
        {"device_id": device_id, "temperature": 22.0},
        blocking=True,
    )
    assert runtime.api.async_set_advance.await_args.kwargs["temperature"] == 22.0

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAR_ADVANCE,
        {"device_id": device_id},
        blocking=True,
    )
    assert runtime.api.async_set_advance.await_args.kwargs["enable"] is False
    assert runtime.status.async_request_refresh.await_count == 3


@pytest.mark.parametrize(
    ("adapter_error", "expected_message"),
    [
        ("ControlRejected", "rejected this control"),
        ("CannotConnect", "Could not reach the Dimplex cloud"),
        ("InvalidAuth", "authentication failed"),
    ],
)
async def test_action_failures_surface_a_readable_error(
    hass: HomeAssistant, adapter_error: str, expected_message: str
) -> None:
    """Every dimplex.* action must translate adapter failures (#198).

    The handlers called the API bare, so an appliance that refuses boost surfaced a
    raw adapter exception — the "unknown error" of #149, which only the climate
    entity had ever translated. The message names the action, because an action can
    target an entity, a device or an area and so has no single appliance name.
    """
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.dimplex import api as api_module

    error_cls = getattr(api_module, adapter_error)

    runtime = _make_runtime()
    runtime.api.async_set_boost = AsyncMock(side_effect=error_cls("nope"))
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    with pytest.raises(HomeAssistantError, match=expected_message):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_BOOST,
            {"device_id": device_id},
            blocking=True,
        )


async def test_action_error_message_names_the_action(hass: HomeAssistant) -> None:
    """The translated message must identify which action failed."""
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.dimplex.api import ControlRejected

    runtime = _make_runtime()
    runtime.api.async_set_boost = AsyncMock(side_effect=ControlRejected("Forbidden", status=403))
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    with pytest.raises(HomeAssistantError, match=r"dimplex\.set_boost"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_BOOST,
            {"device_id": device_id},
            blocking=True,
        )


def _make_schedule_runtime(*, hub_id: str = "hub-1", timer_mode=1):
    """Runtime with two appliances on one hub and a cached schedule for the first."""
    api = MagicMock()
    api.async_copy_schedule = AsyncMock()
    api.async_set_period_setpoint = AsyncMock()
    hub = SimpleNamespace(HubId=hub_id)
    zone = SimpleNamespace(ZoneName="Z")
    source = SimpleNamespace(ApplianceId="app-1", FriendlyName="Hallway Heater")
    target = SimpleNamespace(ApplianceId="app-2", FriendlyName="Lounge Heater")
    status_coord = MagicMock()
    status_coord.async_request_refresh = AsyncMock()
    status_coord.data = {
        "appliances": [
            {"hub": hub, "zone": zone, "appliance": source, "status": None},
            {"hub": hub, "zone": zone, "appliance": target, "status": None},
        ],
        "schedules": {"app-1": SimpleNamespace(TimerMode=timer_mode)},
    }
    return SimpleNamespace(api=api, status=status_coord)


async def test_copy_schedule_copies_the_periods_and_the_source_mode(hass: HomeAssistant) -> None:
    """The source's timer mode travels with the programme, or the copy is not a copy."""
    runtime = _make_schedule_runtime(timer_mode=1)
    entry = await _register_entry(hass, runtime)
    source_device_id = await _device_id(hass, entry, "app-1")
    target_device_id = await _device_id(hass, entry, "app-2")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_COPY_SCHEDULE,
        {"device_id": source_device_id, "target_device_ids": [target_device_id]},
        blocking=True,
    )

    runtime.api.async_copy_schedule.assert_awaited_once()
    args, kwargs = runtime.api.async_copy_schedule.await_args
    assert args == ("hub-1", "app-1", ["app-2"])
    assert kwargs["timer_mode"] == 1
    # Schedules are cached for 15 minutes, so the write has to invalidate them.
    runtime.status.invalidate_schedules.assert_called_once()
    runtime.status.async_request_refresh.assert_awaited_once()


async def test_copy_schedule_uses_user_timer_when_no_schedule_is_cached(hass: HomeAssistant) -> None:
    """An unknown source mode must not send a nonsense timer mode."""
    runtime = _make_schedule_runtime()
    runtime.status.data["schedules"] = {}
    entry = await _register_entry(hass, runtime)
    source_device_id = await _device_id(hass, entry, "app-1")
    target_device_id = await _device_id(hass, entry, "app-2")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_COPY_SCHEDULE,
        {"device_id": source_device_id, "target_device_ids": [target_device_id]},
        blocking=True,
    )

    assert runtime.api.async_copy_schedule.await_args.kwargs["timer_mode"] == 0


async def test_copy_schedule_ignores_the_source_in_its_own_target_list(hass: HomeAssistant) -> None:
    """Listing the source as a target is a no-op, not an error."""
    runtime = _make_schedule_runtime()
    entry = await _register_entry(hass, runtime)
    source_device_id = await _device_id(hass, entry, "app-1")

    await hass.services.async_call(
        DOMAIN,
        SERVICE_COPY_SCHEDULE,
        {"device_id": source_device_id, "target_device_ids": [source_device_id]},
        blocking=True,
    )

    runtime.api.async_copy_schedule.assert_not_awaited()


async def test_copy_schedule_refuses_to_copy_to_only_some_targets(hass: HomeAssistant) -> None:
    """An unresolvable target aborts the whole action rather than copying partially."""
    from homeassistant.exceptions import HomeAssistantError

    runtime = _make_schedule_runtime()
    entry = await _register_entry(hass, runtime)
    source_device_id = await _device_id(hass, entry, "app-1")
    good_target = await _device_id(hass, entry, "app-2")

    with pytest.raises(HomeAssistantError, match="no schedule was copied"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COPY_SCHEDULE,
            {"device_id": source_device_id, "target_device_ids": [good_target, "not-a-device"]},
            blocking=True,
        )

    runtime.api.async_copy_schedule.assert_not_awaited()


async def test_copy_schedule_refuses_a_target_on_another_hub(hass: HomeAssistant) -> None:
    """One API call carries one hub id, so a cross-hub target cannot work."""
    from homeassistant.exceptions import HomeAssistantError

    runtime = _make_schedule_runtime()
    entry = await _register_entry(hass, runtime)
    source_device_id = await _device_id(hass, entry, "app-1")

    other_runtime = _make_schedule_runtime(hub_id="hub-2")
    other_entry = await _register_entry(hass, other_runtime, entry_id="svc-entry-2")
    remote_device_id = await _device_id(hass, other_entry, "app-2")

    with pytest.raises(HomeAssistantError, match="same hub"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COPY_SCHEDULE,
            {"device_id": source_device_id, "target_device_ids": [remote_device_id]},
            blocking=True,
        )

    runtime.api.async_copy_schedule.assert_not_awaited()


async def test_set_period_setpoint_maps_the_day_and_normalises_the_clock(hass: HomeAssistant) -> None:
    """``06:00`` in YAML has to match the cloud's ``06:00:00`` period strings."""
    runtime = _make_schedule_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_PERIOD_SETPOINT,
        {"device_id": device_id, "day": "monday", "start_time": "06:00", "temperature": 21},
        blocking=True,
    )

    runtime.api.async_set_period_setpoint.assert_awaited_once()
    kwargs = runtime.api.async_set_period_setpoint.await_args.kwargs
    assert kwargs["day_of_week"] == 1  # 0 = Sunday, so Monday is 1
    assert kwargs["start_time"] == "06:00:00"
    assert kwargs["temperature"] == 21.0
    assert kwargs["end_time"] is None
    runtime.status.invalidate_schedules.assert_called_once()
    runtime.status.async_request_refresh.assert_awaited_once()


async def test_set_period_setpoint_reports_a_missing_period_readably(hass: HomeAssistant) -> None:
    """A day/time with no matching period must name what to check, not traceback."""
    from homeassistant.exceptions import HomeAssistantError

    runtime = _make_schedule_runtime()
    runtime.api.async_set_period_setpoint = AsyncMock(
        side_effect=ValueError("No timer period for day=1 start='06:00:00' on appliance app-1")
    )
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    with pytest.raises(HomeAssistantError, match="Hallway Heater has no schedule period starting 06:00:00 on monday"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_PERIOD_SETPOINT,
            {"device_id": device_id, "day": "monday", "start_time": "06:00:00", "temperature": 21},
            blocking=True,
        )


def _make_hot_water_runtime():
    """Runtime whose one appliance can be given cylinder capabilities by patching."""
    runtime = _make_runtime()
    runtime.api.async_set_hot_water_temperature = AsyncMock()
    runtime.api.async_set_hot_water_hygiene = AsyncMock()
    return runtime


async def test_hot_water_temperature_writes_the_requested_mode(hass: HomeAssistant) -> None:
    """``mode`` picks between the normal and boost endpoints."""
    from custom_components.dimplex.capabilities import LocalCapabilities

    runtime = _make_hot_water_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    with patch(
        "custom_components.dimplex.services.capabilities_for_row",
        return_value=LocalCapabilities(hot_water=True),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOT_WATER_TEMPERATURE,
            {"device_id": device_id, "mode": "boost", "temperature": 60},
            blocking=True,
        )

    runtime.api.async_set_hot_water_temperature.assert_awaited_once()
    assert runtime.api.async_set_hot_water_temperature.await_args.kwargs == {
        "mode": "boost",
        "temperature": 60.0,
        "enable": True,
    }
    runtime.status.async_request_refresh.assert_awaited_once()


async def test_hot_water_actions_refuse_an_appliance_that_is_not_a_cylinder(hass: HomeAssistant) -> None:
    """A cylinder write must not be sent to a panel heater at all.

    These endpoints are untested, so their failure mode on the wrong appliance is
    unknown — refusing locally is the only safe answer (#199).
    """
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.dimplex.capabilities import LocalCapabilities

    runtime = _make_hot_water_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    with (
        patch(
            "custom_components.dimplex.services.capabilities_for_row",
            return_value=LocalCapabilities(hot_water=False),
        ),
        pytest.raises(HomeAssistantError, match="does not support this control"),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOT_WATER_TEMPERATURE,
            {"device_id": device_id, "mode": "normal", "temperature": 50},
            blocking=True,
        )

    runtime.api.async_set_hot_water_temperature.assert_not_awaited()


async def test_hot_water_hygiene_picks_the_heat_pump_endpoint(hass: HomeAssistant) -> None:
    """The ASHW endpoint variant is chosen from the capability matrix, not the user."""
    from dimplex_controller import HygieneFrequency

    from custom_components.dimplex.capabilities import LocalCapabilities

    runtime = _make_hot_water_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    with patch(
        "custom_components.dimplex.services.capabilities_for_row",
        return_value=LocalCapabilities(hot_water=True, heat_pump=True, hygiene=True),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOT_WATER_HYGIENE,
            {"device_id": device_id, "temperature": 60, "frequency": "weekly"},
            blocking=True,
        )

    assert runtime.api.async_set_hot_water_hygiene.await_args.kwargs == {
        "temperature": 60.0,
        "frequency": HygieneFrequency.WEEKLY,
        "enable": True,
        "heat_pump": True,
    }


async def test_hot_water_hygiene_refuses_an_appliance_without_hygiene(hass: HomeAssistant) -> None:
    """Hygiene is its own capability flag, not implied by being a cylinder."""
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.dimplex.capabilities import LocalCapabilities

    runtime = _make_hot_water_runtime()
    entry = await _register_entry(hass, runtime)
    device_id = await _device_id(hass, entry)

    with (
        patch(
            "custom_components.dimplex.services.capabilities_for_row",
            return_value=LocalCapabilities(hot_water=True, hygiene=False),
        ),
        pytest.raises(HomeAssistantError, match="does not support this control"),
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_HOT_WATER_HYGIENE,
            {"device_id": device_id, "temperature": 60, "frequency": "monthly"},
            blocking=True,
        )

    runtime.api.async_set_hot_water_hygiene.assert_not_awaited()
