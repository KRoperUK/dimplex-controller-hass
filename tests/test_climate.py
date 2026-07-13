"""Tests for the climate platform."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import (
    ATTR_PRESET_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.const import DOMAIN

from .const import MOCK_ENTRY_DATA

pytestmark = pytest.mark.asyncio


def _payload(*, boost=False, away=False, eco=False):
    hub = SimpleNamespace(HubId="hub-1")
    zone = SimpleNamespace(ZoneName="Living Room")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="QM100RF",
        ApplianceType="Quantum",
        FirmwareVersion="6",
        SeriesIdentifier="G12",
    )
    status = SimpleNamespace(
        EcoStartEnabled=eco,
        ComfortStatus=True,
        RoomTemperature=21.5,
        ActiveSetPointTemperature=20,
        NormalTemperature=20,
        BoostTemperature=25.0,
        AwayTemperature=15.0,
        BoostDuration=30 if boost else 0,
        AwayDateTime="2026-07-01T00:00:00" if away else None,
        ApplianceModes=(16 if boost else 0) | (32 if away else 0),
        OpenWindowEnabled=False,
        SetbackEnabled=False,
    )
    return {
        "appliances": [{"hub": hub, "zone": zone, "appliance": appliance, "status": status}],
        "hubs": [hub],
    }


def _climate_entity(hass):
    for state in hass.states.async_all():
        if state.entity_id.startswith("climate."):
            return state.entity_id
    return None


async def test_climate_set_temperature_and_preset(hass):
    """Climate services call the API adapter."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload()

    with (
        patch("custom_components.dimplex.DimplexApiClient.async_initialize"),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    assert entity_id is not None

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_target_temperature",
            new_callable=AsyncMock,
        ) as set_temp,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_TEMPERATURE,
            {ATTR_ENTITY_ID: entity_id, ATTR_TEMPERATURE: 22.5},
            blocking=True,
        )
        set_temp.assert_awaited_once_with("hub-1", "appliance-1", 22.5)

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_boost",
            new_callable=AsyncMock,
        ) as set_boost,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_status_data",
            return_value=payload,
        ),
        patch(
            "custom_components.dimplex.DimplexApiClient.async_get_energy_for_hubs",
            return_value={"energy": {}},
        ),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "boost"},
            blocking=True,
        )
        assert set_boost.await_count == 1
        kwargs = set_boost.await_args.kwargs
        assert kwargs["enable"] is True
        assert kwargs["temperature"] == 25.0
