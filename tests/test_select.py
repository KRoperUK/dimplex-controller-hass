"""Tests for the select platform (per-appliance boost duration, #252)."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.select import SERVICE_SELECT_OPTION
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.capabilities import LocalCapabilities
from custom_components.dimplex.const import DOMAIN

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _payload():
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="QM100RF",
        ApplianceType="Quantum",
    )
    status = SimpleNamespace(
        EcoStartEnabled=False,
        ComfortStatus=True,
        RoomTemperature=21.5,
        ActiveSetPointTemperature=20,
        OpenWindowEnabled=False,
    )
    return {"appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}]}


def _api_data(payload):
    return (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
    )


def _select_entity_id(hass, needle: str = "boost_duration"):
    for state in hass.states.async_all():
        if state.entity_id.startswith("select.") and needle in state.entity_id:
            return state.entity_id
    return None


async def _setup(hass, payload, caps=None):
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    with ExitStack() as stack:
        for patcher in _api_data(payload):
            stack.enter_context(patcher)
        if caps is not None:
            stack.enter_context(patch("custom_components.dimplex.select.capabilities_for_row", return_value=caps))
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


async def test_select_options_come_from_the_capability_durations(hass):
    """A boost-capable appliance gets a select whose options are its boost_durations."""
    await _setup(hass, _payload(), caps=LocalCapabilities(boost_durations=(30, 60, 120, 180)))

    entity_id = _select_entity_id(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("options") == ["30", "60", "120", "180"]
    # Default option mirrors the capability's default_boost_minutes.
    assert state.state == "60"


async def test_selecting_an_option_records_the_duration_for_the_appliance(hass):
    """Choosing a value drives the per-appliance boost_minutes store the climate reads."""
    entry = await _setup(hass, _payload(), caps=LocalCapabilities(boost_durations=(30, 60, 120, 180)))

    entity_id = _select_entity_id(hass)
    assert entity_id is not None

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: entity_id, "option": "120"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "120"
    # This is exactly what the climate boost preset reads for its duration.
    assert entry.runtime_data.boost_minutes["appliance-1"] == 120


async def test_no_select_when_the_appliance_is_not_boost_capable(hass):
    """Capability gating, not the appliance name, decides whether the control exists."""
    await _setup(hass, _payload(), caps=LocalCapabilities(boost=False))

    assert _select_entity_id(hass) is None


async def test_select_feeds_the_climate_boost_minutes(hass):
    """The climate entity's boost length prefers the per-appliance selection.

    Built directly rather than via the component registry so the test asserts the
    wiring (``runtime_data.boost_minutes`` -> ``_boost_minutes``) without depending
    on Home Assistant's internal entity-component layout.
    """
    from custom_components.dimplex.climate import DimplexClimate

    payload = _payload()
    row = payload["appliances"][0]
    coordinator = SimpleNamespace(data=payload)
    runtime = SimpleNamespace(boost_minutes={"appliance-1": 180})
    config_entry = SimpleNamespace(entry_id="test", runtime_data=runtime, options={})

    climate = DimplexClimate(coordinator, config_entry, row, api=SimpleNamespace())

    # Per-appliance selection wins over the (empty) entry option and the default.
    assert climate._boost_minutes == 180

    # With no per-appliance selection it falls back to the capability default (60).
    runtime.boost_minutes.clear()
    assert climate._boost_minutes == 60


async def test_invalid_option_is_rejected(hass):
    """A duration outside the appliance's set raises rather than being recorded."""
    from custom_components.dimplex.select import DimplexBoostDurationSelect

    row = _payload()["appliances"][0]
    coordinator = SimpleNamespace(data=_payload())
    runtime = SimpleNamespace(boost_minutes={})
    config_entry = SimpleNamespace(entry_id="test", runtime_data=runtime)
    select = DimplexBoostDurationSelect(coordinator, config_entry, row, LocalCapabilities(boost_durations=(30, 60)))

    with pytest.raises(ValueError, match="not a valid boost duration"):
        await select.async_select_option("999")
    assert runtime.boost_minutes == {}


async def test_profile_select_options_and_current_option(hass):
    """A timer heater gets a profile select reflecting StatusTwo (#314)."""
    payload = _payload()
    payload["appliances"][0]["status"].ApplianceModes = 1
    payload["appliances"][0]["status"].StatusTwo = 2
    await _setup(hass, payload, caps=LocalCapabilities(boost=False))

    entity_id = _select_entity_id(hass, "schedule_profile")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state.attributes.get("options") == ["user_timer", "home_all_day", "out_all_day"]
    assert state.state == "out_all_day"


async def test_no_profile_select_for_cylinders(hass):
    """Hot-water cylinders have no verified profile support, so no select."""
    await _setup(hass, _payload(), caps=LocalCapabilities(boost=False, hot_water=True))

    assert _select_entity_id(hass, "schedule_profile") is None


async def test_no_profile_select_without_timer(hass):
    await _setup(hass, _payload(), caps=LocalCapabilities(boost=False, timer=False))

    assert _select_entity_id(hass, "schedule_profile") is None


async def test_profile_select_writes_the_chosen_profile(hass):
    """Choosing a profile writes it via the API and refreshes for readback."""
    from unittest.mock import AsyncMock

    from custom_components.dimplex.select import DimplexScheduleProfileSelect

    payload = _payload()
    row = payload["appliances"][0]
    row["status"].ApplianceModes = 1
    row["status"].StatusTwo = 0
    api = SimpleNamespace(async_set_schedule_profile=AsyncMock())
    coordinator = SimpleNamespace(data=payload, async_request_refresh=AsyncMock())
    config_entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace())
    select = DimplexScheduleProfileSelect(coordinator, config_entry, row, api)

    assert select.options == ["user_timer", "home_all_day", "out_all_day"]
    assert select.current_option == "user_timer"

    await select.async_select_option("home_all_day")

    api.async_set_schedule_profile.assert_awaited_once_with("hub-1", "appliance-1", 1)
    coordinator.async_request_refresh.assert_awaited_once()


async def test_profile_select_rejects_unknown_option(hass):
    """An option outside the EStatusTwo set raises and writes nothing."""
    from unittest.mock import AsyncMock

    from custom_components.dimplex.select import DimplexScheduleProfileSelect

    payload = _payload()
    row = payload["appliances"][0]
    row["status"].ApplianceModes = 128
    api = SimpleNamespace(async_set_schedule_profile=AsyncMock())
    coordinator = SimpleNamespace(data=payload, async_request_refresh=AsyncMock())
    config_entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace())
    select = DimplexScheduleProfileSelect(coordinator, config_entry, row, api)

    assert select.current_option is None

    with pytest.raises(ValueError, match="not a valid schedule profile"):
        await select.async_select_option("away")
    api.async_set_schedule_profile.assert_not_awaited()


async def test_restores_last_chosen_duration(hass):
    """The chosen duration survives a restart via RestoreEntity."""
    from unittest.mock import AsyncMock

    from custom_components.dimplex.select import DimplexBoostDurationSelect

    row = _payload()["appliances"][0]
    coordinator = SimpleNamespace(data=_payload(), async_add_listener=lambda *a, **k: lambda: None)
    runtime = SimpleNamespace(boost_minutes={})
    config_entry = SimpleNamespace(entry_id="test", runtime_data=runtime)
    select = DimplexBoostDurationSelect(
        coordinator, config_entry, row, LocalCapabilities(boost_durations=(30, 60, 120, 180))
    )
    select.hass = hass
    select.async_on_remove = lambda func: None

    # Simulate HA restoring the entity's last state across a restart.
    with patch.object(
        DimplexBoostDurationSelect, "async_get_last_state", AsyncMock(return_value=State("select.x", "120"))
    ):
        await select.async_added_to_hass()

    assert runtime.boost_minutes["appliance-1"] == 120
    assert select.current_option == "120"


def _operating_mode_select(modes, **overrides):
    """Build an operating-mode select over a stub coordinator."""
    from unittest.mock import AsyncMock

    from custom_components.dimplex.select import DimplexOperatingModeSelect

    payload = _payload()
    payload["appliances"][0]["status"].ApplianceModes = modes
    row = payload["appliances"][0]
    api = overrides.pop("api", SimpleNamespace(async_set_manual=AsyncMock(), async_set_schedule_profile=AsyncMock()))
    coordinator = SimpleNamespace(
        data=payload,
        async_request_refresh=overrides.pop("refresh", AsyncMock()),
        async_add_listener=lambda *a, **k: lambda: None,
    )
    config_entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace())
    return DimplexOperatingModeSelect(coordinator, config_entry, row, api)


async def test_operating_mode_reports_manual_timer_and_unknown():
    """Live bits map to manual/timer; bit 64 is not special-cased (#298, #299)."""
    assert _operating_mode_select(128).current_option == "manual"
    assert _operating_mode_select(1).current_option == "timer"
    # The reporter's firmware-28 Manual-as-64 frame: exposed raw elsewhere, and
    # not guessed into manual here.
    assert _operating_mode_select(64).current_option is None
    assert _operating_mode_select(None).current_option is None


async def test_operating_mode_manual_writes_manual_with_current_setpoint():
    """Selecting manual holds the current setpoint via the Manual write (#299)."""

    select = _operating_mode_select(1)
    with patch.object(select, "async_write_ha_state", MagicMock()):
        await select.async_select_option("manual")
    select._api.async_set_manual.assert_awaited_once_with("hub-1", "appliance-1", temperature=20.0)
    # Optimistic hold shows the choice before the next poll confirms it.
    assert select.current_option == "manual"


async def test_operating_mode_timer_writes_the_user_timer_profile():
    """Selecting timer returns the heater to its user-timer schedule (#299)."""

    select = _operating_mode_select(128)
    with patch.object(select, "async_write_ha_state", MagicMock()):
        await select.async_select_option("timer")
    select._api.async_set_schedule_profile.assert_awaited_once_with("hub-1", "appliance-1", 0)


async def test_operating_mode_rejects_unknown_option():
    """An option outside manual/timer raises and writes nothing."""
    select = _operating_mode_select(1)
    with pytest.raises(ValueError, match="not a valid operating mode"):
        await select.async_select_option("away")
    select._api.async_set_manual.assert_not_awaited()
    select._api.async_set_schedule_profile.assert_not_awaited()


async def test_operating_mode_refusal_surfaces_an_error():
    """A refused write raises to the caller rather than logging and returning (#299)."""
    from unittest.mock import AsyncMock

    from homeassistant.exceptions import HomeAssistantError

    from custom_components.dimplex.api import ControlRejected
    from custom_components.dimplex.select import DimplexOperatingModeSelect

    payload = _payload()
    row = payload["appliances"][0]
    api = SimpleNamespace(async_set_manual=AsyncMock(side_effect=ControlRejected("Forbidden", status=403)))
    coordinator = SimpleNamespace(data=payload, async_request_refresh=AsyncMock())
    config_entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace())
    select = DimplexOperatingModeSelect(coordinator, config_entry, row, api)

    with pytest.raises(HomeAssistantError):
        await select.async_select_option("manual")


async def test_no_operating_mode_select_for_cylinders(hass):
    """Hot-water cylinders have no verified Manual support, so no select (#299)."""
    await _setup(hass, _payload(), caps=LocalCapabilities(boost=False, hot_water=True))
    assert _select_entity_id(hass, "operating_mode") is None


async def test_no_operating_mode_select_without_timer(hass):
    """Without a timer schedule there is nothing to return to (#299)."""
    await _setup(hass, _payload(), caps=LocalCapabilities(boost=False, timer=False))
    assert _select_entity_id(hass, "operating_mode") is None


async def test_operating_mode_select_created_for_heaters(hass):
    """A timer heater gets both the profile and the operating-mode selects."""
    await _setup(hass, _payload(), caps=LocalCapabilities(boost=False))

    assert _select_entity_id(hass, "schedule_profile") is not None
    assert _select_entity_id(hass, "operating_mode") is not None


# ---------------------------------------------------------------------------
# Remaining operating-mode branches
# ---------------------------------------------------------------------------


async def test_operating_mode_reports_unknown_without_a_status():
    """No status frame means the mode is unknown, not a crash."""
    from custom_components.dimplex.select import DimplexOperatingModeSelect

    payload = _payload()
    payload["appliances"][0]["status"] = None
    coordinator = SimpleNamespace(data=payload, async_add_listener=lambda *a, **k: lambda: None)
    config_entry = SimpleNamespace(entry_id="test", runtime_data=SimpleNamespace())
    api = SimpleNamespace(async_set_manual=MagicMock(), async_set_schedule_profile=MagicMock())

    select = DimplexOperatingModeSelect(coordinator, config_entry, payload["appliances"][0], api)

    assert select.current_option is None


async def test_pending_operating_mode_is_retired_once_confirmed():
    """A poll that agrees with the write clears the optimistic hold."""
    select = _operating_mode_select(128)
    select._pending = "manual"
    select._pending_updates_left = 3

    with patch.object(select, "async_write_ha_state", MagicMock()):
        select._handle_coordinator_update()

    assert select._pending is None


async def test_pending_operating_mode_expires_when_never_confirmed(caplog):
    """A write the appliance ignores is dropped after the bounded wait."""
    import logging

    select = _operating_mode_select(1)  # timer
    select._pending = "manual"
    select._pending_updates_left = 1

    with (
        caplog.at_level(logging.DEBUG, logger="custom_components.dimplex.select"),
        patch.object(select, "async_write_ha_state", MagicMock()),
    ):
        select._handle_coordinator_update()

    assert select._pending is None
    assert "never confirmed the operating mode manual" in caplog.text


async def test_manual_mode_falls_back_to_the_normal_temperature():
    """With no active setpoint, the Manual write carries the normal setpoint."""
    select = _operating_mode_select(1)
    status = select._appliance_row["status"]
    status.ActiveSetPointTemperature = None
    status.NormalTemperature = 19.0

    with patch.object(select, "async_write_ha_state", MagicMock()):
        await select.async_select_option("manual")

    select._api.async_set_manual.assert_awaited_once_with("hub-1", "appliance-1", temperature=19.0)


async def test_manual_mode_falls_back_to_a_fixed_temperature():
    """With no setpoint at all, the Manual write still carries a usable value."""
    select = _operating_mode_select(1)
    status = select._appliance_row["status"]
    status.ActiveSetPointTemperature = None
    status.NormalTemperature = None

    with patch.object(select, "async_write_ha_state", MagicMock()):
        await select.async_select_option("manual")

    select._api.async_set_manual.assert_awaited_once_with("hub-1", "appliance-1", temperature=21.0)
