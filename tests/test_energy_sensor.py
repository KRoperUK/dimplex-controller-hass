"""Tests for the energy sensor."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import (
    DOMAIN,
    ENERGY_REPORT_DAYS,
    ENERGY_REPORT_INTERVAL,
)

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _row(*, energy):
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    status = SimpleNamespace(EcoStartEnabled=False, ComfortStatus=True, RoomTemperature=21.5)
    return {
        "appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}],
        "energy": {"hub-1": {"appliance-1": energy}},
    }


def _state(hass, entity_id_substring: str):
    """Return the state whose entity_id contains the substring, or None."""
    for state in hass.states.async_all():
        if entity_id_substring in state.entity_id:
            return state
    return None


async def test_energy_sensor_with_data(hass):
    """When telemetry is present, the sensor sums the values in kWh."""
    payload = _row(
        energy=[
            (dt_util.parse_datetime("2026-06-01T00:00:00+00:00"), 0.1),
            (dt_util.parse_datetime("2026-06-01T01:00:00+00:00"), 0.25),
        ]
    )
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_data",
            return_value=payload,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = _state(hass, "living_room_heater_energy")
    assert state is not None
    assert state.state == "0.35"
    assert state.attributes.get("unit_of_measurement") == UnitOfEnergy.KILO_WATT_HOUR
    assert state.attributes.get("device_class") == SensorDeviceClass.ENERGY
    assert state.attributes.get("state_class") == SensorStateClass.TOTAL
    assert state.attributes.get("window_days") == ENERGY_REPORT_DAYS
    assert state.attributes.get("interval") == ENERGY_REPORT_INTERVAL
    assert state.attributes.get("telemetry_points") == 2
    # last_reset is the start of the rolling report window.
    assert state.attributes.get("last_reset") is not None


async def test_energy_sensor_unavailable_when_empty(hass):
    """No telemetry means the sensor is unavailable, not 0."""
    payload = _row(energy=[])
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_data",
            return_value=payload,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = _state(hass, "living_room_heater_energy")
    assert state is not None
    # ``unavailable`` is the right state when there is no telemetry — we do
    # not want to push fabricated zeros into the Energy Dashboard.
    assert state.state == "unavailable"


async def test_energy_sensor_unavailable_when_hub_key_missing(hass):
    """Hubs that do not appear in the energy payload get no sensor data."""
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    status = SimpleNamespace(EcoStartEnabled=False, ComfortStatus=True, RoomTemperature=21.5)
    payload = {
        "appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}],
        # "energy" missing entirely — older payloads / fresh installs.
    }
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_data",
            return_value=payload,
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    state = _state(hass, "living_room_heater_energy")
    assert state is not None
    assert state.state == "unavailable"
