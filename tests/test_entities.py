"""Test dimplex entity platforms."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import DOMAIN

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _mock_coordinator_payload():
    hub = SimpleNamespace(
        HubId="hub-1",
        FriendlyName="My Hub",
        HubType="GatewayOther",
        ConnectionState=1,
    )
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
        LastTelemDate=None,
    )
    status = SimpleNamespace(
        EcoStartEnabled=False,
        ComfortStatus=True,
        RoomTemperature=21.5,
        ActiveSetPointTemperature=20,
        BoostTemperature=25.0,
        AwayTemperature=15.0,
        SetbackTemperature=18.0,
        OpenWindowEnabled=True,
        SetbackEnabled=True,
        ErrorCode="E1",
        WarningCode="W2",
    )
    return {"appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}]}


async def test_sensor_and_binary_sensor_entities(hass):
    """Test sensor and binary sensor state mapping."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_data",
            return_value=_mock_coordinator_payload(),
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # Entity ID format varies by Home Assistant version
    sensor_state = hass.states.get("sensor.living_room_heater_room_temperature")
    if sensor_state is None:
        sensor_state = hass.states.get("sensor.living_room_living_room_heater_room_temperature")
    assert sensor_state is not None
    assert sensor_state.state == "21.5"

    binary_state = hass.states.get("binary_sensor.living_room_heater_comfort")
    if binary_state is None:
        binary_state = hass.states.get("binary_sensor.living_room_living_room_heater_comfort")
    assert binary_state is not None
    assert binary_state.state == "on"
    # Comfort active -> sofa icon (matches HA climate "comfort" preset).
    assert binary_state.attributes.get("icon") == "mdi:sofa"

    # EcoStart is disabled in the mock payload -> leaf-off icon.
    switch_state = hass.states.get("switch.living_room_heater_ecostart")
    if switch_state is None:
        switch_state = hass.states.get("switch.living_room_living_room_heater_ecostart")
    assert switch_state is not None
    assert switch_state.attributes.get("icon") == "mdi:leaf-off"

    target_state = hass.states.get("sensor.living_room_heater_target_temperature")
    if target_state is None:
        target_state = hass.states.get("sensor.living_room_living_room_heater_target_temperature")
    assert target_state is not None
    assert target_state.state == "20"

    open_window_state = hass.states.get("binary_sensor.living_room_heater_open_window")
    if open_window_state is None:
        open_window_state = hass.states.get("binary_sensor.living_room_living_room_heater_open_window")
    assert open_window_state is not None
    assert open_window_state.state == "on"

    setback_state = hass.states.get("binary_sensor.living_room_heater_setback")
    if setback_state is None:
        setback_state = hass.states.get("binary_sensor.living_room_living_room_heater_setback")
    assert setback_state is not None
    assert setback_state.state == "on"

    hub_connected_state = hass.states.get("binary_sensor.hub_1_connected")
    if hub_connected_state is None:
        hub_connected_state = hass.states.get("binary_sensor.my_hub_connected")
    assert hub_connected_state is not None
    assert hub_connected_state.state == "on"
