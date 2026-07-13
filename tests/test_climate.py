"""Tests for the climate platform."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import (
    ATTR_PRESET_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_TURN_OFF,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dimplex.climate import (
    _is_away_active,
    _is_boost_active,
)
from custom_components.dimplex.const import DOMAIN

from .const import MOCK_ENTRY_DATA


def _payload(*, boost=False, away=False, eco=False, room=21.5, target=20):
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
        RoomTemperature=room,
        ActiveSetPointTemperature=target,
        NormalTemperature=target,
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


@contextmanager
def _api_data(payload):
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
        yield


def test_boost_and_away_helpers():
    """Helper detection works for raw status namespaces and flag bits."""
    assert _is_boost_active(None) is False
    assert _is_away_active(None) is False

    boost = SimpleNamespace(BoostDuration=10, ApplianceModes=0, AwayDateTime=None)
    assert _is_boost_active(boost) is True

    away = SimpleNamespace(BoostDuration=0, ApplianceModes=0, AwayDateTime="2026-01-01T00:00:00")
    assert _is_away_active(away) is True

    flags = SimpleNamespace(BoostDuration=0, ApplianceModes=16 | 32, AwayDateTime=None)
    assert _is_boost_active(flags) is True
    assert _is_away_active(flags) is True

    off = SimpleNamespace(BoostDuration=0, ApplianceModes=0, AwayDateTime="")
    assert _is_boost_active(off) is False
    assert _is_away_active(off) is False


@pytest.mark.asyncio
async def test_climate_set_temperature_and_presets(hass):
    """Climate services call the API adapter for temperature and presets."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload()

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes.get("current_temperature") == 21.5
    assert state.attributes.get("temperature") == 20
    assert state.attributes.get("preset_mode") == "comfort"

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_target_temperature",
            new_callable=AsyncMock,
        ) as set_temp,
        _api_data(payload),
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
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "boost"},
            blocking=True,
        )
        assert set_boost.await_count == 1
        assert set_boost.await_args.kwargs["enable"] is True
        assert set_boost.await_args.kwargs["temperature"] == 25.0

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_away",
            new_callable=AsyncMock,
        ) as set_away,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "away"},
            blocking=True,
        )
        assert set_away.await_count == 1
        assert set_away.await_args.kwargs["enable"] is True

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_eco_start",
            new_callable=AsyncMock,
        ) as set_eco,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "eco"},
            blocking=True,
        )
        set_eco.assert_awaited_once_with("hub-1", "appliance-1", True)


@pytest.mark.asyncio
async def test_climate_comfort_clears_modes(hass):
    """Comfort preset clears boost, away, and eco when active."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(boost=True, away=True, eco=True)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state.attributes.get("preset_mode") == "boost"

    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_boost",
            new_callable=AsyncMock,
        ) as set_boost,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_away",
            new_callable=AsyncMock,
        ) as set_away,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_eco_start",
            new_callable=AsyncMock,
        ) as set_eco,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_PRESET_MODE,
            {ATTR_ENTITY_ID: entity_id, ATTR_PRESET_MODE: "comfort"},
            blocking=True,
        )
        assert set_boost.await_count == 1
        assert set_boost.await_args.kwargs["enable"] is False
        assert set_away.await_count == 1
        assert set_away.await_args.kwargs["enable"] is False
        set_eco.assert_awaited_once_with("hub-1", "appliance-1", False)


@pytest.mark.asyncio
async def test_climate_turn_off_clears_boost_and_away(hass):
    """Turning climate off clears active boost/away."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_ENTRY_DATA, entry_id="test")
    config_entry.add_to_hass(hass)
    payload = _payload(boost=True, away=True)

    with _api_data(payload):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    entity_id = _climate_entity(hass)
    with (
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_boost",
            new_callable=AsyncMock,
        ) as set_boost,
        patch(
            "custom_components.dimplex.DimplexApiClient.async_set_away",
            new_callable=AsyncMock,
        ) as set_away,
        _api_data(payload),
    ):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: entity_id},
            blocking=True,
        )
        assert set_boost.await_count == 1
        assert set_away.await_count == 1
