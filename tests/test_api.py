"""Tests for dimplex API adapter."""

import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dimplex_controller import (
    DimplexApiError,
    DimplexAuthError,
    DimplexConnectionError,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.dimplex.api import CannotConnect, DimplexApiClient, InvalidAuth

# asyncio_mode = auto (pyproject.toml) auto-handles async tests, so no module-level
# asyncio mark is needed — and adding one would break the sync unit tests below.


def _jwt(exp) -> str:
    """Build a minimal JWT-like string carrying an exp claim."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


async def test_validate_connection_success(hass):
    """Test connection validation with username/password login path."""
    api = DimplexApiClient(
        session=async_get_clientsession(hass),
        username="user@example.com",
        password="password",
    )

    with (
        patch.object(
            api._client.auth,
            "headless_login",
            new=AsyncMock(),
        ),
        patch.object(
            api._client.auth,
            "get_access_token",
            new=AsyncMock(return_value="token"),
        ),
        patch.object(
            api._client,
            "get_user_context",
            new=AsyncMock(return_value=SimpleNamespace(Name="Test User")),
        ),
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

    with (
        patch.object(
            api._client.auth,
            "headless_login",
            new=AsyncMock(side_effect=DimplexAuthError("failed")),
        ),
        pytest.raises(InvalidAuth),
    ):
        await api.async_validate_connection()


async def test_validate_connection_cannot_connect(hass):
    """Test connectivity failure mapping."""
    api = DimplexApiClient(
        session=async_get_clientsession(hass),
        username="user@example.com",
        password="password",
    )

    with (
        patch.object(
            api._client.auth,
            "headless_login",
            new=AsyncMock(side_effect=DimplexConnectionError("offline")),
        ),
        pytest.raises(CannotConnect),
    ):
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
    energy_report = SimpleNamespace(
        ApplianceTelemetryData={
            "appliance-1": [
                {"timestamp": "2026-06-01T00:00:00Z", "value": 0.1},
            ]
        }
    )

    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        patch.object(
            api._client,
            "get_hub_zones",
            new=AsyncMock(return_value=[zone]),
        ),
        patch.object(
            api._client,
            "get_appliance_overview",
            new=AsyncMock(return_value=[status]),
        ),
        patch.object(
            api._client,
            "get_tsi_energy_report",
            new=AsyncMock(return_value=energy_report),
        ),
    ):
        data = await api.async_get_data()

    assert len(data["appliances"]) == 1
    assert data["appliances"][0]["appliance"].ApplianceId == "appliance-1"
    # Energy report is indexed by hub id, then by appliance id, and each value
    # is the parsed telemetry list (one normalised point per cloud entry).
    assert "hub-1" in data["energy"]
    assert data["energy"]["hub-1"]["appliance-1"] == [(datetime(2026, 6, 1, tzinfo=UTC), 0.1)]


async def test_async_get_data_overview_fallback(hass):
    """Test that if bulk get_appliance_overview fails, we retry individually."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    zone = SimpleNamespace(ZoneName="Living Room", Appliances=[appliance])
    status = SimpleNamespace(ApplianceId="appliance-1", EcoStartEnabled=True)
    energy_report = SimpleNamespace(ApplianceTelemetryData={})

    # Side effect: first call (bulk) raises error, second call (individual) succeeds
    mock_overview = AsyncMock()
    mock_overview.side_effect = [
        DimplexApiError(400, "Bad Request"),
        [status],
    ]

    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        patch.object(api._client, "get_hub_zones", new=AsyncMock(return_value=[zone])),
        patch.object(api._client, "get_appliance_overview", new=mock_overview),
        patch.object(
            api._client,
            "get_tsi_energy_report",
            new=AsyncMock(return_value=energy_report),
        ),
    ):
        data = await api.async_get_data()

    assert len(data["appliances"]) == 1
    assert data["appliances"][0]["status"] == status
    assert mock_overview.call_count == 2


async def test_async_get_data_energy_report_api_error_is_skipped(hass):
    """Test that a DimplexApiError from the energy report does not fail the coordinator."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    hub = SimpleNamespace(HubId="hub-1")
    appliance = SimpleNamespace(
        ApplianceId="appliance-1",
        FriendlyName="Living Room Heater",
        ApplianceModel="Model X",
    )
    zone = SimpleNamespace(ZoneName="Living Room", Appliances=[appliance])
    status = SimpleNamespace(ApplianceId="appliance-1", EcoStartEnabled=True)

    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(return_value=[hub])),
        patch.object(api._client, "get_hub_zones", new=AsyncMock(return_value=[zone])),
        patch.object(
            api._client,
            "get_appliance_overview",
            new=AsyncMock(return_value=[status]),
        ),
        patch.object(
            api._client,
            "get_tsi_energy_report",
            new=AsyncMock(side_effect=DimplexApiError(404, "Not Found")),
        ),
    ):
        data = await api.async_get_data()

    # Appliances should still load; energy should be an empty dict for this hub
    assert len(data["appliances"]) == 1
    assert data["energy"]["hub-1"] == {}


async def test_set_eco_start_calls_library(hass):
    """Test eco start control call delegates to library client."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    with patch.object(api._client, "set_eco_start", new=AsyncMock()) as set_eco_start:
        await api.async_set_eco_start("hub-1", "appliance-1", True)

    set_eco_start.assert_awaited_once_with("hub-1", ["appliance-1"], True)


async def test_exchange_code_success(hass):
    """Test auth code exchange returns token payload."""
    api = DimplexApiClient(session=async_get_clientsession(hass))

    with (
        patch.object(
            api._client.auth,
            "exchange_code",
            new=AsyncMock(),
        ),
        patch.object(
            api._client,
            "get_user_context",
            new=AsyncMock(return_value=SimpleNamespace(Name="Test User")),
        ),
    ):
        api._client.auth._access_token = "access"
        api._client.auth._refresh_token = "refresh"
        api._client.auth._expires_at = 123
        token_data = await api.async_exchange_code("test-code")

    assert token_data["access_token"] == "access"
    assert token_data["refresh_token"] == "refresh"


# ---------------------------------------------------------------------------
# _extract_expiry
# ---------------------------------------------------------------------------


def test_extract_expiry_valid():
    """A valid JWT exp claim is parsed to a float."""
    assert DimplexApiClient._extract_expiry(_jwt(1893456000)) == 1893456000.0


def test_extract_expiry_invalid_returns_zero():
    """A malformed token yields 0 instead of raising."""
    assert DimplexApiClient._extract_expiry("not-a-jwt") == 0


# ---------------------------------------------------------------------------
# async_initialize branches
# ---------------------------------------------------------------------------


async def test_initialize_refresh_token_path(hass):
    """A stored refresh token just refreshes the access token."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="refresh")
    with patch.object(api._client.auth, "get_access_token", new=AsyncMock(return_value="token")) as get_token:
        await api.async_initialize()
    get_token.assert_awaited_once()


async def test_initialize_refresh_token_auth_error(hass):
    """Auth errors during refresh map to InvalidAuth."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="refresh")
    with (
        patch.object(
            api._client.auth,
            "get_access_token",
            new=AsyncMock(side_effect=DimplexAuthError("nope")),
        ),
        pytest.raises(InvalidAuth),
    ):
        await api.async_initialize()


async def test_initialize_access_token_not_expired(hass):
    """A non-expired access token short-circuits initialization."""
    api = DimplexApiClient(session=async_get_clientsession(hass))
    api._client.auth._refresh_token = None
    api._client.auth._access_token = "access"
    api._client.auth._expires_at = 1893456000  # far future
    await api.async_initialize()  # should not raise


async def test_initialize_access_token_expired(hass):
    """An expired access token raises InvalidAuth."""
    api = DimplexApiClient(session=async_get_clientsession(hass))
    api._client.auth._refresh_token = None
    api._client.auth._access_token = "access"
    api._client.auth._expires_at = 1  # epoch, long expired
    with pytest.raises(InvalidAuth):
        await api.async_initialize()


async def test_initialize_access_token_expiry_from_jwt(hass):
    """When expires_at is unset, it is derived from the JWT."""
    api = DimplexApiClient(session=async_get_clientsession(hass))
    api._client.auth._refresh_token = None
    api._client.auth._access_token = _jwt(1893456000)
    api._client.auth._expires_at = 0
    await api.async_initialize()  # should not raise
    assert api._client.auth._expires_at == 1893456000.0


async def test_initialize_no_credentials(hass):
    """No refresh token, access token, or credentials raises InvalidAuth."""
    api = DimplexApiClient(session=async_get_clientsession(hass))
    api._client.auth._refresh_token = None
    api._client.auth._access_token = None
    with pytest.raises(InvalidAuth):
        await api.async_initialize()


# ---------------------------------------------------------------------------
# get_auth_url
# ---------------------------------------------------------------------------


def test_get_auth_url_prefers_get_auth_url():
    """get_auth_url is used when the auth manager exposes it."""
    api = DimplexApiClient(session=MagicMock())
    api._client.auth = SimpleNamespace(get_auth_url=lambda: "https://auth/url")
    assert api.get_auth_url() == "https://auth/url"


def test_get_auth_url_falls_back_to_login_url():
    """get_login_url is used when get_auth_url is unavailable."""
    api = DimplexApiClient(session=MagicMock())
    api._client.auth = SimpleNamespace(get_login_url=lambda: "https://login/url")
    assert api.get_auth_url() == "https://login/url"


# ---------------------------------------------------------------------------
# Error mapping for data + control calls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (DimplexAuthError("a"), InvalidAuth),
        (DimplexConnectionError("c"), CannotConnect),
        (DimplexApiError(500, "e"), CannotConnect),
    ],
)
async def test_get_data_error_mapping(hass, exc, expected):
    """Library errors during data fetch map to integration exceptions."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(api._client, "get_hubs", new=AsyncMock(side_effect=exc)),
        pytest.raises(expected),
    ):
        await api.async_get_data()


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (DimplexAuthError("a"), InvalidAuth),
        (DimplexConnectionError("c"), CannotConnect),
        (DimplexApiError(500, "e"), CannotConnect),
    ],
)
async def test_set_eco_start_error_mapping(hass, exc, expected):
    """Library errors during control map to integration exceptions."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(api._client, "set_eco_start", new=AsyncMock(side_effect=exc)),
        pytest.raises(expected),
    ):
        await api.async_set_eco_start("hub-1", "appliance-1", True)


# ---------------------------------------------------------------------------
# async_get_energy_report
# ---------------------------------------------------------------------------


async def test_async_get_energy_report(hass):
    """The energy method returns parsed (ts, value) points per appliance."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")

    report = SimpleNamespace(
        ApplianceTelemetryData={
            "appliance-1": [
                {"timestamp": "2026-06-01T00:00:00Z", "value": 0.1},
                {"timestamp": "2026-06-01T01:00:00Z", "value": 0.2},
            ],
            "appliance-2": [],
        }
    )
    with patch.object(
        api._client,
        "get_tsi_energy_report",
        new=AsyncMock(return_value=report),
    ) as lib_call:
        result = await api.async_get_energy_report("hub-1")

    assert set(result) == {"appliance-1", "appliance-2"}
    assert result["appliance-2"] == []
    assert result["appliance-1"] == [
        (datetime(2026, 6, 1, tzinfo=UTC), 0.1),
        (datetime(2026, 6, 1, 1, tzinfo=UTC), 0.2),
    ]
    lib_call.assert_awaited_once()


async def test_async_get_energy_report_passes_window_to_library(hass):
    """The integration passes the configured days/interval to the library."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    report = SimpleNamespace(ApplianceTelemetryData={})
    with patch.object(
        api._client,
        "get_tsi_energy_report",
        new=AsyncMock(return_value=report),
    ) as lib_call:
        await api.async_get_energy_report("hub-1", days_back=7, interval="00:10:00")

    lib_call.assert_awaited_once_with(
        hub_id="hub-1",
        report_type=1,
        interval="00:10:00",
        days_back=7,
    )


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (DimplexAuthError("a"), InvalidAuth),
        (DimplexConnectionError("c"), CannotConnect),
    ],
)
async def test_async_get_energy_report_error_mapping(hass, exc, expected):
    """Auth/connection errors during energy fetch map to integration exceptions."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with (
        patch.object(
            api._client,
            "get_tsi_energy_report",
            new=AsyncMock(side_effect=exc),
        ),
        pytest.raises(expected),
    ):
        await api.async_get_energy_report("hub-1")


async def test_async_get_energy_report_api_error_returns_empty(hass):
    """A DimplexApiError (e.g. 404/400 for hubs with no metered appliances) returns {} instead of raising."""
    api = DimplexApiClient(session=async_get_clientsession(hass), refresh_token="token")
    with patch.object(
        api._client,
        "get_tsi_energy_report",
        new=AsyncMock(side_effect=DimplexApiError(404, "Not Found")),
    ):
        result = await api.async_get_energy_report("hub-1")
    assert result == {}
