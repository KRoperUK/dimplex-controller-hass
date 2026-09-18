"""Tests for the number platform (setback target)."""

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.components.number import SERVICE_SET_VALUE
from homeassistant.const import ATTR_ENTITY_ID
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.capabilities import LocalCapabilities
from custom_components.dimplex.const import DOMAIN

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _payload(*, setback_temperature=17.5, setback_enabled=True):
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
        SetbackTemperature=setback_temperature,
        SetbackEnabled=setback_enabled,
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


@contextmanager
def _api_data_cm(payload):
    """Patch the adapter's polling surface for the duration of the block."""
    with ExitStack() as stack:
        for patcher in _api_data(payload):
            stack.enter_context(patcher)
        yield


def _number_entity_id(hass, needle: str = "setback"):
    for state in hass.states.async_all():
        if state.entity_id.startswith("number.") and needle in state.entity_id:
            return state.entity_id
    return None


async def _setup(hass, payload, caps=None):
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    with ExitStack() as stack:
        for patcher in _api_data(payload):
            stack.enter_context(patcher)
        if caps is not None:
            stack.enter_context(patch("custom_components.dimplex.number.capabilities_for_row", return_value=caps))
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()


async def test_setback_target_is_created_and_reads_the_cloud_value(hass):
    """A setback-capable appliance gets a number entity showing the reported value."""
    await _setup(hass, _payload(setback_temperature=17.5))

    entity_id = _number_entity_id(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "17.5"
    # Range comes from the capability matrix, not a hard-coded guess.
    assert state.attributes.get("min") == 7.0
    assert state.attributes.get("max") == 30.0


async def test_setback_target_writes_through_the_adapter(hass):
    """Setting the value writes SetSetbackTemperature for the right appliance."""
    payload = _payload()
    await _setup(hass, payload)

    entity_id = _number_entity_id(hass)
    assert entity_id is not None

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_setback_temperature",
            new_callable=AsyncMock,
        ) as set_setback,
        _api_data_cm(payload),
    ):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, "value": 15.0},
            blocking=True,
        )
        await hass.async_block_till_done()

    set_setback.assert_awaited_once()
    assert set_setback.await_args.args[:3] == ("hub-1", "appliance-1", 15.0)


async def test_no_setback_entity_when_the_library_says_it_cannot_be_written(hass):
    """Capability gating, not the appliance name, decides whether the control exists."""
    await _setup(hass, _payload(), caps=LocalCapabilities(setback_write=False))

    assert _number_entity_id(hass) is None


async def test_no_setback_entity_when_the_value_cannot_be_read_back(hass):
    """A write we could never read back would leave a permanently stale number."""
    await _setup(hass, _payload(), caps=LocalCapabilities(setback_read=False))

    assert _number_entity_id(hass) is None


async def test_a_rejected_setback_write_reports_readably(hass):
    """Same control-error translation the climate entity and switches get (#198)."""
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.dimplex.api import ControlRejected

    payload = _payload()
    await _setup(hass, payload)

    entity_id = _number_entity_id(hass)
    assert entity_id is not None

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_setback_temperature",
            new_callable=AsyncMock,
            side_effect=ControlRejected("Forbidden", status=403),
        ),
        _api_data_cm(payload),
        pytest.raises(HomeAssistantError, match="rejected this control for Living Room Heater"),
    ):
        await hass.services.async_call(
            NUMBER_DOMAIN,
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, "value": 15.0},
            blocking=True,
        )
