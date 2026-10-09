"""Tests for the select platform (per-appliance boost duration, #252)."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

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
