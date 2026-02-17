"""Tests for dimplex API adapter."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest
from custom_components.dimplex.api import CannotConnect
from custom_components.dimplex.api import DimplexApiClient
from custom_components.dimplex.api import InvalidAuth
from dimplex_controller import DimplexAuthError
from dimplex_controller import DimplexConnectionError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

pytestmark = pytest.mark.asyncio


async def test_validate_connection_success(hass):
    """Test connection validation with username/password login path."""
    api = DimplexApiClient(
        session=async_get_clientsession(hass),
        username="user@example.com",
        password="password",
    )

    with patch.object(
        api._client.auth,
        "headless_login",
        new=AsyncMock(),
    ), patch.object(
        api._client.auth,
        "get_access_token",
        new=AsyncMock(return_value="token"),
    ), patch.object(
        api._client,
        "get_user_context",
        new=AsyncMock(return_value=SimpleNamespace(Name="Test User")),
    ):
        api._client.auth._refresh_token = "refresh"
        token_data = await api.async_validate_connection()

    assert token_data["refresh_token"] == "refresh"


async def test_validate_connection_invalid_auth(hass):
    """Test auth failure mapping."""
    api = DimplexApiClient(
        session=async_get_clientsession(hass),
        username="user@example.com",
        password="wrong",
    )

    with patch.object(
        api._client.auth,
        "headless_login",
        new=AsyncMock(side_effect=DimplexAuthError("failed")),
    ):
        with pytest.raises(InvalidAuth):
            await api.async_validate_connection()


async def test_validate_connection_cannot_connect(hass):
    """Test connectivity failure mapping."""
    api = DimplexApiClient(
        session=async_get_clientsession(hass),
        username="user@example.com",
        password="password",
    )

    with patch.object(
        api._client.auth,
        "headless_login",
        new=AsyncMock(side_effect=DimplexConnectionError("offline")),
    ):
        with pytest.raises(CannotConnect):
            await api.async_validate_connection()


async def test_async_get_data_maps_appliances(hass):
    """Test that API payload is transformed into appliance rows."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    zone = SimpleNamespace(ZoneName="Living Room", Appliances=[appliance])
    status = SimpleNamespace(ApplianceId="appliance-1", EcoStartEnabled=True)

    with patch.object(
        api._client, "get_hubs", new=AsyncMock(return_value=[hub])
    ), patch.object(
        api._client,
        "get_hub_zones",
        new=AsyncMock(return_value=[zone]),
    ), patch.object(
        api._client,
        "get_appliance_overview",
        new=AsyncMock(return_value=[status]),
    ):
        data = await api.async_get_data()

    assert len(data["appliances"]) == 1
    assert data["appliances"][0]["appliance"].ApplianceId == "appliance-1"


async def test_set_eco_start_calls_library(hass):
    """Test eco start control call delegates to library client."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    with patch.object(api._client, "set_eco_start", new=AsyncMock()) as set_eco_start:
        await api.async_set_eco_start("hub-1", "appliance-1", True)

    set_eco_start.assert_awaited_once_with("hub-1", ["appliance-1"], True)
