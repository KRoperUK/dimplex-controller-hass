"""Test dimplex_controller switch."""

from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.switch import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.const import ATTR_ENTITY_ID
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import (
    DOMAIN,
)

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _mock_coordinator_payload():
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    status = SimpleNamespace(EcoStartEnabled=False, ComfortStatus=True, RoomTemperature=21.5)
    return {"appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}]}


async def test_switch_services(hass):
    """Test switch services."""
    # Create a mock entry so we don't have to go through config flow
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=_mock_coordinator_payload(),
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    switch_entities = sorted(
        state.entity_id for state in hass.states.async_all() if state.entity_id.startswith("switch.")
    )
    assert len(switch_entities) == 2  # EcoStart + Open window detection
    entity_id = next(e for e in switch_entities if "ecostart" in e)

    # Functions/objects can be patched directly in test code as well and can be used to test
    # additional things, like whether a function was called or what arguments it was called with
    with (
        patch("custom_components.dimplex.DimplexApiClient.async_set_eco_start") as eco_start_func,
        patch("custom_components.dimplex.DimplexApiClient.async_set_open_window_detection") as owd_func,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=_mock_coordinator_payload(),
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
    ):
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            service_data={ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        assert eco_start_func.called
        assert eco_start_func.call_args == call("hub-1", "appliance-1", False)

        eco_start_func.reset_mock()

        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            service_data={ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        assert eco_start_func.called
        assert eco_start_func.call_args == call("hub-1", "appliance-1", True)

        owd_entity = next(e for e in switch_entities if "open_window" in e)
        await hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            service_data={ATTR_ENTITY_ID: owd_entity},
            blocking=True,
        )
        assert owd_func.called
        assert owd_func.call_args == call("hub-1", "appliance-1", True)
